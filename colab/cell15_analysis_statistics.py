# === Cell 15: all free analyses + statistics + subgroup analysis (no model calls, no cost) ===
# Needs only Cell 1 (Drive + settings). Uses the stored results of:
#   SA runs (Cell 13: hard_run1..3), team runs (Cell 14: 'ma_run', 'ma_run2', 'ma_run3'),
#   SA-sameFiles runs (Cell 16: same_ma_run1..3).
# Works with whatever runs exist; the report says how many runs each configuration has.
# Writes a full text report to Drive: results_L2/analysis/analysis_report.md  (send this file to Claude)
# and per-bug tables (CSV) next to it.
import subprocess, sys
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'javalang'], check=True)

import csv, gzip, json, re, math, random, statistics
from collections import defaultdict, Counter
from math import comb
import javalang
from scipy.stats import wilcoxon

GT_ALL = BASE / 'ground_truth_all.csv'
HARD_PATH = BASE / 'hard_bugs.csv'
AN_DIR = OUT_DIR / 'analysis'
AN_DIR.mkdir(exist_ok=True)
SA_RUNS = ['hard_run1', 'hard_run2', 'hard_run3']
MA_RUNS = ['ma_run', 'ma_run2', 'ma_run3']          # team run 1 was stored as 'ma_run'
SAME_RUNS = ['same_ma_run1', 'same_ma_run2', 'same_ma_run3']
KS = (1, 3, 5)
random.seed(12345)

REPORT = []


def out(line=''):
    """Print and keep the line for the report file."""
    print(line)
    REPORT.append(line)


# ================================================================ helpers
def norm_file(f):
    return str(f).strip().rsplit('/', 1)[-1].replace('.java', '').split('$')[0]


def norm_method(m):
    return str(m).strip().split('(')[0].rsplit('.', 1)[-1].strip()


def key_of(item):
    return (norm_file(item.get('file', '')), norm_method(item.get('method', '')))


def tolerant_json(text):
    """Parse JSON even with text or code fences around it; {} if impossible."""
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', str(text).strip())
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r'\{.*\}', t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


def as_list(x):
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


with open(HARD_PATH) as f:
    HARD = [(r['project'], int(r['bug_id'])) for r in csv.DictReader(f)]
N = len(HARD)

truth, truth_files, gt_rows = defaultdict(set), defaultdict(set), Counter()
with open(GT_ALL) as f:
    for r in csv.DictReader(f):
        b = (r['project'], int(r['bug_id']))
        gt_rows[b] += 1
        truth_files[b].add(norm_file(r['file']))
        if r['method']:
            truth[b].add((norm_file(r['file']), norm_method(r['method'])))


def rank_of(items, b):
    for i, it in enumerate(items, 1):
        if key_of(it) in truth[b]:
            return i
    return None


def file_hit(paths, b):
    return any(norm_file(p) in truth_files[b] for p in paths)


def read_usage(path):
    tok = defaultdict(lambda: [0, 0])
    if path.exists():
        with open(path) as f:
            for l in f:
                u = json.loads(l)
                b = (u['project'], int(u['bug_id']))
                tok[b][0] += u.get('input_tokens', 0)
                tok[b][1] += u.get('output_tokens', 0) + u.get('thinking_tokens', 0)
    return tok


# ================================================================ load all configurations
# runs[config] = list of dicts {bug: {'rank', 'items', 'files', 'latency'}}
runs = defaultdict(list)
tokens = defaultdict(list)   # config -> list (per run) of {bug: [in, out]}

for run in SA_RUNS:
    p = OUT_DIR / f'SA_results_{run}.csv'
    if not p.exists():
        continue
    d = {}
    with open(p) as f:
        for r in csv.DictReader(f):
            if r['status'] != 'ok':
                continue
            b = (r['project'], int(r['bug_id']))
            items = as_list(json.loads(r['methods']))
            d[b] = {'rank': rank_of(items, b), 'items': items, 'files': json.loads(r['picked_files']),
                    'latency': float(r['latency_s'])}
    if len(d) == N:
        runs['SA'].append(d)
        tokens['SA'].append(read_usage(OUT_DIR / f'SA_usage_{run}.jsonl'))

