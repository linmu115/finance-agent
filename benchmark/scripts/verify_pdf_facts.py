"""Independent presence checks against original PDF text, after visual review."""
import json
from pathlib import Path
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
facts=json.loads((ROOT/'evaluator/facts.json').read_text(encoding='utf-8'))
readers={};checked=[]
for fact in facts:
    doc=fact['document_id']
    if doc not in readers:readers[doc]=PdfReader(ROOT/'sources/reports'/f'{doc}.pdf')
    text=readers[doc].pages[fact['pdf_page']-1].extract_text()
    clean=''.join(text.split()).replace(',','')
    assert fact['source_value'] in clean,(fact['fact_id'],'not found in original PDF page')
    assert fact['source_unit'] in text,(fact['fact_id'],'unit not found')
    checked.append(fact['fact_id'])
report={'date':'2026-10-03','facts_checked':len(checked),'method':'Original value and unit presence in independently extracted source PDF text, plus prior visual inspection of four full pages. This does not measure application extraction quality.','pdf_pages':{k:len(v.pages) for k,v in readers.items()},'facts':checked}
(ROOT/'review/fact_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='facts'},ensure_ascii=False))
