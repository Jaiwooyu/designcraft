//! Evidence-backed source-format observations. No editorial policies are inferred here.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::io::Write;
use std::ops::Range;

use designcraft_doc::{Align, CharProps, Document, Item, ItemId, Leading, PageId, ParaProps, StoryId};
use designcraft_geom::{Affine, Rect};
use serde::Serialize;

mod layout;

const MAX_PAGES: usize = 1_000;
const MAX_ITEMS: usize = 50_000;
const MAX_SPANS: usize = 50_000;
const MAX_TEXT_BYTES: usize = 16 * 1024 * 1024;
const MAX_JSON_BYTES: usize = 32 * 1024 * 1024;
const MAX_NAME_BYTES: usize = 4_096;
const MAX_EXCERPT_CHARS: usize = 512;
const MAX_EXAMPLES: usize = 8;
const MAX_WORK: usize = 2_000_000;

#[derive(Serialize)]
pub struct Analysis {
    schema_version: u32,
    layout_evidence_version: u32,
    analyzer_version: &'static str,
    coordinate_system: &'static str,
    range_unit: &'static str,
    limitations: Vec<&'static str>,
    warnings: Vec<String>,
    pages: Vec<PageObservation>,
    stories: Vec<StoryObservation>,
    fonts: Vec<FontObservation>,
    pub candidates: Vec<FormatCandidate>,
}

#[derive(Serialize)]
struct PageObservation {
    page_id: PageId,
    page_number: usize,
    width_pt: f64,
    height_pt: f64,
    margins: designcraft_doc::Margins,
    column_guides: designcraft_doc::Columns,
    elements: Vec<Element>,
}

#[derive(Clone, Serialize)]
struct Element {
    item_id: ItemId,
    group_id: Option<ItemId>,
    name: String,
    kind: &'static str,
    bounds_pt: [f64; 4],
    object_style: String,
    story_id: Option<StoryId>,
    text_columns: Option<u32>,
    text_gutter_pt: Option<f64>,
    asset_id: Option<designcraft_doc::AssetId>,
    asset_available: Option<bool>,
    role: Option<&'static str>,
    rendered: Option<FrameMeasurement>,
    layout: layout::LayoutEvidence,
}

#[derive(Clone, Serialize)]
struct FrameMeasurement {
    line_count: usize,
    story_range: Range<usize>,
}

#[derive(Serialize)]
struct StoryObservation {
    story_id: StoryId,
    idml_self: Option<String>,
    frame_ids: Vec<ItemId>,
    text_excerpt: String,
    text_excerpt_truncated: bool,
    text_bytes: usize,
    vertical: bool,
    spans: Vec<FormatSpan>,
    rendered_overset_start: Option<usize>,
    rendered_overset_characters: Option<usize>,
}

#[derive(Serialize)]
struct FormatSpan {
    paragraph_index: usize,
    range: Range<usize>,
    paragraph_style: String,
    character_style: String,
    has_paragraph_overrides: bool,
    has_character_overrides: bool,
    format: SourceFormat,
}

#[derive(Clone, Serialize)]
struct SourceFormat {
    font_family: String,
    font_style: String,
    font_size_pt: f64,
    leading: Leading,
    auto_leading_ratio: f64,
    tracking_per_thousand_em: f64,
    horizontal_scale: f64,
    vertical_scale: f64,
    alignment: Align,
    left_indent_pt: f64,
    right_indent_pt: f64,
    first_line_indent_pt: f64,
    space_before_pt: f64,
    space_after_pt: f64,
}

#[derive(Serialize)]
struct FontObservation {
    source_family: String,
    family_available: bool,
    substituted_with: Option<String>,
}

#[derive(Serialize)]
pub struct FormatCandidate {
    id: String,
    description: String,
    kind: &'static str,
    source: &'static str,
    status: &'static str,
    scope: &'static str,
    strength: Option<&'static str>,
    paragraph_style: String,
    character_style: String,
    format: SourceFormat,
    observed_spans: usize,
    evidence: Vec<Evidence>,
    evidence_truncated: bool,
}

