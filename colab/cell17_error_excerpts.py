# === Cell 17: material for the error analysis + Math-12 check (no model calls, no cost) ===
# Needs only Cell 1. Writes Drive results_L2/analysis/error_analysis_excerpts.md (send this file to Claude).
#  - short transcript excerpts of selected team runs (what each agent did)
#  - average length of the final ranking for SA, MA-coop, MA-debate
#  - the Defects4J patch of Math-12 (to explain why it was skipped in the pilot set)
import csv, json, re, os, subprocess, statistics
from collections import defaultdict, Counter

GT_ALL = BASE / 'ground_truth_all.csv'
HARD_PATH = BASE / 'hard_bugs.csv'
AN_DIR = OUT_DIR / 'analysis'
AN_DIR.mkdir(exist_ok=True)
CASES = [('Cli', 14, 'ma_run'), ('Closure', 10, 'ma_run'), ('Time', 22, 'ma_run'), ('Lang', 9, 'ma_run'),
         ('Jsoup', 15, 'ma_run'), ('Closure', 26, 'ma_run'), ('Cli', 2, 'ma_run')]
LINES = []


def out(s=''):
    print(s)
    LINES.append(s)


def norm_file(f):
    return str(f).strip().rsplit('/', 1)[-1].replace('.java', '').split('$')[0]


def norm_method(m):
    return str(m).strip().split('(')[0].rsplit('.', 1)[-1].strip()


def tolerant_json(text):
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', str(text).strip())
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r'\{.*\}', t, re.S)
        try:
            return json.loads(m.group(0)) if m else {}
        except Exception:
            return {}


def short(s, n=160):
    s = ' '.join(str(s).split())
    return s if len(s) <= n else s[:n] + '...'


def lst(x):
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


def names(items):
    return ', '.join(f"{norm_file(i.get('file', ''))}.{norm_method(i.get('method', ''))}" for i in items) or '(empty)'


truth, truth_files = defaultdict(set), defaultdict(set)
with open(GT_ALL) as f:
    for r in csv.DictReader(f):
        b = (r['project'], int(r['bug_id']))
        truth_files[b].add(norm_file(r['file']))
        if r['method']:
            truth[b].add(f"{norm_file(r['file'])}.{norm_method(r['method'])}")

out('# Error-analysis excerpts (from stored team transcripts)')
for p, b, run in CASES:
    sp = OUT_DIR / f'MA_states_{run}' / f'{p}_{b}.json'
    if not sp.exists():
        out(f'\n## {p}-{b} ({run}): state file missing')
        continue
    st = json.loads(sp.read_text())
    calls = {c['agent']: tolerant_json(c['answer']) for c in st['calls']}
    key = (p, b)
    read_ok = any(norm_file(x) in truth_files[key] for x in st['files'])
    out(f'\n## {p}-{b} (team {run})')
    out(f'- Answer key: {", ".join(sorted(truth[key]))}')
    out(f'- Files: Trace Interpreter {[norm_file(x) for x in st["files_ti"]]}; '
        f'Inspector {[norm_file(x) for x in st["files_inspector"]]}; faulty file read: {read_ok}')
    ti = calls.get('trace_interpreter', {})
    out(f'- Trace Interpreter: expected "{short(ti.get("expected_behavior", ""), 120)}"; '
        f'methods on path: {names(lst(ti.get("methods_on_path")))[:200]}')
    out(f'- Inspector suspicious: ' + '; '.join(
        f"{norm_method(s.get('method', ''))} ({short(s.get('reason', ''), 70)})" for s in lst(calls.get('inspector_code', {}).get('suspicious'))[:4]))
    out(f'- Hypotheses: ' + '; '.join(
        f"{norm_method(h.get('method', ''))}: {short(h.get('hypothesis', ''), 80)}" for h in lst(calls.get('hypothesis', {}).get('hypotheses'))[:4]))
    out(f'- Verifier verdicts: ' + '; '.join(
        f"{norm_method(v.get('method', ''))}={v.get('verdict', '')}" for v in lst(calls.get('verifier', {}).get('verdicts'))))
    out(f'- MA-coop ranking: {names(st["ranking_coop"])}')
    for d in st['debate']:
        r = d['round']
        cr = calls.get(f'critic_r{r}', {})
        out(f'- Debate round {r}: objections: ' + '; '.join(
            f"{norm_method(o.get('method', ''))}: {short(o.get('argument', ''), 80)}" for o in lst(cr.get('objections'))[:2]))
        out(f'  alternatives: {names(lst(cr.get("alternatives")))}; ranking changed: {d["changed"]}')
    out(f'- MA-debate ranking: {names(st["ranking_debate"])}')

# ---- average length of final rankings
out('\n## Average length of the final ranking (number of methods returned)')
with open(HARD_PATH) as f:
    HARD = [(r['project'], int(r['bug_id'])) for r in csv.DictReader(f)]
for run in ('hard_run1', 'hard_run2', 'hard_run3'):
    pth = OUT_DIR / f'SA_results_{run}.csv'
    if pth.exists():
        with open(pth) as f:
            lens = [len(json.loads(r['methods'])) for r in csv.DictReader(f) if r['status'] == 'ok']
        out(f'- SA {run}: mean {statistics.mean(lens):.2f} (counts by length {dict(sorted(Counter(lens).items()))})')
for run in ('ma_run', 'ma_run2', 'ma_run3'):
    sd = OUT_DIR / f'MA_states_{run}'
    files = [sd / f'{p}_{b}.json' for p, b in HARD if (sd / f'{p}_{b}.json').exists()]
    if len(files) == len(HARD):
        sts = [json.loads(x.read_text()) for x in files]
        out(f'- team {run}: MA-coop mean {statistics.mean(len(s["ranking_coop"]) for s in sts):.2f}, '
            f'MA-debate mean {statistics.mean(len(s["ranking_debate"]) for s in sts):.2f}')

# ---- Math-12 patch
out('\n## Math-12 patch (why skipped in the pilot set?)')
D4J = '/content/defects4j'
if not os.path.exists(D4J):
    subprocess.run(['git', 'clone', '-q', 'https://github.com/rjust/defects4j', D4J], check=True)
pp = f'{D4J}/framework/projects/Math/patches/12.src.patch'
out('```')
out(open(pp, encoding='utf-8', errors='replace').read()[:3500] if os.path.exists(pp) else 'patch not found')
out('```')
with open(f'{D4J}/framework/projects/Math/active-bugs.csv') as f:
    active = {int(r['bug.id']) for r in csv.DictReader(f)}
out(f'Math-12 active in this Defects4J version: {12 in active}')

(AN_DIR / 'error_analysis_excerpts.md').write_text('\n'.join(LINES), encoding='utf-8')
print(f'\nSaved: {AN_DIR / "error_analysis_excerpts.md"}')
