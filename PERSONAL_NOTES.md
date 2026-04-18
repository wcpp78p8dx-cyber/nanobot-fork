# Personal Nanobot Notes

This file records local fork changes and day-to-day commands that are easy to forget. The upstream README is intentionally left mostly unchanged so future upstream syncs are easier.

## OpenAI Codex OAuth Account Pool

Added: 2026-04-16

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

## Feishu Group Topic Sessions

Added: 2026-04-18

This fork keeps Feishu group topics isolated from the main group chat session. A group message with a real Feishu `thread_id` uses a session key like:

```text
feishu:<group_chat_id>:thread:<thread_id>
```

Plain group messages continue to use the main group session:

```text
feishu:<group_chat_id>
```

Important behavior:

`groupPolicy` still only controls whether group messages must mention the bot. It does not change session routing once a message is accepted.

Only `thread_id` creates a topic session. Regular Feishu "reply to" chains that have `parent_id` / `root_id` but no `thread_id` stay in the main group session. The quoted message context is still prepended when available, so replying to an older group message can help the bot understand what is being referenced without opening a blank session.

Feishu streaming buffers are also scoped by topic, so two active topics in the same group do not share one streaming card buffer.

The `reply_in_thread=true` Feishu API experiment was intentionally not kept exposed to the agent. It can create a topic in the Feishu UI, but nanobot's current session is chosen before the outbound reply is sent, so the first bot reply still persists in the main group session. Manual topic creation is currently clearer: start or convert the topic in Feishu, then reply in that topic so the next inbound message carries `thread_id`.

## Local Fork Maintenance

Keep personal changes small and isolated when possible. For this Codex account pool feature, the main local files are:

```text
nanobot/providers/codex_accounts.py
nanobot/providers/openai_codex_provider.py
nanobot/cli/commands.py
tests/providers/test_codex_accounts.py
tests/providers/test_openai_codex_account_pool.py
```

For Feishu topic sessions, the main local files are:

```text
nanobot/channels/feishu.py
tests/channels/test_feishu_reply.py
tests/channels/test_feishu_streaming.py
```

Before syncing from upstream, commit local changes first. This makes it much easier to rebase or resolve conflicts without losing the Codex account pool work.
