# 0. Are other areas having as many outages as I am?
*~6 min read · an introduction to the series*

## The question

For a stretch of 2026 the water in Leixlip, the town in north Kildare where I live, kept going
off. Not for long, usually — an evening, a morning — but often enough that I started to wonder
whether this was normal, or whether it was us. Uisce Éireann, the national water utility,
publishes every disruption notice on a public map. The map shows what is happening now. It does
not show what happened last month, it does not add anything up, and it has no notion of "as many
as". So on 24 June 2026 I started a small script to fetch the notices and keep them, and asked
one question of it:

> Are other areas having as many outages as I am?

Eight weeks and forty-one pull requests later the script is a public status site — every county,
every month, a letter grade, a breakdown into 1,767 named towns and parishes with a Census
population behind each, and a history of every notice ever published in each of them. And the
answer to the question, for July 2026, is: **yes, it was worse here.** Leixlip lost about one
part in twenty-eight of its person-time to supply outages that month — 438,691 person-hours
across 16,733 people — while Naas and Maynooth, the two nearest towns of the same size, lost
none, and the county figure, 99.20%, averaged all of that into a D. (Chapter 8b is where that
table lives and how it was computed.)

## What this series is

Along the way the project became more complicated than I could hold in my head. There are parts
of it — how a map pin becomes a number of people; how a notice published as eighteen pins over
eighteen nights becomes one event; how the Census's Small Areas, settlements, electoral areas and
divisions fit together — that I directed and reviewed but could no longer explain from a standing
start. This is my attempt to explain them, to myself first, by walking the history in the order it
happened and stopping at each hard idea long enough to work an example.

It is written for an intelligent reader who is not a programmer and has never met a Census
boundary file. Every hard idea gets a **concept box** — a plain-English explanation of a page or
less, at the point it first matters. Every concept gets a **worked example** with a real place and
real numbers, and the arithmetic shown; where it fits, the example is a single notice from my own
street, `KLD00118059`, which appears in chapters 1, 3, 7 and 8a as it passes through each stage of
the pipeline. Every number carries its source and the date it was measured, and every chapter
ends with notes saying where the figures came from. The diagrams are deliberately simple.

Each chapter is written to stand alone. It opens with two lines of *where we are*, so a reader
who arrives at chapter 8b from a search can read it without the seven before it, and it links
back rather than repeats. Read in order, the chapters are the story; read singly, each is a
short essay on one problem.

## The shape of the story

| | | |
|---|---|---|
| **1–2** | *A notice is a row* · *Let a robot do it every week* | Fetch the feed, keep everything, run it on a timer. The one decision — never delete — that everything else rests on. |
| **3–4** | *Ask a local model what the notice actually says* · *Make it a real project* | The end of an outage is buried in prose; a small language model on my laptop reads it out. Then tests. |
| **5a–5b** | *A website, and a number that is fair to Cork* · *An honest number on the model* | Person-hours, population-weighted availability, A–F grades — and measuring how often the model is right. |
| **6–7** | *Say what you actually measured* · *Record the moment a case closes* | Naming the metric honestly; discovering the site was fabricating time in Kildare; making the archive remember transitions. |
| **8a–8b** | *How a pin gets a population* · *Where you actually live* | The Census, the 500 m rule, the polygon method that was wrong, the three tiers of geography — and the Kildare table. |
| **9a–9b** | *Eighteen nights in a trench coat* · *The title is not the severity* | Recurring windows, events versus pins, and the discovery that the utility uses two titles for one situation. |
| **10–11** | *For a reader, not an analyst* · *Be findable* | Rewriting for a person on a phone; being visible to a search engine; a retraction. |
| **12** | *Put a number on what you don't know* | Events charged as zero, the double-count nobody had sized, and the two assumptions examined in public. |
| **13** | *Closing* | What the site can say, what it cannot, what was learned, and a glossary. |

## How it was built, said once

The code was written with an AI assistant — Claude, in Anthropic's Claude Code — across the
whole eight weeks. About half of the ~200 commits carry a `Co-Authored-By` trailer naming the
model that wrote them: Sonnet 4.6 in the last week of June, Sonnet 5 and Opus 4.8 through July,
Opus 5 from late July, and Fable 5, which also drafted this series from the repository's own
history under my direction. I chose what to build, in what order, and what to reject; I read every
diff; I hand-labelled the two model-evaluation rounds (chapter 5b) and the recurrence review
(chapter 9b); and the wrong turns in this account — the polygon method that under-counted a
village fourfold, the 532 cases fabricating a hundred thousand person-hours, the analytics call
that never could have worked — are wrong turns I approved. I mention this here so that the
chapters can say "I" without a footnote each time, and so that anyone weighing the results knows
how they were produced. Nothing about the *findings* depends on who typed them: every one is a
measurement against a public feed and a public census, and the notes and tests that back them are
in the repository.

## What the site is, in one paragraph

A pipeline downloads every current notice from Uisce Éireann's public map twice a day and keeps
it, forever, in a single-file database. A local language model reads each notice's text and
writes down when the works ended and what kind of statement that was. Every notice pin is placed
by the Census: the Small Areas within 500 m of it are its footprint, and the CSO's own labels say
which town or parish those Small Areas belong to. Notices sharing a reference number are one
event; an event's cost is people × hours; a county-month's availability is one minus the share of
all its people's hours that were lost to outages; and a letter grade sits on top of that, with a
separate marker for drinking-water notices. It is published as static pages at
`baz8080.github.io/uisce`, rebuilt with each download. Everything the site cannot honestly claim
— that the start of a span is publication, not onset; that some ends are plans, not
observations; that the radius is an assumption — is stated on the page.

## A note on the numbers

Figures in these chapters are quoted as they were measured at the time, with the date and the
pull request or note they came from; where I re-ran one for this series, I say so and give the
date (mostly 18 August 2026). Some have since moved — the overlap double-count was 3.6% before it
was 2.0%, PR #23's Kildare table used a Naas population that a later fix corrected — and where
that happened the chapter says so rather than quietly using the newer figure. The point of the
series is the journey, and the journey includes being wrong.
