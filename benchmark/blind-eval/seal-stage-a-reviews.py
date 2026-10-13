"""Seal both submitted review files before decoding either round's identities."""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from blind import output
p=argparse.ArgumentParser();p.add_argument('folder');a=p.parse_args();folder=output(a.folder)
paths=[folder/rd/'review.json' for rd in ['round1','round2']]
raw=[p.read_bytes() for p in paths]
record={'sealed_at':datetime.now(timezone.utc).isoformat(),'model':'gpt-6-astra','reasoning_effort':'high','rule':'Both complete original files sealed before identity decoding; neither review rewritten to resolve disagreement.','reviews':[{'path':str(p.relative_to(folder)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for p,b in zip(paths,raw)]}
with (folder/'score-seal.json').open('x',encoding='utf8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps(record,ensure_ascii=False))
