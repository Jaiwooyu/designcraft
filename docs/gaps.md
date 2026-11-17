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
- Editorial analysis currently extracts single-document format observations, not AI-assigned
  article roles, photo/caption relationships, cross-issue practices or user editing policies.
  Candidates require review and have no assigned policy strength.
- Analysis v1 excludes parent-page items, anchored objects, table-cell and note content. It
  reports visible printable document-spread leaves and full source stories for their text frames;
  group clipping and exact visible glyph bounds are not resolved. Resolved source formats include
  importer defaults and do not expand nested/GREP/line styles or composition-time typography.
  Font checks certify family availability only; rendered measurements are not reference-PDF evidence.
