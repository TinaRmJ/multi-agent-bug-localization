# Analysis report (Cell 15)
Hard bugs: 51. Runs available: SA 3, SA-budget 1, SA-sameFiles 3, MA-hyp 3, MA-coop 3, MA-debate 3

## 1. Main results (mean over runs; sd over runs in brackets)
| Config | runs | Top-1 | Top-3 | Top-5 | MRR | file recall | median latency s | tokens/bug in | out+think |
|---|---|---|---|---|---|---|---|---|---|
| SA | 3 | 52.9% (0.0) | 60.8% (3.4) | 60.8% (3.4) | 0.565 (0.014) | 39.0/51 | 21.0 | 24,823 | 7,666 |
| SA-budget | 1 | 52.9% | 74.5% | 74.5% | 0.624 | - | - | - | - |
| SA-sameFiles | 3 | 56.2% (1.1) | 64.1% (1.1) | 64.1% (1.1) | 0.598 (0.006) | 41.0/51 | 12.5 | 26,956 | 6,626 |
| MA-hyp | 3 | 56.9% (2.0) | 64.7% (5.2) | 64.7% (5.2) | 0.603 (0.014) | 41.0/51 | 115.1 | 52,287 | 30,804 |
| MA-coop | 3 | 56.9% (0.0) | 62.1% (5.7) | 62.1% (5.7) | 0.593 (0.025) | 41.0/51 | 115.1 | 52,287 | 30,804 |
| MA-debate | 3 | 55.6% (1.1) | 64.1% (4.1) | 64.1% (4.1) | 0.592 (0.014) | 41.0/51 | 115.1 | 52,287 | 30,804 |
(MA-hyp, MA-coop and MA-debate come from the same team runs; their latency/tokens are those of the whole team run.)

## 2. Paired statistics (unit = bug, 51 pairs; majority outcome over runs; mean RR per bug)
| A vs B | Top-1 A-only / B-only | McNemar p | Top-5 A-only / B-only | McNemar p | MRR A - B | Wilcoxon p | 95% CI Top-1 diff | 95% CI MRR diff |
|---|---|---|---|---|---|---|---|---|
| MA-coop vs SA | 5 / 1 | 0.219 | 6 / 5 | 1.000 | +0.027 | 0.696 | [+0.0, +17.6] pts | [-0.042, +0.108] |
| MA-debate vs SA | 5 / 1 | 0.219 | 6 / 3 | 0.508 | +0.026 | 0.974 | [+0.0, +17.6] pts | [-0.039, +0.102] |
| MA-debate vs SA-budget | 5 / 2 | 0.453 | 3 / 7 | 0.344 | -0.033 | 0.180 | [-3.9, +15.7] pts | [-0.112, +0.056] |
| MA-coop vs SA-sameFiles | 3 / 1 | 0.625 | 2 / 2 | 1.000 | -0.005 | 0.399 | [-3.9, +11.8] pts | [-0.059, +0.054] |
| MA-coop vs MA-hyp | 2 / 0 | 0.500 | 0 / 0 | 1.000 | -0.011 | 0.397 | [+0.0, +9.8] pts | [-0.038, +0.013] |
| MA-debate vs MA-coop | 0 / 0 | 1.000 | 2 / 0 | 0.500 | -0.001 | 0.932 | [+0.0, +0.0] pts | [-0.019, +0.016] |