#[derive(Serialize)]
struct Evidence {
    story_id: StoryId,
    paragraph_index: usize,
    range: Range<usize>,
}

fn name(value: &str) -> Result<String, String> {
    if value.len() > MAX_NAME_BYTES {
        return Err("analysis: name exceeds 4096 bytes".into());
    }
    Ok(value.to_owned())
}

fn finite(values: &[f64]) -> Result<(), String> {
    if values.iter().all(|v| v.is_finite()) { Ok(()) } else { Err("analysis: non-finite source geometry or format".into()) }
}

impl SourceFormat {
    fn new(chars: &CharProps, para: &ParaProps) -> Result<Self, String> {
        finite(&[
            chars.size,
            chars.tracking,
            chars.h_scale,
            chars.v_scale,
            para.auto_leading,
            para.left_indent,
            para.right_indent,
            para.first_line_indent,
            para.space_before,
            para.space_after,
        ])?;
        if let Leading::Points(value) = chars.leading {
            finite(&[value])?;
        }
        Ok(Self {
            font_family: name(&chars.font_family)?,
            font_style: name(&chars.font_style)?,
            font_size_pt: chars.size,
            leading: chars.leading,
            auto_leading_ratio: para.auto_leading,
            tracking_per_thousand_em: chars.tracking,
            horizontal_scale: chars.h_scale,
            vertical_scale: chars.v_scale,
            alignment: para.align,
            left_indent_pt: para.left_indent,
            right_indent_pt: para.right_indent,
            first_line_indent_pt: para.first_line_indent,
            space_before_pt: para.space_before,
            space_after_pt: para.space_after,
        })
    }
}

/// Collect document-spread leaves iteratively. Parent-page and anchored content are explicitly
/// excluded in schema v1 rather than assigning them misleading document-page coordinates.
fn elements(doc: &Document, roots: &[std::sync::Arc<Item>], visited: &mut usize) -> Result<Vec<Element>, String> {
    if roots.len() > MAX_ITEMS {
        return Err("analysis: too many top-level items".into());
    }
    let mut pending: Vec<_> = roots.iter().rev().map(|it| (&**it, Affine::IDENTITY, None, 0usize, false, false)).collect();
    let mut out = Vec::new();
    while let Some((item, parent, group_id, depth, ancestor_locked, ancestor_wrap)) = pending.pop() {
        *visited += 1;
        if *visited > MAX_ITEMS || depth >= 64 {
            return Err("analysis: item count or nesting limit exceeded".into());
        }
        if item.hidden || item.nonprinting || !doc.layer(item.layer).is_some_and(|l| l.visible && l.printable) {
            continue;
        }
        let xf = parent * item.xf;
        finite(&xf.as_coeffs())?;
        finite(&item.wrap.offsets)?;
        if item.is_group() {
            if pending.len().saturating_add(item.children().len()) > MAX_ITEMS {
                return Err("analysis: too many nested items".into());
            }
            for child in item.shown_children().collect::<Vec<_>>().into_iter().rev() {
                pending.push((
                    child,
                    xf,
                    Some(item.id),
                    depth + 1,
                    ancestor_locked || item.locked || doc.layer(item.layer).is_some_and(|layer| layer.locked),
                    ancestor_wrap || item.wrap.mode != designcraft_doc::WrapMode::None,
                ));
            }
            continue;
        }
        let b = xf.transform_rect_bbox(item.inner_bounds());
        let bounds_pt = [b.x0, b.y0, b.x1, b.y1];
        finite(&bounds_pt)?;
        let text = item.text_frame();
        if let Some(tf) = text {
            finite(&[tf.options.gutter])?;
        }
        let graphic = item.graphic();
        out.push(Element {
            item_id: item.id,
            group_id,
            name: name(&item.name)?,
            kind: if text.is_some() {
                "text"
            } else if graphic.is_some() {
                "graphic"
            } else {
                "shape"
            },
            bounds_pt,
            object_style: name(&item.object_style)?,
            story_id: text.map(|tf| tf.story),
            text_columns: text.map(|tf| tf.options.columns),
            text_gutter_pt: text.map(|tf| tf.options.gutter),
            asset_id: graphic.map(|g| g.asset),
            asset_available: graphic.map(|g| doc.assets.get(&g.asset).is_some_and(|a| !a.data.is_empty())),
            role: None,
            rendered: None,
            layout: layout::observe(doc, item, ancestor_locked, ancestor_wrap, out.len())?,
        });
    }
    Ok(out)
}

