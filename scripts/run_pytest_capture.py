import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
print('ROOT', ROOT)
proc = subprocess.run([sys.executable, '-m', 'pytest', '-rA'], cwd=str(ROOT), capture_output=True, text=True)
print(proc.stdout)
print(proc.stderr, file=sys.stderr)
sys.exit(proc.returncode)
