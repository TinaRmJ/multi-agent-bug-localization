# Extra Colab cells added on 2026-11-10 to thesis/level2_baseline.ipynb
# Run order in a fresh Colab session: Cell 1 (with GT_PATH = ground_truth_v2.csv), Cell 3, Cell 4, Cell 5
# (Cell 5 prints "0 bugs to run" once run1 is complete), then any of the cells below.

# =====================================================================
# === Cell 7: inspect the missed bugs (input + model answer + ground truth) ===
import json, csv

MISSED = [('Lang', 9), ('Lang', 10), ('Math', 7), ('Math', 18)]

gt = {}
with open(GT_PATH) as f:
    for r in csv.DictReader(f):
        gt.setdefault((r['project'], int(r['bug_id'])), []).append(
            f"{r['file'].rsplit('/', 1)[-1]} :: {r['method']} (line {r['changed_line']})")

answers = {}
with open(RAW_PATH) as f:
    for line in f:
        a = json.loads(line)
        answers[(a['project'], a['bug_id'], a['step'])] = a['answer']

for project, bug_id in MISSED:
    inp = load_input(project, bug_id)
    print('=' * 80)
    print(f'{project}-{bug_id}')
    print('TEST:', inp['test'])
    print('TRACE (first 600 chars):\n', inp['trace'][:600])
    print('GROUND TRUTH:')
    for g in gt[(project, bug_id)]:
        print('   ', g)
    print('STEP 1 (files):', answers.get((project, bug_id, 1), '')[:400])
    print('STEP 2 (methods):', answers.get((project, bug_id, 2), '')[:800])

# =====================================================================
# === Cell 8: show the real developer patches of selected bugs ===
# Defects4J stores each patch as <id>.src.patch (it goes from FIXED to BUGGY version,
# so '-' lines are the fixed code and '+' lines are the buggy code).
import os, subprocess

D4J = '/content/defects4j'
if not os.path.exists(D4J):
    subprocess.run(['git', 'clone', '-q', 'https://github.com/rjust/defects4j', D4J], check=True)

for project, bug_id in [('Lang', 8), ('Lang', 9), ('Lang', 10), ('Math', 7), ('Math', 18)]:
    path = f'{D4J}/framework/projects/{project}/patches/{bug_id}.src.patch'
    print('=' * 80)
    print(f'{project}-{bug_id}')
    print(open(path).read()[:2500])

# =====================================================================
# === Cell 9: rebuild the ground truth from the real developer patches (all 40 bugs) ===
# Why: the old ground truth was built with a line-based heuristic that missed
# constructors without modifiers and methods of nested classes (Lang-8).
# This version parses the Java code properly and maps every changed line of the
# patch to the method (or constructor) that really contains it.
# Nothing is sent to the model: this only re-checks the answer key.
import subprocess, sys
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'javalang'], check=True)

import csv, gzip, json, os, re
from collections import defaultdict
import javalang

D4J = '/content/defects4j'
if not os.path.exists(D4J):
    subprocess.run(['git', 'clone', '-q', 'https://github.com/rjust/defects4j', D4J], check=True)

NEW_GT_PATH = BASE / 'ground_truth_v2.csv'


def patch_lines(project, bug_id):
    """Return ({file: [(kind, buggy_line)]}, [(file, line, text)] for sanity checks).
    Defects4J patches go FIXED -> BUGGY, so the '+' side is the buggy version."""
    path = f'{D4J}/framework/projects/{project}/patches/{bug_id}.src.patch'
    text = open(path, encoding='utf-8', errors='replace').read()
    changes, checks = defaultdict(list), []
    cur, new, in_hunk = None, 0, False
    for line in text.split('\n'):
        if line.startswith('diff '):
            in_hunk = False
            continue
        if line.startswith('+++ '):
            cur = line[4:].split('\t')[0].strip()
            cur = cur[2:] if cur.startswith('b/') else cur
            continue
        if line.startswith('--- '):
            continue
        m = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
        if m:
            new, in_hunk = int(m.group(1)), True
            continue
        if not in_hunk or cur is None:
            continue
        tag = line[:1]
        if tag == '+':
            changes[cur].append(('add', new))
            checks.append((cur, new, line[1:]))
            new += 1
        elif tag == '-':
            changes[cur].append(('del', new))   # deleted code sat just before buggy line `new`
        elif tag in (' ', ''):
            new += 1
        # '\' ("No newline at end of file") is ignored
    return changes, checks


