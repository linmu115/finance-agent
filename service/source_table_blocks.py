"""Source-bounded nonrecurring-profit tables and their headerless continuations."""
import re
from .normalization import compact


def table_prefix(page, table):
    """Text above this physical table; never take a heading printed below it."""
    if table.get('bbox') and page.get('words'):
        lines={}
        for word in page['words']:
            if word['bbox'][3]<=table['bbox'][1]+1:
                lines.setdefault(round(word['bbox'][1]/3),[]).append(word)
        return '\n'.join(' '.join(w['text'] for w in sorted(ws,key=lambda w:w['bbox'][0])) for _,ws in sorted(lines.items()))
    text=page['text']
    # The first label can be a substring of the chapter title (e.g. 母公司 +
    # 非经常性损益项目); using it would cut off the very scope evidence needed.
    cells=table['rows'][0][1:]+[c for row in table['rows'][1:2] for c in row]
    anchors=[str(c).strip() for c in cells if len(str(c).strip())>3]
    positions=[text.find(a) for a in anchors if text.find(a)>=0]
    return text[:min(positions)] if positions else text


def nonrecurring_blocks(parsed):
    """Close at the total, a new header/section, width change or page gap.

    Return actual source tables, not facts. A group's scope evidence may be on
    its continuation (e.g. the minority-interest deduction before the total).
    """
    pages={p['page']:p for p in parsed['pages']}
    blocks=[];active=None;previous=None
    for table in sorted(parsed['tables'],key=lambda t:(t['page'],t['index'])):
        rows=table['rows']
        if not rows:continue
        first=compact(rows[0][0]);width=max(map(len,rows))
        possible_header='非经常性损益项目' in first or (first=='项目' and any('金额' in compact(c) for c in rows[0][1:]))
        if not active and not possible_header:
            previous=table
            continue
        prefix=table_prefix(pages[table['page']],table)
        headings=[line for line in prefix.splitlines() if re.search(r'非经常性损益(?:项目|及金额|明细|情况)',compact(line))]
        starts='非经常性损益项目' in first or (first=='项目' and headings and any('金额' in compact(c) for c in rows[0][1:]))
        if starts:
            active={'header':rows[0],'tables':[],'heading':headings[-1] if headings else str(rows[0][0]),'width':width}
            blocks.append(active)
        elif active:
            local_prefix=prefix
            if previous['page']==table['page']:
                # Remove the preceding table/title when two tables share a page.
                prior_last=' '.join(str(c) for c in previous['rows'][-1])
                position=local_prefix.rfind(prior_last)
                if position>=0:local_prefix=local_prefix[position+len(prior_last):]
                elif previous.get('bbox') and pages[table['page']].get('words'):
                    local_prefix='\n'.join(w['text'] for w in pages[table['page']]['words']
                        if previous['bbox'][3]<=w['bbox'][1]<table['bbox'][1])
            new_header=first in {'项目','类别','指标','补充资料'} or any(re.search(r'20\d{2}年|本期金额|上期金额|期末余额|期初余额',compact(c)) for c in rows[0][1:])
            new_section=bool(re.search(r'(?m)^\s*(?:[一二三四五六七八九十]+[、．.]|\d+[、．.]|[（(][一二三四五六七八九十\d]+[）)])\s*\S',local_prefix))
            if table['page']-previous['page']>1 or width!=active['width'] or new_header or new_section:
                active=None
        if active:
            active['tables'].append(table)
            if any(compact(row[0]) in {'合计','非经常性损益合计'} for row in rows):active=None
        previous=table
    return blocks


def block_scope(block):
    title=block['heading']
    if '母公司' in compact(title):return {'scope':'parent','quote':title}
    if '合并' in compact(title):return {'scope':'consolidated','quote':title}
    for table in block['tables']:
        for row in table['rows']:
            label=compact(row[0])
            if re.search(r'少数股东(?:权益|损益|影响)|归属于(?:上市公司股东|母公司(?:股东|所有者))',label):
                return {'scope':'consolidated','quote':title+'\n'+str(row[0]),'evidence_table':table['index']}
    return None


def nonrecurring_block(parsed, table):
    return next((b for b in nonrecurring_blocks(parsed) if any(t['index']==table['index'] for t in b['tables'])),None)
