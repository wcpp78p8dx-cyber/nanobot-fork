"""Lightweight OpenAI Codex OAuth account pool."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oauth_cli_kit import get_token as oauth_get_token
from oauth_cli_kit import login_oauth_interactive
from oauth_cli_kit.models import OAuthToken
from oauth_cli_kit.providers import OPENAI_CODEX_PROVIDER

from nanobot.config.paths import get_runtime_subdir

ACCOUNT_POOL_FILENAME = "codex-accounts.json"
DEFAULT_PROFILE_ID = "default"
DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 5 * 60


@dataclass(frozen=True)
class CodexAccount:
    """A resolved Codex account token selected from the pool."""

    profile_id: str
    token: OAuthToken


class CodexAccountTokenStorage:
    """oauth-cli-kit compatible storage for one named profile."""

    def __init__(self, profile_id: str = DEFAULT_PROFILE_ID, path: Path | None = None) -> None:
        self.profile_id = _normalize_profile_id(profile_id)
        self._path = path

    def get_token_path(self) -> Path:
        # Keep Codex OAuth tokens in nanobot's instance directory instead of
        # oauth-cli-kit's global cache so account pools can be copied, backed up,
        # and inspected alongside the rest of the local nanobot config.
        return self._path or get_codex_account_pool_path()

    def load(self) -> OAuthToken | None:
        store = _load_pool(self.get_token_path())
        account = store.get("accounts", {}).get(self.profile_id)
        if not isinstance(account, dict):
            return None
        return _token_from_account(account)

    def save(self, token: OAuthToken) -> None:
        path = self.get_token_path()
        store = _load_pool(path)
        accounts = store.setdefault("accounts", {})
        existing = accounts.get(self.profile_id)
        if not isinstance(existing, dict):
            existing = {}
        existing.update(_account_from_token(token))
        existing.setdefault("created_at", _now_ms())
        existing["updated_at"] = _now_ms()
        accounts[self.profile_id] = existing
        _save_pool(path, store)


def get_codex_account_pool_path() -> Path:
    """Return the explicit nanobot-managed Codex account pool path."""

    return get_runtime_subdir("auth") / ACCOUNT_POOL_FILENAME


def login_codex_account(
    *,
    profile_id: str = DEFAULT_PROFILE_ID,
    force: bool = False,
    print_fn,
    prompt_fn,
) -> CodexAccount:
    """Login to Codex and persist the token in nanobot's account pool."""

    storage = CodexAccountTokenStorage(profile_id)
    token: OAuthToken | None = None
    if not force:
        try:
            token = oauth_get_token(
                provider=OPENAI_CODEX_PROVIDER,
                storage=storage,
            )
        except Exception:
            token = None
    if not (token and token.access):
        token = login_oauth_interactive(
            print_fn=print_fn,
            prompt_fn=prompt_fn,
            provider=OPENAI_CODEX_PROVIDER,
            storage=storage,
        )
    if not (token and token.access):
        raise RuntimeError("OpenAI Codex OAuth authentication failed")
    return CodexAccount(profile_id=_normalize_profile_id(profile_id), token=token)


def get_available_codex_accounts(min_ttl_seconds: int = 60) -> list[CodexAccount]:
    """Return usable accounts, ordered by cooldown and least-recently-used."""

    path = get_codex_account_pool_path()
    store = _load_pool(path)
    accounts = store.get("accounts", {})
    if not isinstance(accounts, dict):
        return []

    now = _now_ms()
    candidates: list[tuple[bool, int, int, str, OAuthToken]] = []
    mutated = False
    for profile_id, raw in accounts.items():
        if not isinstance(raw, dict):
            continue
        disabled_until = _int_or_zero(raw.get("disabled_until"))
        if disabled_until and disabled_until > now:
            continue
        cooldown_until = _int_or_zero(raw.get("cooldown_until"))
        token = _load_or_refresh_profile(profile_id, min_ttl_seconds)
        if not token:
            continue
        refreshed = accounts.get(profile_id)
        if isinstance(refreshed, dict):
            raw = refreshed
        if cooldown_until and cooldown_until <= now:
            raw.pop("cooldown_until", None)
            raw.pop("cooldown_reason", None)
            raw["failure_count"] = 0
            mutated = True
            cooldown_until = 0
        last_used = _int_or_zero(raw.get("last_used"))
        candidates.append((cooldown_until > now, cooldown_until, last_used, profile_id, token))

    if mutated:
        _save_pool(path, store)

    # Prefer accounts that are not cooling down, then use least-recently-used
    # ordering to spread normal traffic across the configured account pool.
    candidates.sort(key=lambda item: (item[0], item[1] if item[0] else item[2], item[3]))
    return [CodexAccount(profile_id=profile_id, token=token) for _, _, _, profile_id, token in candidates]


