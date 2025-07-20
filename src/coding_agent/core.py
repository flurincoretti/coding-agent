from pathlib import Path
from typing import Any, Dict, Iterable, List, cast

import anthropic
from pydantic_settings import BaseSettings

from coding_agent.tools import ALL_TOOLS, TOOL_MAP

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    debug: bool = False
    anthropic_api_key: str
    model: str

    class Config:
        env_file = BASE_DIR / ".env"


settings = Settings()

client = anthropic.Client(api_key=settings.anthropic_api_key)

# Type alias for message parameters used in conversation history.
# Represents the structure: {'role': 'user'|'assistant', 'content': List[Dict[str, str]]}
# where content contains message blocks like [{'type': 'text', 'text': 'message content'}].
MessageParam = Dict[str, Any]

# Type alias for tool parameter definitions passed to the Anthropic API.
# Represents tool schema with structure: {'name': str, 'description': str, 'input_schema': Dict}.
# Compatible with anthropic.types.ToolUnionParam for Claude function calling.
ToolParam = Dict[str, Any]

CONV: List[MessageParam] = []
TOOLS: List[ToolParam] = [
    {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool["input_schema"],
    }
    for tool in ALL_TOOLS
]


def loop() -> None:
    """Main interaction loop for the chat agent.

    Continuously accepts user input, sends it to the Claude API,
    and processes responses until interrupted with CTRL-C.

    Returns:
        None
    """
    print(f"Chat with Claude ({settings.model}) — press CTRL-C to quit")
    while True:
        try:
            user_input = input("\033[93mYou\033[0m: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        CONV.append({"role": "user", "content": [{"type": "text", "text": user_input}]})
        message = client.messages.create(
            model=settings.model,
            max_tokens=1024,
            messages=cast(List[anthropic.types.MessageParam], CONV),
            tools=cast(Iterable[anthropic.types.ToolUnionParam], TOOLS),
        )
        handle(message)


def handle(message: anthropic.types.Message) -> None:
    """Processes Claude's response messages and handles tool calls.

    Consumes a message, prints any assistant text to the console, resolves tool
    calls, and continues until the assistant has no outstanding tool requests.

    Args:
        message: An Anthropic API Message object containing Claude's response.

    Returns:
        None
    """

    pending: List[anthropic.types.Message] = [message]

    while pending:
        current = pending.pop(0)
        CONV.append({"role": message.role, "content": current.content})

        if settings.debug:
            print(f"\033[91mDebug\033[0m: {message.to_dict()}")
        for block in current.content:
            if block.type == "text":
                print(f"\033[93mClaude\033[0m: {block.text}")
            elif block.type == "tool_use":
                result_block = run_tool(block)
                CONV.append({"role": "user", "content": [result_block]})
                pending.append(
                    client.messages.create(
                        model=settings.model,
                        max_tokens=1024,
                        messages=cast(List[anthropic.types.MessageParam], CONV),
                        tools=cast(Iterable[anthropic.types.ToolUnionParam], TOOLS),
                    )
                )


def run_tool(block: Any) -> Dict[str, Any]:
    """Executes a tool based on Claude's tool_use request.

    Takes a tool_use block from Claude's response, attempts to execute the
    specified tool with the provided parameters, and returns a result block
    that can be sent back to Claude.

    Args:
        block: A tool_use block from Claude's response containing tool name and input.

    Returns:
        Dict[str, Any]: A tool_result block containing the execution result or error.
    """
    name: str = getattr(block, "name", "")
    payload: Dict[str, Any] = getattr(block, "input", {}) or {}
    spec = TOOL_MAP.get(name)

    if spec is None:
        result_block: Dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": block.id,
            "is_error": True,
            "content": f"Unknown tool '{name}'",
        }
        print(f"\033[91mTool error\033[0m: Unknown tool {name}")
    else:
        try:
            print(f"\033[92mTool\033[0m: {name}({payload})")
            output = spec["fn"](payload)
            result_block = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            }
        except Exception as e:
            result_block = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "is_error": True,
                "content": str(e),
            }
            print(f"\033[91mTool error\033[0m: {e}")

    return result_block
