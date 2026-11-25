# Cells 1-6: setup (Drive, Defects4J, code snapshots, Gemini client) and the Phase-1 single-agent baseline
# on the 40 Lang/Math pilot bugs. Paste each "=== Cell N" block into its own Colab cell and run them in order.
# After a Colab reset: run Cell 1 and Cell 4 again (snapshots and results are kept in Google Drive).


# === Cell 1: Drive + settings ===
from google.colab import drive
drive.mount('/content/drive')

import os, pathlib
BASE = pathlib.Path('/content/drive/MyDrive/thesis')
SNAP_DIR = BASE / 'snapshots'          # one gzipped JSON per bug (file list + sources)
OUT_DIR = BASE / 'results_L2'          # results of all experiments
for p in (BASE, SNAP_DIR, OUT_DIR):
    p.mkdir(parents=True, exist_ok=True)

GT_PATH = BASE / 'ground_truth_v2.csv'  # answer key of the 40 pilot bugs (built by Cell 9; copy of data/ground_truth_v2.csv)
INPUTS_DIR = BASE / 'inputs'            # one JSON per bug: failing test, test code, stack trace

# Fixed experiment settings (do NOT change in the middle of an experiment)
PROJECT_ID = 'YOUR_GCP_PROJECT_ID'      # Google Cloud project with Vertex AI enabled
LOCATION = 'global'
MODEL = 'gemini-3.5-flash'
TEMPERATURE = 1.0                       # Gemini default; reported in the thesis
MAX_FILES = 3                           # step 1: files the model may pick
MAX_METHODS = 5                         # step 2: ranked method guesses
MAX_CHARS_PER_FILE = 300_000            # never truncate normal files
TOKEN_BUDGET_INPUT = 3_000_000          # safety cap for one run (input tokens)

print('ground truth found:', GT_PATH.exists())
print('inputs found:', INPUTS_DIR.exists(), len(list(INPUTS_DIR.glob('*.json'))) if INPUTS_DIR.exists() else 0, 'files')


# === Cell 2: install Java 11 + Defects4J (15-30 min, once per Colab session) ===
# Only needed to build snapshots / inputs (Cells 3, 8, 9, 11).
import subprocess, os

def sh(cmd):
    """Run a shell command, show its output, stop on error."""
    print('$', cmd)
    r = subprocess.run(cmd, shell=True, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(r.stdout[-3000:])
    if r.returncode != 0:
        raise RuntimeError(f'command failed: {cmd}')

sh('apt-get -qq update && apt-get -qq install -y openjdk-11-jdk-headless cpanminus subversion > /dev/null')
os.environ['JAVA_HOME'] = '/usr/lib/jvm/java-11-openjdk-amd64'
os.environ['PATH'] = os.environ['JAVA_HOME'] + '/bin:' + os.environ['PATH']
sh('java -version')

if not os.path.exists('/content/defects4j'):
    sh('git clone -q https://github.com/rjust/defects4j /content/defects4j')
sh('cd /content/defects4j && cpanm --quiet --notest --installdeps .')
sh('cd /content/defects4j && ./init.sh')
os.environ['PATH'] = '/content/defects4j/framework/bin:' + os.environ['PATH']
sh('git config --global user.name thesis && git config --global user.email thesis@example.com')
sh('defects4j info -p Lang | head -5')


# === Cell 3: build code snapshots for the 40 pilot bugs (saved in Drive) ===
# A snapshot = list of all main source files of the BUGGY version + their text.
# After this cell, the experiments no longer need Defects4J.
import csv, gzip, json, subprocess, os, shutil, pathlib

def load_bugs():
    """Unique (project, bug_id) pairs from the answer key, in file order."""
    seen, bugs = set(), []
    with open(GT_PATH) as f:
        for row in csv.DictReader(f):
            key = (row['project'], int(row['bug_id']))
            if key not in seen:
                seen.add(key); bugs.append(key)
    return bugs

BUGS = load_bugs()
print(len(BUGS), 'bugs')

def snapshot_path(project, bug_id):
    return SNAP_DIR / f'{project}_{bug_id}.json.gz'

def build_snapshot(project, bug_id):
    work = f'/content/work/{project}_{bug_id}'
    shutil.rmtree(work, ignore_errors=True)
    subprocess.run(['defects4j', 'checkout', '-p', project, '-v', f'{bug_id}b', '-w', work],
                   check=True, capture_output=True, text=True)
    src_dir = subprocess.run(['defects4j', 'export', '-p', 'dir.src.classes', '-w', work],
                             check=True, capture_output=True, text=True).stdout.strip()
    files = {}
    root = pathlib.Path(work)
    for p in sorted((root / src_dir).rglob('*.java')):
        rel = str(p.relative_to(root))
        files[rel] = p.read_text(encoding='utf-8', errors='replace')
    with gzip.open(snapshot_path(project, bug_id), 'wt', encoding='utf-8') as f:
        json.dump({'project': project, 'bug_id': bug_id, 'src_dir': src_dir, 'files': files}, f)
    shutil.rmtree(work, ignore_errors=True)
    return len(files)

missing = [b for b in BUGS if not snapshot_path(*b).exists()]
print('missing snapshots:', len(missing))
for project, bug_id in missing:
    try:
        n = build_snapshot(project, bug_id)
        print(f'{project}-{bug_id}: {n} source files')
    except subprocess.CalledProcessError as e:
        print(f'{project}-{bug_id}: FAILED\n{e.stderr[-1500:]}')


# === Cell 4: Gemini client via Vertex AI ===
# In Colab, first run:  !pip -q install google-genai==2.12.1 pandas
from google.colab import auth
auth.authenticate_user()                # log in with the Google account that owns the project

from google import genai
from google.genai import types
import json, re, time, random

client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

RETRY_CODES = ('429', '500', '503', '504', 'RESOURCE_EXHAUSTED', 'UNAVAILABLE', 'DEADLINE')

def call_model(prompt, max_tries=7):
    """Call the fixed model with retries. Returns (text, usage dict) or raises."""
    wait = 30
    for attempt in range(1, max_tries + 1):
        try:
            t0 = time.time()
            resp = client.models.generate_content(
                model=MODEL, contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=TEMPERATURE,
                    response_mime_type='application/json'))
            um = resp.usage_metadata
            usage = {
                'input_tokens': getattr(um, 'prompt_token_count', 0) or 0,
                'output_tokens': getattr(um, 'candidates_token_count', 0) or 0,
                'thinking_tokens': getattr(um, 'thoughts_token_count', 0) or 0,
                'latency_s': round(time.time() - t0, 2),
                'attempts': attempt,
            }
            return resp.text or '', usage
        except Exception as e:
            msg = str(e)
            if attempt < max_tries and any(c in msg for c in RETRY_CODES):
                sleep = wait + random.uniform(0, 10)
                print(f'  API error ({msg[:80]}...), retry {attempt} in {sleep:.0f}s')
                time.sleep(sleep); wait = min(wait * 2, 600)
            else:
                raise

