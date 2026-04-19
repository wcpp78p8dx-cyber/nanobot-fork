import pytest

from nanobot.agent.tools.message import MessageTool


@pytest.mark.asyncio
async def test_message_tool_returns_error_when_no_target_context() -> None:
    tool = MessageTool()
    result = await tool.execute(content="test")
    assert result == "Error: No target channel/chat specified"


@pytest.mark.asyncio
async def test_message_tool_can_request_feishu_reply_in_thread() -> None:
    sent = []

    async def _send(msg):
        sent.append(msg)

    tool = MessageTool(
        send_callback=_send,
        default_channel="feishu",
        default_chat_id="ou_alice",
        default_message_id="om_001",
    )

    result = await tool.execute(content="topic please", reply_in_thread=True)

    assert result == "Message sent to feishu:ou_alice"
    assert len(sent) == 1
    assert sent[0].metadata == {
        "message_id": "om_001",
        "reply_in_thread": True,
    }
