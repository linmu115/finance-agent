"""Explain observed PDF/XLSX byte differences without rewriting any delivery."""
import argparse,hashlib,zipfile,xml.etree.ElementTree as ET
import fitz
from blind import ROOT,read,dump,output
p=argparse.ArgumentParser();p.add_argument('study');a=p.parse_args();study=output(a.study);checks=[]
for r in read(study/'replay-results.json'):
    for c in r['checks']:
        if c['matches']:continue
        old=ROOT/'data/active/analysis'/r['original_run']/'output'/c['name']
        new=study/'artifact-replay'/r['replay_run']/'output'/c['name']
        row={'label':r['label'],'name':c['name'],'byte_identical':False}
        if old.suffix in {'.xlsx','.zip'}:
            with zipfile.ZipFile(old) as z:before={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}
            with zipfile.ZipFile(new) as z:after={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}
            row.update(zip_entry_bytes_equal=before==after,differing_members=[n for n in set(before)|set(after) if before.get(n)!=after.get(n)])
            if old.suffix=='.xlsx' and row['differing_members']==['docProps/core.xml']:
                def properties(path):
                    with zipfile.ZipFile(path) as z:return {x.tag:x.text for x in ET.fromstring(z.read('docProps/core.xml'))}
                left,right=properties(old),properties(new)
                row['core_property_differences']={k:[left.get(k),right.get(k)] for k in set(left)|set(right) if left.get(k)!=right.get(k)}
        elif old.suffix=='.pdf':
            with fitz.open(old) as x,fitz.open(new) as y:
                row['page_count_equal']=len(x)==len(y)
                row['metadata_differences']={k:[x.metadata.get(k),y.metadata.get(k)] for k in set(x.metadata)|set(y.metadata) if x.metadata.get(k)!=y.metadata.get(k)}
                row['text_equal']=len(x)==len(y) and all(p.get_text()==q.get_text() for p,q in zip(x,y))
                row['same_renderer_pixels_equal']=len(x)==len(y) and all(p.get_pixmap().samples==q.get_pixmap().samples for p,q in zip(x,y))
                row['rendering_boundary']='Same MuPDF view only; compatibility differences and independent financial semantics are separate.'
        else:raise ValueError('Unexpected differing artifact: '+str(old))
        checks.append(row)
dump(study/'replay-equivalence.json',{'checks':checks,'original_files_changed':False,'limit':'Explains observed differences; not financial correctness or delivered standalone calculator execution.'})
print({'studied_nonidentical_artifacts':len(checks)})
