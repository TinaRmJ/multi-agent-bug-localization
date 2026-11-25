# Colab cells 11 and 12 (added 2026-11-12): new Defects4J bugs + memorization filter
# Paste each part as its own cell. Cell 11 needs Cells 1+2; Cell 12 needs Cells 1+4 and Cell 11 finished.

# === Cell 11: build inputs, code snapshots and answer keys for NEW Defects4J bugs ===
# Needs Cell 1 (Drive + settings) and Cell 2 (Java 11 + Defects4J) in this Colab session.
# For every bug the buggy version is checked out ONCE, then we save to Drive:
#   inputs/<P>_<id>.json        failing test name, stack trace, test method code
#   snapshots/<P>_<id>.json.gz  all main source files of the buggy version
#   new_bugs/<P>_<id>.json      answer key rows from the real patch + status
# Resumable: bugs already processed are skipped. Nothing is sent to the model here.
import subprocess, sys
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'javalang'], check=True)

import csv, gzip, json, os, re, shutil, pathlib, time
from collections import defaultdict, Counter
import javalang

D4J = '/content/defects4j'
assert os.path.exists(f'{D4J}/framework/bin/defects4j'), 'Run Cell 2 first (Defects4J install)'
os.environ['PATH'] = f'{D4J}/framework/bin:' + os.environ['PATH']

NEW_DIR = BASE / 'new_bugs'
NEW_DIR.mkdir(exist_ok=True)
NEW_GT = BASE / 'ground_truth_new.csv'

# Fixed selection rule, decided BEFORE any model run:
# the first N active bug ids of each project (Defects4J active-bugs list).
PROJECTS = {'Chart': 26, 'Closure': 40, 'Time': 26, 'Cli': 30, 'Compress': 30,
            'Jsoup': 30, 'Gson': 18, 'Csv': 16, 'JacksonCore': 26}
MAX_TRACE_CHARS = 8000   # very long traces are cut (same rule for every bug)


# ---------------------------------------------------------------- helpers
def active_ids(project):
    """Active (non-deprecated) bug ids of a project, sorted."""
    path = f'{D4J}/framework/projects/{project}/active-bugs.csv'
    with open(path) as f:
        return sorted(int(r['bug.id']) for r in csv.DictReader(f))


def export(work, prop):
    return subprocess.run(['defects4j', 'export', '-p', prop, '-w', work],
                          check=True, capture_output=True, text=True).stdout.strip()


def patch_lines(project, bug_id):
    """({file: [(kind, buggy_line)]}, [(file, line, text)]). Patches go FIXED -> BUGGY."""
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
            changes[cur].append(('del', new))
        elif tag in (' ', ''):
            new += 1
    return changes, checks


def skip_literal_or_comment(src, i):
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
    """(first_line, last_line, name) of every method/constructor with a body
    (methods of anonymous classes are skipped; their enclosing method counts)."""
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
    inside = [s for s in spans if s[0] <= line <= s[1]]
    return max(inside, key=lambda s: s[0])[2] if inside else None


def find_key(files, patch_path):
    if patch_path in files:
        return patch_path
    for k in files:
        if k.endswith(patch_path) or patch_path.endswith(k):
            return k
    return None


def first_trigger(project, bug_id):
    """Name and stack trace of the FIRST trigger (failing) test stored by Defects4J."""
    path = f'{D4J}/framework/projects/{project}/trigger_tests/{bug_id}'
    text = open(path, encoding='utf-8', errors='replace').read()
    blocks = [b for b in re.split(r'(?m)^(?=--- )', text) if b.startswith('--- ')]
    first = blocks[0].rstrip()
    test = first.split('\n', 1)[0][4:].strip()
    return test, first[:MAX_TRACE_CHARS]


def test_method_code(work, test_dir, test):
    """Source code of the failing test method ('' if it is inherited / not found)."""
    cls, _, meth = test.partition('::')
    path = pathlib.Path(work) / test_dir / (cls.split('$')[0].replace('.', '/') + '.java')
    if not path.exists():
        return ''
    src = path.read_text(encoding='utf-8', errors='replace')
    try:
        spans = method_spans(src)
    except Exception:
        return ''
    lines = src.split('\n')
    for s, e, name in spans:
        if name == meth:
            return '\n'.join(lines[s - 1:e])
    return ''