MA_STATES = []
for run in MA_RUNS:
    sd = OUT_DIR / f'MA_states_{run}'
    if not all((sd / f'{b[0]}_{b[1]}.json').exists() for b in HARD):
        continue
    coop, deb, hyp, states = {}, {}, {}, {}
    for b in HARD:
        st = json.loads((sd / f'{b[0]}_{b[1]}.json').read_text())
        states[b] = st
        hyp_call = [c for c in st['calls'] if c['agent'] == 'hypothesis']
        hyps = as_list(tolerant_json(hyp_call[0]['answer']).get('hypotheses')) if hyp_call else []
        for name, items, dct in (('coop', st['ranking_coop'], coop), ('debate', st['ranking_debate'], deb),
                                 ('hyp', hyps[:5], hyp)):
            dct[b] = {'rank': rank_of(items, b), 'items': items, 'files': st['files'], 'latency': st['latency_s']}
    runs['MA-coop'].append(coop)
    runs['MA-debate'].append(deb)
    runs['MA-hyp'].append(hyp)
    MA_STATES.append((run, states))
    tokens['MA'].append(read_usage(OUT_DIR / f'MA_usage_{run}.jsonl'))

for run in SAME_RUNS:
    p = OUT_DIR / f'SAsame_results_{run}.csv'
    if not p.exists():
        continue
    d = {}
    with open(p) as f:
        for r in csv.DictReader(f):
            if r['status'] != 'ok':
                continue
            b = (r['project'], int(r['bug_id']))
            items = as_list(json.loads(r['methods']))
            d[b] = {'rank': rank_of(items, b), 'items': items, 'files': json.loads(r['files']),
                    'latency': float(r['latency_s'])}
    if len(d) == N:
        runs['SA-sameFiles'].append(d)
        tokens['SA-sameFiles'].append(read_usage(OUT_DIR / f'SAsame_usage_{run}.jsonl'))

# SA-budget: fixed voting rule (sum of 1/r over SA runs; ties: best single rank, then earliest run)
if runs['SA']:
    budget = {}
    for b in HARD:
        score, best, first = defaultdict(float), {}, {}
        for ri, d in enumerate(runs['SA']):
            for r, it in enumerate(d[b]['items'][:5], 1):
                k = key_of(it)
                score[k] += 1 / r
                best[k] = min(best.get(k, 99), r)
                first.setdefault(k, ri)
        order = sorted(score, key=lambda k: (-score[k], best[k], first[k]))[:5]
        items = [{'file': k[0] + '.java', 'method': k[1]} for k in order]
        budget[b] = {'rank': rank_of(items, b), 'items': items, 'files': [], 'latency': None}
    runs['SA-budget'].append(budget)

CONFIGS = [c for c in ['SA', 'SA-budget', 'SA-sameFiles', 'MA-hyp', 'MA-coop', 'MA-debate'] if runs[c]]
out('# Analysis report (Cell 15)')
out(f'Hard bugs: {N}. Runs available: ' + ', '.join(f'{c} {len(runs[c])}' for c in CONFIGS))


# ================================================================ 1. main table (mean over runs)
def hit(rank, k):
    return rank is not None and rank <= k


