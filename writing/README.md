# The uisce series — brief and style guide

A chapter-by-chapter account of how this repo grew from one question — *are other areas having
as many outages as Leixlip?* — into a status site with Census-weighted availability, LLM-read end
times and a three-tier geography. Written so the author can understand the parts that outgrew
him, and so it can later become a blog series or a paper.

Nothing in `writing/` is imported by the package. It is prose and diagrams only.

## Who it is for

An intelligent professional who is not a programmer and has never met a shapefile. They can
follow arithmetic when it is shown, and a table when it has real place names in it. They will not
tolerate a term used before it is explained, and they will notice a number that appears without a
sentence saying what it means. The author knows more code than that persona; write for the
persona anyway.

## Voice

- First person, "I". The AI-assisted process is named once, in the intro, and not re-litigated
  chapter by chapter.
- Candid. The wrong turns — the polygon method that under-counted Doneraile four-fold, the 532
  cases that fabricated ~101k person-hours in Kildare, the `pushState` that never could have
  worked — are the story, not embarrassments to skim past. Tell what was believed, what was
  measured, what changed.
- Chronological within a chapter. The reader should feel the order the problems arrived in.
- Plain. Prefer "the map pin" to "the geometry", "people × hours" to "person-hour exposure".
  Introduce a technical term once, in a concept box, then use it freely.

## Rules

1. **Every number carries a source and a date.** In text: "(PR #23, 25 Jul 2026)" or
   "(measured 18 Aug 2026)". Every number quoted also gets a row in `figures.md`.
2. **No figure without a sentence saying what it means.** "405,666 person-hours" is followed by
   the arithmetic and by what that is for the town in question.
3. **One concept box per hard idea**, at the point the idea first matters, ≤ 200 words, in a
   blockquote starting `> **Concept: <name>**`. Later chapters link back rather than re-explain.
4. **At least one worked example per hard concept**, using a real place and real numbers, with
   the arithmetic shown. Leixlip is the running example wherever it fits.
5. **Diagrams earn their place.** Mermaid fences for flows and decision trees; small hand-written
   SVG in `diagrams/` for anything spatial (a circle over dots, a straddle). ≤ 40 lines, no polish
   — a later pass can polish. Reference as `![alt](../diagrams/name.svg)`.
6. **Length: target ~2,000 words, hard ceiling 3,000.** Light chapters may be 1,200–1,500; do not
   pad. If a draft cannot fit under 3,000, split it into two posts at a concept boundary rather
   than cutting worked examples. Each post carries a "~N min read" line (≈ 230 words/min).
7. **Standalone.** Each chapter opens with a two-line *Where we are* so it works as a single blog
   post; it may assume nothing except that the reader has read the intro.
8. **Vocabulary is fixed** (see glossary below); do not drift between synonyms.
9. **Missing number → `[verify: what]`** and move on. They are collected in the final pass, not
   chased mid-draft.

## Fixed vocabulary

| Use | Not | Meaning |
|---|---|---|
| **notice** | advisory, alert | what Uisce Éireann publishes, in the feed |
| **pin** | point, marker | one row of the feed: one notice at one coordinate |
| **case** | record | one pin as stored in the `cases` table (a case *is* a pin) |
| **event** | incident, outage (unless it is one) | all pins sharing a `reference_num`, treated as one thing |
| **outage / quality / degraded / maintenance** | severity words | the four classes; only *outage* accrues downtime |
| **Small Area** | SA (after first use), block, tract | Census 2022 smallest statistical unit |
| **settlement** | town (except in prose), built-up area | a Census 2022 Urban Area |
| **LEA** | ward, district | Local Electoral Area |
| **ED** | parish | Electoral Division |
| **area** | region, zone | any row of the drill-down: settlement, LEA or "Around \<ED\>" |
| **footprint** | catchment | the set of Small Areas a pin (or event) reaches |
| **person-hours** | customer-minutes, exposure | people affected × hours affected |
| **availability** | uptime, reliability | 100 × (1 − person-hours lost ÷ person-hours possible) |
| **grade** | score, rating | the A–F letter, county-month only |
| **health marker** | health knock | the boil-water / do-not-drink flag shown beside a grade |

## Chapter template

```markdown
# NN. Title
*~N min read · PRs #a–#b · dates*

*Where we are:* two lines placing this chapter in the series.

## The question that opened this stretch

## What changed
(narrative, chronological within the chapter)

> **Concept: <name>** — plain-English box, ≤ 200 words.

### Worked example: <place>
(real numbers, arithmetic shown, source + date)

## What went wrong / what got retracted   ← when applicable

## Where it left the site
(the numbers as of the chapter's last PR)

## Notes
PRs, commit subjects, `notes/` sections and code functions used; each figure's source.
```

## Working method (cost discipline)

One chapter per session, light pairs together (1+2, 10+11, optionally 3+4). No subagents.
Read, in order: `PROGRESS.md` → this file → the chapter's entry in `outline.md` →
`sources/chNN.md` → only the `notes/` sections and code functions the outline names (grep the
heading, then read with offset/limit; never the big notes files whole). Draft in one write.
Register figures as you go. Update `PROGRESS.md`. If tokens remain, review the previous chapter
for continuity and mark it reviewed. Do not start a third chapter in a session.
