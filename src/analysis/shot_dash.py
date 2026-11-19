import os as _os, sys as _sys
REPO = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..'))
FIGP = _os.path.join(REPO, 'figures', 'paper') + '/'; RES = _os.path.join(REPO, 'data', 'processed', 'analysis'); _os.makedirs(RES, exist_ok=True)
DASH = 'file://' + _os.path.join(REPO, 'docs', 'index.html')
_sys.path.insert(0, _os.path.join(REPO, 'src', 'modelling'))
import asyncio
from playwright.async_api import async_playwright
from PIL import Image
D = FIGP
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={'width': 1400, 'height': 1000}, color_scheme='light', device_scale_factor=2)
        await pg.goto(DASH + '#twin')
        await pg.add_style_tag(content='.topbar{position:static!important}')
        await pg.evaluate("const e=document.querySelector('#in-n'); e.value=20000; e.dispatchEvent(new Event('input'))")
        await pg.click('#speed-seg button[data-s="10"]'); await pg.wait_for_timeout(4500)
        await pg.click('#btn-baseline'); await pg.select_option('#fault', 'erosion'); await pg.wait_for_timeout(2500)
        await pg.click('#speed-seg button[data-s="1"]'); await pg.wait_for_timeout(800)
        await (await pg.query_selector('#sim')).screenshot(path=D + '_sim.png')
        await (await pg.query_selector('#kpis')).screenshot(path=D + '_kpis.png')
        await (await pg.query_selector('.grid-main > .stack:nth-child(2) > .card:nth-child(2)')).screenshot(path=D + '_dev.png')
        await b.close()
    sim, kp, dv = (Image.open(D + f) for f in ('_sim.png', '_kpis.png', '_dev.png'))
    W = sim.width; gap = 30
    # bottom row: KPIs (left) and deviation card (right), same height
    h = max(kp.height, int(dv.height*0.75)); kp2 = kp.resize((int(kp.width*h/kp.height), h)); dv2 = dv.resize((int(dv.width*h/dv.height), h))
    row = Image.new('RGB', (kp2.width + gap + dv2.width, h), 'white'); row.paste(kp2, (0, 0)); row.paste(dv2, (kp2.width + gap, 0))
    row = row.resize((W, int(row.height*W/row.width)))
    out = Image.new('RGB', (W, sim.height + gap + row.height), 'white'); out.paste(sim, (0, 0)); out.paste(row, (0, sim.height + gap))
    out.save(D + 'fig10_dashboard.png', dpi=(300, 300)); print(out.size)
asyncio.run(main())
