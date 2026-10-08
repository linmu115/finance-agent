"""Verify the frozen interface against legacy declarations, without running legacy code.

Run with the project's Python environment from any directory. Requires git history.
Only function signatures/docstrings are compiled; every body is replaced with return {}.
"""
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Literal
from mcp.server.fastmcp.tools.base import Tool

ROOT=Path(__file__).resolve().parents[1]
REVISION='db23e5b'
def historical(name):
    return subprocess.check_output(['git','show',f'{REVISION}:{name}'],cwd=ROOT).decode('utf8')

def main():
    old_runs=historical('server/runs.ts')
    prompt=ast.literal_eval(re.search(r"const GENERIC_PROMPT=('.*?');",old_runs).group(1))
    actual=re.search(r'export const ORIGINAL_PI_PROMPT = (".*?");',(ROOT/'server/original-pi.ts').read_text(encoding='utf8')).group(1)
    assert prompt==json.loads(actual),'legacy prompt changed'
    frozen=json.loads((ROOT/'server/original-pi-tools.json').read_text(encoding='utf8'))
    expected_names=re.findall(r"'([^']+)'",re.search(r'GENERIC_TOOL_ALLOWLIST=new Set\(\[(.*?)\]\)',old_runs).group(1))
    assert [t['name'] for t in frozen]==expected_names
    source=ast.parse(historical('service/server.py'));declarations={}
    for node in source.body:
        if isinstance(node,ast.AsyncFunctionDef) and node.name in expected_names:
            node.decorator_list=[]
            node.body=[ast.Expr(ast.Constant(ast.get_docstring(node))),ast.Return(ast.Dict(keys=[],values=[]))]
            declarations[node.name]=node
    module=ast.fix_missing_locations(ast.Module(body=list(declarations.values()),type_ignores=[]))
    namespace={'Any':Any,'Literal':Literal,'__name__':'legacy_contract_declarations'}
    exec(compile(module,'legacy_contract_declarations','exec'),namespace)
    regenerated=[]
    for name in expected_names:
        tool=Tool.from_function(namespace[name]);schema=tool.parameters
        for key in ('project_id','raw_only'):schema['properties'].pop(key,None)
        schema['required']=[key for key in schema.get('required',[]) if key!='project_id']
        schema['additionalProperties']=False
        regenerated.append({'name':name,'description':tool.description,'inputSchema':schema})
    assert regenerated==frozen,'legacy declarations differ from frozen schema'
    print(json.dumps({'source_commit':subprocess.check_output(['git','rev-parse',REVISION],cwd=ROOT).decode().strip(),
                      'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                      'tools':expected_names,'interfaces_equal':True,'legacy_function_bodies_executed':False},indent=2))

if __name__=='__main__':main()
