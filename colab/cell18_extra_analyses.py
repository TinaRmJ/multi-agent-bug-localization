# === Cell 18: three extra analyses + two figures (no model calls, no cost) ===
# Needs only Cell 1. Uses the stored team transcripts (Cell 14), SA runs (Cell 13) and SA-sameFiles runs (Cell 16).
#  (A) "The team knew it but lost it": bugs where SOME agent named a correct method at some point,
#      but the final ranking does not contain it (and which agent had named it).
#  (B) Funnel: where are bugs lost? (faulty file read -> correct method named -> hypotheses -> coop -> debate)
#  (C) Accuracy vs cost figure for all configurations.
# Writes to Drive results_L2/analysis/: extra_analyses.md, fig_funnel.png, fig_accuracy_cost.png
import csv, json, re, statistics
from collections import defaultdict, Counter
import matplotlib
import matplotlib.pyplot as plt

GT_ALL = BASE / 'ground_truth_all.csv'
HARD_PATH = BASE / 'hard_bugs.csv'
AN_DIR = OUT_DIR / 'analysis'
AN_DIR.mkdir(exist_ok=True)
SA_RUNS = ['hard_run1', 'hard_run2', 'hard_run3']
MA_RUNS = ['ma_run', 'ma_run2', 'ma_run3']          # team run 1 was stored as 'ma_run'
SAME_RUNS = ['same_ma_run1', 'same_ma_run2', 'same_ma_run3']
LINES = []

# colors (fixed order, colorblind-checked reference palette)
C_TEAM, C_SA, C_SAME, C_BUDGET, C_HYP = '#257de0', '#f47230', '#00b894', '#f2a600', '#6a4ce2'
INK, INK2, GRID = '#191919', '#666666', '#e6e6e6'


def out(s=''):
    print(s)
    LINES.append(s)


def norm_file(f):
    return str(f).strip().rsplit('/', 1)[-1].replace('.java', '').split('$')[0]


def norm_method(m):
    return str(m).strip().split('(')[0].rsplit('.', 1)[-1].strip()


def key_of(it):
    return (norm_file(it.get('file', '')), norm_method(it.get('method', '')))


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


def as_list(x):
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


with open(HARD_PATH) as f:
    HARD = [(r['project'], int(r['bug_id'])) for r in csv.DictReader(f)]
N = len(HARD)
truth, truth_files = defaultdict(set), defaultdict(set)
with open(GT_ALL) as f:
    for r in csv.DictReader(f):
        b = (r['project'], int(r['bug_id']))
        truth_files[b].add(norm_file(r['file']))
        if r['method']:
            truth[b].add((norm_file(r['file']), norm_method(r['method'])))


def rank_of(items, b, k=5):
    for i, it in enumerate(items[:k], 1):
        if key_of(it) in truth[b]:
            return i
    return None


# which structured fields of each agent's answer name methods
FIELDS = {'trace_interpreter': ['methods_on_path'], 'inspector_code': ['suspicious'], 'hypothesis': ['hypotheses'],
          'verifier': ['verdicts', 'ranking'], 'critic': ['objections', 'alternatives'],
          'verifier_reply': ['responses', 'ranking']}
NICE = {'trace_interpreter': 'Trace Interpreter', 'inspector_code': 'Inspector', 'hypothesis': 'Hypothesis Formulator',
        'verifier': 'Verifier', 'critic': 'Critic', 'verifier_reply': 'Verifier (debate)'}


def role(agent):
    if agent.startswith('critic_r'):
        return 'critic'
    if agent.startswith('verifier_r'):
        return 'verifier_reply'
    return agent


# ================================================================ (A) + (B) team runs
out('# Extra analyses (Cell 18)')
out(f'Hard bugs: {N}. Team runs: {", ".join(MA_RUNS)}')
STAGES = ['faulty file read', 'correct method named by any agent', 'in hypotheses (top 5)',
          'MA-coop top 5', 'MA-debate top 5', 'MA-debate top 1']
funnel = defaultdict(list)          # stage -> counts per run
lost_all = Counter()                # bug -> number of runs where it was named but lost
named_by = defaultdict(Counter)     # run -> role -> bugs where that role named a correct method
first_by = defaultdict(Counter)     # run -> role that named it FIRST
critic_lost = []                    # (run, bug) critic named correct method, final ranking misses it
runs_ok = 0

