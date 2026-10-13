"""Build one Chinese Markdown document as PDF; no implicit batch writes.

Example:
  D:/anaconda/python.exe submission/build_pdf.py submission/report/技术报告.md

Requires ReportLab and Pillow. Follows the embedded-font layout of
paper/v0.3.0/build_pdf.py, with an explicit input/output command line.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

from PIL import Image as PillowImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, KeepTogether, LongTable, PageBreak,
    PageTemplate, Paragraph, Spacer, TableStyle,
)

INK = colors.HexColor('#18283B')
BLUE = colors.HexColor('#315A78')
RULE = colors.HexColor('#D9E1E8')
WIDTH = A4[0] - 98


def inline(text: str) -> str:
    text = escape(text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                  r'<link href="\2" color="#315A78">\1</link>', text)
    text = re.sub(r'`([^`]+)`', r'<font color="#315A78">\1</font>', text)
    return re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)


def make_styles(font_size: float, leading: float) -> dict:
    base = dict(fontName='SubmissionSong', textColor=INK, wordWrap='CJK',
                splitLongWords=True)
    return {
        'title': ParagraphStyle('Title', **(base | {'fontName': 'SubmissionHei'}),
                                fontSize=25, leading=34, spaceAfter=22),
        'h1': ParagraphStyle('H1', **(base | {'fontName': 'SubmissionHei'}),
                             fontSize=15, leading=22, spaceBefore=7,
                             spaceAfter=14, keepWithNext=True),
        'h2': ParagraphStyle('H2', **(base | {'fontName': 'SubmissionHei', 'textColor': BLUE}),
                             fontSize=11.8, leading=19, spaceBefore=11,
                             spaceAfter=8, keepWithNext=True),
        'body': ParagraphStyle('Body', **base, fontSize=font_size, leading=leading,
                               spaceAfter=10, allowWidows=0, allowOrphans=0),
        'cell': ParagraphStyle('Cell', **base, fontSize=9.3, leading=14.5),
        'head': ParagraphStyle('Head', **(base | {'fontName': 'SubmissionHei', 'textColor': colors.white}),
                               fontSize=9.3, leading=14.5),
        'caption': ParagraphStyle('Caption', **(base | {'textColor': BLUE}),
                                  fontSize=9, leading=14, alignment=1, spaceAfter=10),
        'quote': ParagraphStyle('Quote', **base, fontSize=font_size, leading=leading,
                                leftIndent=12, rightIndent=12, spaceAfter=12,
                                backColor=colors.HexColor('#F3F6F8'), borderPadding=8),
        'code': ParagraphStyle('Code', **base, fontSize=9, leading=14,
                               backColor=colors.HexColor('#F3F6F8'), borderPadding=8,
                               spaceAfter=8),
    }


class Document(BaseDocTemplate):
    def __init__(self, output: Path, label: str, author: str):
        super().__init__(str(output), pagesize=A4, leftMargin=49, rightMargin=49,
                         topMargin=54, bottomMargin=47, title='Finance Agent · '+label,
                         author=author)
        self.label = label
        self.addPageTemplates(PageTemplate(
            id='body', frames=[Frame(49, 47, self.width, self.height,
                                    leftPadding=0, rightPadding=0,
                                    topPadding=0, bottomPadding=0)], onPage=self.decorate))

    def decorate(self, canvas, doc):
        canvas.saveState()
        canvas.setFont('SubmissionSong', 8)
        canvas.setFillColor(BLUE)
        canvas.drawString(49, A4[1]-29, 'Finance Agent  /  '+self.label)
        canvas.drawRightString(A4[0]-49, A4[1]-29, '2026 北京市大学生金融人工智能竞赛')
        canvas.setStrokeColor(RULE)
        canvas.line(49, A4[1]-37, A4[0]-49, A4[1]-37)
        canvas.drawRightString(A4[0]-49, 25, str(doc.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == 'H1':
            key = 'section-'+str(self.seq.nextf('section'))
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.getPlainText(), key, 0, False)


def table(lines: list[str], styles: dict):
    rows = []
    for line in lines:
        row = [v.strip().replace(r'\|', '|')
               for v in re.split(r'(?<!\\)\|', line.strip().strip('|'))]
        if all(re.fullmatch(r':?-+:?', v) for v in row):
            continue
        rows.append(row)
    columns = len(rows[0])
    if any(len(row) != columns for row in rows):
        raise ValueError('Markdown 表格各行列数不同：'+lines[0])
    weights = {2: [1, 4.2], 3: [1.25, 2.2, 2.1], 4: [1.25, 1.7, 1.7, 1.7],
               5: [1.3, 1.4, 1.6, 1.6, 1.5]}.get(columns, [1]*columns)
    if columns == 2 and '编号' in rows[0][0]:
        weights = [.55, 4.65]
    if rows[0][0] == '指标':
        weights = [1.6]+[1.25]*(columns-1)
    data = [[Paragraph(inline(value), styles['head' if i == 0 else 'cell'])
             for value in row] for i, row in enumerate(rows)]
    result = LongTable(data, colWidths=[WIDTH*w/sum(weights) for w in weights],
                       repeatRows=1, spaceBefore=5, spaceAfter=13, hAlign='LEFT')
    result.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BLUE), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F7F9')]),
        ('LINEBELOW', (0, 1), (-1, -1), .3, RULE),
    ]))
    return result


def build(source: Path, output: Path, label: str, author: str, styles: dict) -> dict:
    text = source.read_text(encoding='utf-8-sig')
    lines = text.splitlines()
    story = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if line == '<!-- pagebreak -->':
            story.append(PageBreak())
            continue
        if line.startswith('<!--'):
            continue
        if line.startswith('```'):
            code = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code.append(escape(lines[i]).replace(' ', '&#160;'))
                i += 1
            i += 1
            story.append(Paragraph('<br/>'.join(code), styles['code']))
            continue
        if line.startswith('|'):
            chunk = [line]
            while i < len(lines) and lines[i].lstrip().startswith('|'):
                chunk.append(lines[i]); i += 1
            story.append(table(chunk, styles))
            continue
        figure = re.fullmatch(r'!\[(.*?)\]\((.*?)\)', line)
        if figure:
            image_path = (source.parent / figure[2]).resolve()
            with PillowImage.open(image_path) as im:
                width, height = im.size
            scale = min(WIDTH/width, 325/height)
            story.append(KeepTogether([
                Image(str(image_path), width=width*scale, height=height*scale),
                Spacer(1, 5), Paragraph(inline(figure[1]), styles['caption']),
            ]))
            continue
        if line == '---':
            story.append(Spacer(1, 10))
            continue
        key = ('title' if line.startswith('# ') else 'h1' if line.startswith('## ')
               else 'h2' if line.startswith('### ') else 'quote' if line.startswith('>')
               else 'body')
        if key in ('title', 'h1', 'h2'):
            line = re.sub(r'^#+ ', '', line)
        elif key == 'quote':
            line = line.lstrip('> ').strip()
        elif line.startswith(('- ', '* ')):
            line = '• '+line[2:]
        story.append(Paragraph(inline(line), styles[key]))
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = Document(output, label, author)
    doc.build(story)
    return {'source': str(source), 'pdf': str(output), 'pages': doc.page,
            'source_sha256': sha256(source.read_bytes()).hexdigest(),
            'pdf_sha256': sha256(output.read_bytes()).hexdigest(),
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'renderer': 'ReportLab, A4, embedded Chinese fonts', 'visual_review': 'pending'}


def main():
    parser = argparse.ArgumentParser(description='只构建明确指定的一份 Markdown，不扫描或重建其他文档。')
    parser.add_argument('source', type=Path, help='输入 Markdown')
    parser.add_argument('-o', '--output', type=Path, help='输出 PDF，默认与输入同目录同名')
    parser.add_argument('--label', help='页眉标签，默认输入文件名')
    parser.add_argument('--author', default='【队伍】')
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/simsun.ttc'))
    parser.add_argument('--bold-font', type=Path, default=Path('C:/Windows/Fonts/simhei.ttf'))
    parser.add_argument('--font-size', type=float, default=11)
    parser.add_argument('--line-height', type=float, default=19)
    args = parser.parse_args()
    source = args.source.resolve()
    output = (args.output or source.with_suffix('.pdf')).resolve()
    if output == source:
        parser.error('输出不能覆盖输入 Markdown')
    pdfmetrics.registerFont(TTFont('SubmissionSong', str(args.font), subfontIndex=0))
    pdfmetrics.registerFont(TTFont('SubmissionHei', str(args.bold_font), subfontIndex=0))
    pdfmetrics.registerFontFamily('SubmissionSong', normal='SubmissionSong', bold='SubmissionHei',
                                 italic='SubmissionSong', boldItalic='SubmissionHei')
    record = build(source, output, args.label or source.stem, args.author,
                   make_styles(args.font_size, args.line_height))
    record['fonts'] = [str(args.font), str(args.bold_font)]
    output.with_suffix('.build.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
