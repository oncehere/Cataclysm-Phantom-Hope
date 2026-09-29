#!/usr/bin/env python3
"""Run the project's explicit Gemini fill with hidden key entry and safe progress.

Uses PO Keeper's single production backend, validation and resumable cache.
The transcript records request counts/status classes, never SDK error bodies.
"""

import argparse
from collections import Counter
import getpass
import json
import os
from pathlib import Path
import time

from pokeeper.gemini import fill, _google_transport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--adopt-existing', choices=['protect', 'reuse'])
    parser.add_argument('--retry-unknown', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    candidate = root / args.candidate
    if candidate.exists():
        parser.error('candidate already exists; use a fresh review directory')
    config = root / 'project.toml'
    model = __import__('tomllib').loads(config.read_text())['gemini']['model']
    if not os.environ.get('GEMINI_API_KEY'):
        os.environ['GEMINI_API_KEY'] = getpass.getpass('Gemini API key (hidden): ')
    attempts = []
    started = time.time()

    def send(model, prompt, timeout):
        row = {'request': len(attempts) + 1, 'entries': len(json.loads(prompt)['entries'])}
        attempts.append(row)
        print(json.dumps({**row, 'status': 'started'}), flush=True)
        before = time.time()
        try:
            result = _google_transport(model, prompt, timeout)
        except Exception as exc:
            row['status'] = type(exc).__name__
            code = getattr(exc, 'http_code', None)
            if code in (429, 503):
                row['http_code'] = code
            retry_after = getattr(exc, 'retry_after_seconds', None)
            if isinstance(retry_after, (int, float)) and 0 <= retry_after <= 60:
                row['retry_after_seconds'] = retry_after
            raise
        else:
            row['status'] = 'response_received'
            return result
        finally:
            row['seconds'] = round(time.time() - before, 3)
            print(json.dumps(row), flush=True)

    result = {'model': model, 'requests': attempts, 'status': 'INTERRUPTED'}
    try:
        output = fill(config, candidate, root / '.pokeeper/gemini-cache.json',
                      adopt_existing=args.adopt_existing, transport=send,
                      retry_unknown=args.retry_unknown)
        report = json.loads((output / 'report.json').read_bytes())
        result.update(status='PASS' if not report['gaps'] else 'INCOMPLETE',
                      remaining_gaps=len(report['gaps']),
                      entry_results=dict(Counter(row['status'] for row in report['gemini'])),
                      candidate=str(output))
    finally:
        os.environ.pop('GEMINI_API_KEY', None)
        result['seconds'] = round(time.time() - started, 3)
        evidence = root / (args.candidate + '.run.json')
        evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'requests'}, ensure_ascii=False), flush=True)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
