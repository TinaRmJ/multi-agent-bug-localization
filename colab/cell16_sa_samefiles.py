# === Cell 16: SA-sameFiles control (single agent reads EXACTLY the files the team chose) ===
# Needs Cell 1 (settings) and Cell 4 (Gemini client: call_model, parse_json).
# Why: the team may read up to 6 files, the single agent only 3. This control gives the
# single agent's step 2 (same prompt as Cell 13) the union of files that the team chose
# for the same bug in the same team run. Then both see identical code, so a remaining
# difference comes from the team's reasoning, not from reading more files.
# One SA-sameFiles run per finished team run; team runs that are not complete are skipped.
# Resumable: bugs already done are skipped.
import csv, gzip, json, time
from collections import defaultdict

assert 'call_model' in globals(), 'Run Cell 4 first (Gemini client)'

# SA-sameFiles run id -> team run id (team run 1 was stored as 'ma_run')
PAIRS = {'same_ma_run1': 'ma_run', 'same_ma_run2': 'ma_run2', 'same_ma_run3': 'ma_run3'}
GT_ALL = BASE / 'ground_truth_all.csv'
HARD_PATH = BASE / 'hard_bugs.csv'

# Exactly the step-2 prompt of Cell 13 (do not change it)
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


def norm_file(f):
    return str(f).strip().rsplit('/', 1)[-1].replace('.java', '').split('$')[0]


def norm_method(m):
    return str(m).strip().split('(')[0].rsplit('.', 1)[-1].strip()


with open(HARD_PATH) as f:
    HARD = [(r['project'], int(r['bug_id'])) for r in csv.DictReader(f)]

truth = defaultdict(set)
with open(GT_ALL) as f:
    for r in csv.DictReader(f):
        if r['method']:
            truth[(r['project'], int(r['bug_id']))].add((norm_file(r['file']), norm_method(r['method'])))


def rank_of(items, bug):
    for i, m in enumerate(items, 1):
        if isinstance(m, dict) and (norm_file(m.get('file', '')), norm_method(m.get('method', ''))) in truth[bug]:
            return i
    return None


for same_id, ma_id in PAIRS.items():
    state_dir = OUT_DIR / f'MA_states_{ma_id}'
    done_ma = [b for b in HARD if (state_dir / f'{b[0]}_{b[1]}.json').exists()]
    if len(done_ma) < len(HARD):
        print(f'{same_id}: team run {ma_id} has {len(done_ma)}/{len(HARD)} bugs -> skipped for now')
        continue
    res = OUT_DIR / f'SAsame_results_{same_id}.csv'
    raw = OUT_DIR / f'SAsame_raw_{same_id}.jsonl'
    usage_path = OUT_DIR / f'SAsame_usage_{same_id}.jsonl'
    done = set()
    if res.exists():
        with open(res) as f:
            done = {(r['project'], int(r['bug_id'])) for r in csv.DictReader(f) if r['status'] == 'ok'}
    todo = [b for b in HARD if b not in done]
    print(f'\n{same_id} (files from {ma_id}): {len(todo)} bugs to run')

    for i, (project, bug_id) in enumerate(todo, 1):
        st = json.loads((state_dir / f'{project}_{bug_id}.json').read_text())
        with open(INPUTS_DIR / f'{project}_{bug_id}.json') as f:
            inp = json.load(f)
        with gzip.open(SNAP_DIR / f'{project}_{bug_id}.json.gz', 'rt', encoding='utf-8') as f:
            snap = json.load(f)
        files = [p for p in st['files'] if p in snap['files']]
        row = {'project': project, 'bug_id': bug_id, 'status': 'ok', 'files': json.dumps(files),
               'methods': '', 'error': '', 'latency_s': 0}
        t0 = time.time()
        try:
            sources = '\n\n'.join(f'=== {p} ===\n{snap["files"][p][:MAX_CHARS_PER_FILE]}' for p in files)
            prompt = PROMPT_METHODS.format(test=inp['test'], test_code=inp.get('test_code', ''),
                                           trace=inp['trace'], sources=sources, k=MAX_METHODS)
            text, u = call_model(prompt)
            jsonl(usage_path, {'project': project, 'bug_id': bug_id, **u})
            jsonl(raw, {'project': project, 'bug_id': bug_id, 'answer': text})
            row['methods'] = json.dumps(parse_json(text).get('methods', [])[:MAX_METHODS], ensure_ascii=False)
        except Exception as e:
            # API or parsing errors are NOT counted as misses; retried next time
            row['status'], row['error'] = 'error', str(e)[:300]
        row['latency_s'] = round(time.time() - t0, 1)
        new_file = not res.exists()
        with open(res, 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            if new_file:
                w.writeheader()
            w.writerow(row)
        if i % 10 == 0 or row['status'] != 'ok':
            print(f'  [{i}/{len(todo)}] {project}-{bug_id}: {row["status"]} {row["error"][:100]}')

    # ---- summary: SA-sameFiles vs MA-coop of the same team run (same files)
    same = {}
    with open(res) as f:
        for r in csv.DictReader(f):
            if r['status'] == 'ok':
                same[(r['project'], int(r['bug_id']))] = rank_of(json.loads(r['methods']), (r['project'], int(r['bug_id'])))
    coop = {}
    for b in HARD:
        st = json.loads((state_dir / f'{b[0]}_{b[1]}.json').read_text())
        coop[b] = rank_of(st['ranking_coop'], b)
    n = len(same)
    print(f'{same_id}: {n} bugs evaluated')
    for name, d in (('SA-sameFiles', same), ('MA-coop (same run)', coop)):
        vals = [d[b] for b in same]
        tops = [sum(1 for v in vals if v and v <= k) for k in (1, 3, 5)]
        print(f'  {name:<20} Top-1 {tops[0]}/{n} = {tops[0] / n:.1%}  Top-3 {tops[1] / n:.1%}  '
              f'Top-5 {tops[2] / n:.1%}  MRR {sum(1 / v for v in vals if v) / n:.3f}')
    b_ma = sum(1 for b in same if coop[b] == 1 and same[b] != 1)
    b_sa = sum(1 for b in same if same[b] == 1 and coop[b] != 1)
    print(f'  Top-1 only team: {b_ma}, only SA-sameFiles: {b_sa}')
    if usage_path.exists():
        with open(usage_path) as f:
            u = [json.loads(l) for l in f]
        print(f'  tokens: input {sum(x["input_tokens"] for x in u):,}, output {sum(x["output_tokens"] for x in u):,}, '
              f'thinking {sum(x["thinking_tokens"] for x in u):,}')
