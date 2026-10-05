"""Render the versioned Markdown paper with embedded Chinese fonts and vector figures."""
from __future__ import annotations
from datetime import datetime, timezone
from html import escape
import hashlib
import json
import os
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, LongTable, TableStyle, Flowable, KeepTogether

HERE=Path(__file__).resolve().parent
MD=HERE/'finance-agent-technical-paper.md'
PDF=HERE/'finance-agent-technical-paper.pdf'
FONT=Path(os.environ.get('FINANCE_PAPER_FONT',r'C:\Windows\Fonts\simsun.ttc'))
pdfmetrics.registerFont(TTFont('PaperSong',str(FONT),subfontIndex=0))
bold=Path(r'C:\Windows\Fonts\simhei.ttf')
pdfmetrics.registerFont(TTFont('PaperHei',str(bold if bold.exists() else FONT),subfontIndex=0))
pdfmetrics.registerFontFamily('PaperSong',normal='PaperSong',bold='PaperHei',italic='PaperSong',boldItalic='PaperHei')
INK=colors.HexColor('#18283B'); ACCENT=colors.HexColor('#315A78'); RULE=colors.HexColor('#D9E1E8')
WIDTH=A4[0]-92


def inline(text):
    text=escape(text)
    text=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',lambda m:f'<link href="{m[2]}" color="#315A78">{m[1]}</link>',text)
    text=re.sub(r'`([^`]+)`',r'<font color="#315A78">\1</font>',text)
    text=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',text)
    return text


styles={
 'title':ParagraphStyle('Title',fontName='PaperHei',fontSize=21,leading=29,textColor=INK,spaceAfter=18),
 'body':ParagraphStyle('Body',fontName='PaperSong',fontSize=10.5,leading=17,wordWrap='CJK',splitLongWords=True,textColor=INK,spaceAfter=8,allowWidows=0,allowOrphans=0),
 'h1':ParagraphStyle('H1',fontName='PaperHei',fontSize=15,leading=22,textColor=INK,spaceBefore=17,spaceAfter=10,keepWithNext=True),
 'h2':ParagraphStyle('H2',fontName='PaperHei',fontSize=11.8,leading=19,textColor=ACCENT,spaceBefore=12,spaceAfter=7,keepWithNext=True),
 'cell':ParagraphStyle('Cell',fontName='PaperSong',fontSize=8.8,leading=13.4,wordWrap='CJK',splitLongWords=True,textColor=INK),
 'headcell':ParagraphStyle('HeadCell',fontName='PaperHei',fontSize=8.8,leading=13.4,wordWrap='CJK',textColor=colors.white),
 'caption':ParagraphStyle('Caption',fontName='PaperSong',fontSize=9,leading=14,textColor=ACCENT,alignment=TA_CENTER,spaceAfter=10),
 'ref':ParagraphStyle('Reference',fontName='PaperSong',fontSize=8.7,leading=13.5,wordWrap='CJK',splitLongWords=True,textColor=INK,spaceAfter=7),
 'code':ParagraphStyle('Code',fontName='PaperSong',fontSize=9.1,leading=14.2,wordWrap='CJK',backColor=colors.HexColor('#F3F6F8'),borderPadding=8,spaceBefore=4,spaceAfter=10),
}


class Figure(Flowable):
    def __init__(self,kind):
        super().__init__();self.kind=kind;self.width=WIDTH;self.height=300 if kind=='architecture' else 286
    def wrap(self,availWidth,availHeight):return self.width,self.height
    def draw(self):
        c=self.canv;scale=self.width/500;c.saveState();c.scale(scale,scale)
        boxes,arrows=figure_spec(self.kind)
        for x,y,w,h,title,detail in boxes:
            c.setFillColor(colors.HexColor('#F1F5F8'));c.setStrokeColor(RULE);c.roundRect(x,y,w,h,5,fill=1,stroke=1)
            p=Paragraph(f'<b>{escape(title)}</b><br/>{escape(detail)}',ParagraphStyle('FigureText',parent=styles['cell'],alignment=TA_CENTER,fontSize=9.4,leading=14))
            _,ph=p.wrap(w-14,h);p.drawOn(c,x+7,y+(h-ph)/2)
        c.setStrokeColor(ACCENT);c.setFillColor(ACCENT);c.setLineWidth(.85)
        for x1,y1,x2,y2,label in arrows:
            c.line(x1,y1,x2,y2)
            import math
            angle=math.atan2(y2-y1,x2-x1);size=4
            path=c.beginPath();path.moveTo(x2,y2)
            path.lineTo(x2-size*math.cos(angle-.5),y2-size*math.sin(angle-.5))
            path.lineTo(x2-size*math.cos(angle+.5),y2-size*math.sin(angle+.5));path.close();c.drawPath(path,fill=1,stroke=0)
            if label:c.setFont('PaperSong',8);c.drawString((x1+x2)/2+5,(y1+y2)/2+2,label)
        c.restoreState()


