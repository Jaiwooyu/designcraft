# IDML renderer roadmap

Current focus: a lightweight headless IDML-to-PNG/PDF renderer for an agent-assisted newspaper
layout workflow. The source is derived from DesignCraft. See [known gaps](docs/gaps.md).

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
- Next: validate on Linux with installed Korean fonts; improve linked artwork and typography
  fidelity; implement direct IDML editing and an agent feedback loop as separate work.
