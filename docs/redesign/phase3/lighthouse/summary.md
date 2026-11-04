# Lighthouse comparison

Final production build at http://127.0.0.1:8011/#/overview?scenario=compressor_fouling&seed=42&i=72. Lighthouse 13.6.0; three sequential runs per preset, categories performance/accessibility/best-practices. Raw JSON is preserved beside this summary.

| Preset | Run | Perf | A11y | Best practices | FCP ms | LCP ms | TBT ms | CLS | SI ms | TTI ms | Bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| desktop | desktop-1 | 67 | 100 | 96 | 268 | 2196 | 516 | 0.056 | 874 | 2955 | 4026243 |
| desktop | desktop-2 | 75 | 100 | 96 | 257 | 2148 | 322 | 0.056 | 823 | 2707 | 4026243 |
| desktop | desktop-3 | 74 | 100 | 96 | 261 | 2171 | 339 | 0.056 | 852 | 2756 | 4026243 |
| mobile | mobile-1 | 52 | 100 | 96 | 910 | 12527 | 896 | 0.023 | 4388 | 13568 | 4026243 |
| mobile | mobile-2 | 47 | 100 | 96 | 914 | 12544 | 1931 | 0.023 | 2780 | 14664 | 4026243 |
| mobile | mobile-3 | 47 | 100 | 96 | 915 | 12555 | 1998 | 0.023 | 2786 | 14740 | 4026243 |

**Mobile median:** performance 47, accessibility 100, best practices 96, FCP 914 ms, LCP 12544 ms, TBT 1931 ms, CLS 0.023, Speed Index 2786 ms, TTI 14664 ms, total bytes 4026243.

**Desktop median:** performance 74, accessibility 100, best practices 96, FCP 261 ms, LCP 2171 ms, TBT 339 ms, CLS 0.056, Speed Index 852 ms, TTI 2756 ms, total bytes 4026243.

Phase 0 performance medians were mobile 51 and desktop 80; BASELINE.md records about 5 performance points of run noise. Scores are compared to medians. CLS target is <=0.1 for both presets. Mobile LCP remains slower than Phase 0 and the lazy viewer remains above Vite's 500 kB advisory; defer the full viewer split to Phase 5.
