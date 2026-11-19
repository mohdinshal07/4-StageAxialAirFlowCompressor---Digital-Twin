"""Compact compressor map for the web dashboard (models/pod_rom/map.json), from data/processed speed lines.
Keeps every 3rd point of each speed line (stable flag 's': 1 = right of surge) and the surge line."""
import json, os, pandas as pd
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
d = pd.read_csv(os.path.join(REPO, 'data', 'processed', 'compressor_map_speedlines.csv'))
su = pd.read_csv(os.path.join(REPO, 'data', 'processed', 'surge_line.csv'))
lines = []
for N, g in d.groupby('rpm'):
    g = g.iloc[::3]
    lines.append(dict(N=int(N), m=[round(v, 5) for v in g.mdot_kg_s], PR=[round(v, 5) for v in g.PR], s=[int(v) for v in g.stable]))
out = dict(lines=lines, surge=dict(N=[int(v) for v in su.rpm], m=[round(v, 5) for v in su.surge_mdot_kg_s], PR=[round(v, 5) for v in su.surge_PR]))
os.makedirs(os.path.join(REPO, 'models', 'pod_rom'), exist_ok=True)
json.dump(out, open(os.path.join(REPO, 'models', 'pod_rom', 'map.json'), 'w'))
print('map.json:', len(lines), 'speed lines')
