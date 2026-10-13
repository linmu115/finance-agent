import sys, inspect
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import fitz
import service.report_package as rp
original=fitz.Story.place
counter=0
def place(self,*a,**kw):
    global counter
    counter+=1
    if counter>130:raise RuntimeError('diagnostic stop')
    result=original(self,*a,**kw)
    print(counter,result,flush=True)
    return result
fitz.Story.place=place
code=inspect.getsource(rp.render_pdf).replace('story.write(writer,rectfn);writer.close()', 'try: story.write(writer,rectfn)\n    finally: writer.close()')
exec(code,rp.__dict__)
folder=Path(sys.argv[1])
try:rp.render_pdf(folder)
except RuntimeError:pass
with fitz.open(folder/'.report.pdf') as pdf:
    for i,p in enumerate(pdf):
        text=p.get_text().strip()
        if text:print('CONTENT',i+1,text[-800:],flush=True)