fn check_page(page: &designcraft_doc::Page) -> Result<(), String> {
    finite(&[
        page.width,
        page.height,
        page.x,
        page.margins.top,
        page.margins.bottom,
        page.margins.inside,
        page.margins.outside,
        page.columns.gutter,
    ])?;
    if let Some(positions) = &page.columns.positions {
        if positions.len() > designcraft_doc::MAX_COLUMNS as usize * 2 {
            return Err("analysis: too many custom column positions".into());
        }
        finite(positions)?;
    }
    Ok(())
}

fn page_observations(doc: &Document) -> Result<Vec<PageObservation>, String> {
    let mut pages = Vec::new();
    let mut visited = 0;
    let mut work = 0;
    let mut instances = 0;
    for spread in &doc.spreads {
        let leaves = elements(doc, &spread.items, &mut visited)?;
        for page in &spread.pages {
            check_page(page)?;
            let mut page_elements = Vec::new();
            for element in &leaves {
                work += 1;
                if work > MAX_WORK {
                    return Err("analysis: page intersection budget exceeded".into());
                }
                let [x0, y0, x1, y1] = element.bounds_pt;
                if Rect::new(x0, y0, x1, y1).intersect(page.bounds()).area() <= 0.0 {
                    continue;
                }
                instances += 1;
                if instances > MAX_ITEMS {
                    return Err("analysis: too many page element instances".into());
                }
                let mut local = element.clone();
                local.bounds_pt = [x0 - page.x, y0, x1 - page.x, y1];
                finite(&local.bounds_pt)?;
                page_elements.push(local);
            }
            pages.push(PageObservation {
                page_id: page.id,
                page_number: pages.len() + 1,
                width_pt: page.width,
                height_pt: page.height,
                margins: page.margins,
                column_guides: page.columns.clone(),
                elements: page_elements,
            });
        }
    }
    Ok(pages)
}

fn validate_story(story: &designcraft_doc::Story, text_bytes: &mut usize) -> Result<(), String> {
    *text_bytes = text_bytes.checked_add(story.text.len()).ok_or("analysis: text size overflow")?;
    if *text_bytes > MAX_TEXT_BYTES || story.paras.len() > MAX_SPANS || story.chars.len() > MAX_SPANS || story.frames.len() > MAX_ITEMS {
        return Err("analysis: text or formatting limit exceeded".into());
    }
    if story.text.bytes().filter(|b| *b == b'\n').count() >= MAX_SPANS {
        return Err("analysis: paragraph limit exceeded".into());
    }
    let mut run_end = 0usize;
    for run in &story.chars {
        run_end = run_end.checked_add(run.len).ok_or("analysis: character run size overflow")?;
        if run_end > story.text.len() || !story.text.is_char_boundary(run_end) {
            return Err("analysis: invalid character run range".into());
        }
    }
    if run_end != story.text.len() {
        return Err("analysis: character formatting does not cover text".into());
    }
    Ok(())
}