def parse_json(text):
    """Tolerant JSON parser: accepts text or code fences around the JSON."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', text, re.S)
        if m:
            return json.loads(m.group(0))
        raise

text, usage = call_model('Reply with JSON: {"ok": true}')
print(text, usage)


# === Cell 5: run the level-2 single-agent baseline (40 pilot bugs) ===
# Step 1: model sees test name + test code + stack trace + list of ALL source files, picks up to MAX_FILES files.
# Step 2: model sees the picked files' code and ranks up to MAX_METHODS methods.
# Results are appended to Drive, so the run can resume after a Colab reset.
import csv, gzip, json, pathlib, time, datetime

LIMIT = None         # e.g. 3 for a first test
RUN_ID = 'run1'

RAW_PATH = OUT_DIR / f'raw_answers_L2_{RUN_ID}.jsonl'
RES_PATH = OUT_DIR / f'baseline_L2_results_{RUN_ID}.csv'
USAGE_PATH = OUT_DIR / f'usage_log_L2_{RUN_ID}.jsonl'

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

def load_input(project, bug_id):
    with open(INPUTS_DIR / f'{project}_{bug_id}.json') as f:
        return json.load(f)

def load_snapshot(project, bug_id):
    with gzip.open(SNAP_DIR / f'{project}_{bug_id}.json.gz', 'rt', encoding='utf-8') as f:
        return json.load(f)

def done_bugs():
    if not RES_PATH.exists():
        return set()
    with open(RES_PATH) as f:
        return {(r['project'], int(r['bug_id'])) for r in csv.DictReader(f) if r['status'] == 'ok'}

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

def append_jsonl(path, obj):
    with open(path, 'a') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')

def write_result(row):
    new = not RES_PATH.exists()
    with open(RES_PATH, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new:
            w.writeheader()
        w.writerow(row)

def used_input_tokens():
    if not USAGE_PATH.exists():
        return 0
    with open(USAGE_PATH) as f:
        return sum(json.loads(l)['input_tokens'] for l in f)

todo = [b for b in BUGS if b not in done_bugs()]
if LIMIT:
    todo = todo[:LIMIT]
print(f'{len(todo)} bugs to run; input tokens used so far: {used_input_tokens():,}')

for project, bug_id in todo:
    if used_input_tokens() > TOKEN_BUDGET_INPUT:
        print('TOKEN BUDGET REACHED, stopping.'); break
    t_start = time.time()
    inp, snap = load_input(project, bug_id), load_snapshot(project, bug_id)
    all_files = list(snap['files'].keys())
    row = {'project': project, 'bug_id': bug_id, 'status': 'ok',
           'picked_files': '', 'methods': '', 'error': '', 'latency_s': 0}
    try:
        # Step 1: file selection
        p1 = PROMPT_FILES.format(test=inp['test'], test_code=inp.get('test_code', ''),
                                 trace=inp['trace'], file_list='\n'.join(all_files), k=MAX_FILES)
        t1, u1 = call_model(p1)
        append_jsonl(USAGE_PATH, {'project': project, 'bug_id': bug_id, 'step': 1, **u1})
        append_jsonl(RAW_PATH, {'project': project, 'bug_id': bug_id, 'step': 1, 'answer': t1})
        picked = match_files(parse_json(t1).get('files', []), snap['files'])

        # Step 2: method ranking inside the picked files
        sources = '\n\n'.join(f'=== {p} ===\n{snap["files"][p][:MAX_CHARS_PER_FILE]}' for p in picked)
        p2 = PROMPT_METHODS.format(test=inp['test'], test_code=inp.get('test_code', ''),
                                   trace=inp['trace'], sources=sources, k=MAX_METHODS)
        t2, u2 = call_model(p2)
        append_jsonl(USAGE_PATH, {'project': project, 'bug_id': bug_id, 'step': 2, **u2})
        append_jsonl(RAW_PATH, {'project': project, 'bug_id': bug_id, 'step': 2, 'answer': t2})
        methods = parse_json(t2).get('methods', [])[:MAX_METHODS]

        row['picked_files'] = json.dumps(picked)
        row['methods'] = json.dumps(methods, ensure_ascii=False)
    except Exception as e:
        # API or parsing errors are NOT counted as model misses
        row['status'] = 'error'
        row['error'] = str(e)[:300]
    row['latency_s'] = round(time.time() - t_start, 1)
    write_result(row)
    print(f"{project}-{bug_id}: {row['status']} files={row['picked_files']} methods={row['methods'][:150]}")


# === Cell 6: summary (Top-1/3/5, MRR, file hit rate) ===
import pandas as pd, json, csv
from collections import defaultdict

def norm_file(f):
    """'src/.../NumberUtils.java' or 'NumberUtils' -> 'NumberUtils'."""
    return str(f).strip().rsplit('/', 1)[-1].replace('.java', '')

def norm_method(m):
    """'NumberUtils.createNumber(String)' -> 'createNumber'."""
    m = str(m).strip().split('(')[0]
    return m.rsplit('.', 1)[-1].strip()

truth = defaultdict(set)
truth_files = defaultdict(set)
with open(GT_PATH) as f:
    for r in csv.DictReader(f):
        key = (r['project'], int(r['bug_id']))
        if r['method']:
            truth[key].add((norm_file(r['file']), norm_method(r['method'])))
        truth_files[key].add(norm_file(r['file']))

res = pd.read_csv(RES_PATH)
res = res[res.status == 'ok'].drop_duplicates(['project', 'bug_id'], keep='last')

rows = []
for _, r in res.iterrows():
    key = (r.project, int(r.bug_id))
    methods = json.loads(r.methods)
    rank = None
    for i, m in enumerate(methods, 1):
        if (norm_file(m.get('file', '')), norm_method(m.get('method', ''))) in truth[key]:
            rank = i; break
    file_hit = any(norm_file(p) in truth_files[key] for p in json.loads(r.picked_files))
    rows.append({'bug': f'{r.project}-{r.bug_id}', 'rank': rank, 'file_hit': file_hit,
                 'latency_s': r.latency_s})

df = pd.DataFrame(rows, columns=['bug', 'rank', 'file_hit', 'latency_s'])
n = len(df)
assert n > 0, 'no successful bugs yet - check the error column in the results CSV'
print(f'bugs evaluated: {n} (errors excluded: {(pd.read_csv(RES_PATH).status != "ok").sum()})')
for k in (1, 3, 5):
    hit = (df['rank'].notna() & (df['rank'] <= k)).sum()
    print(f'Top-{k}: {hit}/{n} = {hit / n:.1%}')
print(f"MRR: {df['rank'].apply(lambda x: 1 / x if pd.notna(x) else 0).mean():.3f}")
print(f"File found in step 1: {df.file_hit.sum()}/{n} = {df.file_hit.mean():.1%}")
print(f"Median latency per bug: {df.latency_s.median():.1f} s")
if USAGE_PATH.exists():
    u = pd.read_json(USAGE_PATH, lines=True)
    print(f"Tokens: input {u.input_tokens.sum():,}, output {u.output_tokens.sum():,}, thinking {u.thinking_tokens.sum():,}")
print('\nMissed bugs:', ', '.join(df[df['rank'].isna()].bug) or 'none')
df.to_csv(OUT_DIR / f'per_bug_L2_{RUN_ID}.csv', index=False)
