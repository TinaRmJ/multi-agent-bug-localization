# === Cell 14: coordinated multi-agent bug localization (MA-coop + MA-debate) ===
# Needs Cell 1 (settings) and Cell 4 (Gemini client: call_model, parse_json).
# Same model and same settings as the single agent (call_model from Cell 4).
#
# Team and order of work (state-based orchestrator):
#   1. Trace Interpreter   : test + trace + file list -> explains failure, picks up to 3 files
#   2. Inspector (files)   : test code + file list (NO trace, independent view) -> picks up to 3 files
#   3. Inspector (code)    : code of the union of both file choices -> suspicious methods
#   4. Hypothesis Formulator: all evidence + bodies of candidate methods -> ranked hypotheses
#   5. Verifier            : checks hypotheses against the code -> ranking  ==> MA-coop result
#   6. Debate (max 2 rounds): Adversarial Critic attacks the ranking and proposes alternatives,
#                            Verifier answers and revises the ranking   ==> MA-debate result
# One run therefore gives BOTH results (before and after the debate).
# The orchestrator only gives tools: method bodies and method-name outlines taken from the
# buggy snapshot. It never uses the answer key.
#
# RUN_ID = 'ma_pilot' -> runs only the 5 PILOT bugs (to measure cost and check the code).
# RUN_ID = 'ma_run1' / 'ma_run2' / 'ma_run3' -> runs all 51 hard bugs.
# Resumable: finished bugs are skipped (one state file per bug in Drive).
import subprocess, sys
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'javalang'], check=True)

import csv, gzip, json, re, time
from itertools import zip_longest
from collections import defaultdict, Counter
import javalang

assert 'call_model' in globals(), 'Run Cell 4 first (Gemini client)'

RUN_ID = 'ma_pilot'
PILOT = [('Chart', 15), ('Cli', 14), ('Closure', 12), ('Jsoup', 2), ('Lang', 9)]

MAX_FILES_PER_AGENT = 3      # same as the single agent's file step
MAX_DEBATE_ROUNDS = 2
MAX_RANK = 5                 # final answer: at most 5 methods (same as single agent)
MAX_BODIES = 12              # method bodies shown to an agent at once
MAX_BODY_CHARS = 6000        # per method (all overloads together)
MAX_OUTLINE_PER_FILE = 300   # method names listed per file
TOKEN_BUDGET = 15_000_000    # safety cap on input tokens for this run

GT_ALL = BASE / 'ground_truth_all.csv'
HARD_PATH = BASE / 'hard_bugs.csv'
STATE_DIR = OUT_DIR / f'MA_states_{RUN_ID}'
STATE_DIR.mkdir(exist_ok=True)
USAGE = OUT_DIR / f'MA_usage_{RUN_ID}.jsonl'


# ================================================================ small helpers
def jsonl(path, obj):
    with open(path, 'a') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def used_tokens():
    if not USAGE.exists():
        return 0
    with open(USAGE) as f:
        return sum(json.loads(l)['input_tokens'] for l in f)


def as_dict(x):
    return x if isinstance(x, dict) else {}


def as_list(x):
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


def norm_file(f):
    """'src/a/b/Foo.java' or 'Foo' -> 'Foo'."""
    return str(f).strip().rsplit('/', 1)[-1].replace('.java', '').split('$')[0]


def norm_method(m):
    """'Foo.bar(int)' -> 'bar'."""
    return str(m).strip().split('(')[0].rsplit('.', 1)[-1].strip()


def key_of(item):
    return (norm_file(item.get('file', '')), norm_method(item.get('method', '')))


def short(items, fields=('file', 'method')):
    """Compact JSON of a list of dicts, keeping only some fields (saves tokens)."""
    return json.dumps([{k: i.get(k, '') for k in fields} for i in items], ensure_ascii=False)


def match_files(picked, all_files, k):
    """Map the model's file answers to real paths (exact path or same basename)."""
    by_base = {}
    for p in all_files:
        by_base.setdefault(p.rsplit('/', 1)[-1], []).append(p)
    out = []
    for p in picked if isinstance(picked, list) else []:
        p = str(p).strip()
        if p in all_files:
            out.append(p)
        else:
            base = p.rsplit('/', 1)[-1]
            if not base.endswith('.java'):
                base += '.java'
            out.extend(by_base.get(base, [])[:1])
    return list(dict.fromkeys(out))[:k]


