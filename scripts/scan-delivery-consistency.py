"""Observation-only A5 JSON API: stdin or --input; stdout or --output."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.delivery_consistency import scan_delivery

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args()
    payload=json.loads(a.input.read_text('utf-8-sig') if a.input else sys.stdin.read())
    result=scan_delivery(**payload)
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if a.output:a.output.write_text(text,encoding='utf8')
    else:print(text,end='')