fn story_spans(doc: &Document, story: &designcraft_doc::Story, count: &mut usize) -> Result<Vec<FormatSpan>, String> {
    let mut spans = Vec::new();
    let mut runs = story.runs().peekable();
    for (index, range) in story.para_ranges().into_iter().enumerate() {
        let para = story.paras.get(index).ok_or("analysis: paragraph has no format")?;
        let (pp, base) = doc.styles.resolve_para(para);
        // Empty paragraphs have no used text to promote into a format candidate.
        let mut cursor = range.start;
        while cursor < range.end {
            let Some((run, format)) = runs.peek() else { return Err("analysis: character formatting does not cover text".into()) };
            if run.end <= cursor {
                runs.next();
                continue;
            }
            if run.start > cursor {
                return Err("analysis: gap in character formatting".into());
            }
            let end = range.end.min(run.end);
            let segment = cursor..end;
            if story.text.get(segment.clone()).is_none() {
                return Err("analysis: formatting splits a UTF-8 character".into());
            }
            *count += 1;
            if *count > MAX_SPANS {
                return Err("analysis: too many format spans".into());
            }
            let chars = doc.styles.resolve_char(&base, format);
            spans.push(FormatSpan {
                paragraph_index: index,
                range: segment,
                paragraph_style: name(&para.style)?,
                character_style: name(&format.style)?,
                has_paragraph_overrides: !para.para.is_empty() || !para.chars.is_empty(),
                has_character_overrides: !format.over.is_empty(),
                format: SourceFormat::new(&chars, &pp)?,
            });
            cursor = end;
        }
    }
    Ok(spans)
}

fn format_candidates(stories: &[StoryObservation]) -> Result<Vec<FormatCandidate>, String> {
    let mut candidates: BTreeMap<String, FormatCandidate> = BTreeMap::new();
    for story in stories {
        for span in &story.spans {
            let source = &span.format;
            let key = serde_json::to_string(&(&span.paragraph_style, &span.character_style, source)).map_err(|e| e.to_string())?;
            let candidate = candidates.entry(key).or_insert_with(|| FormatCandidate {
                id: String::new(),
                description: format!(
                    "Observed {} / {} at {} pt in paragraph style {}.",
                    source.font_family, source.font_style, source.font_size_pt, span.paragraph_style
                ),
                kind: "observed_format",
                source: "resolved_idml_format",
                status: "needs_review",
                scope: "uploaded_document",
                strength: None,
                paragraph_style: span.paragraph_style.clone(),
                character_style: span.character_style.clone(),
                format: source.clone(),
                observed_spans: 0,
                evidence: Vec::new(),
                evidence_truncated: false,
            });
            candidate.observed_spans += 1;
            if candidate.evidence.len() < MAX_EXAMPLES {
                candidate.evidence.push(Evidence { story_id: story.story_id, paragraph_index: span.paragraph_index, range: span.range.clone() });
            } else {
                candidate.evidence_truncated = true;
            }
        }
    }
    Ok(candidates
        .into_values()
        .enumerate()
        .map(|(i, mut c)| {
            c.id = format!("format-{}", i + 1);
            c
        })
        .collect())
}

fn source_fonts(doc: &Document, stories: &[StoryObservation]) -> Vec<FontObservation> {
    let families: BTreeSet<_> = stories.iter().flat_map(|s| &s.spans).map(|s| &s.format.font_family).collect();
    let fonts = designcraft_fonts::FontDb::global().scoped(doc.font_scope);
    families
        .into_iter()
        .map(|family| FontObservation { source_family: family.clone(), family_available: fonts.has_family(family), substituted_with: None })
        .collect()
}

