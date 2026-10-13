"""Build an identity-redacted copy; originals and decoded map never enter judge packets."""
from __future__ import annotations
import argparse, csv, io, json, random, re, shutil, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TEXT = {'.md', '.txt', '.csv', '.json', '.py', '.yaml', '.yml', '.toml'}
IDENTITY = re.compile(r'(?i)financial[_ -]?agent|金融\s*(?:agent|组)|通用\s*(?:pi|组)|原版\s*pi|original_pi(?:_launch)?|gpt-[\w.\-]+|cpa-local|pi-cowork|fin-workpapers|financial_workpaper|run_financial_model|run_analysis|source_model|source_run_id|/api/projects/|(?<![a-z0-9_])[A-Z]:(?:\\|/(?!/))')
UUID = re.compile(r'(?i)(?<![a-z0-9_.])(?:[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}|(?=[a-f0-9]*[a-f])[a-f0-9]{64}|(?=[a-f0-9]*[a-f])[a-f0-9]{32})(?![a-z0-9_.])')

def read(p): return json.loads(Path(p).read_text('utf-8-sig'))
def dump(p, obj):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n','utf-8')
def output(p):
    p=Path(p).resolve()
    base=ROOT/'data/evaluation'
    if not p.is_relative_to(base) or not p.relative_to(base).parts[0].startswith('blind-eval-'):
        raise ValueError('Output must be data/evaluation/blind-eval-*')
    return p

def document_review(raw,target,red):
    """Read-only evidence expansion; originals remain outside judge packet for replay."""
    suffix=target.suffix.lower();folder=target.with_suffix(suffix+'.expanded');folder.mkdir()
    if suffix=='.svg':
        import fitz
        source=raw.decode('utf-8-sig')
        (folder/'source.svg.txt').write_text(red(source),'utf8')
        doc=fitz.open(stream=raw,filetype='svg')
        doc[0].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).save(folder/'rendered.png')
        visible=doc[0].get_text()
        (folder/'visible-text.txt').write_text(red(visible),'utf8')
        dump(folder/'document-review.json',{'format':'svg','renderer':'PyMuPDF static rendering; no browser/script execution','pixel_policy':'Original SVG rendered without identity/content modification','blocking_findings':[{'reason':'SVG visible identity marker requires review'}] if IDENTITY.search(visible) else []})
        doc.close()
    elif suffix=='.pdf':
        import fitz
        pdf=fitz.open(stream=raw,filetype='pdf');findings=[]
        for i,page in enumerate(pdf,1):
            text=page.get_text();(folder/f'page-{i:03}.txt').write_text(red(text),'utf8')
            page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).save(folder/f'page-{i:03}.png')
            if red(text)!=text:findings.append({'page':i,'reason':'PDF visible text contains a redacted identity/path; pixels must be reviewed before release'})
        dump(folder/'document-review.json',{'format':'pdf','pages':len(pdf),'pixel_policy':'All original page pixels retained, metadata excluded; visual identity review required','blocking_findings':findings})
        pdf.close()
    elif suffix=='.xlsx':
        import openpyxl
        formulas=openpyxl.load_workbook(io.BytesIO(raw),data_only=False,read_only=False)
        values=openpyxl.load_workbook(io.BytesIO(raw),data_only=True,read_only=False)
        workbook=[]
        for i,sheet in enumerate(formulas,1):
            rows=[]
            for row in sheet:
                for cell in row:
                    if cell.value is None:continue
                    cached=values[sheet.title][cell.coordinate].value
                    rows.append({'cell':cell.coordinate,'value_or_formula':red(cell.value) if isinstance(cell.value,str) else cell.value,'cached_value':red(cached) if isinstance(cached,str) else cached,'number_format':cell.number_format,'style_id':cell.style_id,'comment':red(cell.comment.text) if cell.comment else None,'hidden_row':bool(sheet.row_dimensions[cell.row].hidden)})
            # Dates serialized explicitly; every populated cell, formula and stored cache retained.
            serial=json.loads(json.dumps(rows,ensure_ascii=False,default=str))
            dump(folder/f'sheet-{i:03}.json',{'sheet':red(sheet.title),'state':sheet.sheet_state,'merged_ranges':[str(r) for r in sheet.merged_cells.ranges],'cells':serial})
            workbook.append({'sheet':red(sheet.title),'file':f'sheet-{i:03}.json','cells':len(rows),'charts':len(sheet._charts),'images':len(sheet._images)})
        visual_assets=[]
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for member in archive.namelist():
                if member.startswith('xl/charts/') and member.endswith('.xml'):
                    name=f'chart-{len(visual_assets)+1:03}.xml.txt';(folder/name).write_text(red(archive.read(member).decode('utf8')),'utf8');visual_assets.append(name)
                elif member.startswith('xl/media/') and member.lower().endswith(('.png','.jpg','.jpeg')):
                    name=f'image-{len(visual_assets)+1:03}'+Path(member).suffix;(folder/name).write_bytes(archive.read(member));visual_assets.append(name)
        dump(folder/'document-review.json',{'format':'xlsx','sheets':workbook,'visual_assets':visual_assets,'limits':'All populated cells/formulas/stored caches and chart XML/images retained; never recalculated or executed. Chart/layout appearance still requires visual review, no visual-quality pass inferred.','blocking_findings':[{'sheet':s['sheet'],'reason':'embedded charts/images need visual identity and quality review; XML/images supplied'} for s in workbook if s['charts'] or s['images']]})
        formulas.close();values.close()
    return folder

