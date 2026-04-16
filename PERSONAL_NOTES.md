# Personal Nanobot Notes

This file records local fork changes and day-to-day commands that are easy to forget. The upstream README is intentionally left mostly unchanged so future upstream syncs are easier.

## OpenAI Codex OAuth Account Pool

This fork stores Codex OAuth credentials explicitly under the active nanobot config directory instead of using `oauth-cli-kit`'s global default path or importing `~/.codex/auth.json`.

Default token pool path:

```text
~/.nanobot/auth/codex-accounts.json
```

If nanobot is started with a custom config path, the token pool follows that config directory:

```text
<config-directory>/auth/codex-accounts.json
```

Login or replace the primary Codex account:

```powershell
nanobot provider login openai-codex --profile main --force
```

Login or replace a fallback Codex account:

```powershell
nanobot provider login openai-codex --profile alt --force
```

Useful flags:

`--profile` names the account in the local account pool.

`--force` skips any existing token for that profile and runs the browser OAuth flow again, overwriting that profile with the newly authorized account.

Runtime behavior:

When a Codex request hits a 429/rate-limit error, nanobot puts the current profile into cooldown and automatically retries with the next available Codex profile. Successful requests update `last_used`, so available accounts rotate in least-recently-used order.

## Local Fork Maintenance

Keep personal changes small and isolated when possible. For this Codex account pool feature, the main local files are:

```text
nanobot/providers/codex_accounts.py
nanobot/providers/openai_codex_provider.py
nanobot/cli/commands.py
tests/providers/test_codex_accounts.py
tests/providers/test_openai_codex_account_pool.py
```

Before syncing from upstream, commit local changes first. This makes it much easier to rebase or resolve conflicts without losing the Codex account pool work.