def answer_key(project, bug_id, files):
    """Answer key rows from the real patch, or (None, reason) if the bug must be excluded."""
    changes, checks = patch_lines(project, bug_id)
    for pfile, ln, txt in checks:
        key = find_key(files, pfile)
        lines = files[key].split('\n') if key else []
        if not key or ln > len(lines) or lines[ln - 1].strip() != txt.strip():
            return None, 'patch_mismatch'
    rows, has_method = [], False
    for pfile, items in changes.items():
        key = find_key(files, pfile)
        if key is None:
            return None, 'file_not_found'
        try:
            spans = method_spans(files[key])
        except Exception:
            return None, 'parse_error'
        for kind, ln in items:
            meth = enclosing(spans, ln)
            if meth is None and kind == 'del':
                meth = enclosing(spans, ln - 1)
            has_method = has_method or bool(meth)
            rows.append({'project': project, 'bug_id': bug_id, 'file': key,
                         'method': meth or '', 'changed_line': ln})
    if not has_method:
        return None, 'no_method_change'
    # drop exact duplicates
    uniq = {tuple(r.values()): r for r in rows}
    return list(uniq.values()), ''


def process(project, bug_id):
    meta_path = NEW_DIR / f'{project}_{bug_id}.json'
    if meta_path.exists():
        return json.loads(meta_path.read_text())['status']
    work = f'/content/work/{project}_{bug_id}'
    shutil.rmtree(work, ignore_errors=True)
    meta = {'project': project, 'bug_id': bug_id, 'status': 'ok', 'reason': '', 'gt': []}
    try:
        subprocess.run(['defects4j', 'checkout', '-p', project, '-v', f'{bug_id}b', '-w', work],
                       check=True, capture_output=True, text=True, timeout=1200)
        src_dir, test_dir = export(work, 'dir.src.classes'), export(work, 'dir.src.tests')
        root = pathlib.Path(work)
        files = {str(p.relative_to(root)): p.read_text(encoding='utf-8', errors='replace')
                 for p in sorted((root / src_dir).rglob('*.java'))}
        rows, reason = answer_key(project, bug_id, files)
        if rows is None:
            meta.update(status='excluded', reason=reason)
        else:
            test, trace = first_trigger(project, bug_id)
            code = test_method_code(work, test_dir, test)
            with gzip.open(SNAP_DIR / f'{project}_{bug_id}.json.gz', 'wt', encoding='utf-8') as f:
                json.dump({'project': project, 'bug_id': bug_id, 'src_dir': src_dir, 'files': files}, f)
            with open(INPUTS_DIR / f'{project}_{bug_id}.json', 'w') as f:
                json.dump({'test': test, 'trace': trace, 'test_code': code,
                           'test_code_found': bool(code), 'n_source_files': len(files)}, f)
            meta['gt'] = rows
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        # checkout/export problems are NOT saved, so the bug is retried next time
        err = getattr(e, 'stderr', '') or str(e)
        print(f'  {project}-{bug_id}: checkout ERROR (will retry next run): {str(err)[-200:]}')
        return 'error'
    finally:
        shutil.rmtree(work, ignore_errors=True)
    meta_path.write_text(json.dumps(meta))
    return meta['status']


# ---------------------------------------------------------------- run
INPUTS_DIR.mkdir(exist_ok=True)
todo = [(p, b) for p, n in PROJECTS.items() for b in active_ids(p)[:n]]
print(f'{len(todo)} new bugs selected')
t0 = time.time()
for i, (p, b) in enumerate(todo, 1):
    st = process(p, b)
    if i % 5 == 0 or st != 'ok':
        el = (time.time() - t0) / 60
        print(f'[{i}/{len(todo)}] {p}-{b}: {st}   ({el:.0f} min so far)')

