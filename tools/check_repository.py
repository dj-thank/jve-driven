"""Check tracked text for accidental credentials and oversize generated assets."""
from __future__ import annotations
import re
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    patterns = [re.compile(rb'apikey_[A-Za-z0-9]{24,}_[A-Za-z0-9]{24,}'),
                re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
                re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]
    problems = []
    for name in filter(None, tracked):
        path = root / name
        if path.name.startswith('.env') and path.name != '.env.example':
            problems.append((name, 'environment file'))
        if path.stat().st_size > 1_000_000:
            problems.append((name, 'generated/large asset; store outside Git'))
        if any(pattern.search(path.read_bytes()) for pattern in patterns):
            problems.append((name, 'credential pattern (content redacted)'))
    if problems:
        for name, reason in problems:
            print(f'{name}: {reason}')
        return 1
    print(f'Checked {sum(bool(name) for name in tracked)} tracked files; no credential pattern or oversized asset')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
