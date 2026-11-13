# Redesign evidence index

This folder records the TurbineIQ interface redesign and its measured checks. Each `PHASEn.md` keeps its scope, results, summary tables, and current evidence links. The documents below are the maintained reference set.

## Direction and baseline

- [Design direction and measured tokens](DIRECTION.md)
- [Phase 0 baseline](BASELINE.md)
- [Contrast checker](contrast_check.py)
- [Contrast results](phase3/contrast-check.txt) and [Phase 4 contrast results](phase4/contrast-check.txt)
- [Design glyph vector](glyph/cycle-glyph.svg) and [rendered preview](glyph/cycle-glyph-preview.webp)

## Phase reports

- [Phase 2: foundation](PHASE2.md)
- [Phase 3: Overview](PHASE3.md)
- [Phase 4: Component detail, Evidence, and Assistant](PHASE4.md)
- [Phase 5: 3D Stage](PHASE5.md)
- [Phase 6-7, Part 1: Stage refinements, docs, and CI](PHASE6-7-PART1.md)

- [Phase 6-7, Part 2: final audit](FINAL_REPORT.md)
- [Future pull request description](PR_DESCRIPTION.md)
- [Assistant dock on Overview](assistant-dock/README.md)

## Final visual evidence

- [Phase 5 final state screenshots](phase5/states/)
- [Phase 5 Stage captures](phase5/)
- [Phase 6-7 Stage toolbar before and after, light and dark](phase6-7-part1/)
- [Phase 6-7 Part 2 before/after screenshots](FINAL_REPORT.md#screenshots)
- [Phase 6-7 Part 2 gate summary](phase6-7-part2/gate-summary.txt)
- [Final Lighthouse runs and long-task profile](phase6-7-part2/lighthouse-summary.json)
- [Final browser smoke results](phase6-7-part2/browser-smoke.json)
- [Assistant dock screenshots and gate evidence](assistant-dock/README.md)
- [Meshopt evaluation summary](phase4/meshopt-evaluation.md)
- [Meshopt pipeline](glb-pipeline.md)

Intermediate screenshot matrices, raw Lighthouse JSON, and inspector output from Phases 2 to 4 were removed from the working tree. The Phase 5 raw Lighthouse JSON was also removed to meet the requested size budget; Lighthouse run summaries and CLI logs remain in the reports and Phase 5 folder. Removed artifacts remain recoverable without rewriting history from commit `08e5d1ae1bc4e9541f4cf45a8ee6d4b17e902464` using `git show <commit>:<path>` or `git restore --source=<commit> -- <path>`.

The current docs size and all final audit results are recorded in [FINAL_REPORT.md](FINAL_REPORT.md).