### Sensitivity: McNemar per run (run i of A vs run i of B)
- MA-coop vs SA: run1 Top-1 7/5 p=0.774; run1 Top-5 6/8 p=0.791; run2 Top-1 6/4 p=0.754; run2 Top-5 9/3 p=0.146; run3 Top-1 5/3 p=0.727; run3 Top-5 5/7 p=0.774
- MA-debate vs SA: run1 Top-1 7/5 p=0.774; run1 Top-5 6/7 p=1.000; run2 Top-1 6/5 p=1.000; run2 Top-5 9/3 p=0.146; run3 Top-1 4/3 p=1.000; run3 Top-5 5/5 p=1.000
- MA-debate vs SA-budget: run1 Top-1 6/4 p=0.754; run1 Top-5 3/10 p=0.092
- MA-coop vs SA-sameFiles: run1 Top-1 2/2 p=1.000; run1 Top-5 2/5 p=0.453; run2 Top-1 2/2 p=1.000; run2 Top-5 4/1 p=0.375; run3 Top-1 4/3 p=1.000; run3 Top-5 1/4 p=0.375
- MA-coop vs MA-hyp: run1 Top-1 1/2 p=1.000; run1 Top-5 0/2 p=0.500; run2 Top-1 1/0 p=1.000; run2 Top-5 0/1 p=1.000; run3 Top-1 1/1 p=1.000; run3 Top-5 0/1 p=1.000
- MA-debate vs MA-coop: run1 Top-1 0/0 p=1.000; run1 Top-5 1/0 p=1.000; run2 Top-1 1/2 p=1.000; run2 Top-5 0/0 p=1.000; run3 Top-1 0/1 p=1.000; run3 Top-5 2/0 p=0.500

## 3. Consistency across runs (Top-5 found / not found)
| Config | runs | same outcome in all runs | always found | never found | unstable |
|---|---|---|---|---|---|
| SA | 3 | 37/51 | 24 | 13 | 14 |
| SA-sameFiles | 3 | 43/51 | 29 | 14 | 8 |
| MA-hyp | 3 | 36/51 | 26 | 10 | 15 |
| MA-coop | 3 | 38/51 | 25 | 13 | 13 |
| MA-debate | 3 | 37/51 | 25 | 12 | 14 |

## 4. File choice (does a chosen file contain a faulty method?)
- SA run 1: file recall 39/51
- SA run 2: file recall 37/51
- SA run 3: file recall 41/51
- team ma_run: Trace Interpreter alone 40/51, Inspector alone 37/51, union 42/51; only TI found it 5, only Inspector found it 2; avg files read 3.1
- team ma_run2: Trace Interpreter alone 40/51, Inspector alone 38/51, union 42/51; only TI found it 4, only Inspector found it 2; avg files read 3.1
- team ma_run3: Trace Interpreter alone 36/51, Inspector alone 36/51, union 39/51; only TI found it 3, only Inspector found it 3; avg files read 3.0

## 5. Methods that do not exist in the project (misleading inferences)
- SA run 1: 3 of 84 named methods do not exist
- SA run 2: 4 of 89 named methods do not exist
- SA run 3: 4 of 97 named methods do not exist
- team ma_run: hypotheses naming a non-existing method 3/107; still in the final ranking 2; non-existing in final rankings 3/115
- team ma_run2: hypotheses naming a non-existing method 4/100; still in the final ranking 1; non-existing in final rankings 1/114
- team ma_run3: hypotheses naming a non-existing method 4/90; still in the final ranking 2; non-existing in final rankings 4/118

## 6. Debate (MA-coop -> MA-debate, same run)
- ma_run: ranking changed 26/51; correct method moved up 1, down 0; Top-1 gains 0, losses 0; mean rounds 1.51
- ma_run2: ranking changed 23/51; correct method moved up 1, down 2; Top-1 gains 1, losses 2; mean rounds 1.45
- ma_run3: ranking changed 28/51; correct method moved up 2, down 2; Top-1 gains 0, losses 1; mean rounds 1.55

## 7. Subgroups (EXPLORATORY: small groups, no significance claims). Mean Top-1 / Top-5 over runs

