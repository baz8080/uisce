# Rules vs LLM for end-time extraction

**2026-08-21.** Question: how much of `uisce-infer`'s LLM work is actually language
understanding, and how much is template filling a regex could do on a CPU? Answer:
**~93% is template filling.** A rules extractor (`src/uisce/rules.py`, `rules-v1`)
covers 92.7% of the corpus with 99.99% agreement against the LLM on the cases it
answers, in 0.6 seconds where a corpus inference run takes ~11 GPU-hours. The
hypothesis is accepted; the architecture is **rules first, LLM fallback for
abstentions** — the same shape data-quality.md already recommended for the overrun
metric ("regex first with an LLM fallback"), now measured for the end-time signal
itself.

This closes the gap model-and-runtime-benchmarks.md left open: that note tested
every way to make the *LLM* faster (concurrency, qwen3.5-9b, speculative decoding,
MoE-on-MLX) and closed them all, but never asked whether most calls needed a model
at all.

## Acceptance criteria, fixed before any measurement

The LLM's demonstrated floor is 219/219 on site-relevant labelled rows (rounds 1+2,
see end-time-eval.md), a 95% lower bound of ~98.3%, so rules must not become the
accuracy bottleneck. Accept iff:

| # | Criterion | Threshold | Measured | |
|---|---|---|---|---|
| 1 | Corpus coverage | ≥ 60% | **92.7%** (10,068/10,860) | pass |
| 2 | Agreement with LLM on answered | ≥ 98%, overall and per emitted class | **99.99%** (10,067/10,068); completion 6,670/6,671, scheduled 3,397/3,397 | pass |
| 3 | After adjudicating every disagreement | rules-wrong ≤ 0.3% of answered AND ≤ LLM-wrong | rules-wrong **0**, LLM-wrong **1** | pass |
| 4 | Labelled rounds | 0 wrong emissions | **0** (round 2: 110/110 answered, 91.7% coverage; round 1: 73/73, 64.0% on the stratified draw) | pass |

Comparison everywhere is `(end_source, local_date, local_time)` at minute
precision. A rules answer on a case the LLM read as `recurrence: daily` counts as
a disagreement even when those three fields match, because the rules record would
drop the window the site expands.

## What rules-v1 is

`extract(start_date, description)` returns the same seven-field dict as prompt v3,
or `None` to abstain. It emits **only** `completion_update` (the
`**Update H:MMam D/M/Y**` header of the block containing an English completion
phrase) and `scheduled_end_with_time` (`until <time> on <date>` and
`estimated completion/restoration time of <time> on <date>` in the newest block).
Everything else abstains by construction:

- `not_found` is never emitted — a template not matching is evidence about the
  rules, not the notice.
- `scheduled_end_date_only` is never emitted — a date without its time becomes
  23:59:59 in `build.py:reported_end_utc`, an up-to-24h silent shift.
- Recurring windows abstain (RECURRENCE_TEXT — now in config.py — plus an
  enumerated-day-list pattern): the window *values* are what needed a language
  model (site.py:recurring_events).
- Lift wording, Irish-only completions, unparseable headers, invalid dates, two
  distinct ends in one block, and any `until` the pattern couldn't read in full
  all abstain.

Measured with `uv run uisce-eval-rules-shadow` (compares rules to the LLM's
latest-per-case JSONL answer for every hash-stable case; disagreements go to
`data/eval/rules_shadow_<date>.csv`) and
`uv run uisce-eval-replay --extractor rules` (scores against the human labels).

## The four corpus disagreements, adjudicated

The first shadow run (pre-freeze) disagreed on 4 of 10,075 answered cases. All
four were read in full:

- **237463 — the LLM is wrong, rules right.** Header `**Update 2:42pm
  02/07/2026**`; the LLM answered 14:22 — a digit transposition of exactly the
  kind it was benchmarked as never making. It stands as the one residual
  disagreement, left in place per the no-backfill rule below.
- **232976 — garbled at source** (`until 6pm on 9 May until 9pm 13 May`), already
  recorded in recurrence_review_2026-08-02.csv; the model reads it as a repeating
  window. Rules took the first `until`. Now abstains.
- **236066 — `17 June, 18 June and19 June`**: the missing space after "and"
  defeated the day-list guard, so rules read a single day where the model
  correctly saw three. Now abstains.
- **240600 — `until 5pm on 05 August until 07 August`**: a date range the model
  reads as recurring; rules took the first end. Now abstains.

