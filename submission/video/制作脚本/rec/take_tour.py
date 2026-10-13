"""Take 1: workspace tour — home, attachments, asset dashboard, source jump, saved models."""
import sys
from pathlib import Path

from recorder import BASE, Recorder, S

KEEP = ['c1bdf526-61f4-469f-a8d8-5087c840dddc', '03ccda64-164e-44ab-8c24-4337abb36a4e',
        'f8461957-682f-4018-a18e-f0fe82f315a5']
out = Path(sys.argv[1] if len(sys.argv) > 1 else 'takes/tour')


def select_by_current(page, current):
    """Return the <select> whose selected option text contains `current`."""
    idx = page.evaluate("""(t) => [...document.querySelectorAll('select')]
        .findIndex(s => (s.selectedOptions[0]?.textContent || '').includes(t))""", current)
    return page.locator('select').nth(idx)


with Recorder(out, keep_conversations=KEEP) as r:
    p = r.page
    p.goto(BASE, wait_until='networkidle')
    r.wait(1.0)
    r.start()
    r.mark('home')
    p.mouse.move(760 * S, 430 * S, steps=1)
    r.wait(2.2)

    r.mark('attachments')
    r.click(p.get_by_text('附件看板').first)
    r.wait(2.0)
    r.move_to(p.get_by_text('伊利股份2024年年度报告.pdf').first, steps=34)
    r.wait(1.6)
    r.move_to(p.get_by_text('财务事实 5428').first, steps=24)
    r.wait(2.0)

    r.mark('dashboard')
    r.click(p.get_by_text('资产看板').first)
    r.wait(2.0)
    sel = p.locator('select').first
    r.click(sel)
    label = [o for o in sel.locator('option').all_inner_texts() if '内蒙古伊利' in o][0]
    sel.select_option(label=label)
    p.keyboard.press('Escape')
    r.wait(2.4)
    r.mark('dashboard_overview')
    r.wait(1.2)

    r.mark('financials')
    r.click(p.get_by_text('财务与经营', exact=True).first)
    r.wait(1.6)
    r.click(p.get_by_text('现金流量表', exact=True).first)
    r.wait(1.8)
    r.scroll(420 * S, x=1100 * S, y=600 * S)
    r.wait(1.0)
    idx = p.evaluate("""() => [...document.querySelectorAll('select')].findIndex(s => s.options.length > 50 &&
        [...s.options].some(o => o.textContent.trim() === '经营活动产生的现金流量净额'))""")
    metric = p.locator('select').nth(idx)
    r.click(metric)
    values = p.evaluate("""(i) => [...document.querySelectorAll('select')[i].options]
        .filter(o => o.textContent.trim() === '经营活动产生的现金流量净额').map(o => o.value)""", idx)
    metric.select_option(value=values[0])
    p.keyboard.press('Escape')
    r.wait(2.2)
    p.screenshot(path=str(out / 'probe_chart.png'))
    r.mark('chart')
    r.scroll(460 * S, x=1100 * S, y=600 * S)
    r.wait(1.5)
    p.screenshot(path=str(out / 'probe_detail.png'))
    src = p.get_by_text('原文', exact=True)
    print('原文 links:', src.count())
    if src.count():
        r.mark('source_jump')
        r.click(src.first)
        r.wait(3.5)
        p.screenshot(path=str(out / 'probe_source.png'))
    r.mark('models')
    r.click(p.locator('button[aria-label="关闭附件流向"]').first)
    r.wait(1.0)
    p.mouse.move(1000 * S, 400 * S)
    for _ in range(20):
        p.mouse.wheel(0, -2000)
    r.wait(1.2)
    r.click(p.get_by_text('模型与成果', exact=True).first)
    r.wait(2.0)
    model = p.get_by_text('伊利股份FCFF DCF初建').first
    if model.count():
        r.click(model)
        r.wait(3.0)
        p.screenshot(path=str(out / 'probe_model.png'))
        r.scroll(420 * S, x=1100 * S, y=600 * S)
        r.wait(2.5)
        p.screenshot(path=str(out / 'probe_model2.png'))
    r.mark('tour_end')
    r.wait(1.0)