### by project
| group | bugs | SA T1 / T5 | SA-sameFiles T1 / T5 | MA-coop T1 / T5 | MA-debate T1 / T5 | MA-debate - SA (T1) |
|---|---|---|---|---|---|---|
| Chart | 2 | 17% / 50% | 0% / 17% | 0% / 17% | 0% / 17% | -17 pts |
| Cli | 7 | 43% / 52% | 43% / 48% | 62% / 67% | 52% / 76% | +10 pts |
| Closure | 18 | 56% / 61% | 59% / 70% | 57% / 61% | 59% / 63% | +4 pts |
| Compress | 4 | 42% / 75% | 58% / 83% | 58% / 67% | 50% / 67% | +8 pts |
| Csv | 1 | 100% / 100% | 100% / 100% | 100% / 100% | 100% / 100% | +0 pts |
| Gson | 3 | 78% / 78% | 100% / 100% | 78% / 89% | 78% / 89% | +0 pts |
| JacksonCore | 4 | 58% / 67% | 50% / 58% | 58% / 67% | 58% / 67% | +0 pts |
| Jsoup | 5 | 80% / 80% | 80% / 80% | 73% / 73% | 73% / 73% | -7 pts |
| Lang | 3 | 33% / 33% | 33% / 33% | 33% / 33% | 33% / 33% | +0 pts |
| Math | 1 | 100% / 100% | 100% / 100% | 100% / 100% | 100% / 100% | +0 pts |
| Time | 3 | 11% / 11% | 22% / 22% | 22% / 33% | 22% / 33% | +11 pts |

### by SA class
| group | bugs | SA T1 / T5 | SA-sameFiles T1 / T5 | MA-coop T1 / T5 | MA-debate T1 / T5 | MA-debate - SA (T1) |
|---|---|---|---|---|---|---|
| SA always found | 24 | 93% / 100% | 90% / 99% | 90% / 94% | 89% / 96% | -4 pts |
| SA never found | 13 | 0% / 0% | 15% / 15% | 21% / 23% | 21% / 23% | +21 pts |
| SA unstable | 14 | 33% / 50% | 36% / 50% | 33% / 43% | 31% / 48% | -2 pts |

### by failure type
| group | bugs | SA T1 / T5 | SA-sameFiles T1 / T5 | MA-coop T1 / T5 | MA-debate T1 / T5 | MA-debate - SA (T1) |
|---|---|---|---|---|---|---|
| assertion failure | 39 | 52% / 59% | 57% / 64% | 56% / 61% | 55% / 62% | +3 pts |
| exception | 12 | 56% / 67% | 53% / 64% | 58% / 67% | 58% / 72% | +3 pts |

### by trace visibility
| group | bugs | SA T1 / T5 | SA-sameFiles T1 / T5 | MA-coop T1 / T5 | MA-debate T1 / T5 | MA-debate - SA (T1) |
|---|---|---|---|---|---|---|
| faulty method in trace | 2 | 50% / 50% | 50% / 50% | 100% / 100% | 100% / 100% | +50 pts |
| neither in trace | 45 | 53% / 61% | 56% / 64% | 56% / 60% | 54% / 62% | +1 pts |
| only faulty file in trace | 4 | 58% / 58% | 58% / 67% | 50% / 67% | 50% / 67% | -8 pts |

### by faulty methods
| group | bugs | SA T1 / T5 | SA-sameFiles T1 / T5 | MA-coop T1 / T5 | MA-debate T1 / T5 | MA-debate - SA (T1) |
|---|---|---|---|---|---|---|
| one | 41 | 58% / 61% | 62% / 66% | 63% / 66% | 61% / 67% | +3 pts |
| several | 10 | 33% / 60% | 33% / 57% | 33% / 47% | 33% / 50% | +0 pts |

### by faulty files
| group | bugs | SA T1 / T5 | SA-sameFiles T1 / T5 | MA-coop T1 / T5 | MA-debate T1 / T5 | MA-debate - SA (T1) |
|---|---|---|---|---|---|---|
| one | 46 | 56% / 62% | 60% / 66% | 60% / 64% | 59% / 67% | +4 pts |
| several | 5 | 27% / 47% | 20% / 47% | 27% / 40% | 20% / 40% | -7 pts |