# ================================================================ code tools (from the snapshot)
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
    """(first_line, last_line, name) of every method/constructor with a body."""
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
    return sorted(spans)


class CodeTools:
    """Gives agents method bodies and method-name outlines of the buggy version."""

    def __init__(self, snap):
        self.files = snap['files']
        self.cache = {}

    def spans(self, path):
        if path not in self.cache:
            try:
                self.cache[path] = method_spans(self.files[path])
            except Exception:
                self.cache[path] = []
        return self.cache[path]

    def resolve(self, file_name, preferred):
        base = norm_file(file_name) + '.java'
        for p in list(preferred) + list(self.files):
            if p.rsplit('/', 1)[-1] == base:
                return p
        return None

    def outline(self, paths):
        lines = []
        for p in paths:
            names = list(dict.fromkeys(n for _, _, n in self.spans(p)))[:MAX_OUTLINE_PER_FILE]
            lines.append(f'{p.rsplit("/", 1)[-1]}: ' + ', '.join(names))
        return '\n'.join(lines) or '(none)'

    def bodies(self, candidates, preferred):
        out, seen = [], set()
        for c in candidates:
            f, m = key_of(c)
            if not m or (f, m) in seen:
                continue
            seen.add((f, m))
            path = self.resolve(f, preferred)
            parts = []
            if path:
                src_lines = self.files[path].split('\n')
                parts = ['\n'.join(src_lines[s - 1:e]) for s, e, n in self.spans(path) if n == m]
            if parts:
                out.append(f'=== {f}.java :: {m} ===\n' + '\n\n'.join(parts)[:MAX_BODY_CHARS])
            else:
                out.append(f'=== {f}.java :: {m} === (NOT FOUND in the project code)')
            if len(out) >= MAX_BODIES:
                break
        return '\n\n'.join(out) or '(none)'


# ================================================================ prompts
def ctx(inp, with_trace=True):
    s = f"Failing test: {inp['test']}\n\nTest code:\n{inp.get('test_code', '')}\n\n"
    if with_trace:
        s += f"Error and stack trace:\n{inp['trace']}\n\n"
    return s


def p_trace_interpreter(inp, file_list):
    return f"""You are the Dynamic Trace Interpreter in a debugging team that must find the method containing a bug in a Java project.
Your job: understand the failure from the failing test and its stack trace. You do not see the project code, only the list of its source files.

{ctx(inp)}All source files of the project:
{file_list}

Tasks:
1. In one or two sentences each, say what the test expects and what actually happened.
2. List the project methods (not test methods) that are on the execution path of the failure.
3. Pick at most {MAX_FILES_PER_AGENT} source files that most likely contain the bug, most likely first.
Answer ONLY with JSON:
{{"expected_behavior": "...", "observed_failure": "...", "methods_on_path": [{{"file": "Name.java", "method": "methodName"}}], "files": ["path/one.java"]}}
"""


def p_inspector_files(inp, file_list):
    return f"""You are the Static Code Inspector in a debugging team that must find the method containing a bug in a Java project.
Another teammate analyses the stack trace; you work independently from the test code and the project structure.
First you must choose which source files to read.

{ctx(inp, with_trace=False)}All source files of the project:
{file_list}

Pick at most {MAX_FILES_PER_AGENT} source files whose code is most likely responsible for the behaviour this test checks, most likely first.
Answer ONLY with JSON: {{"files": ["path/one.java"]}}
"""


def p_inspector_code(inp, sources):
    return f"""You are the Static Code Inspector in a debugging team that must find the method containing a bug in a Java project.
Read the code below and find methods with suspicious logic (wrong conditions, missing cases, boundary errors, wrong state handling) related to what the test checks.

{ctx(inp, with_trace=False)}Source code:
{sources}

List at most 8 suspicious methods, most suspicious first, each with a short reason (max 25 words) that points to the suspicious code.
For a constructor, use the class name as the method name.
Answer ONLY with JSON: {{"suspicious": [{{"file": "Name.java", "method": "methodName", "reason": "..."}}]}}
"""


def p_hypothesis(inp, ti, ins, outline, bodies):
    return f"""You are the Hypothesis Formulator in a debugging team that must find the method containing a bug in a Java project.
Combine the evidence of your teammates and formulate hypotheses about the root cause.

{ctx(inp)}Trace Interpreter report:
{json.dumps(ti, ensure_ascii=False)}

Static Code Inspector report:
{json.dumps(ins, ensure_ascii=False)}

Methods available in the inspected files:
{outline}

Code of the candidate methods:
{bodies}

Give at most {MAX_RANK} hypotheses, most likely first. Each names ONE method that contains the bug and says what is wrong in it (max 30 words) and which evidence supports it.
Answer ONLY with JSON: {{"hypotheses": [{{"file": "Name.java", "method": "methodName", "hypothesis": "...", "evidence": "..."}}]}}
"""


