# Notes

**Simply put:** these notes hold the measurements and decisions behind the site, so nobody has to work one out twice. Start with how-it-works.md. Every note opens with a "Simply put" paragraph; the detail follows it.

| Note | What it holds |
|---|---|
| [how-it-works.md](how-it-works.md) | the moving parts, and where to change things |
| [statuspage-methodology.md](statuspage-methodology.md) | how notices become letters, medians, day bars and areas, and why |
| [data-quality.md](data-quality.md) | what each feed field turned out to mean, and the guard for it |
| [frontend-notes.md](frontend-notes.md) | the pages: design, copy, area pages, search, payload and loading |
| [boil-notices.md](boil-notices.md) | the one class of notice that cannot end itself |
| [end-time-eval.md](end-time-eval.md) | how the extracted end times are checked by hand |
| [rules-vs-llm-end-times.md](rules-vs-llm-end-times.md) | why text rules read 93% of notices and a model the rest |
| [model-and-runtime-benchmarks.md](model-and-runtime-benchmarks.md) | the model choice, and every faster option that lost |
| [pipeline-dependencies.md](pipeline-dependencies.md) | how the DB, the JSONL and the site get out of step |
| [population-data-sources.md](population-data-sources.md) | the Census geography a pin is placed by |
| [water-sla-benchmarks.md](water-sla-benchmarks.md) | what regulators measure, and why the site cannot borrow it |
| [roadmap.md](roadmap.md) | follow-ups not started, and decisions waiting on the owner |
| [simplification-plan.md](simplification-plan.md) | the plan that replaced the population estimate with a count, session by session |

Settled decisions are indexed in [../CLAUDE.md](../CLAUDE.md), one row each, pointing at the section that closed them.

## Archive

Retired text, kept as it was written. Nothing in it describes a figure the site still publishes; each file opens by saying what replaced it.

| File | What it was |
|---|---|
| [archive/availability-method.md](archive/availability-method.md) | the population-weighted availability method and its grades, used until 2026-10-06 |
| [archive/frontend-superseded.md](archive/frontend-superseded.md) | three frontend entries a later one replaced |
| [archive/end-time-eval-handoffs.md](archive/end-time-eval-handoffs.md) | the working notes of the pv2 prompt change, completed July 2026 |

Older history is in git: `git log -p notes/`.
