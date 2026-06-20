# Building a Native MCP Server (stdio) — Hello World + Basic Math

This guide walks through building a minimal **Model Context Protocol (MCP)
server** in Python that communicates over **stdio** (standard input/output)
and exposes two kinds of tools:

- `hello_world` — returns a greeting
- `add`, `subtract`, `multiply`, `divide` — basic math

You'll then connect it to two different clients:

- **Claude Desktop / Claude Code** (official Anthropic apps)
- **A local Gemma model running on Ollama** (via a small bridge script,
  since Ollama doesn't speak MCP natively)

---

## 1. What "stdio MCP server" actually means

MCP defines a protocol for how an AI client (Claude, a custom app, etc.)
discovers and calls "tools" exposed by a server. The **stdio transport**
is the simplest version: the client launches your script as a subprocess
and the two talk by writing JSON-RPC messages to each other's stdin/stdout.
No network ports, no HTTP — just a pipe.

```
Client (Claude Desktop / your script)
      │  spawns subprocess
      ▼
your server.py  ── reads JSON-RPC from stdin
                ── writes JSON-RPC to stdout
```

This is why, when you run `python server.py` directly in a terminal, it
just sits there waiting — that's correct. It's waiting for a client to
talk to it, not for you to type.

---

## 2. Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) installed (`curl -LsSf https://astral.sh/uv/install.sh | sh` on macOS/Linux, or see the uv docs for Windows)
- The official MCP Python SDK
- (Optional, for local Gemma) [Ollama](https://ollama.com) installed and a
  Gemma model pulled

```bash
uv init mcp-hello-math
cd mcp-hello-math

uv add mcp
```

`uv init` creates the project (`pyproject.toml`, a `.venv`, a `main.py`
stub you can ignore/delete). `uv add mcp` installs the SDK into that
project's virtual environment and records it in `pyproject.toml` — no
manual `venv activate` step needed; `uv run` handles that for you.

If you plan to test with local Gemma via Ollama, also run:

```bash
uv add ollama
ollama pull gemma3      # or gemma2, gemma3:4b, etc. — whatever tag you use
```

---

## 3. Write the server

Create `server.py`:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hello-math-server")

@mcp.tool()
def hello_world(name: str = "World") -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"

@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b

@mcp.tool()
def subtract(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b

@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b

@mcp.tool()
def divide(a: float, b: float) -> float:
    """Divide a by b. Raises an error if b is zero."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

A few things worth noting:

- `FastMCP` is the high-level helper in the official SDK — it auto-generates
  the JSON schema for each tool from your Python type hints and docstring.
- The **docstring becomes the tool description** the LLM sees, so write it
  like you're explaining the tool to the model, not just to a human reader.
- `mcp.run(transport="stdio")` is what wires everything to stdin/stdout.

---

## 4. Test it without any LLM

Before involving Claude or Gemma, confirm the server itself works using a
plain MCP client script. Create `test_client.py`:

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(command="python", args=["server.py"])

async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Available tools:", [t.name for t in tools.tools])

            result = await session.call_tool("hello_world", {"name": "Gemma"})
            print(result.content[0].text)

            result = await session.call_tool("add", {"a": 7, "b": 5})
            print(result.content[0].text)

asyncio.run(main())
```

Run it:

```bash
uv run test_client.py
```

Expected output:

```
Available tools: ['hello_world', 'add', 'subtract', 'multiply', 'divide']
Hello, Gemma!
12.0
```

If you see that, your MCP server is working correctly — the rest is just
wiring it up to different clients.

---

## 5. Connect it to Claude Desktop or Claude Code

Claude Desktop and Claude Code both read MCP server definitions from a
JSON config file.

**Config file location:**

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

Add an entry under `mcpServers`, using `uv run` so the project's
dependencies resolve correctly. Use `--directory` to point at your project
folder with an **absolute path**:

```json
{
  "mcpServers": {
    "hello-math": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/mcp-hello-math",
        "run",
        "server.py"
      ]
    }
  }
}
```

If `uv` isn't on the PATH that Claude Desktop launches with (common on
macOS, since GUI apps don't always inherit your shell's PATH), use the
absolute path to the `uv` binary instead — find it with `which uv`
(macOS/Linux) or `where uv` (Windows), e.g.
`"command": "/Users/you/.local/bin/uv"`.

Then **fully quit and restart** Claude Desktop. Your tools (`hello_world`,
`add`, `subtract`, `multiply`, `divide`) will show up in the tool/connector
picker, and Claude will call them automatically when relevant — e.g. asking
"what's 23 times 4?" should trigger `multiply`.

> Config details can change between app versions — if something doesn't
> match what you see in your installed app, check
> https://docs.claude.com or https://support.claude.com for the current
> behavior.

---

## 6. Connect it to a local Gemma model (Ollama)

Gemma running locally through Ollama doesn't understand MCP's JSON-RPC
protocol — it only understands Ollama's own function-calling format. So you
need a small **bridge script** that:

1. Talks to your MCP server (the same way `test_client.py` does) to fetch
   the tool list.
2. Converts that tool list into the JSON-schema shape Ollama expects.
3. Sends the user's message + tool definitions to Gemma.
4. If Gemma asks to call a tool, forwards the call to the MCP server and
   feeds the result back to Gemma.

Create `ollama_bridge.py`:

```python
import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import ollama

server_params = StdioServerParameters(command="python", args=["server.py"])
MODEL = "gemma3"  # match the tag from `ollama list`

def mcp_tool_to_ollama_format(tool) -> dict:
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

            messages = [{"role": "user",
                         "content": "Say hello to Alice, then tell me what 23 times 4 is."}]

            response = ollama.chat(model=MODEL, messages=messages, tools=ollama_tools)
            messages.append(response["message"])

            for call in response["message"].get("tool_calls") or []:
                name = call["function"]["name"]
                args = call["function"]["arguments"]
                if isinstance(args, str):
                    args = json.loads(args)
                result = await session.call_tool(name, args)
                messages.append({"role": "tool", "content": result.content[0].text, "name": name})

            final = ollama.chat(model=MODEL, messages=messages, tools=ollama_tools)
            print(final["message"]["content"])

asyncio.run(main())
```

Run it (make sure `ollama serve` is running and the model is pulled):

```bash
uv run ollama_bridge.py
```

Gemma should respond with something like:
*"Hello, Alice! And 23 times 4 is 92."* — with the actual multiplication
having been done by your `multiply` tool, not "guessed" by the model.

**Alternative for local models:** if you'd rather not maintain a bridge
script yourself, tools like **LM Studio** (which has added native MCP
client support) or community bridges such as `mcpo` / `ollama-mcp-bridge`
can connect Ollama-served models to MCP servers without custom code. Search
their docs for current setup steps, since these projects move quickly.

---

## 7. Project structure recap

```
mcp-hello-math/
├── .venv/              # created by uv, don't edit directly
├── pyproject.toml      # created by uv, tracks dependencies
├── server.py            # the MCP server itself
├── test_client.py       # sanity check, no LLM needed
└── ollama_bridge.py      # optional: wires server.py to local Gemma
```

---

## 8. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Claude Desktop doesn't show the server | Wrong absolute path in `--directory`, or `uv` not found on the launching PATH, or you didn't fully quit/restart the app after editing the config |
| `ModuleNotFoundError: mcp` | You ran `python server.py` directly instead of `uv run server.py` — uv's `.venv` isn't activated unless you go through `uv run` |
| Server "hangs" when run directly | Normal — it's waiting for a client on stdin, not for terminal input |
| JSON parse errors in Claude Desktop logs | Trailing commas or unescaped backslashes in `claude_desktop_config.json` — validate with a JSON linter |
| `uv: command not found` inside Claude Desktop logs | Use the absolute path to the `uv` binary in `command` instead of relying on PATH |
| Ollama bridge errors on `tool_calls` | Some Gemma tags/versions support function calling better than others — check `ollama show <model>` for "tools" capability, or try a newer tag |

---

## 9. Where to go from here

- Add more tools (file access, web requests, database queries) — same
  `@mcp.tool()` pattern.
- Switch to the **HTTP/SSE transport** instead of stdio if you want the
  server reachable over a network rather than launched as a local subprocess.
- For Claude Code specifically, you can also register servers via the CLI
  (`claude mcp add ...`) instead of hand-editing JSON — see
  https://docs.claude.com for current command syntax.
