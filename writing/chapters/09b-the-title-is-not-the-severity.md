# 9b. The title is not the severity
*~9 min read · PRs #28–#31 · 2 August 2026*

*Where we are:* recurring windows are charged as the hours inside them (chapter 9a), and July's
largest event has fallen from 2.5 million person-hours to 949,824. That number was still on the
top of the national ranking, for a village of 6,596 people whose water was off nine hours a
night. This chapter is four PRs on one day, and it ends by giving up on the idea — planted in
chapter 4 — that the notice's title tells you how bad it is.

## The question that opened this stretch

A sniff test on the new top-ten page: *~1M person-hours for 6,596 people looked wrong.* It was.
But before that, a smaller inconsistency the top ten had made visible.

## What changed

### PR #28: name an event once

The open-cases list and the top ten *named* the same event by different rules. The open list
took the area of the **first pin the feed published**; the top ten took the area holding the
**largest share of the event's whole footprint** (chapter 8b's dominant-share rule, applied to
the union). So a multi-pin burst could read "Allenwood" in the county drill-down and
"Prosperous" in the national ranking — same page, same event. **348 events (4.7%)** disagreed;
of multi-pin events, 37.6%. Now the site unions each event's footprint as it goes and names it
once; the open list came to the top ten's rule, 14 labels changed, no published figure moved.

The subtlety is worth the toy table the PR used, because it is a real trap in "sum then take the
max". Shares are summed per area across all pins:

| | Exton | Wyeville | Zedbury |
|---|---|---|---|
| pin 1 sees | — | 60 | **90** |
| pin 2 sees | **100** | 60 | — |
| union | 100 | **120** | 90 |

Wyeville wins the union while being *no pin's home* — pin 1 is homed in Zedbury, pin 2 in
Exton — so it was never registered in the county's area table, and the page would render the
event under a blank heading and drop it from the open counts. No event in the corpus does this
today; the naming is now restricted to the pins' own homes, so it cannot.

### PR #29: the same zone, two titles, opposite treatment

Here is the finding that made 949,824 wrong. Severity (chapter 5a) is keyed to the notice's
title category, and Uisce Éireann uses two titles for one situation. The same Donegal supply
zone — Lifford, Rossgier — under the same nightly 10pm–7am regime:

| date | reference | title | class | accrued |
|---|---|---|---|---|
| 30 Apr | `DON00111054` | Water **Conservation** | degraded | **nothing** |
| 23 Jun | `DON00114559` | Reservoir **Interruption** | outage | everything |
| 9 Jul | `DON00115765` | Reservoir **Interruption** | outage | **949,824 person-hours** |

Overlapping villages, identical window, near-identical wording, opposite treatment — and the
July one was the largest single figure on the site. Whichever way that pair resolves, it has to
resolve alike.

The obvious reading — that these notices describe degraded service rather than outage, and the
text says so — was ruled out first, by counting. *"May cause supply disruptions"* appears on
**100% of burst mains**, which are unambiguous total outages; it is boilerplate about *who* is
affected within a named area, not *whether*. *"Allow 3–4 hours for your supply to fully
return"*: 99–100% everywhere. *"Supply should have returned"*: 39–48% of every category, used
*more* by low-pressure notices than by burst mains. Exactly one phrase discriminates — *"may
cause low pressure to …"*, 98% of low-pressure notices, 0% of burst mains — and neither Donegal
event uses it.

> **Concept: a scheduled repeating window is a restriction, whatever the title says.** A burst
> main is an outage: the water is off until it is fixed. A notice that announces the water will
> be off *nightly, 10 pm to 7 am, for three weeks* is describing a managed regime — a
> conservation measure, a restriction — even when the title reads "Reservoir Interruption". So
> the classifier now downgrades an outage to *degraded* when the **event** announced a window
> repeating over a date range. An outage and nothing else — a nightly leak-detection round is
> still maintenance. And it is read at *event* level, not per pin, for the reason chapter 9a
> found: the pin carrying the completion update reports no window, and would otherwise sit as a
> lone outage inside a restriction event, whose full interval the union then charges.

| | before | after |
|---|---|---|
| July national person-hours | 25,395,359 | **24,440,623** (−3.8%) |
| Donegal July | 2,118,941 · 98.295% | **1,169,117 · 99.060%** |
| Donegal per-capita | rank 1, 12,682 h/1k | **rank 6, 6,997** |

No county's grade changed. Only two July events moved class. And the control held again:
Drogheda's 23.8-hour reservoir interruption — one continuous interruption, no window — stays an
outage at 551,427 person-hours, which is the discrimination the rule exists to make.

Two more notices moved in the same PR, for a related reason: titled *Reservoir Interruption*,
their text read *"may cause low pressure to …"* with no mention of supply loss. The feed has a
`reduced_pressure` flag; it was set from the feed's own notice text — the same principle as
chapter 4's `work_type` override — and the classifier already reads that flag ahead of the hard
categories. The far commoner *"low pressure **and** supply disruptions"* (100 cases) is
deliberately not matched: those announce both, and the supply loss is the part that accrues.

One consequence, stated in the PR because it is easy to miss: this makes chapter 9a's
recurring-window expansion **numerically inert**. Person-hours accrue for outages only, so an
event that is now degraded contributes nothing however its intervals are shaped. The expansion
keeps its place — day bars and event counts read the intervals, and the v3 window field is
exactly what this rule keys on — but nothing multiplies by a window's length any more.

### PRs #30–#31: review the calls that matter, and be wrong about why

With a rule that flips an event's class on a single field, the question is how often that field
is right. There is no labelled round for windows. So instead of a sample, PR #30 enumerated
*every* recurrence call that changes a figure — an outage downgraded to a restriction, or an
event still charged continuously whose own text describes a window. Eleven events nationally,
1,289,079 person-hours between them, small enough to read in full.

