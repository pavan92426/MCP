"""
Bridge: local Gemma (via Ollama) <-> your MCP server.

Ollama does not speak MCP natively, so this script does the translation:
  1. Connect to server.py over stdio and fetch its tool list.
  2. Convert that tool list into the JSON-schema format Ollama's
     function-calling API expects.
  3. Send the user's prompt to Gemma along with the tool definitions.
  4. If Gemma asks to call a tool, forward that call to the MCP server,
     get the result, and send it back to Gemma for a final answer.

Prerequisites:
    pip install mcp ollama
    ollama pull gemma3        # or whichever Gemma tag you have
    ollama serve              # if not already running

Run:
    python ollama_bridge.py
"""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import ollama

server_params = StdioServerParameters(
    command="python",
    args=["server.py"],
)

MODEL = "gemma3"  # change to match `ollama list` on your machine


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


async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = (await session.list_tools()).tools
            ollama_tools = [mcp_tool_to_ollama_format(t) for t in mcp_tools]

            messages = [
                {"role": "user", "content": "Say hello to Alice, then tell me what 23 times 4 is."}
            ]

            response = ollama.chat(model=MODEL, messages=messages, tools=ollama_tools)
            messages.append(response["message"])

            # If Gemma requested tool calls, execute them against the MCP server
            tool_calls = response["message"].get("tool_calls") or []
            for call in tool_calls:
                name = call["function"]["name"]
                args = call["function"]["arguments"]
                if isinstance(args, str):
                    args = json.loads(args)

                result = await session.call_tool(name, args)
                tool_output = result.content[0].text

                messages.append({
                    "role": "tool",
                    "content": tool_output,
                    "name": name,
                })

            # Ask Gemma to produce the final answer now that it has tool results
            final = ollama.chat(model=MODEL, messages=messages, tools=ollama_tools)
            print(final["message"]["content"])


if __name__ == "__main__":
    asyncio.run(main())
