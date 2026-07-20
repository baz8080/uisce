# Boil notices

Boil-water notices are the weakest class in the dataset. This note records why, what was measured, and the policy that follows — so the question doesn't get re-litigated from scratch. Measurements are from the 2026-07-18 snapshot (7,553 cases).

## The structural problem: a notice cannot end itself

Uisce publishes the lifting of a boil notice as a **separate case**, with a new `reference_num`, titled "Lifting of Boil Water Notice". The original notice's description is never updated to say it ended. Two consequences follow, and they drive everything below.

**The LLM extraction is irrelevant to this class.** Every `boil_notice_issued` case comes back `end_source = not_found`, and correctly so — there is no end-time signal in the text to find. No prompt version will change this, so boil notices are out of scope for the end-time eval work in [end-time-eval.md](end-time-eval.md). Don't read a bad boil-notice number as a prompt failure.

**The only real end signal is a paired lift**, which means cross-case logic: `paired_lift()` in `site.py` matches on county + normalised scheme name (`location`), tolerating a lift timestamped up to 2 days before the issue pin, because multi-pin publishing is not chronologically tidy.

## What that yields today

| | count |
|---|---|
| `boil_notice_issued` cases | 23 |
| …with a real end (paired lift) | **1** (Donegal / Downings) |
| …unpaired | 22 |
| `boil_notice_lifted` cases | 41 |
| …counted as events | 0 — dropped by `IGNORE_CATS` in `classify()`; a lift is good news, not an event |
| …used as pairing signals | fires for 1 issue case |

One in twenty-three. Every other lift in the DB refers to a notice issued **before collection began** (2026-04-20), so it has nothing to pair with. Coverage should improve as history accumulates — the currently-open notices are the natural test — but it is thin now and the policy has to be honest about that.

## Why unpaired notices can't simply accrue

Before 2026-07-18 an unpaired open notice accrued from its start until now, capped at `CAP_DAYS`. That rests entirely on the feed's `status` field, which goes stale: 8 unpaired notices were older than the 14-day cap, and case **221165** had sat `Open` since 2025-11-13 while *its own description* said the notice had been lifted with immediate effect.

221165 is also the one case where `end_source = lifted_immediate` leaks past the lift exclusion, because that exclusion keys on `work_category` (derived from the **title**), and this record is titled "Boil Water Notice - Tipperary", not "Lifting of…". It is a notice record whose description was overwritten in place with lift text — a third publishing pattern, distinct from the two below.

Accruing those stale notices fabricated roughly 37 merged days of quality time across Cork, Donegal, Mayo, Tipperary and Waterford. Because `quality` doesn't accrue availability downtime (only `outage` does), the damage landed on **grades, day colouring, `clear_days` and open counts** rather than the availability percentage. Removing it moved Cork 2026-05 from F to D and Donegal 2026-04 from C to B — those grades were being knocked by notices resolved months earlier.

## The policy

All of it lives in `boil_notice_fate()` in `site.py`, deliberately in one function, because this was previously smeared across three files (`pipeline.py` derived the category from the title, `build.py` nulled the duration, `site.py` held the fallback branch) and no one of them knew what the others assumed. Four outcomes:

- **paired** — a matching lift exists; use it as the real end. Survives regardless of age: a real signal always beats the staleness rule.
- **accrue** — no lift, younger than `CAP_DAYS`, still `Open`. Plausibly genuinely live; runs to now.
- **exclude** — no lift, older than `CAP_DAYS`. The feed's `Open` is not credible; drop the case rather than invent downtime.
- **closed_no_signal** — closed with no lift; token 1-second footprint, as for any no-signal case, so its start day still colours.

`IGNORE_BOIL_NOTICES` (default `False`) drops the class from the metrics entirely. This is a **defensible position, not a panic switch** — with 1 of 23 notices carrying a real end, what survives is a handful of events resting on a status flag we know goes stale. It is left off so genuinely-live notices still surface to users, which is arguably the class's main value: a current boil notice matters to a reader even if its duration is unmeasurable. Flip it if the class stays this thin as history grows.

## `lifted_immediate` (the LLM class) is excluded — settled 2026-07-18

Distinct from the above: `lifted_immediate` is what the *extraction* assigns to lift records. Round 1 of the end-time eval spent 15 of its 32 misses here, so it was measured before being dismissed. 42 pins / 7,553 cases = 0.56%, deduping to **15 distinct lift events**.

The lift text always states the issue date of the notice being lifted ("Uisce Éireann issued a boil water notice … on the 03/05/26"). Comparing that against the record's own `start_date` splits the class:

- **lag > 0** (5 pins, 1 event — Newport, Tipperary): `start_date` is the lift, the text gives the issue, so the pair yields a real 17-day duration.
- **lag 0** (the rest): the stated issue date equals `start_date`, reading as a same-day issue-and-lift.

The lag-0 group is ambiguous, not merely low-value, and that's the blocking reason. **The feed uses `start_date` inconsistently across lift records.** Case 232518 has `start_date` = the issue date, yet carries "Effective Date of Lifting of Boil Water Notice: 07 May 2026" — the real lift is four days later. Case 233792 has the opposite: `start_date` = the lift date. Nothing in a lag-0 row distinguishes "genuinely resolved same-day" from "`start_date` is the issue date and the lift time is unrecorded". Admitting them would plant the shortest durations in the corpus into the median time-to-fix.

So extracting the issue date into the prompt, splitting the class, and adding a `build.py` branch would buy **one usable event out of fifteen**. Rejected on volume. `build.py` keeps `lifted_immediate` in `NO_DURATION_SOURCES` (NULL duration) and `site.py` drops the records as events. Revisit only if pairing coverage grows materially, in which case the description-derived issue date is the cheaper of the two routes, since it needs no cross-case logic.

The labelling consequence is recorded in [end-time-eval.md](end-time-eval.md): a lift row with the right class and a **null** `local_time` is `correct`. Don't expect the model to copy a time from `start_date` — that's a UTC→local conversion, which is Python's job.

## Three publishing patterns, for anyone extending this

1. **Separate lift case**, `start_date` = lift time, text gives the issue date (233792).
2. **Separate lift case**, `start_date` = issue date, real lift date only in an "Effective Date of Lifting" line (232518).
3. **Notice case updated in place**, title unchanged, description overwritten with lift text (221165).

Pattern 3 is the one that escapes title-based filtering, and it is why `boil_notice_fate` keys on age and pairing rather than trusting `work_category` alone to have caught every lift.
