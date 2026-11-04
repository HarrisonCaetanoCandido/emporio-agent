"""Servidor MCP (stdio) com as mesmas ferramentas do loop em Python.

Expõe o catálogo, pedidos e políticas da loja para qualquer cliente MCP (Claude Desktop, outros
agentes, etc.):
    python -m emporio.mcp_server

stdout é o canal do protocolo — nada além do MCP pode ser impresso nele (logs vão para stderr).
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .tools import TOOLS, execute

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)


def build_server() -> Server:
    server = Server("emporio-musica")

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [types.Tool(name=t.name, description=t.description, inputSchema=t.parameters) for t in TOOLS]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
        result = execute(name, arguments or {})
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    return server


async def _serve() -> None:
    server = build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