def skip_literal_or_comment(src, i):
    """If a comment or string/char literal starts at i, return the index after it, else None."""
    if src.startswith('//', i):
        j = src.find('\n', i)
        return len(src) if j < 0 else j
    if src.startswith('/*', i):
        j = src.find('*/', i + 2)
        return len(src) if j < 0 else j + 2
    if src[i] in '"\'':
        q, j = src[i], i + 1
        while j < len(src) and src[j] != q:
            j += 2 if src[j] == '\\' else 1
        return j + 1
    return None


def match_close(src, i, open_ch, close_ch):
    """Index of the bracket that closes the one at src[i] (skips comments and strings)."""
    depth = 0
    while i < len(src):
        nxt = skip_literal_or_comment(src, i)
        if nxt is not None:
            i = nxt
            continue
        if src[i] == open_ch:
            depth += 1
        elif src[i] == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(src) - 1


def method_spans(src):
    """List of (first_line, last_line, name) for every method/constructor with a body.
    Methods of anonymous classes are skipped (their enclosing method counts instead)."""
    tree = javalang.parse.parse(src)
    line_start = [0] + [i + 1 for i, ch in enumerate(src) if ch == '\n']
    spans = []
    for kind in (javalang.tree.MethodDeclaration, javalang.tree.ConstructorDeclaration):
        for path, node in tree.filter(kind):
            if node.position is None or getattr(node, 'body', None) is None:
                continue
            if any(isinstance(p, javalang.tree.ClassCreator) for p in path):
                continue
            pos = line_start[node.position.line - 1] + node.position.column - 1
            m = re.compile(r'\b' + re.escape(node.name) + r'\s*\(').search(src, pos)
            if not m:
                continue
            close_paren = match_close(src, m.end() - 1, '(', ')')
            brace = src.find('{', close_paren)
            end = match_close(src, brace, '{', '}')
            spans.append((node.position.line, src.count('\n', 0, end) + 1, node.name))
    return spans


def enclosing(spans, line):
    """Innermost method containing the line, or None."""
    inside = [s for s in spans if s[0] <= line <= s[1]]
    return max(inside, key=lambda s: s[0])[2] if inside else None


def find_key(files, patch_path):
    if patch_path in files:
        return patch_path
    for k in files:
        if k.endswith(patch_path) or patch_path.endswith(k):
            return k
    return None


# Old ground truth, for comparison
old = defaultdict(set)
with open(GT_PATH) as f:
    for r in csv.DictReader(f):
        old[(r['project'], int(r['bug_id']))].add((r['file'].rsplit('/', 1)[-1], r['method']))

new_rows, report, problems = [], [], []
for project, bug_id in BUGS:
    snap = load_snapshot(project, bug_id)
    changes, checks = patch_lines(project, bug_id)

    # Sanity check: every '+' line of the patch must exist at that line in the BUGGY snapshot
    bad = 0
    for pfile, ln, txt in checks:
        key = find_key(snap['files'], pfile)
        lines = snap['files'][key].split('\n') if key else []
        if not key or ln > len(lines) or lines[ln - 1].strip() != txt.strip():
            bad += 1
    if bad:
        problems.append(f'{project}-{bug_id}: {bad} patch lines do not match the buggy source')

    found = set()
    for pfile, items in changes.items():
        key = find_key(snap['files'], pfile)
        if key is None:
            problems.append(f'{project}-{bug_id}: file not in snapshot: {pfile}')
            continue
        try:
            spans = method_spans(snap['files'][key])
        except Exception as e:
            problems.append(f'{project}-{bug_id}: parse error in {pfile}: {e}')
            continue
        for kind, ln in items:
            meth = enclosing(spans, ln)
            if meth is None and kind == 'del':
                meth = enclosing(spans, ln - 1)
            new_rows.append({'project': project, 'bug_id': bug_id, 'file': key,
                             'method': meth or '', 'changed_line': ln})
            if meth:
                found.add((key.rsplit('/', 1)[-1], meth))

    if not found:
        problems.append(f'{project}-{bug_id}: NO change inside a method (field-only fix?)')
    if found != old[(project, bug_id)]:
        report.append(f'{project}-{bug_id}:\n    old: {sorted(old[(project, bug_id)])}\n    new: {sorted(found)}')

# Remove exact duplicates and save
seen, final = set(), []
for r in new_rows:
    k = (r['project'], r['bug_id'], r['file'], r['method'], r['changed_line'])
    if k not in seen:
        seen.add(k)
        final.append(r)
with open(NEW_GT_PATH, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['project', 'bug_id', 'file', 'method', 'changed_line'])
    w.writeheader()
    w.writerows(final)