def p_verifier(inp, hyps, outline, bodies):
    return f"""You are the Verification and Validation Agent in a debugging team that must find the method containing a bug in a Java project.
Check every hypothesis against the actual code and the test expectation. Reject hypotheses that name methods that do not exist or that contradict the code.

{ctx(inp)}Hypotheses:
{json.dumps(hyps, ensure_ascii=False)}

Methods available in the inspected files:
{outline}

Code of the hypothesised methods:
{bodies}

Give a verdict for each hypothesis, then the final ranking of at most {MAX_RANK} methods most likely to contain the bug, most likely first.
Answer ONLY with JSON:
{{"verdicts": [{{"file": "Name.java", "method": "methodName", "verdict": "supported|weak|rejected", "reason": "..."}}], "ranking": [{{"file": "Name.java", "method": "methodName"}}]}}
"""


def p_critic(inp, ranking, verdicts, outline, bodies):
    return f"""You are the Adversarial Critic in a debugging team that must find the method containing a bug in a Java project.
Your job is to challenge the team's current ranking. Look for counter-evidence against the top-ranked methods and for other methods that could explain the failure better. Be specific and refer to the code. Do not agree just to be polite.

{ctx(inp)}Current ranking (most likely first):
{json.dumps(ranking, ensure_ascii=False)}

Verifier's verdicts:
{json.dumps(verdicts, ensure_ascii=False)}

Methods available in the inspected files:
{outline}

Code of the ranked methods:
{bodies}

Give objections against ranked methods and at most 3 alternative methods (they must exist in the project).
Answer ONLY with JSON:
{{"objections": [{{"file": "Name.java", "method": "methodName", "argument": "..."}}], "alternatives": [{{"file": "Name.java", "method": "methodName", "argument": "..."}}]}}
"""


def p_verifier_reply(inp, ranking, critique, outline, bodies):
    return f"""You are the Verification and Validation Agent in a debugging team that must find the method containing a bug in a Java project.
The Adversarial Critic challenged your ranking. Answer each objection and alternative using the code: accept it only if the code supports it. Then give your revised ranking.

{ctx(inp)}Your current ranking (most likely first):
{json.dumps(ranking, ensure_ascii=False)}

Critic's objections and alternatives:
{json.dumps(critique, ensure_ascii=False)}

Methods available in the inspected files:
{outline}

Code of the ranked and alternative methods:
{bodies}

Answer ONLY with JSON:
{{"responses": [{{"file": "Name.java", "method": "methodName", "decision": "accept|reject", "reason": "..."}}], "ranking": [{{"file": "Name.java", "method": "methodName"}}]}}
"""


