from pathlib import Path

import pytest
from oauth_cli_kit.models import OAuthToken

from nanobot.config.loader import set_config_path
from nanobot.providers import codex_accounts
from nanobot.providers.codex_accounts import (
    CodexAccountTokenStorage,
    get_available_codex_accounts,
    get_codex_account_pool_path,
    mark_codex_account_rate_limited,
    mark_codex_account_used,
)


@pytest.fixture(autouse=True)
def restore_default_config_path():
    yield
    set_config_path(Path.home() / ".nanobot" / "config.json")


def test_codex_account_pool_path_follows_nanobot_config_dir(tmp_path: Path) -> None:
    set_config_path(tmp_path / "config.json")

    assert get_codex_account_pool_path() == tmp_path / "auth" / "codex-accounts.json"


def test_codex_account_storage_saves_named_profiles(tmp_path: Path) -> None:
    set_config_path(tmp_path / "config.json")
    storage = CodexAccountTokenStorage("work")

    storage.save(OAuthToken(access="access", refresh="refresh", expires=999999, account_id="acct"))

    token = storage.load()
    assert token is not None
    assert token.access == "access"
    assert token.refresh == "refresh"
    assert token.account_id == "acct"


def test_codex_account_order_uses_least_recent_available_first(tmp_path: Path, monkeypatch) -> None:
    set_config_path(tmp_path / "config.json")
    CodexAccountTokenStorage("first").save(
        OAuthToken(access="a1", refresh="r1", expires=9999999999999, account_id="acct1")
    )
    CodexAccountTokenStorage("second").save(
        OAuthToken(access="a2", refresh="r2", expires=9999999999999, account_id="acct2")
    )
    mark_codex_account_used("first")

    def fake_get_token(*, storage, **_kwargs):
        return storage.load()

    monkeypatch.setattr(codex_accounts, "oauth_get_token", fake_get_token)

    accounts = get_available_codex_accounts()

    assert [account.profile_id for account in accounts] == ["second", "first"]


def test_codex_rate_limited_account_moves_behind_available_accounts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    set_config_path(tmp_path / "config.json")
    CodexAccountTokenStorage("first").save(
        OAuthToken(access="a1", refresh="r1", expires=9999999999999, account_id="acct1")
    )
    CodexAccountTokenStorage("second").save(
        OAuthToken(access="a2", refresh="r2", expires=9999999999999, account_id="acct2")
    )
    mark_codex_account_rate_limited("first", retry_after=60)

    def fake_get_token(*, storage, **_kwargs):
        return storage.load()

    monkeypatch.setattr(codex_accounts, "oauth_get_token", fake_get_token)

    accounts = get_available_codex_accounts()

    assert [account.profile_id for account in accounts] == ["second", "first"]