class Redactor:
    def __init__(self, replacements):
        self.replacements=sorted(replacements.items(),key=lambda x:-len(x[0]))
        self.ids={}
    def __call__(self, text):
        for a,b in self.replacements: text=text.replace(a,b)
        text=re.sub(r'https?://(?:127\.0\.0\.1|localhost):\d+[^\s\)\]"\']*','[local-link]',text)
        text=re.sub(r'/api/(?:projects|conversations|runs)/[^\s\)\]"\']*','[local-link]',text)
        # A drive path must not match the final "s:/" in an ordinary https URL.
        text=re.sub(r'(?i)(?<![a-z0-9_])[A-Z]:(?:\\|/(?!/))[^\n\r"\'<>]*','[local-path]',text)
        text=re.sub(r'/(?:input|output|opt/finance|workspace|data/active|mnt/data)(?:/[^\s"\'\)\]`,;]*)?(?![a-zA-Z_])','[local-file]',text)
        text=UUID.sub(lambda m:self.ids.setdefault(m[0],f'ref_{len(self.ids)+1:04}'),text)
        text=re.sub(r'(?<=analysis/)[a-f0-9]{20,}(?=/|\[local-file\])',lambda m:self.ids.setdefault(m[0],f'ref_{len(self.ids)+1:04}'),text)
        text=re.sub(r'\b(?:research|revision|model|run)_[\w-]{12,}\b','object_ref',text)
        return IDENTITY.sub('system_component',text)

def redact_structured_value(value, red):
    """Redact parsed string values/keys, preserving numeric types and containers."""
    if isinstance(value,str):
        return red(value)
    if isinstance(value,list):
        return [redact_structured_value(v,red) for v in value]
    if isinstance(value,dict):
        pairs=[(red(k),'system_component' if k in {'profile','evaluation_profile','agent_profile'} and v in ('original_pi','prepared','financial') else redact_structured_value(v,red)) for k,v in value.items()]
        if len({k for k,v in pairs})!=len(pairs):
            raise ValueError('Anonymization would merge distinct JSON keys')
        return dict(pairs)
    return value

def redact_text(text, suffix, red):
    """Operate inside CSV cells/JSON strings; serialization owns quote escaping."""
    if suffix=='.csv':
        rows=list(csv.reader(io.StringIO(text,newline='')))
        dest=io.StringIO(newline='');writer=csv.writer(dest,lineterminator='\n')
        for row in rows:writer.writerow([red(cell) for cell in row])
        return dest.getvalue()
    if suffix=='.json':
        return json.dumps(redact_structured_value(json.loads(text),red),ensure_ascii=False,indent=2)+'\n'
    return red(text)

def tools_in(source):
    names=set()
    for p in source.glob('*-audit.jsonl'):
        for line in p.read_text('utf-8-sig').splitlines():
            e=json.loads(line)
            if e.get('type','').startswith('tool_') and e.get('data',{}).get('name'): names.add(e['data']['name'])
    names.update(['analysis_report','finance_charts','financial_workpaper','financial_metrics','get_financial_metrics','save_table','source_run_id','source_model','investment_memo','statement_analysis','report_audit','model_delivery','model_units','plot_runtime','sandbox profile'])
    return {n:f'component_{i:03}' for i,n in enumerate(sorted(names),1)}

