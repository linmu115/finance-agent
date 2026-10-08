"""Private offline replay of captured developer-data MCP results."""
import json
import os
from pathlib import Path
from typing import Annotated, Any
from mcp.types import CallToolResult
from service.server import mcp,service,ownership
from service.lifecycle import run_service_stdio

@mcp.tool()
async def get_replay(case: str) -> Annotated[CallToolResult, dict[str, Any]]:
    root=Path(os.environ['MCP_REAL_CASES']).resolve()
    target=(root/case).resolve()
    if target.parent!=root:raise ValueError('invalid_case')
    return CallToolResult.model_validate(json.loads(target.read_bytes())['result'])

run_service_stdio(mcp,service,ownership)
