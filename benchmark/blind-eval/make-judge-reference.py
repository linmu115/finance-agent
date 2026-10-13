"""Make a cohort reference packet from already-frozen values, without answer access."""
import argparse,shutil
from blind import ROOT,read,dump,output
p=argparse.ArgumentParser();p.add_argument('destination');p.add_argument('--tasks',nargs='+',required=True);p.add_argument('--additional-reference');a=p.parse_args()
dest=output(a.destination);dest.mkdir(parents=True,exist_ok=False)
dev=read(ROOT/'benchmark/blind-eval/reference-development.json');phase1=read(ROOT/'benchmark/blind-eval/reference-phase1.json')
gold={'rubric_version':phase1['rubric_version'],'task_requirements':{},'references':{}}
extra=read(a.additional_reference) if a.additional_reference else {'tasks':{},'sources':{}}
selected_sources=set()
for task in a.tasks:
    if task in ['D1','D2','D3']:
        gold['task_requirements'][task]=dev['task_requirements'][task[1:]]
        gold['references'].setdefault('development_original',dev)
    else:
        reference=phase1 if task in phase1['tasks'] else extra
        gold['references'][task]=reference['tasks'][task];gold['task_requirements'][task]=reference['tasks'][task]['task_requirements']
        selected_sources.update(reference.get('sources',{}))
dump(dest/'gold.json',gold)
(dest/'reference-notes.md').write_text('冻结参考来自N1独立原页核对。只判断对应题目要求；任何实质错误使实质取数计算最高1分。来源页是物理PDF页码。程序精确数值不证明语义或投资观点正确。未交付、下载失败与无法评审文件分别记载。不得读取包外组别、用量、开发记录或另一遍评审。\n','utf8')
if any(t.startswith('D') for t in a.tasks):
    (dest/'reference-notes.md').write_text((dest/'reference-notes.md').read_text('utf8')+'\n'+(ROOT/'benchmark/blind-eval/reference-notes.md').read_text('utf8'),'utf8')
for name,source in {**phase1['sources'],**extra.get('sources',{})}.items():
    if name not in selected_sources:continue
    for page in source['page_evidence']:
        for key in ['text','image']:
            owner=extra if name in extra.get('sources',{}) else phase1
            src=ROOT/owner['evidence_root']/page[key]
            shutil.copyfile(src,dest/src.name)
print('Reference packet only; no answer or group data read')