out('\n## 1. Main results (mean over runs; sd over runs in brackets)')
out('| Config | runs | Top-1 | Top-3 | Top-5 | MRR | file recall | median latency s | tokens/bug in | out+think |')
out('|---|---|---|---|---|---|---|---|---|---|')
for c in CONFIGS:
    rs = runs[c]
    vals = {}
    for k in KS:
        v = [sum(hit(d[b]['rank'], k) for b in HARD) / N for d in rs]
        vals[k] = f'{statistics.mean(v):.1%}' + (f' ({statistics.stdev(v) * 100:.1f})' if len(v) > 1 else '')
    mrr = [sum(1 / d[b]['rank'] for b in HARD if d[b]['rank']) / N for d in rs]
    mrr_s = f'{statistics.mean(mrr):.3f}' + (f' ({statistics.stdev(mrr):.3f})' if len(mrr) > 1 else '')
    fr = '-'
    if c in ('SA', 'SA-sameFiles', 'MA-coop', 'MA-debate', 'MA-hyp'):
        fr = f'{statistics.mean(sum(file_hit(d[b]["files"], b) for b in HARD) for d in rs):.1f}/{N}'
    lat = [d[b]['latency'] for d in rs for b in HARD if d[b]['latency'] is not None]
    lat_s = f'{statistics.median(lat):.1f}' if lat else '-'
    tk = tokens.get({'MA-coop': 'MA', 'MA-debate': 'MA', 'MA-hyp': 'MA'}.get(c, c), [])
    if tk:
        tin = statistics.mean(sum(t[b][0] for b in HARD) / N for t in tk)
        tout = statistics.mean(sum(t[b][1] for b in HARD) / N for t in tk)
        tk_s = f'{tin:,.0f} | {tout:,.0f}'
    else:
        tk_s = '- | -'
    out(f'| {c} | {len(rs)} | {vals[1]} | {vals[3]} | {vals[5]} | {mrr_s} | {fr} | {lat_s} | {tk_s} |')
out('(MA-hyp, MA-coop and MA-debate come from the same team runs; their latency/tokens are those of the whole team run.)')


# ================================================================ 2. per-bug summary + statistics (unit = bug)
def per_bug(c):
    rs = runs[c]
    n = len(rs)
    maj = {k: {b: sum(hit(d[b]['rank'], k) for d in rs) * 2 > n for b in HARD} for k in KS}
    mrr = {b: statistics.mean((1 / d[b]['rank']) if d[b]['rank'] else 0 for d in rs) for b in HARD}
    return maj, mrr


def mcnemar_exact(b_only, c_only):
    m = b_only + c_only
    if m == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(m, i) for i in range(min(b_only, c_only) + 1)) / 2 ** m)


def bootstrap_ci(xa, xb, reps=10000):
    diffs = []
    for _ in range(reps):
        idx = [random.randrange(N) for _ in range(N)]
        diffs.append(sum(xa[i] - xb[i] for i in idx) / N)
    diffs.sort()
    return diffs[int(0.025 * reps)], diffs[int(0.975 * reps) - 1]


PAIRS = [('MA-coop', 'SA'), ('MA-debate', 'SA'), ('MA-debate', 'SA-budget'),
         ('MA-coop', 'SA-sameFiles'), ('MA-coop', 'MA-hyp'), ('MA-debate', 'MA-coop')]
SUM = {c: per_bug(c) for c in CONFIGS}
out(f'\n## 2. Paired statistics (unit = bug, {N} pairs; majority outcome over runs; mean RR per bug)')
out('| A vs B | Top-1 A-only / B-only | McNemar p | Top-5 A-only / B-only | McNemar p | MRR A - B | Wilcoxon p | 95% CI Top-1 diff | 95% CI MRR diff |')
out('|---|---|---|---|---|---|---|---|---|')
for a, bb in PAIRS:
    if a not in SUM or bb not in SUM:
        continue
    (ma, ra), (mb, rb) = SUM[a], SUM[bb]
    cells = []
    for k in (1, 5):
        a_only = sum(1 for b in HARD if ma[k][b] and not mb[k][b])
        b_only = sum(1 for b in HARD if mb[k][b] and not ma[k][b])
        cells.append(f'{a_only} / {b_only} | {mcnemar_exact(a_only, b_only):.3f}')
    d = [ra[b] - rb[b] for b in HARD]
    try:
        wp = wilcoxon([ra[b] for b in HARD], [rb[b] for b in HARD]).pvalue if any(d) else 1.0
    except ValueError:
        wp = 1.0
    t1a = [1 if ma[1][b] else 0 for b in HARD]
    t1b = [1 if mb[1][b] else 0 for b in HARD]
    lo1, hi1 = bootstrap_ci(t1a, t1b)
    lo2, hi2 = bootstrap_ci([ra[b] for b in HARD], [rb[b] for b in HARD])
    out(f'| {a} vs {bb} | {cells[0]} | {cells[1]} | {statistics.mean(d):+.3f} | {wp:.3f} | '
        f'[{lo1 * 100:+.1f}, {hi1 * 100:+.1f}] pts | [{lo2:+.3f}, {hi2:+.3f}] |')

