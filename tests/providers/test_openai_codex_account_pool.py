from types import SimpleNamespace

import pytest

from nanobot.providers.base import LLMResponse
from nanobot.providers.openai_codex_provider import OpenAICodexProvider, _CodexHTTPError


@pytest.mark.asyncio
async def test_codex_provider_falls_back_to_next_account_on_rate_limit(monkeypatch) -> None:
    provider = OpenAICodexProvider()
    accounts = [
        SimpleNamespace(
            profile_id="first",
            token=SimpleNamespace(access="token-1", account_id="acct-1"),
        ),
        SimpleNamespace(
            profile_id="second",
            token=SimpleNamespace(access="token-2", account_id="acct-2"),
        ),
    ]
    called_accounts: list[str] = []
    cooled_down: list[str] = []
    used: list[str] = []

    def fake_accounts():
        return accounts

    async def fake_request(_url, headers, _body, on_content_delta=None):
        del on_content_delta
        called_accounts.append(headers["chatgpt-account-id"])
        if headers["chatgpt-account-id"] == "acct-1":
            raise _CodexHTTPError("rate limit", retry_after=30, status_code=429)
        return LLMResponse(content="ok")

    def fake_rate_limited(profile_id: str, **_kwargs) -> None:
        cooled_down.append(profile_id)

    def fake_used(profile_id: str) -> None:
        used.append(profile_id)

    monkeypatch.setattr("nanobot.providers.openai_codex_provider.get_available_codex_accounts", fake_accounts)
    monkeypatch.setattr(
        "nanobot.providers.openai_codex_provider.mark_codex_account_rate_limited",
        fake_rate_limited,
    )
    monkeypatch.setattr("nanobot.providers.openai_codex_provider.mark_codex_account_used", fake_used)
    monkeypatch.setattr(provider, "_request_with_ssl_fallback", fake_request)

    response = await provider.chat(messages=[{"role": "user", "content": "hello"}])

    assert response.content == "ok"
    assert called_accounts == ["acct-1", "acct-2"]
    assert cooled_down == ["first"]
    assert used == ["second"]


@pytest.mark.asyncio
async def test_codex_provider_reports_missing_account_pool(monkeypatch) -> None:
    provider = OpenAICodexProvider()

    monkeypatch.setattr("nanobot.providers.openai_codex_provider.get_available_codex_accounts", lambda: [])

    response = await provider.chat(messages=[{"role": "user", "content": "hello"}])

    assert response.finish_reason == "error"
    assert "no OpenAI Codex OAuth accounts are configured" in (response.content or "")
