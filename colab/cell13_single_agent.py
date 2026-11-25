# === Cell 13: single-agent baseline (level 2) on the HARD bugs ===
# Needs Cell 1 (settings) and Cell 4 (Gemini client: call_model, parse_json).
# Same two-step method and the SAME prompts as Cell 5 (do not change them):
#   step 1: test + test code + stack trace + list of ALL source files -> pick up to 3 files
#   step 2: code of the picked files -> rank up to 5 methods
# Runs only on hard_bugs.csv (bugs the model could NOT localize without code).
# Change RUN_ID to 'hard_run2' / 'hard_run3' for the repeated runs.
# Resumable: bugs already done in this run are skipped.
import csv, gzip, json, time
from collections import defaultdict, Counter

assert 'call_model' in globals(), 'Run Cell 4 first (Gemini client)'

RUN_ID = 'hard_run1'
GT_ALL = BASE / 'ground_truth_all.csv'
HARD_PATH = BASE / 'hard_bugs.csv'
RES = OUT_DIR / f'SA_results_{RUN_ID}.csv'
RAW = OUT_DIR / f'SA_raw_answers_{RUN_ID}.jsonl'
USAGE = OUT_DIR / f'SA_usage_{RUN_ID}.jsonl'
TOKEN_BUDGET = 6_000_000   # safety cap on input tokens for this run

PROMPT_FILES = """You are an expert Java debugger. A test fails in a Java project.

Failing test: {test}

Test code:
{test_code}

Error and stack trace:
{trace}

These are ALL source files of the project:
{file_list}

Which files most likely contain the bug? Pick at most {k} files, most likely first.
Answer ONLY with JSON: {{"files": ["path/one.java", "path/two.java"]}}
"""

PROMPT_METHODS = """You are an expert Java debugger. A test fails in a Java project.

Failing test: {test}

Test code:
{test_code}

Error and stack trace:
{trace}

Source code of the suspicious files:
{sources}

Which methods most likely contain the bug? Give at most {k} methods, most likely first.
For a constructor, use the class name as the method name.
Answer ONLY with JSON: {{"methods": [{{"file": "Name.java", "method": "methodName"}}]}}
"""


def jsonl(path, obj):
    with open(path, 'a') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def done():
    if not RES.exists():
        return set()
    with open(RES) as f:
        return {(r['project'], int(r['bug_id'])) for r in csv.DictReader(f) if r['status'] == 'ok'}


def used_tokens():
    if not USAGE.exists():
        return 0
    with open(USAGE) as f:
        return sum(json.loads(l)['input_tokens'] for l in f)


def match_files(picked, all_files):
    """Map the model's file answers to real paths (exact path or same basename)."""
    by_base = {}
    for p in all_files:
        by_base.setdefault(p.rsplit('/', 1)[-1], []).append(p)
    out = []
    for p in picked:
        p = str(p).strip()
        if p in all_files:
            out.append(p)
        else:
            base = p.rsplit('/', 1)[-1]
            if not base.endswith('.java'):
                base += '.java'
            out.extend(by_base.get(base, [])[:1])
    return list(dict.fromkeys(out))[:MAX_FILES]


with open(HARD_PATH) as f:
    HARD = [(r['project'], int(r['bug_id'])) for r in csv.DictReader(f)]

