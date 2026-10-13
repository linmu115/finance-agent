"""Add frozen complete sources and reviewed read-only workbook previews.

No participant answers, calculations, rubric, or scores are edited.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from blind import read, dump, output

p=argparse.ArgumentParser();p.add_argument('study');p.add_argument('anonymous');a=p.parse_args()
study=output(a.study);anonymous=output(a.anonymous)
mapping=read(anonymous/'private-map.json')['cases']
review=read(study/'visual-identity-review.json')
copies=[]
for base in [anonymous,anonymous/'round1',anonymous/'round2']:
    dest=base/'reference/complete-originals'
    shutil.copytree(study/'judge-reference/complete-originals',dest)
    copies += [{'path':p.relative_to(anonymous).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
               for p in dest.iterdir() if p.is_file()]

previews=[]
for case in mapping:
    for item in case['files']:
        if not item['anonymous'].endswith('.xlsx'):
            continue
        original=item['original']
        checked=next(x for x in review['workbooks'] if x['sha256']==original['sha256'])
        assert checked['explicit_group_or_tool_identity_visible'] is False
        destinations=[anonymous/'packet'/case['case_id']]
        for rd in ['round1','round2']:
            rmap=read(anonymous/f'private-{rd}-map.json')
            q=next(q for q,c in rmap.items() if c==case['case_id'])
            destinations.append(anonymous/rd/q)
        for folder in destinations:
            expanded=folder/(item['anonymous']+'.expanded')
            for i,sheet in enumerate(checked['sheets'],1):
                src=study/sheet['actually_opened_preview']
                target=expanded/f'render-sheet-{i:03}.png'
                shutil.copyfile(src,target)
                previews.append({'path':target.relative_to(anonymous).as_posix(),
                                 'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
            (expanded/'render-note.txt').write_text(
                '只读导入渲染预览；原工作簿未编辑、重算或导出。完整单元格、原公式与保存的缓存值见 sheet-*.json。'
                '此预览不是原生 Excel 截图；排版须结合原始列宽/样式和完整单元格评估。共享文档标识是来源引文，不是参评身份。\n',encoding='utf-8')

dump(anonymous/'supplement-receipt.json',{'complete_sources':copies,'workbook_previews':previews,
     'originals_changed':False,'gold_changed':False,'scores_supplied':False})
print(json.dumps({'source_copies':len(copies),'workbook_previews':len(previews)}))