Both fixes are strictly narrowing (more abstention, no new emissions), the only
kind of tuning allowed against observed disagreements without a fresh labelled
round. One iteration total; frozen as rules-v1. After the freeze the shadow eval
reads 10,068 answered / 1 disagreement (the LLM's transposition) / 0 on
LLM-recurring cases, and both labelled rounds still show 0 wrong emissions.

## What the LLM keeps (the abstention taxonomy, 792 cases)

| n | LLM class | why rules abstain |
|---|---|---|
| 381 | not_found | no template at all ("we are investigating", boil notices) |
| 117 | completion_update | completion phrase with an unparseable or absent header |
| 108 | scheduled_end_with_time | recurrence wording — model territory |
| 91 | lifted_immediate + not_found | lift wording |
| 27 | scheduled_end_with_time | enumerated day lists |
| 15 | mixed | Irish-only completion (`críoch leis an obair`) |
| 12 | scheduled_end_with_time | an `until` the pattern couldn't read (garbled/range/"further notice") |
| 41 | scheduled_end_with_time | two candidate ends, unusual time forms, other |

Nothing in the residue is a class the rules should have answered: it is exactly
the language-understanding tail the model earns its keep on.

## Rejected alternatives

- **Rules handle recurring windows too.** Rejected without measurement:
  site.py:recurring_events already settled that detection is the easy half and
  the window values needed a model, and 2 of the 4 corpus disagreements were
  range forms the rules mis-read as single ends. Detection patterns here exist
  only to abstain.
- **Rules emit `not_found` for the "we are investigating" template.** Rejected:
  turns absence of a match into a claim, and buys nothing — those cases are
  cheap for the LLM and mostly boil notices that are structurally `not_found`
  anyway.
- **Full replacement, no LLM fallback.** Rejected: 7.3% of the corpus (792
  cases) is real language work — recurring windows, lifts, Irish, garbled text —
  and it is precisely the part with the site's hardest failure modes.
- **Widening the prompt instead of adding rules.** Already rejected for the
  sibling overrun problem (data-quality.md, "regex first with an LLM fallback,
  *not* a widened pv2 prompt"); pv2→pv3 also showed prompt widening costs ~2x
  runtime (end-time-eval.md).
- **Tuning rules against the labelled rounds.** Not done, deliberately: the 234
  labelled rows are the *judge*, so patterns were derived from corpus frequency
  surveys and the shadow eval, and round replays only gated (0 wrong emissions
  before and after the one tuning pass). Residual overfitting risk is real but
  bounded; the clean out-of-sample check is below.

## Consequences for `uisce-infer` (the hybrid)

- Rules records stamp `model: "rules-v1"` and the `prompt_version` whose
  semantics they mirror — the JSONL schema already carries both fields, so no
  migration. Any pattern or precedence change bumps `RULES_VERSION`, the same
  discipline PROMPT_VERSION carries.
- Staleness keys on the model too: bumping RULES_VERSION re-runs only
  rules-produced cases; bumping PROMPT_VERSION re-runs everything, as before.
- **No backfill.** Historical LLM records stand even where the shadow eval shows
  rules would disagree (that is 1 case, and it is the LLM's error): unchanged
  descriptions are never re-extracted, by the same hash-skip rule as always.
  Rules answer new and changed cases only.
- A corpus re-run after a future RULES_VERSION bump costs seconds, not 11 hours,
  which removes the main cost end-time-eval.md attributes to prompt bumps — for
  the 93%, at least.

## Out-of-sample validation (done 2026-08-21)

The shadow eval measures agreement on cases the LLM has already seen and the
labelled rounds predate rules-v1, so the clean check was one fresh round:
`uv run uisce-eval-sample-fresh` (~5 min of GPU for 120 unseen cases), label it,
then `uv run uisce-eval-replay --extractor rules --csv <new round>`. Expected:
0 wrong emissions at ~90% coverage.

**Drawn and inferred the same day (local, GPU):**
`data/eval/end_time_sample_2026-08-21_gemma-4-12b-qat_pv3.csv`, 120 unseen
cases, seed 42. Before any labelling, rules-v1 vs the LLM on those fresh
cases: **coverage 110/120 (91.7%), agreement 110/110, zero disagreements**
(completion 71 agree / 3 abstain, scheduled 39/39 answered, all 7 not_found
abstained). The first hybrid production run the same morning answered 1 of 4
backlog cases with rules and fell back to the LLM for the rest, as designed.

**Human-labelled the same day, and the truth gate passed:** all 120 rows
`correct` for the LLM (pv3's second perfect uniform round), and rules-v1
scored **110/110 on every row it answered — 0 wrong emissions at 91.7%
coverage**, exactly the expectation above. These 120 cases were never used to
derive or tune any pattern, which is what retires the overfitting caveat in
"Rejected alternatives": the evidence now stands on three legs — 354
human-labelled rows across three rounds (0 wrong emissions on all of them),
the 10,860-case corpus shadow, and this unseen draw.

## CI runs the rules half (2026-08-21)

`uisce-infer` grew a `--rules-only` flag and `Build DB` runs it every build: the rules answer what they cover, abstentions are counted and left for a local LLM run, and the JSONL is committed back to `main` after the release is published (so it never references a case the latest release lacks). `data/inferred_end_times.jsonl merge=union` in `.gitattributes` lets CI's appends and a local run's appends merge instead of conflicting; `build.py:latest_per_case` keys on `inferred_at`, so the order the union leaves them in does not matter.

Where the JSONL lives was the real question — esb and lifts keep collected data in `*-data` repos. Two alternatives were rejected:

- **A `uisce-data` repo.** The esb/lifts split exists because the Pi is the writer and the raw logs are the source of truth. Here the source of truth (the DB) is already off-repo as a release, and the JSONL is a derived cache of it. A data repo would add a checkout to every workflow and put the JSONL↔DB freshness guard (above) across two repos, for no gain in history or size — the JSONL costs ~4 MB of packed repo after 39 commits.
- **The JSONL as a release asset beside `uisce.db`.** Two writers on one blob means last upload wins and the other's records are silently lost; git at least conflicts loudly, and `merge=union` resolves it.

## rules-v2: midnight, tanker hours, bilingual completions (2026-09-24)

A review of the 2026-09-23 release found three wrong readings in rules-v1, each emitting or
withholding an answer the site then published. All three are fixed in `rules-v2`, with a
fourth, smaller widening that fell out of checking the cases the review named.

**1. "until midnight on D" after a start on D.** "from 2pm until midnight on 11 September"
(244089) was read as 11 September 00:00, fourteen hours before the works began and before
the notice was published, so build.py nulled the span and the site charged an imputed one.
245031 ("from 8pm until midnight on 29 September") ended twenty hours before its own start.
Now a 00:00 end (midnight, 12am) is read against the `from` directly before its `until`:

- a start earlier the same day (no date of its own, or D): D+1 00:00;
- a start the day before ("from 9pm on 21 May until 12am on 22 May", 233690): D 00:00, as
  before;
- no start, a start two or more days earlier, or `estimated completion time of midnight`:
  abstain. "until midnight on 9 May" alone is either end of the day.

Rejected: always D+1 (turns the 21-to-22 May shape into a 27-hour outage); always the date
as written (the bug); reading the no-start form as the end of D. The last is probably right
(232957 and 234332 were published the afternoon of the D they name, so D 00:00 is already in
their past) but it is a reading, and reading is the model's job.

**2. Tanker hours are not the works' end.** "An alternative water supply will be available
at ... from 4:30pm until 11:59pm on 22 July" was emitted as the end of a pump failure with no
stated end (239696, and pins 239697/239698); the case closed on 25 July. An `until` in
a sentence about an alternative supply (alternative water, tanker, bowser, water station,
bottled water, standpipe) is no longer a candidate end. Where it was the only one the rules
abstain; where it had been competing with the works' own end, which made v1 abstain on two
candidates, the works' end is now read. Rejected: abstaining on any notice that mentions an
alternative supply, which would drop 62 scheduled answers that are right today.

**3. An English completion below an Irish one.** The Irish-completion check ran per block, so
a bilingual update, Irish block first ("11:31rn 23/09/2026 - Tá críoch leis an obair...") and
the English "Update 11:31am 23/09/2026 Works are now complete" below it, abstained on the
Irish block before reaching the English one (244925). The corpus has 129 of these. Now an
Irish completion abstains only when the next block with any text in it carries no English
completion; otherwise the English block's header is read. Rejected: requiring the two
headers to agree. 121 of the 129 do, but the Irish header is the unreliable one (232673 says
`8:17rn` against `8:17pm`, 236544 names March for a June notice, 244926 `4:24rn` against
`4:24pm`) and 3 more do not parse at all (`9:38 rn` with a space), so agreement would throw
away the good header to protect the bad one. 15 Irish-only completions still abstain.

**4. A 24-hour time with a stray `pm`.** `**Update 16:59pm 23/09/2026**` (245025) was
unparseable, so its completion abstained and the stale schedule stood. An hour 13-23
followed by `pm` now reads as the 24-hour time; `14:13am` still abstains. 33 such tokens in
the corpus, 31 with `pm`; the LLM read every one of those it answered as the 24-hour time.

### Measured on the 2026-09-23 release

`uv run uisce-eval-rules-shadow` against the release DB and the committed JSONL: rules-v2
answers 12,822 of 13,556 compared cases (94.6%), agreeing on 12,803 (99.85%), 0 on
LLM-recurring cases. That comparison now includes 2,686 rules-v1 records; against the LLM's
own records alone (10,870 hash-stable gemma cases):

| | rules-v1 | rules-v2 |
|---|---|---|
| answered | 9,970 (91.7%) | 10,137 (93.3%) |
| agree | 9,969 | 10,120 |
| disagree | 1 | 17 |

What moved on those 10,870, by change:

| change | effect | vs the LLM |
|---|---|---|
| midnight, same-day start | 15 ends move to D+1 00:00 | 15 disagree: the LLM is wrong (8 are the pins of one event, 231693-231700) |
| midnight, no usable start | 5 abstain (232219, 232957, 233026, 234332, 239927) | were agreeing on D 00:00 |
| tanker hours | 3 abstain (239696-239698); 29 newly answered | the 3 were agreeing on the tanker's 23:59; the 29 all agree |
| bilingual | 125 newly answered completions | 124 agree; 244190 disagrees |
| 24-hour `pm` | 18 completions, 3 schedules newly answered | all agree |

The 17 disagreements, read in full: the 15 midnight rows; 237463, the LLM's digit
transposition from the rules-v1 section above; and 244190, where the Irish header says
`3:39 in` and the English one `3:49pm`. The rules read the English header, as they do
everywhere; the text cannot say which is true.

Labelled rounds (`uisce-eval-replay --extractor rules`): round 1 73/73 (64.0% coverage,
unchanged); the 2026-08-21 round 113/113 (94.2%, was 110/110); round 2 111/112 (93.3%, was
110/110). The one miss is 231853, "from 4pm until midnight on 30 April", labelled correct at
30 April 00:00. That instant is 15h49m before the notice was published at 15:49 on 30 April;
the label accepted the model's reading and is exactly what fix 1 corrects. The CSV is
recorded data and stays as it is.

`uisce-infer --rules-only` against a copy of the release DB and a copy of the JSONL: 2,716
cases selected (the RULES_VERSION bump makes every rules-v1 record stale), 2,695 answered,
21 left for the LLM. Latest record per case against the committed JSONL:

- 2,683 rules-v1 records restamped `rules-v2` with the identical answer;
- 2 changed: 244089 and 245031, a day later at 00:00;
- 4 stale records replaced: 244845, 244925 and 245025 go from their original schedule to a
  completion (22/09 09:38, 23/09 11:31, 23/09 16:59), 244538 from a superseded schedule to
  the current one;
- 6 never-inferred cases answered (4 scheduled, 2 completion);
- rules-v2 emitted 1,773 `completion_update` and 922 `scheduled_end_with_time`, nothing else.

The first CI build after this merges appends those 2,695 lines (the JSONL goes from 19.8 MB
to 21.1 MB). No historical gemma record changes: the no-backfill rule stands, so the 15 LLM
midnight rows and the 3 tanker rows are still published until the prompt is fixed (roadmap,
"LLM prompt reads 'until midnight on D' as the start of D").

### Build no longer hides a stale record or crashes on a bad one (same day)

Two build.py changes shipped with rules-v2, because the review found both by following the
cases above:

- A case whose newest record `uisce-infer` would redo (description changed, or extractor or
  prompt retired, decided by the same `is_current` the inference run uses) still publishes
  that record, the best there is, but build now prints a `::warning::` listing them. Before
  rules-v2, 244925's completion sat behind a record for its pre-completion text with nothing
  said. On the rules-only run above, 6 remain (5 open): 243084 (its `start_date` is now NULL
  in the DB, so no year resolves), 244237/244239/244243 (recurring), 244597 ("until midnight
  23 September" with no "on") and 244720 (two notices concatenated).
- A model value build cannot read ("24:00", "5pm", "28/04/2026", a window "7:00") is refused
  by `parse_response`, so the case counts as failed and is retried; one already in the JSONL
  is left out with a `::warning::` and its case inferred again. Before, any of them raised in
  build and failed every CI build after it, and a raise after `DROP TABLE` left
  `inferred_cases` empty because the DROP had autocommitted. The rebuild is now one
  transaction. The committed JSONL has 0 such records in 33,974.