# ---------------------------------------------------------------- run
todo = [b for b in HARD if b not in done()]
print(f'{len(HARD)} hard bugs, {len(todo)} still to run; input tokens used: {used_tokens():,}')
for i, (project, bug_id) in enumerate(todo, 1):
    if used_tokens() > TOKEN_BUDGET:
        print('TOKEN BUDGET REACHED, stopping.')
        break
    t0 = time.time()
    with open(INPUTS_DIR / f'{project}_{bug_id}.json') as f:
        inp = json.load(f)
    with gzip.open(SNAP_DIR / f'{project}_{bug_id}.json.gz', 'rt', encoding='utf-8') as f:
        snap = json.load(f)
    all_files = list(snap['files'].keys())
    row = {'project': project, 'bug_id': bug_id, 'status': 'ok',
           'picked_files': '', 'methods': '', 'error': '', 'latency_s': 0}
    try:
        p1 = PROMPT_FILES.format(test=inp['test'], test_code=inp.get('test_code', ''),
                                 trace=inp['trace'], file_list='\n'.join(all_files), k=MAX_FILES)
        t1, u1 = call_model(p1)
        jsonl(USAGE, {'project': project, 'bug_id': bug_id, 'step': 1, **u1})
        jsonl(RAW, {'project': project, 'bug_id': bug_id, 'step': 1, 'answer': t1})
        picked = match_files(parse_json(t1).get('files', []), snap['files'])

        sources = '\n\n'.join(f'=== {p} ===\n{snap["files"][p][:MAX_CHARS_PER_FILE]}' for p in picked)
        p2 = PROMPT_METHODS.format(test=inp['test'], test_code=inp.get('test_code', ''),
                                   trace=inp['trace'], sources=sources, k=MAX_METHODS)
        t2, u2 = call_model(p2)
        jsonl(USAGE, {'project': project, 'bug_id': bug_id, 'step': 2, **u2})
        jsonl(RAW, {'project': project, 'bug_id': bug_id, 'step': 2, 'answer': t2})
        row['picked_files'] = json.dumps(picked)
        row['methods'] = json.dumps(parse_json(t2).get('methods', [])[:MAX_METHODS], ensure_ascii=False)
    except Exception as e:
        # API or parsing errors are NOT counted as model misses
        row['status'], row['error'] = 'error', str(e)[:300]
    row['latency_s'] = round(time.time() - t0, 1)
    new_file = not RES.exists()
    with open(RES, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new_file:
            w.writeheader()
        w.writerow(row)
    print(f'[{i}/{len(todo)}] {project}-{bug_id}: {row["status"]} {row["error"][:100]}')


# ---------------------------------------------------------------- summary
def norm_file(f):
    return str(f).strip().rsplit('/', 1)[-1].replace('.java', '')


def norm_method(m):
    return str(m).strip().split('(')[0].rsplit('.', 1)[-1].strip()


truth, truth_files = defaultdict(set), defaultdict(set)
with open(GT_ALL) as f:
    for r in csv.DictReader(f):
        key = (r['project'], int(r['bug_id']))
        truth_files[key].add(norm_file(r['file']))
        if r['method']:
            truth[key].add((norm_file(r['file']), norm_method(r['method'])))

per_bug = {}
with open(RES) as f:
    for r in csv.DictReader(f):
        if r['status'] != 'ok':
            continue
        key = (r['project'], int(r['bug_id']))
        rank = None
        for i, m in enumerate(json.loads(r['methods']), 1):
            if (norm_file(m.get('file', '')), norm_method(m.get('method', ''))) in truth[key]:
                rank = i
                break
        file_hit = any(norm_file(p) in truth_files[key] for p in json.loads(r['picked_files']))
        per_bug[key] = (rank, file_hit, float(r['latency_s']))

with open(OUT_DIR / f'SA_per_bug_{RUN_ID}.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['project', 'bug_id', 'rank', 'file_hit', 'latency_s'])
    for (p, b), (rank, fh, lat) in sorted(per_bug.items()):
        w.writerow([p, b, rank or '', fh, lat])

n = len(per_bug)
print(f'\nSINGLE AGENT on HARD bugs ({RUN_ID}): {n} evaluated, {len(HARD) - n} missing/errors')
for k in (1, 3, 5):
    hit = sum(1 for r, _, _ in per_bug.values() if r and r <= k)
    print(f'Top-{k}: {hit}/{n} = {hit / n:.1%}')
print(f'MRR: {sum(1 / r for r, _, _ in per_bug.values() if r) / n:.3f}')
print(f'Correct file picked in step 1: {sum(fh for _, fh, _ in per_bug.values())}/{n}')
lat = sorted(l for _, _, l in per_bug.values())
print(f'Median latency per bug: {lat[len(lat) // 2]:.1f} s')

per = defaultdict(Counter)
for (p, b), (rank, fh, _) in per_bug.items():
    per[p]['n'] += 1
    per[p]['top1'] += rank == 1
    per[p]['top5'] += rank is not None
print(f'\n{"project":<12}{"bugs":>6}{"Top-1":>7}{"Top-5":>7}')
for p, c in sorted(per.items()):
    print(f'{p:<12}{c["n"]:>6}{c["top1"]:>7}{c["top5"]:>7}')
if USAGE.exists():
    with open(USAGE) as f:
        u = [json.loads(l) for l in f]
    print(f'\ntokens: input {sum(x["input_tokens"] for x in u):,}, output {sum(x["output_tokens"] for x in u):,}, '
          f'thinking {sum(x["thinking_tokens"] for x in u):,}')
print('Missed bugs:', ', '.join(f'{p}-{b}' for (p, b), (r, _, _) in sorted(per_bug.items()) if r is None) or 'none')
