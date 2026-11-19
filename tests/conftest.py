import os, sys
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
for sub in ('modelling', 'twin', 'acquisition'):
    sys.path.insert(0, os.path.join(REPO, 'src', sub))
