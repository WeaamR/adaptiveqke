"""Verify archived inputs against the frozen repository manifest."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]

def verify():
    failures = []
    lines = (ROOT / 'ORIGINAL_SHA256SUMS').read_text().splitlines()
    for line in lines:
        expected, relative = line.split('  ', 1)
        path = ROOT / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append(relative)
    return len(lines), failures

if __name__ == '__main__':
    count, failures = verify()
    if failures:
        raise SystemExit('Integrity mismatch: ' + ', '.join(failures))
    print(f'{count} frozen core/data files match their archived SHA-256 fingerprints.')
