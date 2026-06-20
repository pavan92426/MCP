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
