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

## Feishu Topic Sessions

Added: 2026-04-18

This fork keeps Feishu topics isolated from the main chat session when Feishu provides a real `thread_id`. A group topic uses a session key like:

```text
feishu:<group_chat_id>:thread:<thread_id>
```

If Feishu returns a `thread_id` for a direct-message topic, it uses the sender session as the base:

```text
feishu:<sender_open_id>:thread:<thread_id>
```

Plain group messages continue to use the main group session:

```text
feishu:<group_chat_id>
```

Important behavior:

`groupPolicy` still only controls whether group messages must mention the bot. It does not change session routing once a message is accepted.

Only `thread_id` creates a topic session. Regular Feishu "reply to" chains that have `parent_id` / `root_id` but no `thread_id` stay in the main group session. The quoted message context is still prepended when available, so replying to an older group message can help the bot understand what is being referenced without opening a blank session.

Feishu streaming buffers are also scoped by topic, so two active topics in the same group do not share one streaming card buffer.

The `message` tool exposes `reply_in_thread=true` for Feishu/Lark. This asks the Feishu Reply API to reply in topic form when the current message has a `message_id`. Official Feishu docs describe this mainly around group topics, so direct-message topic support should be treated as a live-platform behavior to verify. If Feishu does return `thread_id` on the next inbound direct-message topic event, nanobot now stores that conversation in the topic-scoped session above.

For group chats, remember that nanobot chooses the current session before an outbound reply is sent. If the bot itself converts a plain group message into a topic, that first bot reply may still be persisted in the main group session until the next inbound event arrives with `thread_id`. Manual topic creation is still clearer for group discussions when exact first-turn history placement matters.

Observed Feishu behavior:

If a human user's message is the topic root, the topic session begins with the user's first in-topic reply and includes the root message as quoted context in that reply content. The root message also remains in the outer chat session, which keeps the transition understandable.

If a bot message is the topic root and the human starts a thread from that bot message, the topic session starts from the human's first in-topic reply. The original bot root message is not present in the topic session history.

If the bot creates the topic by sending `reply_in_thread=true`, Feishu shows the reply inside the topic UI, but nanobot still persists that first bot reply in the current outer session. This is because the session is selected before the outbound reply result returns. Fixing first-reply migration would require plumbing the Feishu reply response back into the agent/session layer, which is larger than this fork currently needs.

After a thread exists and inbound messages carry `thread_id`, the bot does not need to keep passing `reply_in_thread=true`. Normal replies use the thread metadata and stay inside the current thread.

In topic-only group chats, the behavior is slightly better when the bot creates the topic. Before the human replies, nanobot may not create a dedicated session file for that topic yet. Once the human replies inside the topic, the topic `sessions/*.jsonl` file appears, and the top-level topic message is preserved as quoted `reply to` context in the first stored thread message instead of being lost.

Thread session files only store the conversation turns. System prompt context is not written into each `sessions/*.jsonl` file. At runtime, `ContextBuilder.build_messages()` still injects identity, workspace bootstrap files (`AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`), customized `memory/MEMORY.md`, active skills, and recent history before sending the request to the model. This keeps thread sessions small and lets updated memory/personality files apply to old threads.

Memory/consolidation tradeoff:

Topic isolation makes each Feishu topic much cleaner, but it also lowers the chance that any one session reaches the token threshold for consolidator compression. In practice, short topic sessions may never be summarized into `memory/history.jsonl`, so Dream may have little or no topic history to solidify. This is intentional for now because the personal reflection workflow summarizes daily conversations into dated diary files and promotes only meaningful information into longer-term memory. Without that workflow, manually use `/new` after an important topic to force an archive, or configure idle auto-compact with `agents.defaults.idleCompactAfterMinutes` in `config.json` (`0` disables it; value is minutes). Note that auto-compact preserves recent messages, so very short topics may still remain only in their session files.

## Local Fork Maintenance

Keep personal changes small and isolated when possible. For this Codex account pool feature, the main local files are:

```text
nanobot/providers/codex_accounts.py
nanobot/providers/openai_codex_provider.py
nanobot/cli/commands.py
tests/providers/test_codex_accounts.py
tests/providers/test_openai_codex_account_pool.py
```

For Feishu topic sessions and topic replies, the main local files are:

```text
nanobot/agent/tools/message.py
nanobot/channels/feishu.py
tests/channels/test_feishu_reply.py
tests/channels/test_feishu_streaming.py
tests/tools/test_message_tool.py
```

Before syncing from upstream, commit local changes first. This makes it much easier to rebase or resolve conflicts without losing the Codex account pool work.
