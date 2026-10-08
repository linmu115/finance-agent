"""Run six paired independent sessions; order alternates by question."""
import json,shutil,subprocess,time
from pathlib import Path
base=Path(__file__).resolve().parent
plan=[]
for n in range(1,7):
 for arm in (['financial','prepared'] if n%2 else ['prepared','financial']):plan.append((f'Q{n}',arm))
state=[]
for case,arm in plan:
 out=base/'runs'/f'{case}-{arm}'
 assert not out.exists(),f'Existing attempt must be inspected, not silently replayed: {out}'
 out.mkdir(parents=True);shutil.copytree(base/'seed',out/'app-data')
 row={'case':case,'profile':arm,'start':time.time(),'state':'running'};state.append(row)
 (base/'batch.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf8')
 print('START',case,arm,flush=True)
 with (out/'worker.log').open('w',encoding='utf8') as log:
  process=subprocess.Popen(['node','--import','tsx','tmp/adoption/worker.ts',case,arm],cwd=base.parents[1],stdout=log,stderr=subprocess.STDOUT)
  row['pid']=process.pid
  (base/'batch.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf8')
  code=process.wait()
 row.update(state='exited',exit_code=code,finish=time.time())
 result=out/'result.json'
 if result.exists():
  saved=json.loads(result.read_text(encoding='utf8'));row.update(run_status=saved['run']['status'],usage=saved['run']['usage'])
 (base/'batch.json').write_text(json.dumps(state,indent=2)+'\n',encoding='utf8')
 print('DONE',case,arm,json.dumps(row,ensure_ascii=False),flush=True)
 if code!=0:
  print('Worker infrastructure error; inspect before starting remaining sessions.',flush=True);break