def expand_archive(raw, target, replacements):
    """Nested original-calculator ZIPs are reviewable, never executed or path-extracted."""
    target.mkdir()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        members=[x for x in z.infolist() if not x.is_dir()]
        names={x.filename:f'member_{j:03}'+Path(x.filename).suffix for j,x in enumerate(members,1)}
        red=Redactor({**replacements,**names})
        for member in members:
            data=z.read(member);ext=Path(member.filename).suffix.lower();dest=target/names[member.filename]
            if ext in TEXT:dest.write_text(redact_text(data.decode('utf-8-sig'),ext,red),'utf-8',newline='')
            elif ext=='.zip':expand_archive(data,dest.with_suffix('.zip.expanded'),{**replacements,**names})
            elif ext in {'.png','.jpg','.jpeg'}:dest.write_bytes(data)
            elif ext in {'.pdf','.xlsx','.svg'}:document_review(data,dest,red)
            else:raise ValueError('Unreviewed archive type: '+member.filename)

def build(source, dest, seed, reference_dir=None, task_ids=None):
    source=Path(source).resolve();dest=output(dest)
    dest.mkdir(parents=True,exist_ok=False)
    state=read(source/'experiment.json')
    runs=[r for r in state['runs'] if r['status'] in ['completed','failed','cancelled'] and (source/(r['label']+'-deliverables.json')).exists()]
    if task_ids is not None:runs=[r for r in runs if r.get('taskId',r['label'][1:]) in task_ids]
    tasks=state['config']['tasks'] if state.get('schema') in ('blind-eval-f1-v1','blind-eval-v3-gate-1') else state['tasks']
    rng=random.Random(seed);rng.shuffle(runs)
    mapping=[];issues=[]; tools=tools_in(source)
    shared=dest/'reference';shared.mkdir()
    shutil.copyfile(HERE/'rubric.md',shared/'rubric.md')
    reference_dir=Path(reference_dir).resolve() if reference_dir else source/'judge'
    gold=read(reference_dir/'gold.json')
    # baseline/scenario here are economic scenarios, rename so no arm words enter review.
    dump(shared/'reference.json',json.loads(json.dumps(gold,ensure_ascii=False).replace('"baseline"','"original_scenario"')))
    notes=reference_dir/'reference-notes.md'
    if not notes.exists():
        if source.name!='pi-cowork-acceptance-20261006':raise ValueError('Supply approved reference-notes.md with the new cohort')
        notes=HERE/'reference-notes.md'
    shutil.copyfile(notes,shared/'reference-notes.md')
    for p in reference_dir.glob('*-p*.png'): shutil.copyfile(p,shared/p.name)
    for p in reference_dir.glob('*-p*.txt'): shutil.copyfile(p,shared/p.name)
    for i,run in enumerate(runs,1):
        case=f'S{rng.randrange(100000,999999)}'; folder=dest/'packet'/case;folder.mkdir(parents=True)
        label=run['label'];delivery=read(source/f'{label}-deliverables.json')
        arts=delivery['artifacts']; replacements=dict(tools); private=[]
        # Names shared by versions retain a family ID; each visible file keeps its own version.
        families={}
        for a in arts:
            families.setdefault(a['name'],f'file_{len(families)+1:03}')
        versions={}
        for a in arts:
            name=a['name'];versions[name]=versions.get(name,0)+1
            ext=Path(name).suffix.lower(); new=f'{families[name]}_v{versions[name]}{ext}'
            replacements[a['url']]=new
            for key in ['localFile','evaluatorLocalFile']:
                if a.get(key): replacements[a[key]]=new
            private.append({'original':a,'anonymous':new,'version':versions[name]})
        for name,family in families.items():
            matches=[x for x in private if x['original']['name']==name]
            replacements[name]=matches[0]['anonymous'] if len(matches)==1 else family+'_[ambiguous_version]'+Path(name).suffix
        red=Redactor(replacements)
        task=next(t for t in tasks if t['id']==run.get('taskId',label[1:]))
        prompt=task['prompt']
        if task.get('continuationOf'):
            prompt=next(t['prompt'] for t in tasks if t['id']==task['continuationOf'])+'\n\n后续问题：\n'+prompt
        (folder/'question.md').write_text(red(prompt),'utf-8')
        (folder/'answer.md').write_text(red((source/f'{label}-answer.md').read_text('utf-8-sig')),'utf-8')
        visible=[]
        for item in private:
            a=item['original'];name=item['anonymous'];suffix=Path(name).suffix
            local=a.get('localFile') or a.get('evaluatorLocalFile')
            role='delivered_attachment' if a.get('localFile') else 'evaluator_copy_download_failed'
            if not local:
                visible.append({'file':None,'expected_file':name,'version':item['version'],'download_status':a.get('httpStatus'),'role':'unavailable_attachment','error':red(a.get('error','No collected file'))})
                continue
            src=source/f'{label}-artifacts'/local;target=folder/name
            if suffix in TEXT:
                text=src.read_bytes().decode('utf-8-sig')
                target.write_text(redact_text(text,suffix,red),'utf-8',newline='')
            elif suffix=='.zip':
                target=folder/(name+'.expanded');expand_archive(src.read_bytes(),target,replacements)
            elif suffix in {'.png','.jpg','.jpeg'}:shutil.copyfile(src,target)
            elif suffix in {'.pdf','.xlsx','.svg'}:target=document_review(src.read_bytes(),target,red)
            else:raise ValueError('Unreviewed attachment type: '+str(src))
            visible.append({'file':target.name,'version':item['version'],'download_status':a.get('httpStatus'),'role':role})
        # Source code actually executed, including attempts, is extra evaluator evidence, not delivery credit.
        for j,s in enumerate(delivery.get('evaluatorScripts',[]),1):
            name=f'code_{j:03}.py'; (folder/name).write_text(red((source/f'{label}-artifacts'/s['file']).read_text('utf-8-sig')),'utf-8')
            visible.append({'file':name,'role':'evaluator_copy_not_delivery','execution_status':s['status']})
        dump(folder/'files.json',visible)
        mapping.append({'case_id':case,'label':label,'profile':run['profile'],'task':task['id'],'files':private,'replacements':red.ids})
    dump(dest/'private-map.json',{'seed':seed,'source':str(source),'cases':mapping})
    caseids=[x['case_id'] for x in mapping]
    for round_id,order in [('round1',caseids),('round2',list(reversed(caseids)))]:
        rd=dest/round_id;rd.mkdir()
        shutil.copytree(dest/'reference',rd/'reference')
        # A separate anonymous numbering per round prevents location/label anchors in a future human re-review.
        round_map={}
        for j,case in enumerate(order,1):
            new=f'Q{j:02}'; shutil.copytree(dest/'packet'/case,rd/new);round_map[new]=case
        dump(rd/'cases.json',list(round_map))
        dump(dest/f'private-{round_id}-map.json',round_map)
    for p in (dest/'packet').rglob('*'):
        if p.is_file() and p.suffix in TEXT:
            for m in IDENTITY.finditer(p.read_text('utf-8')):issues.append({'file':str(p.relative_to(dest)),'match':m[0]})
        if p.name=='document-review.json':
            for finding in read(p)['blocking_findings']:issues.append({'file':str(p.relative_to(dest)),**finding})
    dump(dest/'anonymization-audit.json',{'cases':len(mapping),'attachments':sum(len(x['files']) for x in mapping),'explicit_marker_findings':issues,'images':'Pixels and bytes preserved; filenames anonymized. Review visible identity clues manually. No original paths/maps/audits/usage or historical verdicts supplied to judges.','limits':'Semantic tool behavior or writing style may permit inference; identity blinding is not a guarantee against inference. Redacted code is read-only review material; replay uses original code in sandbox.'})
    if issues:raise ValueError('Explicit identity markers remain')
    print(json.dumps({'cases':len(mapping),'dest':str(dest),'findings':len(issues)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('dest');p.add_argument('--seed',type=int,default=20261007);p.add_argument('--reference-dir');p.add_argument('--tasks',nargs='+');a=p.parse_args();build(a.source,a.dest,a.seed,a.reference_dir,a.tasks)
