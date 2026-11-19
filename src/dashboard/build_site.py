"""Assemble the single-file digital-twin site: styles + markup + embedded ROM/map JSON + scripts."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__)); ROM_OUT = os.path.join(HERE, '..', '..', 'models', 'pod_rom'); WEB = os.path.join(HERE, 'web'); DOCS = os.path.join(HERE, '..', '..', 'docs')
css = open(os.path.join(WEB, 'style.css')).read()
body = open(os.path.join(WEB, 'body.html')).read()
rom = json.load(open(os.path.join(ROM_OUT, 'rom_pod.json')))
mp = json.load(open(os.path.join(ROM_OUT, 'map.json')))
js = '\n'.join(open(os.path.join(WEB, f)).read() for f in ('core.js', 'draw.js', 'ui.js'))
def rnd(o):
    if isinstance(o, float): return float('%.8g' % o)
    if isinstance(o, list): return [rnd(v) for v in o]
    if isinstance(o, dict): return {k: rnd(v) for k, v in o.items()}
    return o
rom_s = json.dumps(rnd(rom), separators=(',', ':')).replace('</', '<\\/')
map_s = json.dumps(mp, separators=(',', ':'))
html = f'''<title>Four-Stage Compressor Twin</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..125,500..800&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
{css}
</style>
{body}
<script type="application/json" id="rom-data">{rom_s}</script>
<script type="application/json" id="map-data">{map_s}</script>
<script>
{js}
</script>
'''
os.makedirs(os.path.join(HERE, 'dist'), exist_ok=True)
out = os.path.join(HERE, 'dist', 'artifact.html'); open(out, 'w').write(html)   # body-only version used for the claude.ai artifact
# full page for GitHub Pages (docs/index.html) and for headless tests
open(os.path.join(DOCS, 'index.html'), 'w').write('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"></head><body>' + html + '</body></html>')
print('docs/index.html', len(html)//1024, 'KB')
