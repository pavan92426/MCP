"""
A minimal native MCP server using the stdio transport.
Exposes two kinds of tools:
  1. hello_world  - returns a greeting
  2. add / subtract / multiply / divide - basic math

Run it directly to sanity check imports:
    python server.py
(It will then sit waiting for JSON-RPC messages on stdin — that's normal.
 An MCP client, like Claude Desktop or a custom script, is what actually
 talks to it. Press Ctrl+C to quit when testing manually.)
"""

from mcp.server.fastmcp import FastMCP

# The name you give FastMCP() is what shows up as the server's identity
# to whatever client connects to it.
mcp = FastMCP("hello-math-server")


@mcp.tool()
def hello_world(name: str = "World") -> str:
    """Say hello to someone.

    Args:
        name: Who to greet. Defaults to "World".
    """
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
    # "stdio" means: read JSON-RPC requests from stdin, write responses to
    # stdout. This is what lets a parent process (Claude Desktop, a custom
    # client, etc.) launch this script as a subprocess and talk to it.
    mcp.run(transport="stdio")