# ---------------------------------------------------------------- summary + combined answer key
status, reasons, gt_rows = Counter(), Counter(), []
for p, b in todo:
    mp = NEW_DIR / f'{p}_{b}.json'
    if not mp.exists():
        status[(p, 'error')] += 1
        continue
    m = json.loads(mp.read_text())
    status[(p, m['status'])] += 1
    if m['status'] == 'excluded':
        reasons[m['reason']] += 1
    gt_rows.extend(m['gt'])
with open(NEW_GT, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['project', 'bug_id', 'file', 'method', 'changed_line'])
    w.writeheader()
    w.writerows(gt_rows)

print(f'\n{"project":<12}{"ok":>5}{"excluded":>10}{"error":>7}')
for p in PROJECTS:
    print(f'{p:<12}{status[(p, "ok")]:>5}{status[(p, "excluded")]:>10}{status[(p, "error")]:>7}')
print(f'{"TOTAL":<12}{sum(v for (p, s), v in status.items() if s == "ok"):>5}'
      f'{sum(v for (p, s), v in status.items() if s == "excluded"):>10}'
      f'{sum(v for (p, s), v in status.items() if s == "error"):>7}')
print('exclusion reasons:', dict(reasons) or 'none')
print(f'saved {len(gt_rows)} answer-key rows to {NEW_GT.name}')

# =====================================================================
# === Cell 12: no-code control on the NEW bugs + memorization filter ===
# Needs Cell 1 (settings), Cell 4 (Gemini client: call_model, parse_json) and Cell 11 finished.
# 1) Runs the SAME no-code control prompt as Cell 10 on every new bug (cheap: no source code).
# 2) Applies the memorization filter to ALL bugs (Lang/Math + new):
#    a bug is "hard" if the model does NOT name a correct method in its top 5 WITHOUT code.
# Resumable: bugs already answered are skipped.
import csv, json, time
from collections import defaultdict, Counter

assert 'call_model' in globals(), 'Run Cell 4 first (Gemini client)'

NEW_GT = BASE / 'ground_truth_new.csv'
CTRL_RES_OLD = OUT_DIR / 'control_results_control_run1.csv'   # Lang/Math, from Cell 10
CTRL_RES_NEW = OUT_DIR / 'control_results_new_run1.csv'
CTRL_RAW_NEW = OUT_DIR / 'raw_answers_control_new_run1.jsonl'
CTRL_USAGE_NEW = OUT_DIR / 'usage_log_control_new_run1.jsonl'
HARD_PATH = BASE / 'hard_bugs.csv'
GT_ALL = BASE / 'ground_truth_all.csv'
CTRL_TOKEN_BUDGET = 3_000_000   # safety cap on input tokens for this cell

# Exactly the prompt of Cell 10 (do not change it, so all bugs get the same control)
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


def read_bugs(path):
    seen, bugs = set(), []
    with open(path) as f:
        for r in csv.DictReader(f):
            k = (r['project'], int(r['bug_id']))
            if k not in seen:
                seen.add(k)
                bugs.append(k)
    return bugs


def done(path):
    if not path.exists():
        return set()
    with open(path) as f:
        return {(r['project'], int(r['bug_id'])) for r in csv.DictReader(f) if r['status'] == 'ok'}


def jsonl(path, obj):
    with open(path, 'a') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def used_tokens():
    if not CTRL_USAGE_NEW.exists():
        return 0
    with open(CTRL_USAGE_NEW) as f:
        return sum(json.loads(l)['input_tokens'] for l in f)