def figure_spec(kind):
    if kind=='architecture':
        boxes=[(0,253,500,36,'React 研究界面','会话 · 附件流向 · 资产看板 · 逐次授权'),
          (0,183,500,48,'TypeScript 宿主 / Express','项目上下文 · 任务与 SSE · 工具边界 · 用量审计'),
          (0,106,235,48,'Pi 原生会话','循环 · 压缩 · 重试 · steering / follow-up'),
          (265,106,235,48,'Python 领域服务','解析 · 来源校验 · 事务提交 · 金融公式'),
          (0,10,145,61,'模型与联网服务','用户配置的 API\n密钥留在宿主配置'),
          (171,10,158,61,'SQLite 与原件','披露 · 预测 · 观点\n检查点 · 成果版本'),
          (355,10,145,61,'Docker 沙箱','断网 · 输入只读\n不挂载主库或密钥')]
        arrows=[(250,253,250,231,'HTTP / SSE'),(117,183,117,154,'SDK'),(382,183,382,154,'MCP stdio'),(80,106,73,71,''),(345,106,250,71,''),(423,106,427,71,'')]
    else:
        boxes=[(18,230,464,44,'1. 原始资料与证据','PDF / 表格 / 页码 / 原格 / 源哈希'),
          (18,174,222,43,'2. 模型制定 Python 规则','理解表头、期间、主体、单位'),
          (260,174,222,43,'3. 沙箱生成候选映射','输出字段与坐标，不重写原值'),
          (18,111,464,47,'4. 宿主重读原格并校验','数值区间 · 单位 · 维度 · 覆盖 · 冲突'),
          (18,51,464,44,'5. 模型语义复核与逐表意见','检查异常；无法确定则保留待核验'),
          (18,0,464,37,'6. 事务提交、历史和检查点','当前批次可恢复；下一批继续原生循环')]
        arrows=[(125,230,125,217,''),(240,195,260,195,''),(370,174,370,158,''),(250,111,250,95,''),(250,51,250,37,'')]
    return boxes,arrows


def write_svg(kind):
    boxes,arrows=figure_spec(kind);height=300 if kind=='architecture' else 286
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="{height*2}" viewBox="0 0 500 {height}">',
      '<defs><marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#315A78"/></marker></defs>',
      '<rect width="100%" height="100%" fill="white"/>']
    for x,y,w,h,title,detail in boxes:
        top=height-y-h
        out.append(f'<rect x="{x}" y="{top}" width="{w}" height="{h}" rx="5" fill="#F1F5F8" stroke="#D9E1E8"/>')
        out.append(f'<text x="{x+w/2}" y="{top+h/2-4}" text-anchor="middle" font-family="SimSun,serif" font-size="10" fill="#18283B"><tspan font-weight="bold">{escape(title)}</tspan><tspan x="{x+w/2}" dy="15" font-size="8.5">{escape(detail.replace(chr(10)," · "))}</tspan></text>')
    for x1,y1,x2,y2,label in arrows:
        out.append(f'<line x1="{x1}" y1="{height-y1}" x2="{x2}" y2="{height-y2}" stroke="#315A78" marker-end="url(#arrow)"/>')
        if label:out.append(f'<text x="{(x1+x2)/2+5}" y="{height-(y1+y2)/2}" font-family="sans-serif" font-size="8" fill="#315A78">{escape(label)}</text>')
    out.append('</svg>');(HERE/(kind+'.svg' if kind=='architecture' else 'cleaning-flow.svg')).write_text('\n'.join(out),encoding='utf-8')


