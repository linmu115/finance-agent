"""Preserve both renderer views of the same original PDF; never edit PDF content."""
import argparse, hashlib, importlib.util, json, shutil, subprocess
from pathlib import Path
from datetime import datetime, timezone
from blind import read, dump, output

p=argparse.ArgumentParser();p.add_argument('study');p.add_argument('anonymous');p.add_argument('--clone-from');a=p.parse_args()
study=output(a.study);anonymous=output(a.anonymous)
if a.clone_from:
    prior=output(a.clone_from);anonymous.mkdir(exist_ok=False)
    for name in ['packet','reference','round1','round2']:
        shutil.copytree(prior/name,anonymous/name,ignore=shutil.ignore_patterns('review.json','progress.json'))
    for name in ['private-map.json','private-round1-map.json','private-round2-map.json','anonymization-audit.json','integrity-audit.json','supplement-receipt.json']:
        shutil.copyfile(prior/name,anonymous/name)
spec=importlib.util.spec_from_file_location('preserving',Path(__file__).with_name('blind-structure-preserving.py'))
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
copies=[]
for case in read(anonymous/'private-map.json')['cases']:
    folders=[anonymous/'packet'/case['case_id']]
    for rd in ['round1','round2']:
        mapping=read(anonymous/f'private-{rd}-map.json')
        folders.append(anonymous/rd/next(q for q,c in mapping.items() if c==case['case_id']))
    replacements=mod.tools_in(study)
    replacements.update({x['original']['name']:x['anonymous'] for x in case['files']})
    red=mod.Redactor(replacements)
    for item in case['files']:
        if not item['anonymous'].endswith('.pdf'):continue
        original=study/(case['label']+'-artifacts')/item['original']['localFile']
        assert hashlib.sha256(original.read_bytes()).hexdigest()==item['original']['sha256']
        pages=read(folders[0]/(item['anonymous']+'.expanded')/'document-review.json')['pages']
        for page in range(1,pages+1):
            image=study/'visual-originals'/f"{case['label']}-{page}.png"
            assert image.exists()
            text=subprocess.run(['pdftotext','-f',str(page),'-l',str(page),'-layout',str(original),'-'],capture_output=True,encoding='utf-8',check=True).stdout
            for folder in folders:
                dest=folder/(item['anonymous']+'.expanded')
                target=dest/f'poppler-page-{page:03}.png';shutil.copyfile(image,target)
                (dest/f'poppler-page-{page:03}.txt').write_text(red(text),encoding='utf8')
                copies.append({'path':target.relative_to(anonymous).as_posix(),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
        for folder in folders:
            (folder/(item['anonymous']+'.expanded')/'renderer-note.txt').write_text(
                'page-* 是 MuPDF 原文件渲染，poppler-page-* 是同一原文件的 Poppler 渲染；二者均未修改原 PDF 内容。'
                '嵌入字体在不同渲染器下可能显示不同，请同时查看，不把单一展开器缺字自动当作原交付正文缺失。'
                '渲染兼容性与实际可读性可分别记录；可读取文字也不意味着版式或内容正确。共享来源文档标识不是参评身份。\n',encoding='utf8')
for rd in ['round1','round2']:
    target=anonymous/rd/'READ_FIRST.md'
    content=target.read_text('utf8') if target.exists() else ''
    target.write_text(content+'\nPDF 必须同时查看 MuPDF 与 Poppler 原始渲染视图及 renderer-note.txt；不要只凭一种渲染器的字体表现作结论。\n',encoding='utf8')
dump(anonymous/'pdf-renderer-supplement.json',{'at':datetime.now(timezone.utc).isoformat(),'copies':copies,'originals_edited':False,'scores_read':False,'gold_changed':False,'clone_from':a.clone_from})
print(json.dumps({'pdf_page_copies':len(copies),'scores_read':False}))
