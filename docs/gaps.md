# Known gaps

- Korean substitute fonts do not have the original fonts' metrics. The supplied newspaper example
  still reports 25 characters of overset text with Apple SD Gothic Neo; other substitutes can
  produce different line breaks and more overset.
- Missing linked files are warned about, not recovered. Package them beside the IDML or in `Links`.
- Import and output are not guaranteed to reproduce every IDML feature. Placed PDFs with non-default
  crop boxes and some parent-page overset cases need additional work and regression tests.
- Linux deployment, performance and real-document fidelity have not been measured yet.
- The retained shared CI workflow has not yet been verified on the new fork. Local checks run
  with `cargo xtask ci`.
- Direct IDML article editing and a render–review–edit loop are not implemented.
- Editorial analysis extracts source formats and bounded layout evidence. The Python pipeline
  adds story-based article units, source thread order, photo/caption/article candidates,
  AABB overlap/wrap observations and missing/overset state. Semantic ownership, cross-story
  reading order, crop intent and user editing permissions remain unresolved.
  Candidates require review and have no assigned policy strength.
  Native folder analysis writes independent reports only. The separate
  [Python library builder](editorial-library.md) groups observed formats across issue folders,
  but semantic roles, approved rules and page types remain unresolved; similarity weights are
  unvalidated heuristics, and only byte-identical source copies are deduplicated.
  The combined Markdown handoff remains observed reference material, not approved editing
  policy. Its default library-wide form has page summaries; exact frame coordinates are
  included when a target page is selected. No LLM or IDML editing is executed by this step.
  Markdown alone does not supply original image assets, confirmed article/photo/caption
  relationships or crop-preservation constraints. The initial relationship model uses style
  names, groups and proximity, not image content. It retains alternatives and truncation flags;
  an asset-inclusive editing package is not implemented.
  It scans direct regular IDML files, excluding subdirectories and symlinks, with a 1,000-file limit.
- Analysis v1 excludes parent-page items, anchored objects, table-cell and note content. It
  reports visible printable document-spread leaves and full source stories for their text frames;
  group clipping and exact visible glyph bounds are not resolved. Resolved source formats include
  importer defaults and do not expand nested/GREP/line styles or composition-time typography.
  Font checks certify family availability only; rendered measurements are not reference-PDF evidence.