# ================================================================ orchestrator
def run_bug(project, bug_id):
    with open(INPUTS_DIR / f'{project}_{bug_id}.json') as f:
        inp = json.load(f)
    with gzip.open(SNAP_DIR / f'{project}_{bug_id}.json.gz', 'rt', encoding='utf-8') as f:
        snap = json.load(f)
    tools = CodeTools(snap)
    all_files = list(snap['files'].keys())
    file_list = '\n'.join(all_files)
    state = {'project': project, 'bug_id': bug_id, 'run_id': RUN_ID, 'status': 'ok', 'calls': [], 'debate': []}
    t_start = time.time()

    def agent(name, prompt):
        text, usage = call_model(prompt)
        state['calls'].append({'agent': name, 'answer': text, **usage})
        jsonl(USAGE, {'project': project, 'bug_id': bug_id, 'agent': name, **usage})
        return as_dict(parse_json(text))

    # 1-2: two independent views choose files
    ti = agent('trace_interpreter', p_trace_interpreter(inp, file_list))
    ti_files = match_files(ti.get('files'), snap['files'], MAX_FILES_PER_AGENT)
    insf = agent('inspector_files', p_inspector_files(inp, file_list))
    ins_files = match_files(insf.get('files'), snap['files'], MAX_FILES_PER_AGENT)
    files = [p for pair in zip_longest(ti_files, ins_files) for p in pair if p]
    files = list(dict.fromkeys(files))
    state['files_ti'], state['files_inspector'], state['files'] = ti_files, ins_files, files
    outline = tools.outline(files)

    # 3: inspector reads the code of all chosen files
    sources = '\n\n'.join(f'=== {p} ===\n{snap["files"][p][:MAX_CHARS_PER_FILE]}' for p in files)
    ins = agent('inspector_code', p_inspector_code(inp, sources))

    # 4: hypotheses from both reports + bodies of all candidate methods
    cands = as_list(ti.get('methods_on_path')) + as_list(ins.get('suspicious'))
    hyp = agent('hypothesis', p_hypothesis(inp, ti, ins, outline, tools.bodies(cands, files)))
    hyps = as_list(hyp.get('hypotheses'))[:MAX_RANK]

    # 5: verification -> cooperative result
    ver = agent('verifier', p_verifier(inp, hyps, outline, tools.bodies(hyps, files)))
    ranking = as_list(ver.get('ranking'))[:MAX_RANK] or hyps
    verdicts = as_list(ver.get('verdicts'))
    state['ranking_coop'] = [{'file': r.get('file', ''), 'method': r.get('method', '')} for r in ranking]

    # 6: adversarial debate
    for rnd in range(1, MAX_DEBATE_ROUNDS + 1):
        crit = agent(f'critic_r{rnd}', p_critic(inp, json.loads(short(ranking)), verdicts, outline,
                                                tools.bodies(ranking, files)))
        alts = as_list(crit.get('alternatives'))[:3]
        reply = agent(f'verifier_r{rnd}', p_verifier_reply(inp, json.loads(short(ranking)), crit, outline,
                                                            tools.bodies(ranking + alts, files)))
        new = as_list(reply.get('ranking'))[:MAX_RANK] or ranking
        changed = [key_of(x) for x in new] != [key_of(x) for x in ranking]
        state['debate'].append({'round': rnd, 'changed': changed,
                                'n_objections': len(as_list(crit.get('objections'))), 'n_alternatives': len(alts)})
        ranking = new
        if not changed:
            break
    state['ranking_debate'] = [{'file': r.get('file', ''), 'method': r.get('method', '')} for r in ranking]
    state['latency_s'] = round(time.time() - t_start, 1)
    return state


# ================================================================ run
if RUN_ID == 'ma_pilot':
    BUGLIST = PILOT
else:
    with open(HARD_PATH) as f:
        BUGLIST = [(r['project'], int(r['bug_id'])) for r in csv.DictReader(f)]

todo = [b for b in BUGLIST if not (STATE_DIR / f'{b[0]}_{b[1]}.json').exists()]
print(f'{RUN_ID}: {len(BUGLIST)} bugs, {len(todo)} still to run; input tokens used: {used_tokens():,}')
for i, (project, bug_id) in enumerate(todo, 1):
    if used_tokens() > TOKEN_BUDGET:
        print('TOKEN BUDGET REACHED, stopping.')
        break
    try:
        st = run_bug(project, bug_id)
        (STATE_DIR / f'{project}_{bug_id}.json').write_text(json.dumps(st, ensure_ascii=False))
        print(f'[{i}/{len(todo)}] {project}-{bug_id}: ok  calls={len(st["calls"])}  '
              f'debate_rounds={len(st["debate"])}  {st["latency_s"]}s')
    except Exception as e:
        # API or parsing errors are NOT counted as misses; the bug is retried next time
        print(f'[{i}/{len(todo)}] {project}-{bug_id}: ERROR (will retry next run): {str(e)[:150]}')


# ================================================================ summary
truth, truth_files = defaultdict(set), defaultdict(set)
with open(GT_ALL) as f:
    for r in csv.DictReader(f):
        k = (r['project'], int(r['bug_id']))
        truth_files[k].add(norm_file(r['file']))
        if r['method']:
            truth[k].add((norm_file(r['file']), norm_method(r['method'])))


def rank_of(ranking, k):
    for i, item in enumerate(ranking, 1):
        if key_of(item) in truth[k]:
            return i
    return None


