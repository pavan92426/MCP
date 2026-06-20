# gemma-tools-mcp — A Native MCP Server (stdio): Hello World + Basic Math

This guide walks through building a minimal **Model Context Protocol (MCP)
server** in Python that communicates over **stdio** (standard input/output)
and exposes two kinds of tools:

- `hello_world` — returns a greeting
- `add`, `subtract`, `multiply`, `divide` — basic math

You'll then connect it to three different clients:

- **Claude Desktop / Claude Code** (official Anthropic apps)
- **A local Gemma model running on Ollama** (via a small bridge script,
  since Ollama doesn't speak MCP natively)
- **LM Studio running Gemma 4** (LM Studio has a built-in MCP client, so
  no bridge script needed)

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
uv init gemma-tools-mcp
cd gemma-tools-mcp

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

> **Renaming a project you already `uv init`'d:** uv doesn't have a single
> "rename" command. The name lives in two places — fix both:
> 1. Rename the folder: `mv old-name gemma-tools-mcp && cd gemma-tools-mcp`
> 2. Edit the `name = "..."` field under `[project]` in `pyproject.toml`
>    to `gemma-tools-mcp`, then run `uv sync` to refresh the lockfile/venv
>    metadata.
> Don't forget to update any **absolute paths** pointing at the old folder
> name in `claude_desktop_config.json` or LM Studio's `mcp.json`.

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
        "/absolute/path/to/gemma-tools-mcp",
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
3. Runs a **continuous chat loop**: read what you type, send the full
   conversation history + tool definitions to Gemma, resolve any tool
   calls against the MCP server, print the answer, then wait for your
   next message — repeating until you type `exit`/`quit`.

Create `ollama_bridge.py`:

```python
import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import ollama

server_params = StdioServerParameters(command="uv", args=["run", "server.py"])
MODEL = "gemma4"  # match the exact tag from `ollama list`

def mcp_tool_to_ollama_format(tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
        },
    }

async def handle_tool_calls(session, assistant_message, messages):
    tool_calls = assistant_message.get("tool_calls") or []
    for call in tool_calls:
        name = call["function"]["name"]
        args = call["function"]["arguments"]
        if isinstance(args, str):
            args = json.loads(args)
        result = await session.call_tool(name, args)
        messages.append({"role": "tool", "content": result.content[0].text, "name": name})
    return bool(tool_calls)

async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            ollama_tools = [mcp_tool_to_ollama_format(t) for t in mcp_tools]

            messages = []  # persists across turns so Gemma keeps context
            while True:
                user_input = input("You: ").strip()
                if user_input.lower() in {"exit", "quit"}:
                    break
                messages.append({"role": "user", "content": user_input})

                response = ollama.chat(model=MODEL, messages=messages, tools=ollama_tools)
                assistant_message = response["message"]
                messages.append(assistant_message)

                while await handle_tool_calls(session, assistant_message, messages):
                    response = ollama.chat(model=MODEL, messages=messages, tools=ollama_tools)
                    assistant_message = response["message"]
                    messages.append(assistant_message)

                print(f"Gemma: {assistant_message['content']}\n")

asyncio.run(main())
```

(The actual file also prints which tool was called and its result, and
handles `Ctrl+C`/EOF gracefully — see `ollama_bridge.py` in your project.)

Run it (make sure `ollama serve` is running and the model is pulled):

```bash
uv run ollama_bridge.py
```

Then just keep typing — each line is a new turn, and the conversation
history (`messages`) is kept in memory for the whole session so Gemma
remembers earlier turns:

```
Connected. Available tools: ['hello_world', 'add', 'subtract', 'multiply', 'divide']
Type a message (or 'exit'/'quit' to stop).

You: say hello to Alice
  [tool call] hello_world({'name': 'Alice'}) -> Hello, Alice!
Gemma: Hello, Alice!

You: now what's 23 times 4?
  [tool call] multiply({'a': 23, 'b': 4}) -> 92.0
Gemma: 23 times 4 is 92.

You: exit
Goodbye!
```

**Why your earlier one-shot run only answered once:** the original version
of this script sent a single hardcoded prompt and exited after one
response — it never looped back to read more input. The version above
wraps that same logic in a `while True` loop with a persistent
`messages` list, which is what gives you a real back-and-forth chat.

**Alternative for local models:** if you'd rather not maintain a bridge
script yourself, tools like **LM Studio** (which has added native MCP
client support) or community bridges such as `mcpo` / `ollama-mcp-bridge`
can connect Ollama-served models to MCP servers without custom code. Search
their docs for current setup steps, since these projects move quickly.

---

## 7. Connect it to LM Studio (running Gemma 4)

Unlike Ollama, **LM Studio has a built-in MCP client** (since v0.3.17), so
you don't need a bridge script — you just point LM Studio's `mcp.json` at
your server the same way you'd point Claude Desktop at it.

### 7.1 Get LM Studio + Gemma 4

1. Install/update [LM Studio](https://lmstudio.ai) to a recent version
   (Help → About to check; MCP support requires 0.3.17+).
2. In the **Discover** tab, search for **Gemma 4** and download a size that
   fits your hardware — e.g. `E2B`/`E4B` for laptops, `26B` (MoE) or `31B`
   for a workstation with more VRAM. Pick an **instruction-tuned** variant
   for chat/tool-use.
3. Confirm the model shows a tool/function-calling icon in its card — that
   indicates LM Studio recognizes it as tool-call capable.

### 7.2 Register your MCP server

1. Open LM Studio, go to the right sidebar's **Program** tab.
2. Click **Install → Edit mcp.json**. This opens LM Studio's MCP config
   file in its built-in editor (it lives at `~/.lmstudio/mcp.json` on
   macOS/Linux, `%USERPROFILE%\.lmstudio\mcp.json` on Windows).
3. Add your server, same `uv run` pattern as the Claude Desktop config:

```json
{
  "mcpServers": {
    "hello-math": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/gemma-tools-mcp",
        "run",
        "server.py"
      ]
    }
  }
}
```

4. Save the file — LM Studio auto-reloads `mcp.json` and spawns the server
   process for you.

### 7.3 Use it in a chat

1. Load the Gemma 4 model in a new chat.
2. At the bottom of the chat input, find the MCP/tools selector and enable
   `hello-math`.
3. Ask something like *"Say hello to Priya, then tell me what 17 minus 9
   is."*
4. LM Studio will show a **confirmation dialog** before each tool call
   (you can review/edit the arguments, and choose "allow once" or "always
   allow" for that tool) — approve it, and Gemma 4 will use `hello_world`
   and `subtract` to answer.

This is generally simpler to get right than the Ollama route, precisely
because LM Studio handles the MCP protocol itself instead of you writing a
bridge script.

> LM Studio's UI and exact menu names can change between releases — if
> something doesn't match what you see, check https://lmstudio.ai/docs for
> the current steps.

---

## 8. Project structure recap

```
gemma-tools-mcp/
├── .venv/              # created by uv, don't edit directly
├── pyproject.toml      # created by uv, tracks dependencies
├── server.py            # the MCP server itself
├── test_client.py       # sanity check, no LLM needed
└── ollama_bridge.py      # optional: wires server.py to local Gemma
```

---

## 9. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Claude Desktop doesn't show the server | Wrong absolute path in `--directory`, or `uv` not found on the launching PATH, or you didn't fully quit/restart the app after editing the config |
| `ModuleNotFoundError: mcp` | You ran `python server.py` directly instead of `uv run server.py` — uv's `.venv` isn't activated unless you go through `uv run` |
| Server "hangs" when run directly | Normal — it's waiting for a client on stdin, not for terminal input |
| JSON parse errors in Claude Desktop logs | Trailing commas or unescaped backslashes in `claude_desktop_config.json` — validate with a JSON linter |
| `uv: command not found` inside Claude Desktop logs | Use the absolute path to the `uv` binary in `command` instead of relying on PATH |
| Ollama bridge errors on `tool_calls` | Some Gemma tags/versions support function calling better than others — check `ollama show <model>` for "tools" capability, or try a newer tag |
| LM Studio doesn't show your server / tools | `mcp.json` has a syntax error (validate with a linter), the path in `--directory` is wrong, or `uv` isn't on LM Studio's PATH — try the absolute path to the `uv` binary |
| LM Studio model never calls the tool | Confirm the loaded Gemma 4 variant is instruction-tuned and shows the tool-calling icon, and that the `hello-math` server is toggled on in the chat's tools selector |

---

## 10. Where to go from here

- Add more tools (file access, web requests, database queries) — same
  `@mcp.tool()` pattern.
- Switch to the **HTTP/SSE transport** instead of stdio if you want the
  server reachable over a network rather than launched as a local subprocess.
- For Claude Code specifically, you can also register servers via the CLI
  (`claude mcp add ...`) instead of hand-editing JSON — see
  https://docs.claude.com for current command syntax.
