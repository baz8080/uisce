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
| Prompt v1 vs v2 | v1 asked for a UTC timestamp with DST rules in the prompt; v2 (PR #9, 3 Jul) reports notes/end_source/local_date/local_time only, temperature 0, `lifted_immediate` added | diffs of `819faaf^2`, `52bee6c^2` |
| Model in PR #8 | gemma-4-12b-qat via LM Studio at localhost:1234, from the first commit | `819faaf^2:infer_duration.py` |
| `end_date` vs completion updates | agree within 1 h on 6.6% of 2,500 `completion_update` cases; offsets cluster at −30 d, −29 d, +24 h, 0 h | notes/data-quality.md (probed 7 Jul, PR #11 commit) |
| Negative spans at PR #11 | ~19 cases (later 532 on 20 Jul) | PR #11 commit; notes/data-quality.md |
| Date-only end | taken as 23:59:59 local | PR #11 |
| start_date drift | observed twice, same time-of-day, date shifted forward whole days | PR #12 |
| Model timing | ~1.9 s/call: prefill ~0.6 s (~1,700 tok/s, ~1,000-token input), decode ~75 tokens at ~57 tok/s; parallel slots ≈ 1.1× | notes/model-and-runtime-benchmarks.md, 15 Jul |
| qwen3.5-9b | 1.15 s/call (~40% faster), 61% agreement, 150 header-block refusals, 12→24 h errors | same |
| KLD00118059 inferred | pv3, completion_update, 2026-08-10 13:00 local = 12:00 UTC; 52,987 s = 14 h 43 m 07 s | measured 18 Aug 2026 (verified Y) |
| Categories today | burst_main 3,332 (Unplanned) · essential_works 1,376 (Planned) · mains_repair 1,272 (828 blank/269 U/175 P) · investigation 671 · reservoir_interruption 620; work_type filled 90.4%; 16 uncategorised | measured 18 Aug 2026 (verified Y) |
| Tests after PR #15 | 56 | PR #15 |

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
| Louth population | 139,703; May 2026 = 744 h → 103,939,032 person-hours possible; Drogheda event alone → 99.469% (C); against Drogheda's 44,135 → ~98.3% | `site.py:COUNTY_POP`; arithmetic (Ch 5a) |
| Drogheda event affected population | ≈ 23,169 (551,427 ÷ 23.8) | derived |
| Investigation share pre-split | 4,090 h vs 27,128 h burst mains, May–Jun 2026 (~8%) | notes/statuspage-methodology.md "Severity classes" |
| `water_outage` flag | set on 97% of cases | same |
| Feed deletions | none since collection began (~2026-04-20), checked 16 Jul | PR #16 commit |
| Tests at PR #16 | 86 | PR #16 |
| Round 1 per-class | completion_update 37/40 · scheduled_end_with_time 27/30 · not_found 18/20 · date_only 0/9 · lifted_immediate 0/15 = 82/114 | notes/end-time-eval.md 2026-07-18 |
| Round 1 error taxonomy | 7 completion-precedence failures (worst 8 days early); 8 recurring-window date-only; 2 single-digit-day time drops | same |
| Skip-logic bug | prompt bump re-inferred 0; fixed → 7,552 flagged | PR #17 commit |
| Label defects | 4 rows amended, ~4 points; truth_for fallback bug | PR #17 |
| Fresh-round cost | ~120 calls ≈ 5 min vs 7,552 calls ≈ 4.2 h | PR #17 commit |
| Round 2 mix | 67% completion_update; two classes zero rows | PR #17 |
| pv1→pv2 corpus | 7,552 inferred under both; 15 apparent time-fabrications all real (12 "midday", 3 Irish) | PR #17 commit |
| Boil-notice staleness | 22 open notices, 8 older than cap, one Open since 2025-11-13; ~37 merged days quality time, 5 counties; Cork May F→D, Donegal Apr C→B; 1 of 23 pairs | PR #17 commit |
| Start-basis toggle | 55% of descriptions state a start; Unplanned n=1,512 median −0.8 h (21% published after); Planned n=2,094 +0.1 h (51%) | PR #17 commit; notes/data-quality.md "Resolved 2026-07-20" |

### Ch 6
| Figure | Value | Source |
|---|---|---|
| Observed completions | median 17.0 h, n = 3,166 | PR #18, 20 Jul |
| Scheduled ends | median 5.4 h, n = 894 | PR #18 |
| Pooled | 9.3 h (scheduled = 22% of the pool) | PR #18 |
| Schedule overrun | 69.5% finish late; median +2.7 h; 8.8% within 15 min | PR #18 |
| Negative-span family | 532 cases (6.6% of 8,074 inferred; 314 scheduled_end_with_time, 218 completion_update); median −2.7 h, 78% within −6 h; 18 more than a day negative; 28 open, 12 outage-class; ~101k person-hours Kildare, ~66k Donegal, July | PR #19, 20 Jul; notes/data-quality.md "Measured 2026-07-20" |
| Case 237573 | works "9am until midday on 03 July", published 17:04 → −5 h 04 m → NULL | notes/data-quality.md |
| Re-stamp evidence | case 232428 works 08 May, start_date 08 Jun; 10 JSONL cases with date moved, time-of-day kept (235225 `12:43:19` +40 d; 238140 `09:17:25` −30 d) | same |
| Rescue routes closed | earliest-JSONL start: only 1 of 532 has two starts; minimum-start rejected (backward re-stamps); stated window: parses 478/532, plan-minus-plan median 4.0 h; hybrid 4.7 h vs corpus 18.3 h | same |
| Positive-side clusters | ±12 h of 7/14/28/29/30/31 d: 19/2/0/0/1/2 of 7,177 — noise | same |
| start_date machine stamp | 97.6% non-zero seconds; publication precedes stated start in 59% | notes/data-quality.md "Sharpened 2026-07-19" |
| Event-level medians by month Apr–Jul | observed 7.1/12.6/15.8/10.2 h; scheduled 4.8/5.3/4.4/4.3 h | notes/statuspage-methodology.md "The published time metric" |
| Overrun retention | 90.3% of completion updates keep the scheduled window in text | PR #18 |
| Un-inferred backlog at PR #18 | 183 cases, 98% open | PR #18 |
| Tests | 114 (PR #18), 118 (PR #19) | PRs |
| Toy median | observed {10,15,17,20,30}=17; scheduled {4,5,6}=5; pooled median 12.5; weighted mean 14 | illustrative |

### Ch 7
| Figure | Value | Source |
|---|---|---|
| Schema v2 migration | 0.7 ms on a 20 MB DB, no rows touched | PR #21, 21 Jul |
| Closure recovery | 7,613 closed; 1,816 (24%) recovered by replay; 5,797 unrecoverable | PR #21 |
| Cases opening and closing within one build gap | 12% | PR #21 |
| Release asset growth at daily builds | ~7 GB/yr | PR #22 |
| Snapshots replayed | 10 releases, 30 Jun – 20 Jul 2026 | PR #21 |
| Daily-cadence re-measure | 18 of 933 (1.9%) never seen open; observed close vs inferred completion median +75.7 h, p25 +57.2 h, p90 +85.2 h, 97% > 24 h (n = 484); twice-daily → ~1.1% at best | notes/data-quality.md "Re-measured 2026-07-31" |
| closed_at coverage today | 4,303 of 10,130 non-Open cases | measured 18 Aug 2026 (verified Y) |
| closed_at by day (replay era) | 6 Jul 304 · 8 Jul 113 · 10 Jul 209 · 15 Jul 363 · 17 Jul 365 · 20 Jul 399 (Mon/Wed/Fri) | measured 18 Aug 2026 (verified Y) |
| KLD00118059 lifecycle | published Sun 9 Aug 21:16Z; first_seen Mon 10 Aug 12:01:46Z; complete 13:00 local; closed_at Thu 13 Aug 12:02:06Z → 72 h 02 m after completion | measured 18 Aug 2026 (verified Y) |
| Tests at PR #21 | 142 (+27) | PR #21 |
| Geocode cache at PR #21 | ~8k entries | PR #21 |

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
| KLD00118059 footprint | 12 SAs within 500 m of 53.3627, −6.506 → 3,255 people, all Leixlip (nearest 56 m, farthest 495 m); 300 m → 8 SAs / 1,966; 1 km → 29 SAs / 8,440; × 14.72 h ≈ 47,900 person-hours | measured 18 Aug 2026 via `SmallAreaIndex` (verified Y) |
| Doneraile Small Areas | 385 + 214 + 258 = 857; polygon method caught only the 214 | measured 18 Aug 2026 (verified Y); PR #23 |
| Polygon-method figures | 12,837 of 18,919 SAs in a settlement (67.9%), 3,539,104 people = 97.5%; Allenwood 1,233 vs 1,685; check warned only for >5,000 recovering <80% | PR #23 commit |
| Missing settlements' population | 15,893 (54 settlements) | PR #23 commit |
| Geocode cache `city_district` only | 94% of rows | PR #23 commit |
| Urban Areas layer | 867 settlements; BUA CSV 868 rows (Ireland total row); cp1252 dies at byte 8,073 in utf-8 | notes/population-data-sources.md |
| Small Area count/pages | 18,919 features in 10 pages of 2,000 | same |
| Grid bin | 0.01° ≈ 1.1 km latitude | `site.py:SmallAreaIndex.BIN` |
| Kildare table reconciliation | denominator on 25 Jul ≈ 588.5 h observed: Leixlip 405,666 ÷ (16,733 × 588.5) = 4.12% → 95.88%; Prosperous 7.56% → 92.44%; Celbridge 0.76% → 99.24%; Lackagh 3.45% → 96.55% | my arithmetic on PR #23's table |
| Kildare July 2026 today | county person_h 1,466,931 / 744 h / 99.202% / D / 20 outage events; Leixlip 2 / 438,691 / 96.48%; Prosperous 2 / 201,335 / 88.78%; Allenwood 2 / 137,870 / 89.0%; Newbridge (24,366) 3 / 95,158 / 99.47%; Celbridge 4 / 93,305 / 99.39%; Around Lackagh 1 / 17,091 / 97.27%; Naas (26,180) 0 / 100.0%; Maynooth (17,259) 0 / 100.0% | measured 18 Aug 2026 from `out/site/data.js` built 14:37Z (verified Y) |
| Agglomerations | Dublin 1,261,884 / 808 of 973 cases (83%); Cork 222,288 / 257 (25%); Galway 85,876 / 124 (32%); Limerick 102,287 / 82 (22%); Waterford 60,079 / 40 (14%) | notes/statuspage-methodology.md "Cities" |
| LEA slivers | 26 of Dublin's 30 parts ≥91% inside; Elsewhere: Dublin 0.6%, Cork 2.8%, Galway 2.2%, Limerick 4.3%, Waterford 9.6% (Ferrybank); Carrigaline LEA 942 of 39,145 vs town 18,239 | PR #23 commit |
| Dublin LEA names | 12 hyphenated compounds, 5 compass-qualified, 11 plain; Cork 4 quadrants; ED alternative: 104 names ~12,100 people | PR #23 commit; notes |
| Rural bucket | 44% of cases, first in 22 of 26 (Longford 80%, Tipperary 72%, Roscommon 71%, Kerry 63%); Tipperary 456 cases → Around Ardmayle etc.; 1,172 areas ~2.9 cases; median county 33 rows/month, Cork 104 | notes "The countryside" |
| ED keying | (county, name) merges 50 of 3,368 pairs | notes |
| Pinned outside the county | ~1.5% of case-months; Tipperary 21, Kilkenny 24 | notes; data-quality |
| Area breakdowns | 1,767 nationally (623 settlement-only at first commit) | notes; PR #23 commit |
| Carlow July closures | 8 (0 open) | PR #23 |

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
| Build-latency simulation | 8,135 cases: 1×18:45 mean 7.7 h / median 7.5 / p90 11.1; 2×06:45+18:45 6.8 h; 2×12:45+18:45 3.9 h / 3.4 / 5.6; 3× 3.5 h; burst mains 8.7→4.0 h; boil-flagged 7.0→3.3 h | PR #26 |
| DON00115765 reconciliation | 18 nights × 9 h = 162 h announced; 16 nights run → 144.0 h; 385.2 h ≈ 16 days continuous; 6,596 people = 949,824 ÷ 144.0; 2,540,854 = 6,596 × 385.2 | my arithmetic on PRs #27/#29 |
| v3 replay | identical to pv2: 99/114, 120/120, 0 parse errors / 234 rows; 8 labelled recurring rows | PR #27 |
| First v3 run | −0.4% vs −5.9% projected (completion pin re-covered gaps) | PR #27 |
| unquotable_windows | 89 of 97 exact, 0 flagged | PR #27 |
| Prompt v3 size | 6,255 → 9,746 chars; 29 cases hit context length until LM Studio raised to 8,192 | PR #27 |
| Cork DNC lift mis-stored | "Lifting of Do Not Consume Notice" stored as consumption_notice_issued | PR #27 |
| Phrase counts | "may cause supply disruptions" 100% of burst mains; "allow 3–4 hours" 99–100%; "supply should have returned" 39–48%; "may cause low pressure to" 98% low_pressure vs 0% burst | PR #29 |
| Donegal after #29 | July national 25,395,359 → 24,440,623 (−3.8%); Donegal 2,118,941/98.295% → 1,169,117/99.060%; per-capita rank 1 (12,682) → 6 (6,997); Clare 9,588 | PR #29 |
| Recurrence review | 11 events, 1,289,079 ph; 2 correct / 9 wrong; text 33 events, model 5; May/Jun/Jul −0.2/−0.4/−0.5%; 238,887 ph on the eight; case 232976 47,124 ph left | PRs #30, #31 |
| Grade thresholds check | 78 settled county-months; cuts at A 97%, B 76%, C 33→32%, D 10→9%; exactly one letter changes after −11.8% national | PR #31 |

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
