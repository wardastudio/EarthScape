import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import app

rules = sorted([(r.rule, ','.join(sorted(r.methods))) for r in app.url_map.iter_rules()])
for rule, methods in rules:
    print(rule, methods)
print('\nregistered blueprints:')
for name, bp in app.blueprints.items():
    print(name, '->', getattr(bp, 'url_prefix', None))
