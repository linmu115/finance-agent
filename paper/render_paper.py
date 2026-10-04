"""Run the skill renderer with an explicit project-scoped official LibreOffice."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

root=Path(__file__).resolve().parent
soffice=root/'runtime/libreoffice/LibreOffice/program/soffice.exe'
if not soffice.is_file():raise RuntimeError('Approved project LibreOffice executable missing')
renderer=Path('C:/Users/32185/.codex/plugins/cache/openai-primary-runtime/documents/26.909.12148/skills/documents/render_docx.py')
poppler=Path('C:/Users/32185/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin')
os.environ['PATH']=str(poppler)+os.pathsep+os.environ.get('PATH','')
spec=importlib.util.spec_from_file_location('skill_render_docx',renderer)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
module._resolve_soffice=lambda:str(soffice)
sys.argv=[str(renderer),str(root/'financial_analysis_paper_v0.1.docx'),'--output_dir',str(root/'render'),'--emit_pdf','--verbose']
module.main()
shutil.copy2(root/'render/financial_analysis_paper_v0.1.pdf',root/'financial_analysis_paper_v0.1.pdf')
from pdf2image import pdfinfo_from_path
page_count=pdfinfo_from_path(str(root/'financial_analysis_paper_v0.1.pdf'),poppler_path=str(poppler))['Pages']
render_root=(root/'render').resolve()
for page in render_root.glob('page-*.png'):
    suffix=page.stem.removeprefix('page-')
    if suffix.isdigit() and int(suffix)>page_count:
        if page.resolve().parent!=render_root:raise RuntimeError('Unexpected render path')
        page.unlink()
(root/'render/render-current.json').write_text(json.dumps({'pages':page_count,'visual_review_pending':True,'docx':str(root/'financial_analysis_paper_v0.1.docx')},indent=2),encoding='utf-8')
(root/'runtime/render_environment.json').write_text(json.dumps({'authoring_python':sys.executable,'renderer':str(renderer),'soffice':str(soffice),'poppler':str(poppler),'msi_sha256':'f9877032fd908beb9c0ddf06df4af5c2e85f419c42e14876c4cce5aae5fb2660','msi_signature':'Valid; The Document Foundation'},indent=2),encoding='utf-8')