pub fn extract(doc: &Document, story_ids: &HashMap<String, StoryId>) -> Result<Analysis, String> {
    if doc.page_count() > MAX_PAGES || doc.stories.len() > MAX_ITEMS || story_ids.len() > MAX_ITEMS {
        return Err("analysis: page or story limit exceeded".into());
    }
    let pages = page_observations(doc)?;
    let used_stories: BTreeSet<_> = pages.iter().flat_map(|p| &p.elements).filter_map(|e| e.story_id).collect();
    let mut source_ids = BTreeMap::new();
    for (source, id) in story_ids {
        source_ids.insert(*id, name(source)?);
    }
    let mut stories = Vec::new();
    let mut text_bytes = 0;
    let mut span_count = 0;
    for id in used_stories {
        let story = doc.story(id).ok_or("analysis: text frame references missing story")?;
        validate_story(story, &mut text_bytes)?;
        let spans = story_spans(doc, story, &mut span_count)?;
        let excerpt: String = story.text.chars().take(MAX_EXCERPT_CHARS).collect();
        stories.push(StoryObservation {
            story_id: id,
            idml_self: source_ids.remove(&id),
            frame_ids: story.frames.clone(),
            text_excerpt_truncated: excerpt.len() < story.text.len(),
            text_excerpt: excerpt,
            text_bytes: story.text.len(),
            vertical: story.vertical,
            spans,
            rendered_overset_start: None,
            rendered_overset_characters: None,
        });
    }
    let fonts = source_fonts(doc, &stories);
    let candidates = format_candidates(&stories)?;
    Ok(Analysis {
        schema_version: 1,
        layout_evidence_version: 1,
        analyzer_version: env!("CARGO_PKG_VERSION"),
        coordinate_system: "page-local points; top-left origin; axis-aligned frame bounds; excludes bleed",
        range_unit: "UTF-8 byte offsets into the original story, not the excerpt",
        limitations: vec![
            "Single-document format observations only; no recurring practices or editorial policies inferred.",
            "Roles and article/photo/caption relationships are unresolved; no AI service is called.",
            "Parent-page, anchored, table-cell and note content is excluded from source observations.",
            "Only visible printable document-spread leaves intersecting a page are included; group clipping is not resolved.",
            "Resolved formats include importer defaults; nested/GREP/line styles and composition-time typography are not expanded.",
            "Rendered measurements use available/substituted fonts and are not verified against a reference PDF.",
            "Font availability is checked by family; exact faces and glyph coverage are not certified.",
            "Candidate counts are formatted spans, not independent issues, pages or policy confidence.",
            "IDs are local to this import; evidence links through story/frame IDs to page element bounds.",
            "Layout evidence records source locks/wrap settings and AABB geometry, not editing permissions or confirmed collisions; ancestor wrap contours are not expanded.",
        ],
        warnings: Vec::new(),
        pages,
        stories,
        fonts,
        candidates,
    })
}

impl Analysis {
    pub fn measure(
        &mut self,
        doc: &Document,
        cache: &designcraft_compose::Cache,
        substitutions: &[(String, String)],
        warnings: Vec<String>,
    ) -> Result<(), String> {
        let mut frames = BTreeMap::new();
        for story in &mut self.stories {
            let composed = cache.get(doc, story.story_id, None);
            story.rendered_overset_start = composed.overset_at;
            story.rendered_overset_characters = Some(match composed.overset_at {
                Some(start) => doc.story(story.story_id).and_then(|s| s.text.get(start..)).ok_or("analysis: invalid overset range")?.chars().count(),
                None => 0,
            });
            for frame in &composed.frames {
                if frames.len() >= MAX_ITEMS {
                    return Err("analysis: too many composed frames".into());
                }
                frames.insert(frame.frame, (frame.lines.len(), frame.range.clone()));
            }
        }
        for page in &mut self.pages {
            for element in &mut page.elements {
                if let Some((line_count, range)) = frames.get(&element.item_id) {
                    element.rendered = Some(FrameMeasurement { line_count: *line_count, story_range: range.clone() });
                }
            }
        }
        for font in &mut self.fonts {
            font.substituted_with = substitutions.iter().find(|(source, _)| *source == font.source_family).map(|(_, target)| target.clone());
        }
        self.warnings = warnings;
        Ok(())
    }

    pub fn to_json(&self) -> Result<Vec<u8>, String> {
        let mut writer = CappedWriter(Vec::new());
        serde_json::to_writer_pretty(&mut writer, self).map_err(|e| format!("analysis JSON: {e}"))?;
        writer.write_all(b"\n").map_err(|e| e.to_string())?;
        Ok(writer.0)
    }
}

struct CappedWriter(Vec<u8>);

impl Write for CappedWriter {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        if self.0.len().checked_add(bytes.len()).is_none_or(|n| n > MAX_JSON_BYTES) {
            return Err(std::io::Error::other("analysis exceeds 32 MiB"));
        }
        self.0.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

#[cfg(test)]
mod tests;
