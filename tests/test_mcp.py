import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from emporio.tools import TOOLS


def test_mcp_stdio_roundtrip():
    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "emporio.mcp_server"])
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                listed = await s.list_tools()
                assert {t.name for t in listed.tools} == {t.name for t in TOOLS}
                res = await s.call_tool("obter_produto", {"produto": "Takamine GD20"})
                return json.loads(res.content[0].text)

    out = asyncio.run(run())
    assert out["produto"]["preco_atual_fmt"] == "R$ 2.199,00"