rows = []
for b in BUGLIST:
    p = STATE_DIR / f'{b[0]}_{b[1]}.json'
    if not p.exists():
        continue
    st = json.loads(p.read_text())
    rows.append({'bug': b, 'coop': rank_of(st['ranking_coop'], b), 'debate': rank_of(st['ranking_debate'], b),
                 'file_hit': any(norm_file(x) in truth_files[b] for x in st['files']),
                 'n_files': len(st['files']), 'rounds': len(st['debate']),
                 'changed': any(d['changed'] for d in st['debate']),
                 'tok_in': sum(c['input_tokens'] for c in st['calls']),
                 'tok_out': sum(c['output_tokens'] + c['thinking_tokens'] for c in st['calls']),
                 'latency': st['latency_s']})

with open(OUT_DIR / f'MA_per_bug_{RUN_ID}.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['project', 'bug_id', 'rank_coop', 'rank_debate', 'file_hit', 'n_files', 'debate_rounds',
                'debate_changed', 'input_tokens', 'output_plus_thinking_tokens', 'latency_s'])
    for r in rows:
        w.writerow([*r['bug'], r['coop'] or '', r['debate'] or '', r['file_hit'], r['n_files'], r['rounds'],
                    r['changed'], r['tok_in'], r['tok_out'], r['latency']])

n = len(rows)
print(f'\nMULTI-AGENT ({RUN_ID}): {n} bugs evaluated')
if n:
    for name in ('coop', 'debate'):
        tops = [sum(1 for r in rows if r[name] and r[name] <= k) for k in (1, 3, 5)]
        mrr = sum(1 / r[name] for r in rows if r[name]) / n
        print(f'MA-{name:<7} Top-1 {tops[0]}/{n} = {tops[0] / n:.1%}   Top-3 {tops[1] / n:.1%}   '
              f'Top-5 {tops[2] / n:.1%}   MRR {mrr:.3f}')
    print(f'Correct file among chosen files: {sum(r["file_hit"] for r in rows)}/{n} '
          f'(avg {sum(r["n_files"] for r in rows) / n:.1f} files per bug)')
    t1_gain = sum(1 for r in rows if r['debate'] == 1 and r['coop'] != 1)
    t1_loss = sum(1 for r in rows if r['coop'] == 1 and r['debate'] != 1)
    print(f'Debate changed the ranking in {sum(r["changed"] for r in rows)}/{n} bugs; '
          f'Top-1 wrong->right {t1_gain}, right->wrong {t1_loss}')
    lat = sorted(r['latency'] for r in rows)
    print(f'Median latency per bug: {lat[len(lat) // 2]:.1f} s')

    # token cost compared with the single agent on the same bugs
    sa_in, sa_out = Counter(), Counter()
    for run in ('hard_run1', 'hard_run2', 'hard_run3'):
        up = OUT_DIR / f'SA_usage_{run}.jsonl'
        if up.exists():
            with open(up) as f:
                for l in f:
                    u = json.loads(l)
                    sa_in[(u['project'], u['bug_id'])] += u['input_tokens'] / 3
                    sa_out[(u['project'], u['bug_id'])] += (u['output_tokens'] + u['thinking_tokens']) / 3
    ma_in, ma_out = sum(r['tok_in'] for r in rows), sum(r['tok_out'] for r in rows)
    s_in, s_out = sum(sa_in[r['bug']] for r in rows), sum(sa_out[r['bug']] for r in rows)
    print(f'Tokens per bug: MA input {ma_in / n:,.0f}, output+thinking {ma_out / n:,.0f}')
    if s_in:
        print(f'Single agent on the same bugs (avg of 3 runs): input {s_in / n:,.0f}, output+thinking {s_out / n:,.0f}')
        print(f'=> MA uses {ma_in / s_in:.1f}x the input tokens and {ma_out / max(s_out, 1):.1f}x the output+thinking tokens')

    # per-bug comparison with the 3 single-agent runs
    sa_rank = defaultdict(dict)
    for run in ('hard_run1', 'hard_run2', 'hard_run3'):
        pp = OUT_DIR / f'SA_per_bug_{run}.csv'
        if pp.exists():
            with open(pp) as f:
                for r in csv.DictReader(f):
                    sa_rank[(r['project'], int(r['bug_id']))][run] = r['rank'] or '-'
    print(f'\n{"bug":<14}{"SA run1/2/3":>14}{"MA-coop":>9}{"MA-debate":>11}')
    for r in rows:
        sa = '/'.join(sa_rank[r['bug']].get(x, '?') for x in ('hard_run1', 'hard_run2', 'hard_run3'))
        print(f'{r["bug"][0] + "-" + str(r["bug"][1]):<14}{sa:>14}{str(r["coop"] or "-"):>9}{str(r["debate"] or "-"):>11}')
