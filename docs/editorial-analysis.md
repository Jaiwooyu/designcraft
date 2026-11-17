# Editorial analysis, schema v1

```sh
cargo run -p idml-render -- --in input.idml --analysis analysis.json
cargo run -p idml-render -- --in input.idml --analysis analysis.json --png-dir pages \
  --fallback-font 'Noto Sans CJK KR'
```

No network access or AI credentials are needed. The first implementation provides deterministic
inputs for a later AI role/relationship classifier and an evidence-backed review interface.
It does not identify headlines or infer newspaper-wide rules from a single layout.

## Report

| Field | Meaning |
| --- | --- |
| `schema_version`, `analyzer_version` | JSON schema and application version |
| `pages` | Document pages in order; dimensions, margin/column settings and visible printable elements |
| `pages[].elements` | Imported item ID, nearest group ID, page-local frame bounds, object style, story or graphic asset reference; role remains null |
| `stories` | Original IDML story `Self` when available, imported story ID, ordered frame IDs, bounded text excerpt and resolved format spans |
| `stories[].spans` | Paragraph/character style names, local-override presence, original resolved font/paragraph settings and source-text range |
| `fonts` | Original family, family availability in the document font scope, and explicit replacement family if used |
| `candidates` | Distinct used combinations of paragraph style, character style and the recorded source format, with evidence |
| `warnings`, `limitations` | Import/link/font warnings and qualifications on the analysis |

Source formats are captured **before** missing-font replacement. They resolve paragraph-style
inheritance, paragraph overrides, character-style inheritance and character overrides. The
recorded subset includes font family/style/size, auto or explicit leading, auto-leading ratio,
tracking, horizontal/vertical scale, paragraph alignment, indents and paragraph spacing.
These are importer-resolved values, including defaults where source attributes are absent.
Unused style definitions and empty paragraphs do not generate candidates.

Rendered frame line counts and story ranges live in `elements[].rendered`. Overset byte offset
and character count live in `stories[].rendered_overset_*`. They describe the current renderer
with the available fonts, including substitutions. They are not measurements from the original
InDesign output or a reference PDF. A missing font does not prevent extracting its declared name.
Font availability is checked by family, not exact face or per-character glyph coverage.

## Evidence and review

All ranges are half-open **UTF-8 byte** ranges in the full original imported story, never character
indices or offsets into `text_excerpt`. The excerpt is capped at 512 Unicode scalar values and
can be shorter than a cited range. An IDML `Self` identifies the original story; imported numeric
IDs identify elements within this import only and are not promised stable across importer versions.

To highlight an example, follow its `story_id` to `stories[].frame_ids`, find those item IDs in
`pages[].elements`, then intersect the example range with each `rendered.story_range`. Bounds
are axis-aligned, page-local points with a top-left origin, including nested group transforms.
An item crossing two pages appears on both pages in each page's coordinate system. Bounds are
frame bounds, not glyph bounds; clipping and rotation can make the highlighted box approximate.
PNG output includes bleed, so an overlay must also account for the page's bleed offset and scale.
Overset text may have no visible range to highlight; use the final frame as the overflow location.

Every candidate has `kind: observed_format`, `source: resolved_idml_format`,
`status: needs_review`, `scope: uploaded_document` and `strength: null`. Descriptions report
observations rather than giving editorial instructions. `observed_spans` counts format spans,
not independent issues or pages. At most eight evidence examples are retained per candidate,
with `evidence_truncated` indicating additional occurrences; all spans remain in `stories`.
Candidate IDs are report-local. Grouping uses exact recorded values and style names, with no
numeric tolerance, cross-document aggregation, role classification or confidence score.

## Bounds and limitations

Extraction rejects more than 1,000 document pages, 50,000 visited items, page-element instances,
source stories or format spans, nesting of 64 levels, more than 16 MiB of referenced story text,
names over 4,096 bytes or non-finite recorded geometry/format values. Page intersection work is
capped at two million comparisons. JSON serialization is capped at 32 MiB and written atomically;
failure leaves an existing analysis output intact. The input cannot be the analysis output, and
PDF/analysis paths cannot alias each other. Existing renderer input/link limits still apply.

Parent-page items, anchored objects, table cells, footnotes and endnotes are excluded. Source
stories are included in full for referenced frames, even if some of their text is overset or in
other frames. Hidden and nonprinting document-spread items are excluded. Page column settings
are guides, not inferred actual newspaper column usage. Nested/GREP/line styles, variable text,
exact glyph geometry and group clipping are not expanded by the source-format pass.

For the next AI stage, send bounded page elements, source format spans, excerpts and rendered
page images. Require the model to refer only to known item/story IDs and permit unresolved
relationships. Treat source text as untrusted document data, validate model output separately,
and retain human corrections. Cross-issue practices and editorial policy approval belong in
later stages; high observation counts alone must not create mandatory rules.
