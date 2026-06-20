"""
Bridge: local Gemma (via Ollama) <-> your MCP server.

Ollama does not speak MCP natively, so this script does the translation:
  1. Connect to server.py over stdio and fetch its tool list.
  2. Convert that tool list into the JSON-schema format Ollama's
     function-calling API expects.
  3. Loop: read a prompt from you, send the conversation so far + tool
     definitions to Gemma, run any tool calls it asks for against the
     MCP server, and print the final answer. Repeat until you quit.

Prerequisites:
    uv add mcp ollama
    ollama pull gemma4        # or whichever Gemma tag `ollama list` shows
    ollama serve               # if not already running

Run:
    uv run ollama_bridge.py

Type 'exit' or 'quit' (or Ctrl+C) to stop.
"""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import ollama

server_params = StdioServerParameters(
    command="uv",
    args=["run", "server.py"],
)

MODEL = "gemma4"  # match the exact tag from `ollama list`


def mcp_tool_to_ollama_format(tool) -> dict:
    """Convert an MCP tool definition into Ollama's function-calling schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
        },
    }


async def handle_tool_calls(session, assistant_message, messages):
    """Run any tool calls Gemma requested, appending results to messages."""
    tool_calls = assistant_message.get("tool_calls") or []
    for call in tool_calls:
        name = call["function"]["name"]
        args = call["function"]["arguments"]
        if isinstance(args, str):
            args = json.loads(args)

        try:
            result = await session.call_tool(name, args)
            tool_output = result.content[0].text
        except Exception as e:
            tool_output = f"Error calling {name}: {e}"

        print(f"  [tool call] {name}({args}) -> {tool_output}")
        messages.append({
            "role": "tool",
            "content": tool_output,
            "name": name,
        })
    return bool(tool_calls)


async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = (await session.list_tools()).tools
            ollama_tools = [mcp_tool_to_ollama_format(t) for t in mcp_tools]
            print(f"Connected. Available tools: {[t.name for t in mcp_tools]}")
            print("Type a message (or 'exit'/'quit' to stop).\n")

            # Conversation history persists across turns, so Gemma keeps context.
            messages = []

            while True:
                try:
                    user_input = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye!")
                    break

                if user_input.lower() in {"exit", "quit"}:
                    print("Goodbye!")
                    break
                if not user_input:
                    continue

                messages.append({"role": "user", "content": user_input})

                response = ollama.chat(model=MODEL, messages=messages, tools=ollama_tools)
                assistant_message = response["message"]
                messages.append(assistant_message)

                # Keep resolving tool calls until Gemma stops requesting them
                # (handles cases where one tool's result triggers another call).
                while await handle_tool_calls(session, assistant_message, messages):
                    response = ollama.chat(model=MODEL, messages=messages, tools=ollama_tools)
                    assistant_message = response["message"]
                    messages.append(assistant_message)

                print(f"Gemma: {assistant_message['content']}\n")


if __name__ == "__main__":
    asyncio.run(main())
