"""
Standalone test client — talks to server.py over stdio using the official
MCP Python SDK, with no LLM involved. Use this to confirm your server works
before plugging it into Claude Desktop or a local model.

Run:
    python test_client.py
"""

import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["server.py"],
)


async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools
            tools = await session.list_tools()
            print("Available tools:")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description}")
            print()

            # Call hello_world
            result = await session.call_tool("hello_world", {"name": "Gemma"})
            print("hello_world ->", result.content[0].text)

            # Call add
            result = await session.call_tool("add", {"a": 7, "b": 5})
            print("add(7, 5) ->", result.content[0].text)

            # Call divide
            result = await session.call_tool("divide", {"a": 10, "b": 4})
            print("divide(10, 4) ->", result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