print(f'saved {len(final)} rows to {NEW_GT_PATH.name}')
print(f'\nBUGS WHOSE FAULTY METHODS CHANGED ({len(report)}):')
print('\n'.join(report) or '  none')
print(f'\nPROBLEMS ({len(problems)}):')
print('\n'.join(problems) or '  none')

# =====================================================================
# === Cell 10: control experiment - NO source code, NO file list ===
# The model only sees the failing test, its code and the stack trace.
# If it still names the right method, it is guessing from memory of the public
# benchmark (or from names in the stack trace), not from reading the code.
# Uses call_model / parse_json (Cell 4), BUGS (Cell 3), load_input (Cell 5).
import csv, json, time
from collections import defaultdict

CTRL_RUN = 'control_run1'
CTRL_RES = OUT_DIR / f'control_results_{CTRL_RUN}.csv'
CTRL_RAW = OUT_DIR / f'raw_answers_{CTRL_RUN}.jsonl'
CTRL_USAGE = OUT_DIR / f'usage_log_{CTRL_RUN}.jsonl'

PROMPT_CONTROL = """You are an expert Java debugger. A test fails in a Java project.
You do NOT have access to the source code. Use only the information below.

Failing test: {test}

Test code:
{test_code}

Error and stack trace:
{trace}

Which methods of the project (not the test) most likely contain the bug?
Give at most {k} methods, most likely first.
For a constructor, use the class name as the method name.
Answer ONLY with JSON: {{"methods": [{{"file": "Name.java", "method": "methodName"}}]}}
"""


def ctrl_done():
    if not CTRL_RES.exists():
        return set()
    with open(CTRL_RES) as f:
        return {(r['project'], int(r['bug_id'])) for r in csv.DictReader(f) if r['status'] == 'ok'}


def ctrl_write(row):
    new = not CTRL_RES.exists()
    with open(CTRL_RES, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new:
            w.writeheader()
        w.writerow(row)


def jsonl(path, obj):
    with open(path, 'a') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


# ---------- run ----------
todo = [b for b in BUGS if b not in ctrl_done()]
print(f'{len(todo)} bugs to run')
for project, bug_id in todo:
    inp = load_input(project, bug_id)
    row = {'project': project, 'bug_id': bug_id, 'status': 'ok', 'methods': '', 'error': '', 'latency_s': 0}
    t0 = time.time()
    try:
        prompt = PROMPT_CONTROL.format(test=inp['test'], test_code=inp.get('test_code', ''),
                                       trace=inp['trace'], k=MAX_METHODS)
        text, usage = call_model(prompt)
        jsonl(CTRL_USAGE, {'project': project, 'bug_id': bug_id, **usage})
        jsonl(CTRL_RAW, {'project': project, 'bug_id': bug_id, 'answer': text})
        row['methods'] = json.dumps(parse_json(text).get('methods', [])[:MAX_METHODS], ensure_ascii=False)
    except Exception as e:
        # API or parsing errors are NOT counted as model misses
        row['status'] = 'error'
        row['error'] = str(e)[:300]
    row['latency_s'] = round(time.time() - t0, 1)
    ctrl_write(row)
    print(f"{project}-{bug_id}: {row['status']} {row['methods'][:120]}")


# ---------- summary (same matching rule as Cell 6) ----------
def norm_file(f):
    return str(f).strip().rsplit('/', 1)[-1].replace('.java', '')


def norm_method(m):
    m = str(m).strip().split('(')[0]
    return m.rsplit('.', 1)[-1].strip()


truth = defaultdict(set)
with open(GT_PATH) as f:
    for r in csv.DictReader(f):
        if r['method']:
            truth[(r['project'], int(r['bug_id']))].add((norm_file(r['file']), norm_method(r['method'])))

ranks, errors = {}, 0
with open(CTRL_RES) as f:
    for r in csv.DictReader(f):
        key = (r['project'], int(r['bug_id']))
        if r['status'] != 'ok':
            errors += 1
            continue
        rank = None
        for i, m in enumerate(json.loads(r['methods']), 1):
            if (norm_file(m.get('file', '')), norm_method(m.get('method', ''))) in truth[key]:
                rank = i
                break
        ranks[key] = rank   # last ok answer wins

n = len(ranks)
print(f'\nCONTROL (no code) - bugs evaluated: {n} (errors: {errors})')
for k in (1, 3, 5):
    hit = sum(1 for r in ranks.values() if r is not None and r <= k)
    print(f'Top-{k}: {hit}/{n} = {hit / n:.1%}')
print(f'MRR: {sum(1 / r for r in ranks.values() if r) / n:.3f}')
print('Found WITHOUT code:', ', '.join(f'{p}-{b}' for (p, b), r in ranks.items() if r == 1) or 'none')
