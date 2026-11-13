# Assistant dock Lighthouse check

The prior `FINAL_REPORT.md` Lighthouse medians were captured before the assistant dock and did not include `environment.benchmarkIndex`. Because of that, those historical TBT values cannot be used for a threshold comparison under the current `benchmarkIndex >= 2,500` rule.

## New measurements available

The parent build (`7509f06`, before the dock) and dock build (`c7af346`) were served locally and alternated with Lighthouse 13.6.0. Three runs per preset were captured, followed by one additional mobile pair to obtain a third qualifying dock sample. Performance, accessibility, and best-practices categories were enabled. The runner recorded CPU and memory state with each run.

For mobile, all four parent samples met the benchmark floor: TBT median **1,411 ms** (1,327–1,738 ms), with benchmarkIndex median **2,900.3** (2,791–3,012). Three of four dock samples met the floor: TBT median **1,499.5 ms** (1,402–1,550), with benchmarkIndex median **3,023** (2,682–3,139.5). Every qualifying mobile TBT was below 2,000 ms. The dock's fourth sample had TBT 2,080 ms at benchmarkIndex 2,391.5 and is excluded as below floor. Based on the qualifying samples, median LCP/CLS was 917.3 ms / 0.046377 before the dock and 922.1 ms / 0.046438 with the dock. Both remain within the mobile LCP and CLS limits. Mobile performance medians on qualifying samples were 71.5 and 72; accessibility was 100 and best practices 96 for both.

All three desktop samples for both builds had benchmarkIndex below 2,500, so desktop comparisons are not classified. The observed desktop LCP values were 255–261.3 ms before and 262–264.8 ms with the dock, but they are not used to claim the desktop gate passed because none of these runs met the comparison floor. Desktop TBT is not comparable.

| Preset | Build | Run | TBT (ms) | benchmarkIndex | LCP (ms) | CLS | Performance |
|---|---|---:|---:|---:|---:|---:|---:|
| Mobile | Parent | A1 | 1,327 | 2,880.5 | 946.4 | 0.046438 | 72 |
| Mobile | Parent | A2 | 1,412 | 2,920 | 913.9 | 0.046316 | 72 |
| Mobile | Parent | A3 | 1,410 | 3,012 | 911.2 | 0.046316 | 71 |
| Mobile | Parent | A4 | 1,738 | 2,791 | 920.7 | 0.046438 | 70 |
| Mobile | Dock | B1 | 1,402 | 3,023 | 922.1 | 0.046438 | 72 |
| Mobile | Dock | B2 | 1,550 | 2,682 | 917.5 | 0.047443 | 71 |
| Mobile | Dock | B3 | 2,080 | 2,391.5 | 917.2 | 0.046438 | 70 |
| Mobile | Dock | B4 | 1,499.5 | 3,139.5 | 926.9 | 0.046438 | 72 |
| Desktop | Parent | A1 | 372.5 | 2,096.5 | 256.3 | 0.013613 | 83 |
| Desktop | Parent | A2 | 242.5 | 2,287 | 255 | 0.013613 | 91 |
| Desktop | Parent | A3 | 242.5 | 1,847 | 261.3 | 0.013613 | 91 |
| Desktop | Dock | B1 | 282.5 | 2,195.5 | 264.8 | 0.013613 | 88 |
| Desktop | Dock | B2 | 276 | 2,072 | 262 | 0.013613 | 89 |
| Desktop | Dock | B3 | 272 | 2,088.5 | 263 | 0.013613 | 89 |

Raw per-run records and the runner output are in [`lighthouse-dock-ab.json`](evidence/lighthouse-dock-ab.json), [`lighthouse-dock-ab.txt`](evidence/lighthouse-dock-ab.txt), [`lighthouse-dock-extra.json`](evidence/lighthouse-dock-extra.json), and [`lighthouse-dock-extra.txt`](evidence/lighthouse-dock-extra.txt). A preliminary standalone mobile run in [`manual-mobile.json`](evidence/manual-mobile.json) used an invalid scenario ID in its query and recorded TBT 2,761 ms at benchmarkIndex 2,596 and CLS 0.1274; it is preserved as a failed exploratory check, not part of the valid-route paired medians. The later alternating runs were stable on the Overview route: every qualifying candidate sample had CLS 0.0464–0.0474, and the qualifying TBT median was below 2,000 ms. The earlier smoke report in [`lighthouse-smoke.json`](evidence/lighthouse-smoke.json) includes a below-floor B sample and is not used in the medians. The app entry bundle grows by about 1.25 kB gzip from the parent dashboard; dock and consent chunks are fetched only when opened, as asserted by Playwright.

Do not compare below-floor runs or historical runs without `benchmarkIndex` to the 2,000 ms TBT target. Repeat the desktop preset on a quiet host until at least three samples per build meet the floor. Every TBT result in this note is accompanied by its per-run benchmarkIndex in the raw JSON records.