### by patch size
| group | bugs | SA T1 / T5 | SA-sameFiles T1 / T5 | MA-coop T1 / T5 | MA-debate T1 / T5 | MA-debate - SA (T1) |
|---|---|---|---|---|---|---|
| large (> 2) | 20 | 37% / 53% | 33% / 48% | 38% / 47% | 37% / 52% | +0 pts |
| small (<= 2) | 31 | 63% / 66% | 71% / 74% | 69% / 72% | 68% / 72% | +4 pts |

### by project size
| group | bugs | SA T1 / T5 | SA-sameFiles T1 / T5 | MA-coop T1 / T5 | MA-debate T1 / T5 | MA-debate - SA (T1) |
|---|---|---|---|---|---|---|
| large (> 106) | 25 | 48% / 57% | 53% / 63% | 52% / 57% | 52% / 59% | +4 pts |
| small (<= 106) | 26 | 58% / 64% | 59% / 65% | 62% / 67% | 59% / 69% | +1 pts |

### by faulty file size
| group | bugs | SA T1 / T5 | SA-sameFiles T1 / T5 | MA-coop T1 / T5 | MA-debate T1 / T5 | MA-debate - SA (T1) |
|---|---|---|---|---|---|---|
| large (> 21791) | 25 | 44% / 53% | 49% / 56% | 48% / 53% | 47% / 53% | +3 pts |
| small (<= 21791) | 26 | 62% / 68% | 63% / 72% | 65% / 71% | 64% / 74% | +3 pts |

### Where the misses happen (Top-5 misses: file not read vs file read but wrong method)
- SA run 1: 19 misses = 12 file misses + 7 method misses
- SA run 2: 22 misses = 14 file misses + 8 method misses
- SA run 3: 19 misses = 10 file misses + 9 method misses
- SA-sameFiles run 1: 18 misses = 9 file misses + 9 method misses
- SA-sameFiles run 2: 19 misses = 9 file misses + 10 method misses
- SA-sameFiles run 3: 18 misses = 10 file misses + 8 method misses
- MA-coop run 1: 21 misses = 8 file misses + 13 method misses
- MA-coop run 2: 16 misses = 8 file misses + 8 method misses
- MA-coop run 3: 21 misses = 11 file misses + 10 method misses
- MA-debate run 1: 20 misses = 8 file misses + 12 method misses
- MA-debate run 2: 16 misses = 8 file misses + 8 method misses
- MA-debate run 3: 19 misses = 11 file misses + 8 method misses

