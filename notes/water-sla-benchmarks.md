# Water supply SLA benchmarks

Documented service levels for municipal water supply in nearby jurisdictions, researched July 2026 to calibrate the status site's A–F grades (see [statuspage-methodology.md](statuspage-methodology.md)). Headline: real SLAs exist and are strikingly tight, but they measure something different from what this project can measure, so they inform the framing rather than the thresholds.

## Ofwat (England & Wales)

Ofwat's common performance commitment for **water supply interruptions** is average minutes of lost supply per property per year, counting only interruptions of **3 hours or longer** (properties interrupted ≥180 min × full duration ÷ total properties served).

- Performance commitment level for 2024-25: **5 minutes per property per year** — roughly 99.999% availability.
- Sector actual, 2020–24 average: **about 15 minutes 23 seconds** per property per year (≈ 99.997%), and worsening year-on-year at sector level per the 2024-25 performance report.
- The worst performer in 2024-25, South East Water, averaged **~44 minutes per property** and incurred a **£3.373 M** outcome-delivery penalty; the best (e.g. SES Water, ~4 minutes) sit at or under target.

Sources: [PC definition (PDF)](https://www.ofwat.gov.uk/wp-content/uploads/2023/05/Water-supply-interruptions.pdf) · [Water company performance report 2024-25 (PDF)](https://www.ofwat.gov.uk/wp-content/uploads/2025/10/WCPR-24-25.pdf) · [Discover Water sector dashboard](https://www.discoverwater.co.uk/loss-of-supply) · [South East Water ODI page](https://performance.southeastwater.co.uk/odi/interruptions-to-customers-water-supply/) · [PR24 PC definitions](https://www.ofwat.gov.uk/regulated-companies/price-review/2024-price-review/pr24-final-determinations-performance-commitment-definitions/)

## CRU (Ireland)

The CRU's Performance Assessment Framework monitors Uisce Éireann annually. It replaced counting unplanned interruptions longer than 4 hours with **minutes of lost supply** from planned and unplanned interruptions — the same family of metric as Ofwat's. The RC4 revenue-control period (2025–29) targets a **one-third reduction in minutes of lost supply**, described as narrowing the gap with better-performing utilities. In the 2023 assessment Uisce Éireann fully met 57% of its targets, with a 4% year-on-year decrease in unplanned interruptions.

Sources: [framework publications](https://www.cru.ie/document_group/irish-water-performance-assessment/) · [2023 monitoring reports announcement](https://www.cru.ie/about-us/news/cru-publishes-water-monitoring-reports-for-2023-on-uisce-eireann-performance/) · [metric review & target-setting decision paper](https://www.cru.ie/document_group/irish-water-performance-assessment/cru21101-irish-water-performance-assessment-framework-2020-2024-metric-review-and-target-setting-decision-paper-2/)

## Why these numbers can't be this project's thresholds

Regulators count *measured* minutes without water at the customer's tap, generally only for ≥3-hour events. This project counts the **entire published notice duration** for **everyone within an assumed 500 m of the pin**, including "customers may experience disruptions" notices and short events, with publication-time start floors. The result differs by construction: regulator scales sit at 99.99–99.999% availability, while the county-months here span roughly 99.0–99.9%. That 2–3 order-of-magnitude gap says nothing about Irish supply being that much worse — it reflects exposure-counting versus interruption-measurement. Hence the site's grades are calibrated to the observed distribution of this dataset and presented as a disruption-exposure index, explicitly not comparable to Ofwat/CRU figures.

## Related metrics worth adopting later

- **SAIDI / SAIFI / CAIDI** (electricity reliability terms): the site's availability metric is already a SAIDI analogue; CAIDI — median time to restore — is the most consumer-meaningful companion and is robust to over-reporting.
- **AWWA benchmark**: water main breaks per 100 miles of main per year (industry guide is below ~15) — an asset-health lens once enough located events accumulate.
- **IBNET/IWA continuity** (hours of supply per day) — aimed at intermittent-supply systems, less relevant here.
