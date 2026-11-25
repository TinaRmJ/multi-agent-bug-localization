# Extra analyses (Cell 18, run 2026-11-25) - output as printed in Colab
Hard bugs: 51. Team runs: ma_run, ma_run2, ma_run3

## A. "The team knew it but lost it"
- ma_run: a correct method was named by some agent in 37/51 bugs, but the final (MA-debate) top 5 has it in only 31/51 -> lost inside the team: 6 bugs
    Chart-15: named by Critic, Verifier (debate)
    Closure-26: named by Critic, Verifier (debate)
    Closure-35: named by Hypothesis Formulator, Inspector, Verifier
    Jsoup-15: named by Hypothesis Formulator, Inspector, Verifier
    Lang-9: named by Critic, Verifier (debate)
    Time-3: named by Trace Interpreter
    which agents named a correct method (bugs): Trace Interpreter 12, Inspector 31, Hypothesis Formulator 32, Verifier 32, Critic 26, Verifier (debate) 34
    agent that named it FIRST: Trace Interpreter 12, Inspector 21, Critic 4
- ma_run2: a correct method was named by some agent in 37/51 bugs, but the final (MA-debate) top 5 has it in only 35/51 -> lost inside the team: 2 bugs
    Cli-2: named by Critic, Verifier (debate)
    JacksonCore-1: named by Hypothesis Formulator, Trace Interpreter, Verifier
    which agents named a correct method (bugs): Trace Interpreter 15, Inspector 32, Hypothesis Formulator 36, Verifier 36, Critic 31, Verifier (debate) 36
    agent that named it FIRST: Trace Interpreter 15, Inspector 20, Hypothesis Formulator 1, Critic 1
- ma_run3: a correct method was named by some agent in 36/51 bugs, but the final (MA-debate) top 5 has it in only 32/51 -> lost inside the team: 4 bugs
    Chart-15: named by Critic, Verifier (debate)
    Lang-9: named by Hypothesis Formulator, Inspector, Verifier
    Time-3: named by Critic, Trace Interpreter, Verifier (debate)
    Time-27: named by Inspector
    which agents named a correct method (bugs): Trace Interpreter 12, Inspector 31, Hypothesis Formulator 31, Verifier 31, Critic 29, Verifier (debate) 34
    agent that named it FIRST: Trace Interpreter 12, Inspector 21, Critic 3

Bugs lost inside the team in at least 2 of 3 runs: Chart-15 (2x), Lang-9 (2x), Time-3 (2x)
Cases where the CRITIC named a correct method but the final ranking missed it: 6 (Chart-15 [ma_run], Closure-26 [ma_run], Lang-9 [ma_run], Cli-2 [ma_run2], Chart-15 [ma_run3], Time-3 [ma_run3])
"Oracle" upper bound (correct method named anywhere in the conversation), mean over runs: 71.9% vs MA-debate Top-5 64.1%

## B. Funnel: where are bugs lost? (number of bugs, mean over runs; per run in brackets)
| stage | team | single agent (SA) | SA-sameFiles |
|---|---|---|---|
| faulty file read | 41.0 (42/42/39) | 39.0 (39/37/41) | 41.0 (42/42/39) |
| correct method named by any agent | 36.7 (37/37/36) | - | - |
| in hypotheses (top 5) | 33.0 (32/36/31) | - | - |
| MA-coop top 5 / SA top 5 | 31.7 (30/35/30) | 31.0 (32/29/32) | 32.7 (33/32/33) |
| MA-debate top 5 | 32.7 (31/35/32) | - | - |
| MA-debate top 1 / SA top 1 | 28.3 (29/28/28) | 27.0 (27/27/27) | 28.7 (29/29/28) |
Note: "named by any agent" can exceed "faulty file read" because the Trace Interpreter names methods seen in the stack trace and the method-body tool looks up named methods in the whole project.

## C. Accuracy vs relative cost (single agent = 1.0; cost = input tokens + 6 x output/thinking tokens)
| config | relative cost | Top-1 | Top-5 |
|---|---|---|---|
| SA | 1.00 | 52.9% | 60.8% |
| SA-budget | 3.00 | 52.9% | 74.5% |
| SA-sameFiles | 1.45 | 56.2% | 64.1% |
| MA-hyp | 3.35 | 56.9% | 64.7% |
| MA-coop | 3.35 | 56.9% | 62.1% |
| MA-debate | 3.35 | 55.6% | 64.1% |
(SA-sameFiles cost includes the two team file-choice calls it depends on; MA-hyp/coop/debate are stages of one team run and are shown at the full team cost; MA-hyp/coop stages alone would be somewhat cheaper.)
Team file-choice calls per bug: input 10,065, output+thinking 4,344

Figures (Drive results_L2/analysis/): fig_funnel.png (horizontal bars of the team stages, SA reference ticks), fig_accuracy_cost.png (two panels Top-1 / Top-5 vs relative cost).