out('\n### Sensitivity: McNemar per run (run i of A vs run i of B)')
for a, bb in PAIRS:
    if a not in runs or bb not in runs or not runs[a] or not runs[bb]:
        continue
    parts = []
    for i in range(min(len(runs[a]), len(runs[bb]))):
        for k in (1, 5):
            x = sum(1 for b in HARD if hit(runs[a][i][b]['rank'], k) and not hit(runs[bb][i][b]['rank'], k))
            y = sum(1 for b in HARD if hit(runs[bb][i][b]['rank'], k) and not hit(runs[a][i][b]['rank'], k))
            parts.append(f'run{i + 1} Top-{k} {x}/{y} p={mcnemar_exact(x, y):.3f}')
    out(f'- {a} vs {bb}: ' + '; '.join(parts))


# ================================================================ 3. consistency (RQ3)
out('\n## 3. Consistency across runs (Top-5 found / not found)')
out('| Config | runs | same outcome in all runs | always found | never found | unstable |')
out('|---|---|---|---|---|---|')
CLASS = {}
for c in ['SA', 'SA-sameFiles', 'MA-hyp', 'MA-coop', 'MA-debate']:
    if len(runs[c]) < 2:
        continue
    al = [b for b in HARD if all(hit(d[b]['rank'], 5) for d in runs[c])]
    nv = [b for b in HARD if not any(hit(d[b]['rank'], 5) for d in runs[c])]
    un = [b for b in HARD if b not in al and b not in nv]
    out(f'| {c} | {len(runs[c])} | {len(al) + len(nv)}/{N} | {len(al)} | {len(nv)} | {len(un)} |')
    if c == 'SA':
        CLASS = {**{b: 'SA always found' for b in al}, **{b: 'SA never found' for b in nv},
                 **{b: 'SA unstable' for b in un}}


# ================================================================ 4. file-choice analysis
out('\n## 4. File choice (does a chosen file contain a faulty method?)')
for i, d in enumerate(runs['SA']):
    out(f'- SA run {i + 1}: file recall {sum(file_hit(d[b]["files"], b) for b in HARD)}/{N}')
for run, states in MA_STATES:
    ti = {b: file_hit(states[b]['files_ti'], b) for b in HARD}
    ins = {b: file_hit(states[b]['files_inspector'], b) for b in HARD}
    un = {b: file_hit(states[b]['files'], b) for b in HARD}
    out(f'- team {run}: Trace Interpreter alone {sum(ti.values())}/{N}, Inspector alone {sum(ins.values())}/{N}, '
        f'union {sum(un.values())}/{N}; only TI found it {sum(ti[b] and not ins[b] for b in HARD)}, '
        f'only Inspector found it {sum(ins[b] and not ti[b] for b in HARD)}; '
        f'avg files read {statistics.mean(len(states[b]["files"]) for b in HARD):.1f}')


# ================================================================ 5. non-existing methods (hallucinations)
def spans_names(src):
    names = set()
    try:
        tree = javalang.parse.parse(src)
        for kind in (javalang.tree.MethodDeclaration, javalang.tree.ConstructorDeclaration):
            for _, node in tree.filter(kind):
                names.add(node.name)
    except Exception:
        return None
    return names


SNAP_NAMES = {}


