"""Markdown consistency check for the PXD32D5-D4 document set.

Reports two things per file:
  table_issues  - line numbers of table blocks whose rows do not all have the same
                  pipe count (escaped pipes backslash-pipe are ignored, so cells
                  containing them do not produce false positives);
  fence_ok      - whether triple-backtick code fences pair up.

Run with no arguments: python _pxd_mdcheck.py
"""
import glob, os

here = os.path.dirname(os.path.abspath(__file__))
ESCAPED = chr(92) + '|'
for f in sorted(glob.glob(os.path.join(here, '*.md'))):
    lines = open(f, encoding='utf-8').read().split('\n')
    # count unescaped pipes only: strip backslash-pipe before counting
    rows = [(i, l.replace(ESCAPED, '').count('|'))
            for i, l in enumerate(lines, 1) if l.startswith('|')]
    blocks, cur, prev = [], [], None
    for i, c in rows:
        if prev is not None and i != prev + 1: blocks.append(cur); cur = []
        cur.append((i, c)); prev = i
    if cur: blocks.append(cur)
    bad = [b[0][0] for b in blocks if len({c for _, c in b}) > 1]
    fences = sum(1 for l in lines if l.startswith('```'))
    print(os.path.basename(f), 'table_issues', bad, 'fence_ok', fences % 2 == 0)