## 8. Per-bug ranks (runs separated by /, - = not in top 5)
| bug | SA | SA-budget | SA-sameFiles | MA-hyp | MA-coop | MA-debate | SA class | trace visibility |
|---|---|---|---|---|---|---|---|---|
| Chart-15 | 2/-/2 | 2 | 2/-/- | -/2/- | -/2/- | -/2/- | SA unstable | neither in trace |
| Chart-26 | -/1/- | 2 | -/-/- | -/-/- | -/-/- | -/-/- | SA unstable | neither in trace |
| Cli-2 | 2/-/3 | 2 | -/-/- | -/-/- | -/-/- | 3/-/3 | SA unstable | neither in trace |
| Cli-9 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/2/1 | SA always found | neither in trace |
| Cli-13 | 1/-/- | 1 | -/-/3 | -/3/1 | -/3/1 | -/3/2 | SA unstable | neither in trace |
| Cli-14 | -/-/- | - | -/-/- | 1/1/1 | 1/1/1 | 1/1/1 | SA never found | faulty method in trace |
| Cli-15 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Cli-16 | -/-/- | - | -/-/- | -/-/- | -/-/- | -/-/- | SA never found | only faulty file in trace |
| Cli-27 | 1/-/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA unstable | neither in trace |
| Closure-1 | -/-/- | - | -/-/- | -/-/- | -/-/- | -/-/- | SA never found | neither in trace |
| Closure-4 | 1/1/1 | 1 | 2/1/2 | 1/3/2 | 1/2/1 | 1/1/1 | SA always found | neither in trace |
| Closure-5 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Closure-7 | 1/1/1 | 1 | 1/1/1 | 1/1/- | 1/1/- | 1/1/- | SA always found | neither in trace |
| Closure-9 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Closure-10 | -/-/- | - | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA never found | neither in trace |
| Closure-12 | -/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA unstable | neither in trace |
| Closure-13 | -/-/- | - | -/-/- | -/-/- | -/-/- | -/-/- | SA never found | neither in trace |
| Closure-18 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Closure-23 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Closure-24 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Closure-26 | 3/2/2 | 3 | 3/3/2 | -/2/- | -/2/- | -/2/2 | SA always found | neither in trace |
| Closure-31 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Closure-33 | -/-/- | - | -/-/- | -/-/- | -/-/- | -/-/- | SA never found | neither in trace |
| Closure-35 | -/-/- | - | 1/-/- | 1/-/- | -/-/- | -/-/- | SA never found | neither in trace |
| Closure-36 | -/-/- | - | -/-/- | -/-/- | -/-/- | -/-/- | SA never found | neither in trace |
| Closure-38 | 1/-/1 | 1 | 1/1/1 | 1/1/- | 1/1/- | 1/1/- | SA unstable | neither in trace |
| Closure-39 | 1/-/1 | 1 | -/-/2 | -/-/1 | -/-/1 | -/-/1 | SA unstable | neither in trace |
| Compress-1 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Compress-3 | 1/-/- | 2 | -/-/1 | -/-/1 | -/-/1 | -/-/1 | SA unstable | neither in trace |
| Compress-4 | 2/2/- | 3 | 2/2/2 | -/2/- | -/2/- | -/2/- | SA unstable | neither in trace |
| Compress-25 | 2/1/2 | 2 | 1/1/1 | 1/1/1 | 1/1/1 | 1/3/1 | SA always found | neither in trace |
| Csv-15 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Gson-2 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Gson-3 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Gson-18 | -/1/- | 2 | 1/1/1 | 2/-/2 | 1/-/2 | 1/-/3 | SA unstable | only faulty file in trace |
| JacksonCore-1 | -/-/3 | 3 | -/-/- | -/3/- | -/-/- | -/-/- | SA unstable | neither in trace |
| JacksonCore-7 | -/-/1 | 3 | 1/1/- | 1/1/- | 1/1/- | 1/1/- | SA unstable | neither in trace |
| JacksonCore-10 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | only faulty file in trace |
| JacksonCore-11 | 1/1/1 | 1 | -/2/1 | 2/2/1 | 2/1/1 | 2/1/1 | SA always found | only faulty file in trace |
| Jsoup-2 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Jsoup-4 | -/-/- | - | -/-/- | -/-/- | -/-/- | -/-/- | SA never found | neither in trace |
| Jsoup-12 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | faulty method in trace |
| Jsoup-15 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | -/1/1 | -/1/1 | SA always found | neither in trace |
| Jsoup-23 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Lang-8 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Lang-9 | -/-/- | - | -/-/- | -/-/1 | -/-/- | -/-/- | SA never found | neither in trace |
| Lang-10 | -/-/- | - | -/-/- | -/-/- | -/-/- | -/-/- | SA never found | neither in trace |
| Math-20 | 1/1/1 | 1 | 1/1/1 | 1/1/1 | 1/1/1 | 1/1/1 | SA always found | neither in trace |
| Time-3 | -/-/- | - | -/-/- | -/3/- | -/3/- | -/3/- | SA never found | neither in trace |
| Time-22 | -/-/- | - | 1/1/- | 1/1/- | 1/1/- | 1/1/- | SA never found | neither in trace |
| Time-27 | -/1/- | 2 | -/-/- | -/-/- | -/-/- | -/-/- | SA unstable | neither in trace |