out('\n## A. "The team knew it but lost it"')
for run in MA_RUNS:
    sd = OUT_DIR / f'MA_states_{run}'
    if not all((sd / f'{p}_{b}.json').exists() for p, b in HARD):
        out(f'- {run}: incomplete, skipped')
        continue
    runs_ok += 1
    c = Counter()
    lost = []
    for bug in HARD:
        st = json.loads((sd / f'{bug[0]}_{bug[1]}.json').read_text())
        roles_named, first = set(), None
        for call in st['calls']:
            r = role(call['agent'])
            ans = tolerant_json(call['answer'])
            items = [it for fld in FIELDS.get(r, []) for it in as_list(ans.get(fld))]
            if any(key_of(it) in truth[bug] for it in items):
                roles_named.add(r)
                first = first or r
        hyps = []
        for call in st['calls']:
            if call['agent'] == 'hypothesis':
                hyps = as_list(tolerant_json(call['answer']).get('hypotheses'))
        file_read = any(norm_file(x) in truth_files[bug] for x in st['files'])
        r_coop, r_deb = rank_of(st['ranking_coop'], bug), rank_of(st['ranking_debate'], bug)
        c['faulty file read'] += file_read
        c['correct method named by any agent'] += bool(roles_named)
        c['in hypotheses (top 5)'] += rank_of(hyps, bug) is not None
        c['MA-coop top 5'] += r_coop is not None
        c['MA-debate top 5'] += r_deb is not None
        c['MA-debate top 1'] += r_deb == 1
        for r in roles_named:
            named_by[run][r] += 1
        if first:
            first_by[run][first] += 1
        if roles_named and r_deb is None:
            lost.append((bug, sorted(NICE[x] for x in roles_named)))
            lost_all[bug] += 1
            if 'critic' in roles_named:
                critic_lost.append((run, bug))
    for s in STAGES:
        funnel[s].append(c[s])
    named = c['correct method named by any agent']
    out(f'- {run}: a correct method was named by some agent in {named}/{N} bugs, but the final (MA-debate) '
        f'top 5 has it in only {c["MA-debate top 5"]}/{N} -> lost inside the team: {len(lost)} bugs')
    for bug, who in lost:
        out(f'    {bug[0]}-{bug[1]}: named by {", ".join(who)}')
    out(f'    which agents named a correct method (bugs): '
        + ', '.join(f'{NICE[r]} {named_by[run][r]}' for r in FIELDS if named_by[run][r]))
    out(f'    agent that named it FIRST: ' + ', '.join(f'{NICE[r]} {first_by[run][r]}' for r in FIELDS if first_by[run][r]))

if runs_ok:
    out(f'\nBugs lost inside the team in at least 2 of {runs_ok} runs: '
        + (', '.join(f'{p}-{b} ({n}x)' for (p, b), n in sorted(lost_all.items()) if n >= 2) or 'none'))
    out(f'Cases where the CRITIC named a correct method but the final ranking missed it: {len(critic_lost)} '
        f'({", ".join(f"{p}-{b} [{r}]" for r, (p, b) in critic_lost)})')
    out(f'"Oracle" upper bound (correct method named anywhere in the conversation), mean over runs: '
        f'{statistics.mean(funnel["correct method named by any agent"]) / N:.1%} vs MA-debate Top-5 '
        f'{statistics.mean(funnel["MA-debate top 5"]) / N:.1%}')

# ================================================================ SA / SA-sameFiles funnel numbers
def sa_counts(prefix, runs_, files_col):
    res = defaultdict(list)
    for run in runs_:
        p = OUT_DIR / f'{prefix}_results_{run}.csv'
        if not p.exists():
            continue
        rows = {}
        with open(p) as f:
            for r in csv.DictReader(f):
                if r['status'] == 'ok':
                    rows[(r['project'], int(r['bug_id']))] = r
        if len(rows) != N:
            continue
        fr = t5 = t1 = 0
        for b, r in rows.items():
            fr += any(norm_file(x) in truth_files[b] for x in json.loads(r[files_col]))
            rk = rank_of(as_list(json.loads(r['methods'])), b)
            t5 += rk is not None
            t1 += rk == 1
        res['faulty file read'].append(fr)
        res['top 5'].append(t5)
        res['top 1'].append(t1)
    return res


