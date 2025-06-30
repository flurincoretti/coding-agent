from pathlib import Path
from typing import Any, Dict, List

import anthropic
from environs import Env

from agent.tools import ALL_TOOLS, TOOL_MAP

BASE_DIR = Path(__file__).resolve().parent.parent

env = Env()
env.read_env(BASE_DIR / ".env")
ANTHROPIC_API_KEY = env.str("ANTHROPIC_API_KEY")
MODEL = env.str("MODEL")

DEBUG = env.bool("DEBUG")

client = anthropic.Client(api_key=ANTHROPIC_API_KEY)

CONV: List[Dict[str, Any]] = []
TOOLS: List[dict] = [
    {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool["input_schema"],
    }
    for tool in ALL_TOOLS
]


def loop() -> None:
    print(f"Chat with Claude ({MODEL}) — press CTRL-C to quit")
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
            model=MODEL,
            max_tokens=1024,
            messages=CONV,
            tools=TOOLS,
        )
        handle(message)


def handle(message: anthropic.types.Message) -> None:
    """
    Consume a message, print any assistant text to the console, resolve tool
    calls, and continue until the assistant has no outstanding tool requests.
    """

    pending: List[anthropic.types.Message] = [message]

    while pending:
        current = pending.pop(0)
        CONV.append({"role": message.role, "content": current.content})

        if DEBUG:
            print(f"\033[91mDebug\033[0m: {message.to_dict()}")
        for block in current.content:
            if block.type == "text":
                print(f"\033[93mClaude\033[0m: {block.text}")
            elif block.type == "tool_use":
                result_block = run_tool(block)
                CONV.append({"role": "user", "content": [result_block]})
                pending.append(
                    client.messages.create(
                        model=MODEL,
                        max_tokens=1024,
                        messages=CONV,
                        tools=TOOLS,
                    )
                )


def run_tool(block: Any) -> Dict[str, Any]:
    name: str = getattr(block, "name", "")
    payload: Dict[str, Any] = getattr(block, "input", {}) or {}
    spec = TOOL_MAP.get(name)

    if spec is None:
        result_block: Dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": block.id,
            "is_error": True,
            "error": f"Unknown tool '{name}'",
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
                "error": str(e),
            }
            print(f"\033[91mTool error\033[0m: {e}")

    return result_block