> **Concept: review the consequential calls, not a sample.** A random sample of a rare decision
> mostly measures the cases where the decision doesn't matter — a window claimed on a notice
> that was already a restriction is inert. When only a handful of calls change any number, and
> they can be listed, list them all, sorted by how much rides on each, and read them. That is
> not a substitute for a labelled round; it is what you do when the labelled round doesn't
> exist yet and a figure is already published.

The labels came back **2 correct, 9 wrong**. I had predicted that count and misread the cause.
Eight of the nine were events "still charged as outage" whose text plainly said *nightly*; I
had them down as an extraction failure — the model didn't emit the window — needing a prompt v4
and another eleven-hour corpus run. The review notes said otherwise: the *classification* was
wrong on its own terms. The rule only needs to know **whether** a notice announces a repeating
window; that is the easy half, and a regular expression can do it. The window's *values* are
what needed a language model.

The two signals turned out to fail in opposite directions, so the classifier now uses both:

| signal | catches | misses |
|---|---|---|
| notice text | every completion notice the model suppressed — 33 events, including all 8 labelled | the enumerated form |
| model extraction | *"from 10am until 6pm on 5 May, 6 May and 7 May"*, which names its days rather than saying "daily" — 5 events | completion notices |

The model suppresses the window whenever a completion phrase is present: the prompt tells it a
completion takes priority over a scheduled end, and it applies that to the window fields too. A
prompt bug, and this routes around it without a re-run. May −0.2%, June −0.4%, July −0.5% —
small in aggregate because most text-detected events were already restrictions by category, but
right on the eight that were not, worth 238,887 person-hours. One case was labelled and left:
*"Works are scheduled to take place until 6pm on 9 May until 9pm 13 May"* — two "until"s and no
"from", garbled at source, read as a repeating 18:00–21:00 window. One event in about eighty-five;
a rule keyed on the missing "from" would be fitted to this case rather than derived from
anything.

Two smaller honesty items from the same day. The review tool wrote to a filename keyed on the
date, so re-running it the same day — exactly what you do after changing a rule — silently
overwrote a hand-labelled file; it now suffixes `_r2`, `_r3` like the end-time rounds. And I had
claimed the grade thresholds must have gone stale, since four definitional changes had taken
national person-hours down 11.8%. Measured — rebuilding the pre-change code against pre-change
data and comparing the 78 settled county-months — every cut sat at the percentile it always
did and **exactly one county-month changed letter**. The error was reading a distribution off an
aggregate: the national total is dominated by a few large events, so stripping 2.6M person-hours
out of Donegal moves one county-month a long way and leaves the median of 78 where it was.
Thresholds unchanged; finding recorded so nobody re-derives it.

### Worked example: what the Donegal event costs, and what it now costs

Same 6,596 people, same 16 nights, same 144.0 hours inside the windows (chapter 9a).

- Charged as a continuous outage (before chapter 9a): 6,596 × 385.2 h = **2,540,854**
  person-hours; 9.9% of the national July.
- Charged as an outage inside its windows (after 9a): 6,596 × 144.0 h = **949,824**; still #1
  nationally.
- Classed as a *restriction* (after 9b): **0** person-hours against availability; the 31 July
  days still colour on Donegal's bar, the event still counts, and it still appears in the
  history — as degraded. Donegal's July availability moves from 98.295% to 99.060% and its
  per-capita rank from 1st to 6th.

The April notice for the same zone, titled *Water Conservation*, had been treated that way from
the start. The two now agree.

## Where it left the site

Events named once; a repeating window a restriction whatever the title; recurrence detected
from text *and* extraction; the consequential calls reviewed by hand and the review tool no
longer eating its own labels; and the grade thresholds checked and left alone. The July national
figure had come down from 27.5M to 24.3M person-hours across chapters 9a and 9b, and Donegal
from double the field to mid-table, without a single county changing letter. Chapter 4's
warning — *a title is a category, not a severity* — is now a rule in the code rather than a
sentence in a note. The site was, at this point, mostly correct and almost entirely
unreadable. Chapter 10.

## Notes

- PR #28 (2 Aug 2026): `area_of` first-pin vs `top_events` dominant-over-union; 348 events
  (4.7%; 37.6% of multi-pin); 14 labels change; `TownLookup.dominant(allowed=…)`; Exton table;
  four advance-notice cases with no breakdown entry, unchanged.
- PR #29 (2 Aug): DON00111054 / DON00114559 / DON00115765 table; phrase counts ("may cause supply
  disruptions" 100% of burst mains; "may cause low pressure to" 98% vs 0%); `classify(recurring)`;
  results table; two events move; `backfill_reduced_pressure` (WAT00113034, LON00116458); "low
  pressure and supply disruptions" 100 cases not matched; ~2% "intermittent" noticed.
- PR #30 (2 Aug): review of 11 events / 1,289,079 ph; 2 correct, 9 wrong; case 232976 (47,124
  ph). PR #31 (2 Aug): text + model detection (33 + 5 events); May/June/July −0.2/−0.4/−0.5%
  (17,185,748 → 17,145,060; 20,643,022 → 20,397,763; 24,509,791 → 24,324,401); 238,887 ph on the
  eight; `_r2` suffixes; thresholds: 78 county-months, cuts at 97/76/33→32/10→9%, one letter
  changes.
- `notes/statuspage-methodology.md` "A scheduled repeating window is a restriction, not an
  outage"; `notes/data-quality.md` "The notice title is not a reliable severity signal", "What
  the v3 corpus run delivered".
