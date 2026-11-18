# IDML renderer roadmap

Current focus: a lightweight headless IDML-to-PNG/PDF renderer for an agent-assisted newspaper
layout workflow. The source is derived from DesignCraft. See [known gaps](docs/gaps.md).

- 2026-11-18: integrated the supplied DesignCraft command-line editor into `cli/` as a root
  workspace member. It shares the existing rendering/analysis libraries and root lock file;
  editing engine, tools, MCP and interchange dependencies live once under `crates/`.
  Layer guide locks survive editing and IDML round trips. Desktop/web applications and
  their separate workspace are excluded from the retained product.

- 2026-11-15: removed the unused desktop contributor data and obsolete review and test-runner settings.
- 2026-11-15: replaced the desktop-focused workspace with the rendering application and its
  document, typography, image, IDML and PDF dependencies. Desktop, web, editing engine and
  unrelated interchange crates were removed.
- 2026-11-15: the headless path reproduced all three pages of the supplied IDML byte-for-byte
  against the earlier DesignCraft rendering when using the same font substitute. The reference
  PDF still differs: the supplied package lacks an image and two text frames overflow.
- 2026-11-17: added `--analysis` JSON output with original resolved text formats, page-local
  element bounds, story/thread evidence, source-font availability, separate rendered line/overset
  measurements and review-only format candidates. This is the deterministic input for a later
  AI role/relationship pass, not a learned editorial policy engine. See [analysis](docs/editorial-analysis.md).
- 2026-11-17: added bounded folder analysis with `--in-dir` / `--analysis-dir`, per-file JSON
  reports, sequential isolated renderer processes, failure continuation and final counts.
- 2026-11-18: added a standalone Python issue/page library builder for IDML or analysis JSON,
  with scoped provenance, duplicate-aware format observations, page similarity and bounded
  per-page LLM briefs without a predefined page taxonomy. See [library](docs/editorial-library.md).
- 2026-11-18: separated local newspaper packages from documentation into the Git-ignored corpus,
  added a documentation index, removed the superseded initial handoff and relocated the retained
  brand licence to `licenses/brand/` without changing its contents.
- 2026-11-18: connected the library pipeline to a single Markdown editing handoff with
  scoped IDs, complete candidate variants, page summaries and representative evidence;
  existing outputs can be repackaged without IDML analysis, optionally for one target page.
- 2026-11-18: added bounded source lock/wrap/graphic evidence and five-category structural
  extraction: article candidates, source-thread order, image/caption candidates, AABB overlaps
  and missing/overset state. Library profiles, structure JSON and Markdown retain evidence,
  unresolved semantics, old-report availability and comparison-limit flags.
- Next: validate on Linux with installed Korean fonts; improve linked artwork and typography
  fidelity; implement direct IDML editing and an agent feedback loop as separate work.