# ---------------------------------------------------------------- 1) control run on new bugs
new_bugs = read_bugs(NEW_GT)
todo = [b for b in new_bugs if b not in done(CTRL_RES_NEW)]
print(f'{len(new_bugs)} new bugs, {len(todo)} still to run')
for i, (project, bug_id) in enumerate(todo, 1):
    if used_tokens() > CTRL_TOKEN_BUDGET:
        print('TOKEN BUDGET REACHED, stopping.')
        break
    with open(INPUTS_DIR / f'{project}_{bug_id}.json') as f:
        inp = json.load(f)
    row = {'project': project, 'bug_id': bug_id, 'status': 'ok', 'methods': '', 'error': '', 'latency_s': 0}
    t0 = time.time()
    try:
        prompt = PROMPT_CONTROL.format(test=inp['test'], test_code=inp.get('test_code', ''),
                                       trace=inp['trace'], k=MAX_METHODS)
        text, usage = call_model(prompt)
        jsonl(CTRL_USAGE_NEW, {'project': project, 'bug_id': bug_id, **usage})
        jsonl(CTRL_RAW_NEW, {'project': project, 'bug_id': bug_id, 'answer': text})
        row['methods'] = json.dumps(parse_json(text).get('methods', [])[:MAX_METHODS], ensure_ascii=False)
    except Exception as e:
        # API or parsing errors are NOT counted as model misses
        row['status'], row['error'] = 'error', str(e)[:300]
    row['latency_s'] = round(time.time() - t0, 1)
    new_file = not CTRL_RES_NEW.exists()
    with open(CTRL_RES_NEW, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new_file:
            w.writeheader()
        w.writerow(row)
    if i % 10 == 0 or row['status'] != 'ok':
        print(f'[{i}/{len(todo)}] {project}-{bug_id}: {row["status"]} {row["error"][:100]}')


# ---------------------------------------------------------------- 2) memorization filter (all bugs)
def norm_file(f):
    return str(f).strip().rsplit('/', 1)[-1].replace('.java', '')


def norm_method(m):
    return str(m).strip().split('(')[0].rsplit('.', 1)[-1].strip()


# combined answer key = Lang/Math v2 + new projects
all_rows = []
for path in (GT_PATH, NEW_GT):
    with open(path) as f:
        all_rows.extend(csv.DictReader(f))
with open(GT_ALL, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['project', 'bug_id', 'file', 'method', 'changed_line'])
    w.writeheader()
    w.writerows(all_rows)

truth = defaultdict(set)
for r in all_rows:
    if r['method']:
        truth[(r['project'], int(r['bug_id']))].add((norm_file(r['file']), norm_method(r['method'])))

ranks = {}
for path in (CTRL_RES_OLD, CTRL_RES_NEW):
    if not path.exists():
        continue
    with open(path) as f:
        for r in csv.DictReader(f):
            if r['status'] != 'ok':
                continue
            key = (r['project'], int(r['bug_id']))
            rank = None
            for i, m in enumerate(json.loads(r['methods']), 1):
                if (norm_file(m.get('file', '')), norm_method(m.get('method', ''))) in truth[key]:
                    rank = i
                    break
            ranks[key] = rank

missing = [k for k in truth if k not in ranks]
hard = sorted(k for k, r in ranks.items() if r is None)   # not found in top 5 without code

with open(HARD_PATH, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['project', 'bug_id'])
    w.writerows(hard)

per = defaultdict(Counter)
for (p, b), r in ranks.items():
    per[p]['n'] += 1
    per[p]['top1'] += r == 1
    per[p]['top5'] += r is not None
    per[p]['hard'] += r is None
print(f'\nCONTROL WITHOUT CODE + FILTER')
print(f'{"project":<12}{"bugs":>6}{"Top-1":>8}{"Top-5":>8}{"hard":>6}')
for p, c in sorted(per.items()):
    print(f'{p:<12}{c["n"]:>6}{c["top1"] / c["n"]:>8.0%}{c["top5"] / c["n"]:>8.0%}{c["hard"]:>6}')
tot = sum((c for c in per.values()), Counter())
print(f'{"TOTAL":<12}{tot["n"]:>6}{tot["top1"] / tot["n"]:>8.0%}{tot["top5"] / tot["n"]:>8.0%}{tot["hard"]:>6}')
print(f'\nHARD bugs kept for the main experiment: {len(hard)}  -> saved to {HARD_PATH.name}')
print('bugs without a control answer yet (errors / budget):', len(missing))
if CTRL_USAGE_NEW.exists():
    with open(CTRL_USAGE_NEW) as f:
        u = [json.loads(l) for l in f]
    print(f'tokens (new bugs): input {sum(x["input_tokens"] for x in u):,}, '
          f'output {sum(x["output_tokens"] for x in u):,}, thinking {sum(x["thinking_tokens"] for x in u):,}')