class PaperDoc(BaseDocTemplate):
    def __init__(self,filename):
        super().__init__(filename,pagesize=A4,leftMargin=46,rightMargin=46,topMargin=49,bottomMargin=44,title='从财报问答到证据驱动的金融研究 Agent：设计、实现与工程演进',author='Finance Agent project',subject='Engineering case study, application v0.2.0')
        self.addPageTemplates(PageTemplate(id='paper',frames=[Frame(self.leftMargin,self.bottomMargin,self.width,self.height,id='body',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=self.decorate))
    def decorate(self,c,doc):
        c.saveState();c.setFont('PaperSong',8);c.setFillColor(ACCENT)
        c.drawString(46,A4[1]-29,'Finance Agent  ·  v0.2.0  ·  技术论文')
        c.drawRightString(A4[0]-46,A4[1]-29,'2026-10-05')
        c.setStrokeColor(RULE);c.line(46,A4[1]-36,A4[0]-46,A4[1]-36)
        c.drawCentredString(A4[0]/2,25,str(doc.page));c.restoreState()
    def afterFlowable(self,flowable):
        if isinstance(flowable,Paragraph) and flowable.style.name=='H1':
            label=flowable.getPlainText();key='section-'+str(self.seq.nextf('heading'))
            self.canv.bookmarkPage(key);self.canv.addOutlineEntry(label,key,level=0,closed=False)


def table(lines):
    rows=[]
    for line in lines:
        cols=[s.strip() for s in line.strip().strip('|').split('|')]
        if all(re.fullmatch(r':?-+:?',s) for s in cols):continue
        rows.append(cols)
    n=len(rows[0]);weights={3:[1.25,2.6,2.7],4:[1.15,2.1,2.1,2.25],5:[1.3,.8,1.4,1.5,2.0],6:[1.5,.6,1.55,.85,1.45,1.25]}.get(n,[1]*n)
    widths=[WIDTH*w/sum(weights) for w in weights]
    data=[[Paragraph(inline(cell),styles['headcell' if i==0 else 'cell']) for cell in row] for i,row in enumerate(rows)]
    t=LongTable(data,colWidths=widths,repeatRows=1,hAlign='LEFT',spaceBefore=5,spaceAfter=12)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),ACCENT),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F5F7F9')]),('LINEBELOW',(0,0),(-1,0),.6,ACCENT),('LINEBELOW',(0,1),(-1,-1),.3,RULE)]))
    return t


def build():
    text=MD.read_text(encoding='utf-8');lines=text.splitlines();story=[];i=0;references=False
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line.startswith('|'):
            chunk=[]
            while i<len(lines) and lines[i].lstrip().startswith('|'):chunk.append(lines[i]);i+=1
            story.append(table(chunk));continue
        if line.startswith('!['):
            match=re.fullmatch(r'!\[(.*?)\]\((.*?)\)',line)
            kind='architecture' if 'architecture' in match[2] else 'cleaning'
            block=[Spacer(1,5),Figure(kind),Paragraph(inline(match[1]),styles['caption'])]
            if story and isinstance(story[-1],Paragraph) and story[-1].style.name in {'H1','H2'}:
                block.insert(0,story.pop())
            story.append(KeepTogether(block));i+=1;continue
        if line.startswith('# '):story.append(Paragraph(inline(line[2:]),styles['title']));i+=1;continue
        if line.startswith('## '):
            if '参考文献' in line:references=True
            story.append(Paragraph(inline(line[3:]),styles['h1']));i+=1;continue
        if line.startswith('### '):story.append(Paragraph(inline(line[4:]),styles['h2']));i+=1;continue
        chunk=[line];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','![')):
            chunk.append(lines[i].strip());i+=1
        paragraph=' '.join(chunk)
        key='ref' if references else 'code' if paragraph.startswith('`') and paragraph.endswith('`') else 'body'
        story.append(Paragraph(inline(paragraph),styles[key]))
    doc=PaperDoc(str(PDF));doc.build(story)
    write_svg('architecture');write_svg('cleaning')
    names=[MD.name,PDF.name,'architecture.svg','cleaning-flow.svg']
    manifest={'version':'0.2.0','generated_at':datetime.now(timezone.utc).isoformat(),'pages':doc.page,'cjk_characters':len(re.findall(r'[\u4e00-\u9fff]',text)),'source_characters':len(text),'files':{name:{'sha256':hashlib.sha256((HERE/name).read_bytes()).hexdigest(),'bytes':(HERE/name).stat().st_size} for name in names},'visual_review':'pending'}
    (HERE/'paper-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'pdf':str(PDF),'pages':doc.page,'cjk_characters':manifest['cjk_characters']},ensure_ascii=False))


if __name__=='__main__':build()