sa = sa_counts('SA', SA_RUNS, 'picked_files')
same = sa_counts('SAsame', SAME_RUNS, 'files')

out('\n## B. Funnel: where are bugs lost? (number of bugs, mean over runs; per run in brackets)')
out('| stage | team | single agent (SA) | SA-sameFiles |')
out('|---|---|---|---|')


def fmt(v):
    return f'{statistics.mean(v):.1f} ({"/".join(map(str, v))})' if v else '-'


rows_tab = [('faulty file read', funnel['faulty file read'], sa['faulty file read'], same['faulty file read']),
            ('correct method named by any agent', funnel['correct method named by any agent'], [], []),
            ('in hypotheses (top 5)', funnel['in hypotheses (top 5)'], [], []),
            ('MA-coop top 5 / SA top 5', funnel['MA-coop top 5'], sa['top 5'], same['top 5']),
            ('MA-debate top 5', funnel['MA-debate top 5'], [], []),
            ('MA-debate top 1 / SA top 1', funnel['MA-debate top 1'], sa['top 1'], same['top 1'])]
for name, a, b, c in rows_tab:
    out(f'| {name} | {fmt(a)} | {fmt(b)} | {fmt(c)} |')
out('Note: "named by any agent" can exceed "faulty file read" because the Trace Interpreter names methods '
    'seen in the stack trace and the method-body tool looks up named methods in the whole project.')