def method_exists(b, item):
    """True / False / None (cannot check) for a (file, method) named by a model."""
    f, m = key_of(item)
    if not m:
        return None
    if b not in SNAP_NAMES:
        with gzip.open(SNAP_DIR / f'{b[0]}_{b[1]}.json.gz', 'rt', encoding='utf-8') as fh:
            SNAP_NAMES[b] = {'files': json.load(fh)['files'], 'cache': {}}
    s = SNAP_NAMES[b]
    paths = [p for p in s['files'] if p.rsplit('/', 1)[-1] == f + '.java']
    if not paths:
        return False
    for p in paths:
        if p not in s['cache']:
            s['cache'][p] = spans_names(s['files'][p])
        if s['cache'][p] is None:
            return None
        if m in s['cache'][p]:
            return True
    return False


out('\n## 5. Methods that do not exist in the project (misleading inferences)')
for i, d in enumerate(runs['SA']):
    named = [(b, it) for b in HARD for it in d[b]['items']]
    bad = [x for x in named if method_exists(*x) is False]
    out(f'- SA run {i + 1}: {len(bad)} of {len(named)} named methods do not exist')
for i, (run, states) in enumerate(MA_STATES):
    hyp_bad = kept = 0
    hyp_all = 0
    for b in HARD:
        for it in runs['MA-hyp'][i][b]['items']:
            hyp_all += 1
            if method_exists(b, it) is False:
                hyp_bad += 1
                if key_of(it) in {key_of(x) for x in runs['MA-debate'][i][b]['items']}:
                    kept += 1
    fin = [(b, it) for b in HARD for it in runs['MA-debate'][i][b]['items']]
    fin_bad = sum(1 for x in fin if method_exists(*x) is False)
    out(f'- team {run}: hypotheses naming a non-existing method {hyp_bad}/{hyp_all}; '
        f'still in the final ranking {kept}; non-existing in final rankings {fin_bad}/{len(fin)}')


# ================================================================ 6. debate effect per run
out('\n## 6. Debate (MA-coop -> MA-debate, same run)')
for i, (run, states) in enumerate(MA_STATES):
    co, de = runs['MA-coop'][i], runs['MA-debate'][i]
    g1 = sum(1 for b in HARD if hit(de[b]['rank'], 1) and not hit(co[b]['rank'], 1))
    l1 = sum(1 for b in HARD if hit(co[b]['rank'], 1) and not hit(de[b]['rank'], 1))
    up = sum(1 for b in HARD if (de[b]['rank'] or 9) < (co[b]['rank'] or 9))
    down = sum(1 for b in HARD if (de[b]['rank'] or 9) > (co[b]['rank'] or 9))
    changed = sum(1 for b in HARD if any(x['changed'] for x in states[b]['debate']))
    rounds = statistics.mean(len(states[b]['debate']) for b in HARD)
    out(f'- {run}: ranking changed {changed}/{N}; correct method moved up {up}, down {down}; '
        f'Top-1 gains {g1}, losses {l1}; mean rounds {rounds:.2f}')


# ================================================================ 7. subgroup analysis (exploratory)
FEAT = {}
for b in HARD:
    with open(INPUTS_DIR / f'{b[0]}_{b[1]}.json') as fh:
        inp = json.load(fh)
    trace = inp.get('trace', '')
    body = [l for l in trace.split('\n') if l.strip() and not l.startswith('---')]
    first = body[0] if body else ''
    ftype = 'assertion failure' if re.search(r'AssertionFailedError|ComparisonFailure|AssertionError', first) else 'exception'
    vis = 'neither in trace'
    for (f, m) in truth[b]:
        meth = '<init>' if m == f else re.escape(m)
        if re.search(r'\b' + re.escape(f) + r'(\$\w+)*\.' + meth + r'\(', trace):
            vis = 'faulty method in trace'
            break
        if re.search(r'\b' + re.escape(f) + r'(\$\w+)*\.', trace):
            vis = 'only faulty file in trace'
    if b not in SNAP_NAMES:
        with gzip.open(SNAP_DIR / f'{b[0]}_{b[1]}.json.gz', 'rt', encoding='utf-8') as fh:
            SNAP_NAMES[b] = {'files': json.load(fh)['files'], 'cache': {}}
    files = SNAP_NAMES[b]['files']
    fsize = max((len(src) for p, src in files.items() if norm_file(p) in truth_files[b]), default=0)
    FEAT[b] = {'project': b[0], 'SA class': CLASS.get(b, '?'), 'failure type': ftype, 'trace visibility': vis,
               'faulty methods': 'one' if len(truth[b]) == 1 else 'several',
               'faulty files': 'one' if len(truth_files[b]) == 1 else 'several',
               'patch_rows': gt_rows[b], 'n_files': len(files), 'faulty_file_chars': fsize}