def mark_codex_account_used(profile_id: str) -> None:
    """Mark a profile as successfully used."""

    def update(account: dict[str, Any]) -> None:
        account["last_used"] = _now_ms()
        account["failure_count"] = 0
        account.pop("cooldown_until", None)
        account.pop("cooldown_reason", None)

    _update_account(profile_id, update)


def mark_codex_account_rate_limited(
    profile_id: str,
    *,
    retry_after: float | None = None,
    reason: str = "rate_limit",
) -> None:
    """Put a profile into a short cooldown after a Codex rate limit."""

    delay_seconds = retry_after if retry_after and retry_after > 0 else DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS

    def update(account: dict[str, Any]) -> None:
        failures = _int_or_zero(account.get("failure_count")) + 1
        account["failure_count"] = failures
        account["cooldown_until"] = _now_ms() + int(delay_seconds * 1000)
        account["cooldown_reason"] = reason
        account["last_failure_at"] = _now_ms()

    _update_account(profile_id, update)


def mark_codex_account_disabled(profile_id: str, *, reason: str = "auth") -> None:
    """Temporarily disable an account after an auth-looking failure."""

    def update(account: dict[str, Any]) -> None:
        account["disabled_until"] = _now_ms() + 60 * 60 * 1000
        account["disabled_reason"] = reason
        account["last_failure_at"] = _now_ms()

    _update_account(profile_id, update)


def _load_or_refresh_profile(profile_id: str, min_ttl_seconds: int) -> OAuthToken | None:
    try:
        return oauth_get_token(
            provider=OPENAI_CODEX_PROVIDER,
            storage=CodexAccountTokenStorage(profile_id),
            min_ttl_seconds=min_ttl_seconds,
        )
    except Exception:
        return None


def _update_account(profile_id: str, updater) -> None:
    path = get_codex_account_pool_path()
    store = _load_pool(path)
    accounts = store.setdefault("accounts", {})
    normalized = _normalize_profile_id(profile_id)
    account = accounts.get(normalized)
    if not isinstance(account, dict):
        return
    updater(account)
    account["updated_at"] = _now_ms()
    accounts[normalized] = account
    _save_pool(path, store)


def _normalize_profile_id(profile_id: str | None) -> str:
    raw = (profile_id or DEFAULT_PROFILE_ID).strip()
    return raw or DEFAULT_PROFILE_ID


def _now_ms() -> int:
    return int(time.time() * 1000)


def _int_or_zero(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _token_from_account(account: dict[str, Any]) -> OAuthToken | None:
    try:
        access = str(account["access"])
        refresh = str(account["refresh"])
        expires = int(account["expires"])
    except Exception:
        return None
    if not access or not refresh or expires <= 0:
        return None
    account_id = account.get("account_id")
    return OAuthToken(
        access=access,
        refresh=refresh,
        expires=expires,
        account_id=str(account_id) if account_id else None,
    )


def _account_from_token(token: OAuthToken) -> dict[str, Any]:
    data: dict[str, Any] = {
        "access": token.access,
        "refresh": token.refresh,
        "expires": token.expires,
    }
    if token.account_id:
        data["account_id"] = token.account_id
    return data


def _load_pool(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "accounts": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "accounts": {}}
    if not isinstance(data, dict):
        return {"version": 1, "accounts": {}}
    if not isinstance(data.get("accounts"), dict):
        data["accounts"] = {}
    data["version"] = 1
    return data


def _save_pool(path: Path, store: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=True, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