# ---- figure 1: funnel (horizontal bars, team stages; SA reference ticks)
plt.rcParams.update({'font.size': 10, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': INK2, 'ytick.color': INK})
if runs_ok:
    labels = ['Faulty file read', 'Correct method named\nby any agent', 'In hypotheses (top 5)',
              'After verification\n(MA-coop top 5)', 'After debate\n(MA-debate top 5)', 'Final answer at rank 1\n(MA-debate top 1)']
    vals = [statistics.mean(funnel[s]) for s in STAGES]
    sa_ref = {0: sa['faulty file read'], 3: sa['top 5'], 5: sa['top 1']}
    fig, ax = plt.subplots(figsize=(7.5, 4.6), dpi=200)
    y = list(range(len(labels)))[::-1]
    ax.barh(y, vals, height=0.55, color=C_TEAM, label='Multi-agent team')
    for yi, v in zip(y, vals):
        ax.text(v + 0.6, yi, f'{v:.1f}', va='center', color=INK, fontsize=9)
    first = True
    for i, v in sa_ref.items():
        if v:
            m = statistics.mean(v)
            ax.plot([m, m], [y[i] - 0.38, y[i] + 0.38], color=C_SA, lw=2.5,
                    label='Single agent (same stage)' if first else None)
            first = False
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlim(0, N)
    ax.set_xlabel(f'Number of bugs (of {N}), mean over {runs_ok} runs')
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ('top', 'right', 'left'):
        ax.spines[s].set_visible(False)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False, fontsize=9)
    ax.set_title('Where bugs are lost in the multi-agent pipeline', loc='left', color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(AN_DIR / 'fig_funnel.png', bbox_inches='tight')
    plt.show()

# ================================================================ (C) accuracy vs cost
# relative cost = tokens weighted by list price ratio (output+thinking ~6x input), single agent = 1.0
W_OUT = 6.0


def usage(prefix, runs_):
    per = []
    for run in runs_:
        p = OUT_DIR / f'{prefix}_usage_{run}.jsonl'
        if not p.exists():
            continue
        i = o = 0
        with open(p) as f:
            for l in f:
                u = json.loads(l)
                i += u.get('input_tokens', 0)
                o += u.get('output_tokens', 0) + u.get('thinking_tokens', 0)
        per.append((i / N, o / N))
    return (statistics.mean(x[0] for x in per), statistics.mean(x[1] for x in per)) if per else None


u_sa, u_same, u_ma = usage('SA', SA_RUNS), usage('SAsame', SAME_RUNS), usage('MA', MA_RUNS)
# team file-choice calls (needed by SA-sameFiles) from the team usage log
fc = []
for run in MA_RUNS:
    p = OUT_DIR / f'MA_usage_{run}.jsonl'
    if p.exists():
        i = o = 0
        with open(p) as f:
            for l in f:
                u = json.loads(l)
                if u.get('agent') in ('trace_interpreter', 'inspector_files'):
                    i += u.get('input_tokens', 0)
                    o += u.get('output_tokens', 0) + u.get('thinking_tokens', 0)
        fc.append((i / N, o / N))
u_fc = (statistics.mean(x[0] for x in fc), statistics.mean(x[1] for x in fc)) if fc else (0, 0)


def cost(u):
    return u[0] + W_OUT * u[1]


# accuracy = official means from Cell 15 (results_for_writing.md section 12.1)
ACC = {'SA': (52.9, 60.8), 'SA-budget': (52.9, 74.5), 'SA-sameFiles': (56.2, 64.1),
       'MA-hyp': (56.9, 64.7), 'MA-coop': (56.9, 62.1), 'MA-debate': (55.6, 64.1)}
if u_sa and u_ma:
    base = cost(u_sa)
    COST = {'SA': 1.0, 'SA-budget': 3.0,
            'SA-sameFiles': (cost(u_same) + cost(u_fc)) / base if u_same else None,
            'MA-hyp': None, 'MA-coop': None, 'MA-debate': cost(u_ma) / base}
    # stages of the same team run: cost up to that stage is not logged separately, so use the full run
    COST['MA-coop'] = COST['MA-debate']
    COST['MA-hyp'] = COST['MA-debate']
    out('\n## C. Accuracy vs relative cost (single agent = 1.0; cost = input tokens + 6 x output/thinking tokens)')
    out('| config | relative cost | Top-1 | Top-5 |')
    out('|---|---|---|---|')
    for k, (t1, t5) in ACC.items():
        out(f'| {k} | {COST[k]:.2f} | {t1}% | {t5}% |' if COST[k] else f'| {k} | - | {t1}% | {t5}% |')
    out('(SA-sameFiles cost includes the two team file-choice calls it depends on; MA-hyp/coop/debate are stages '
        'of one team run and are shown at the full team cost; MA-hyp/coop stages alone would be somewhat cheaper.)')
    out(f'Team file-choice calls per bug: input {u_fc[0]:,.0f}, output+thinking {u_fc[1]:,.0f}')

    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.6), dpi=200, sharex=True)
    pts = [('SA', C_SA), ('SA-budget', C_BUDGET), ('SA-sameFiles', C_SAME), ('MA-coop', C_TEAM), ('MA-debate', C_HYP)]
    for ax, idx, title in ((axes[0], 0, 'Top-1 accuracy'), (axes[1], 1, 'Top-5 accuracy')):
        shown = [(n, c) for n, c in pts if COST[n] is not None]
        for name, col in shown:
            ax.scatter(COST[name], ACC[name][idx], s=70, color=col, edgecolor='white', linewidth=2, zorder=3, label=name)
        # direct labels, pushed apart vertically when points sit at (almost) the same cost
        lab = sorted(((COST[n], ACC[n][idx], n) for n, _ in shown), key=lambda t: (round(t[0], 1), t[1]))
        ys = {}
        for x, yv, n in lab:
            yl = yv
            for (x2, n2), y2 in ys.items():
                if abs(x2 - x) < 0.4 and abs(y2 - yl) < 2.2:
                    yl = y2 + 2.2
            ys[(x, n)] = yl
            ax.annotate(n, (x, yv), xytext=(x + 0.12, yl), textcoords='data', fontsize=8, color=INK, va='center',
                        arrowprops=dict(arrowstyle='-', color=GRID, lw=0.8) if abs(yl - yv) > 0.5 else None)
        ax.set_title(title, loc='left', color=INK, fontsize=10)
        ax.set_xlabel('Relative cost (single agent = 1)')
        ax.yaxis.grid(True, color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        ax.set_ylim(45, 80)
        ax.set_xlim(0, max(v for v in COST.values() if v) * 1.5)
        for s in ('top', 'right'):
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel('% of 51 hard bugs (mean over runs)')
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc='lower center', ncol=5, frameon=False, fontsize=8, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle('Accuracy versus cost', x=0.01, ha='left', color=INK, fontsize=11)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(AN_DIR / 'fig_accuracy_cost.png', bbox_inches='tight')
    plt.show()

(AN_DIR / 'extra_analyses.md').write_text('\n'.join(LINES), encoding='utf-8')
print(f'\nSaved: {AN_DIR / "extra_analyses.md"}, {AN_DIR / "fig_funnel.png"}, {AN_DIR / "fig_accuracy_cost.png"}')
