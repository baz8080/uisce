# Figures registry

Every number quoted in a chapter gets a row here. *Source* is a PR number, a commit subject, a
`notes/` section heading, or "measured" (a read-only query run by the writing session).
*Verified* means re-run against the working tree / `out/uisce.db` on the date given.
Chapters quote from here rather than re-deriving; a missing figure is written into the draft as
`[verify: …]` and added here in the final pass.

## Anchors verified 2026-08-18 (Session 0)

| Figure | Value | How | Verified |
|---|---|---|---|
| Small Areas in `data/sa_pop.csv` | 18,919 | csv count | Y |
| Sum of Small Area populations | 5,149,139 (= Census 2022 state total) | csv sum; `sa_pop.py:CENSUS_2022_STATE_POP` | Y |
| Leixlip (Kildare) | 56 SAs, 16,733 people | `sa_towns.csv` × `sa_pop.csv` | Y |
| Naas (Kildare) | 84 SAs, 26,180 people (PR #23's table showed 25,824 — the earlier approximation; commit "Naas 25,824 vs 26,180") | same | Y |
| Celbridge (Kildare) | 69 SAs, 20,601 | same | Y |
| Prosperous (Kildare) | 8 SAs, 2,413 | same | Y |
| Around Ardmayle (Tipperary) | 1 SA, 494 | same | Y |
| Doneraile (Cork) | 3 SAs, 857 (polygon method had read 214) | same; PR #23 | Y |
| Drogheda (Louth) | 153 SAs, 44,135 — largest settlement under the 50,000 split | same | Y |
| Knockbridge / Termonbarry / Kilmore Quay | 759 / 699 / 447 — the "54 settlements with no row" examples | same | Y |
| Distinct (name, county) areas in `sa_towns.csv` | 3,717 (909 settlement/LEA rows, 2,808 "Around …") — note: the site's directory counts only areas with cases (1,836, PR #32) | csv | Y |
| `cases` rows / distinct `reference_num` / `closed_at` set | 10,610 / 8,568 / 4,306 | `sqlite3 -readonly out/uisce.db` | Y |
| `inferred_cases.end_source` mix | completion_update 6,624 · scheduled_end_with_time 3,486 · not_found 414 · lifted_immediate 48 | same | Y |
| LOU00112686 pins | 13 | same | Y |
| DON00115765 pins / start range | 18 pins, 2026-07-09 14:06 → 07-11 15:26 (publication) | same | Y |
| Oldest `start_date` in DB | `0206-08-10` — a mis-typed year in the feed; a footnote for Ch 1 or 6 | same | Y |
| `PRAGMA user_version` | 3 (`SCHEMA_VERSION = 3`; README still says 2) | same | Y |
| Constants | `AFFECT_RADIUS_KM` 0.5 · `FALLBACK_KM` 8.0 · `SPLIT_ABOVE_POP` 50,000 · `MIN_PART_SHARE` 0.30 · `CAP_DAYS` 14 · `MIN_CATEGORY_N` 15 · `COLLECTION_START` 2026-04-20 | `site.py`, `towns.py` | Y |

## Lifted figures by chapter (source + date measured; not re-run)

### Ch 1–2
| Figure | Value | Source |
|---|---|---|
| Feed rows with LASTUPDATE/CREATEDATE | 0 of 8,155 (100% NULL); `ENDDATE IS NOT NULL` 6,497 for scale; capabilities = Query only | notes/data-quality.md "The feed carries no modification timestamp", probed 21 Jul 2026 |
| Cases with empty county backfilled | ~10 of 5,000+ | PR #6, 30 Jun 2026 |
| Cases vs distinct rounded coordinates | 10,610 cases at 10,550 distinct (rounded_lat, rounded_lon); `geocode_cache` 10,567 rows | measured 18 Aug 2026 (verified Y) |
| Coordinate rounding | 4 dp ≈ 11 m latitude (commit `5ac63dc`; earlier `c171eb6` used 5 dp ≈ 1 m); KLD00118059 moves ≈ 3 m when rounded | code + arithmetic |
| Worked example KLD00118059 | Investigation Works – Kildare; Forest Park, Leixlip; start 2026-08-09 21:16:53Z, end_date 2026-08-10 21:16:57Z (24 h 4 s later), text says complete 1 pm 10 Aug; closed_at 2026-08-13 12:02:06Z; geocode: road Forest Park, town Leixlip, county "County Kildare", W23 A6YH | measured 18 Aug 2026 (verified Y) |
| Weekly build cadence | Mondays 06:00 UTC (PR #5); later Mon/Wed/Fri; daily from PR #22 (21 Jul); midday added PR #26 (31 Jul) | PRs #5, #22, #26; notes/data-quality.md "closed_at is a floor" |
| PR #4 size | +29/−32 lines | gh |

### Ch 3–4
| Figure | Value | Source |
|---|---|---|
| JSONL records backfilled with hash/model/prompt_version | 5,911 | PR #10, 6 Jul |
| Rows upserted from the release DB into `inferred_cases` | 6,561 | PR #13, 9 Jul |
| Test count after restructure | 42 | PR #14, 10 Jul |
| Dedupe of identical descriptions | ≈ 15% fewer LLM calls; timeout 15 s → 120 s | PR #14 |
| `work_type` coverage | 31% → 68% (#14) → 89% via 26 title categories, 29 unplaced (#15) | PRs #14, #15 |
| Circuit breaker | after 10 consecutive geocode failures | PR #14 |

### Ch 5
| Figure | Value | Source |
|---|---|---|
| Eval sample / raw accuracy | 114 cases stratified; 71.9% raw, 82.8% on duration-feeding classes (pv1) | PR #16, 18 Jul |
| pv1 → pv2 replay | 81/114 → 99/114; 99/99 excluding `lifted_immediate` | PR #17, 20 Jul |
| pv2 holdout round 2 | 120/120 unseen; 95% lower bound ≈ 97.5% | PR #17 |
| Corpus re-inference | 7,892 cases, 0 failures; `scheduled_end_date_only` 55 → 0 | PR #17 |
| Boil notices | 42 pins → 15 events | PR #17 |
| Cork May 2026 availability | 2% binary uptime vs ~99.2% population-weighted | notes/statuspage-methodology.md "Why not plain uptime?" |
| Drogheda reservoir interruption | 23.8 h → 551,427 person-hours | notes/statuspage-methodology.md |
| Grade thresholds | A ≥ 99.9, B ≥ 99.75, C ≥ 99.45, D ≥ 99.0, else F | `site.py:grade` |
| County populations used as denominators | Cork 584,156 · Kildare 246,977 · Dublin 1,458,154 (Census 2022) | `site.py:COUNTY_POP` |

### Ch 6
| Figure | Value | Source |
|---|---|---|
| Observed completions | median 17.0 h, n = 3,166 | PR #18, 20 Jul |
| Scheduled ends | median 5.4 h, n = 894 | PR #18 |
| Pooled | 9.3 h (scheduled = 22% of the pool) | PR #18 |
| Schedule overrun | 69.5% finish late; median +2.7 h; 8.8% within 15 min | PR #18 |
| Negative-span family | 532 cases (not ~19); ~101k person-hours Kildare, ~66k Donegal, July | PR #19, 20 Jul |

### Ch 7
| Figure | Value | Source |
|---|---|---|
| Schema v2 migration | 0.7 ms on a 20 MB DB, no rows touched | PR #21, 21 Jul |
| Closure recovery | 7,613 closed; 1,816 (24%) recovered by replay; 5,797 unrecoverable | PR #21 |
| Cases opening and closing within one build gap | 12% | PR #21 |
| Release asset growth at daily builds | ~7 GB/yr | PR #22 |

### Ch 8
| Figure | Value | Source |
|---|---|---|
| Kildare July 2026 area table | Leixlip (16,733) 2 / 405,666 ph / 95.88% · Prosperous (2,413) 2 / 107,352 / 92.44% · Celbridge (20,601) 3 / 91,886 / 99.24% · Naas (25,824) 0 / — / 100.00% · Around Lackagh (841) 1 / 17,091 / 96.55% | PR #23, 25 Jul |
| `cases.location` distinct values | 3,866 | PR #23 |
| Dublin city and suburbs | 1,261,884 people; 83% of Dublin's cases; split into 40 rows | PR #23 |
| Cases outside any settlement | ~40%; the rural bucket held 44% of cases and ranked first in 22 of 26 counties → 1,172 named areas | PR #23; notes/statuspage-methodology.md "The countryside" |
| ED letter-suffixing | city 242 of 1,492; rural 0 of 2,552 | PR #23 |
| Point-in-polygon failure | 37 MB polygons; 54 settlements no row; 187 of 789 >10% short; Doneraile 214 vs 857 (~4×) | PR #23 |
| Attribute method | all 867 settlement populations exact; urban total 3,630,501; `uisce-fetch-towns` 25 s → 4 s | PR #23 |
| Settlement resolution | 13,060 matched on (name, county); 125 straddlers; 19 names shared by unrelated settlements | notes/population-data-sources.md |
| Median dominant share of a pin | 1.00 | notes/statuspage-methodology.md "The county drill-down" |
| Why no town grades | 24 h event: county of 62,000 moves 0.18 pt; town of 1,000 moves 11 | notes/statuspage-methodology.md |
| Payload | data.js 645 KB (84 KB gz), down from 960 KB; grows ~85 KB/month | PR #23 |

### Ch 9
| Figure | Value | Source |
|---|---|---|
| Publication latency | mean 7.7 h → 3.9 h with a 12:45 build | PR #26, 31 Jul |
| Feed lag marking Closed | median 75.7 h after works finish; 97% > 24 h | PR #26 |
| Ten largest events | 21.9% of July person-hours; one = 9% | PR #27, 2 Aug |
| DON00115765 | 18 pins; "daily 10pm–7am, 9–27 July"; 385.2 h continuous → 144.0 h | PR #27 |
| July national person-hours | 27,505,846 → 25,395,359 (−7.7%) | PR #27 |
| Donegal per-capita | 22,156 → 12,682 h per 1,000 | PR #27 |
| NULL-category leak | 66 cases classed as hard outages; one ranked #9 nationally | PR #27 |
| Event naming disagreement | 348 events (4.7%); 37.6% of multi-pin events | PR #28 |
| Same Donegal zone, two titles | "Conservation" accrued nothing; "Interruption" 949,824 person-hours | PR #29 |
| Recurring-window downgrade effect | July 25,395,359 → 24,440,623 (−3.8%) | notes/statuspage-methodology.md "A scheduled repeating window is a restriction" |
| Recurrence review | 2 correct, 9 wrong | PRs #30, #31 |
| Multi-pin events | LOU00112686 13 pins in 22 min; 675 refs cover 1,930 rows; 6,758 cases ≈ 5,485 events | notes/data-quality.md "Multi-pin events…" |

### Ch 10–11
| Figure | Value | Source |
|---|---|---|
| Directory areas | 1,836; 220 of 1,830 county-table areas had no history; 764 multi-area events; fix cost 6 KB gz | PR #32, 5 Aug |
| False 0.0 h | 801 events | PR #32 |
| Cavan clear days | "27/31" shown on 6 Aug when 6 days had happened | PR #34, 6 Aug |
| Methodology paragraph | 2,600 chars → seven sections | PR #34 |
| Health knock vs real harm | 0.45 pp band vs 0.003–0.012 pp; ~100× ; grade mix A2 B16 C31 D19 F10 → A2 B17 C34 D18 F7 | notes/statuspage-methodology.md "The health notice was unbundled" |
| Indexable URLs | 2 → 28; static text 73,087 → 383,714 chars; analytics pages 1 → 28 | PR #37, 6 Aug |

### Ch 12
| Figure | Value | Source |
|---|---|---|
| Events on the 1-second footprint | 204 of 4,473 outage events; 200 negative-span, 4 `not_found` | PR #40, 15 Aug |
| Category medians | mains_repair 7.5 h; pump_repair 43.7 h; `MIN_CATEGORY_N` 15 | PR #40 |
| Kaplan–Meier vs naive | 13.9 h vs 13.4 h | PR #40 |
| Imputation effect | +2.3% to +4.4% person-hours/month; four county-months drop one grade | PR #40 |
| Overlap double-count | 3.6% (per pin, wrong) → 2.0% (1.58M of 80.3M, Apr–Aug; 0.5–2.5% by month) | PR #41, 18 Aug; notes "Known limitations" |
| `do_not_drink` flag | wrong on 9 of 19 | PR #41 |
| WCAG contrast failures | 3.35:1, 2.87:1, 2.64:1; badge 1.79:1 | PR #41 |
| Radius sensitivity | rank corr 0.93/0.91 at 300 m, 0.90/0.86 at 1 km; 48 of 52 county-months change letter | notes/statuspage-methodology.md "Radius sensitivity" |
| Grade calibration | 78 settled county-months; p10 ≈ 98.9%, median ≈ 99.6%, p90 ≈ 99.87%; cuts at 97th/76th/33rd/10th pct; robustness: −11.8% person-hours moved one county-month (Waterford May D→C) | notes/statuspage-methodology.md grade section |
| Health notice on grade removed | Tipperary July: three active notices, none shown | notes/statuspage-methodology.md |
| Health marker on 2026-08-18 build | Galway 2/2, Mayo 1/1 standing; Monaghan 1/0 record only | notes/statuspage-methodology.md |