for num, name in (('patch_rows', 'patch size'), ('n_files', 'project size'), ('faulty_file_chars', 'faulty file size')):
    med = statistics.median(FEAT[b][num] for b in HARD)
    for b in HARD:
        FEAT[b][name] = f'small (<= {med:g})' if FEAT[b][num] <= med else f'large (> {med:g})'

GROUPS = ['project', 'SA class', 'failure type', 'trace visibility', 'faulty methods', 'faulty files',
          'patch size', 'project size', 'faulty file size']
SHOW = [c for c in ['SA', 'SA-sameFiles', 'MA-coop', 'MA-debate'] if runs[c]]


def mean_top(c, bugs, k):
    return statistics.mean(sum(hit(d[b]['rank'], k) for b in bugs) / len(bugs) for d in runs[c])


out('\n## 7. Subgroups (EXPLORATORY: small groups, no significance claims). Mean Top-1 / Top-5 over runs')
for g in GROUPS:
    out(f'\n### by {g}')
    out('| group | bugs | ' + ' | '.join(f'{c} T1 / T5' for c in SHOW) + ' | MA-debate - SA (T1) |')
    out('|---|---|' + '---|' * (len(SHOW) + 1))
    vals = sorted(set(FEAT[b][g] for b in HARD))
    for v in vals:
        bugs = [b for b in HARD if FEAT[b][g] == v]
        cells = [f'{mean_top(c, bugs, 1):.0%} / {mean_top(c, bugs, 5):.0%}' for c in SHOW]
        diff = (mean_top('MA-debate', bugs, 1) - mean_top('SA', bugs, 1)) * 100 if runs['MA-debate'] and runs['SA'] else 0
        out(f'| {v} | {len(bugs)} | ' + ' | '.join(cells) + f' | {diff:+.0f} pts |')

# where the misses happen
out('\n### Where the misses happen (Top-5 misses: file not read vs file read but wrong method)')
for c in ['SA', 'SA-sameFiles', 'MA-coop', 'MA-debate']:
    for i, d in enumerate(runs[c]):
        miss = [b for b in HARD if not hit(d[b]['rank'], 5)]
        fm = sum(1 for b in miss if not file_hit(d[b]['files'], b))
        out(f'- {c} run {i + 1}: {len(miss)} misses = {fm} file misses + {len(miss) - fm} method misses')


# ================================================================ 8. per-bug table + save
out('\n## 8. Per-bug ranks (runs separated by /, - = not in top 5)')
cols = [c for c in CONFIGS]
out('| bug | ' + ' | '.join(cols) + ' | SA class | trace visibility |')
out('|---|' + '---|' * (len(cols) + 2))
with open(AN_DIR / 'per_bug_all.csv', 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['project', 'bug_id', 'config', 'run', 'rank'] + list(FEAT[HARD[0]].keys()))
    for b in HARD:
        row = []
        for c in cols:
            row.append('/'.join(str(d[b]['rank'] or '-') for d in runs[c]))
            for i, d in enumerate(runs[c], 1):
                w.writerow([b[0], b[1], c, i, d[b]['rank'] or ''] + list(FEAT[b].values()))
        out(f'| {b[0]}-{b[1]} | ' + ' | '.join(row) + f' | {FEAT[b]["SA class"]} | {FEAT[b]["trace visibility"]} |')

(AN_DIR / 'analysis_report.md').write_text('\n'.join(REPORT), encoding='utf-8')
print(f'\nSaved: {AN_DIR / "analysis_report.md"} and {AN_DIR / "per_bug_all.csv"}')
