use std::collections::BTreeSet;
use std::sync::Arc;

use designcraft_doc::{CharAttrs, Document};
use designcraft_fonts::FontDb;

/// Replace unavailable families after resolving inherited paragraph and character styles.
pub fn replace_missing(doc: &mut Document, family: &str) -> Result<Vec<String>, String> {
    let fonts = FontDb::global().scoped(doc.font_scope);
    if !fonts.has_family(family) {
        return Err(format!("fallback font {family:?} is not installed"));
    }
    let original_styles = doc.styles.clone();
    let mut replaced = BTreeSet::new();
    let ids: Vec<_> = doc.stories.keys().copied().collect();
    let mut visited = 0usize;
    for id in ids {
        let Some(story) = doc.story_mut(id) else { continue };
        let mut pending = vec![story];
        while let Some(story) = pending.pop() {
            visited = visited.saturating_add(1);
            if visited > 100_000 {
                return Err("too many nested stories while replacing fonts".into());
            }
            let mut ranges = Vec::new();
            for (index, paragraph) in story.para_ranges().iter().enumerate() {
                let Some(format) = story.paras.get(index) else { continue };
                let (_, base) = original_styles.resolve_para(format);
                for (run, format) in story.runs() {
                    let start = run.start.max(paragraph.start);
                    let end = if paragraph.is_empty() && run.contains(&paragraph.start) {
                        story.text.get(start..).and_then(|tail| tail.chars().next()).map_or(start, |c| start.saturating_add(c.len_utf8()))
                    } else {
                        run.end.min(paragraph.end)
                    };
                    if start >= end {
                        continue;
                    }
                    let effective = original_styles.resolve_char(&base, format);
                    if !effective.font_family.is_empty() && !fonts.has_family(&effective.font_family) {
                        replaced.insert(effective.font_family.clone());
                        let style = fonts.face(family, &effective.font_style).style.clone();
                        ranges.push((start..end, style));
                    }
                }
            }
            for (range, style) in ranges {
                story.format_chars(range, |format| {
                    format.over.font_family = Some(family.to_string());
                    format.over.font_style = Some(style.clone());
                });
            }
            pending.extend(story.tables.values_mut().flat_map(|table| Arc::make_mut(table).cells.iter_mut().map(|cell| &mut cell.text)));
            pending.extend(story.notes.iter_mut().chain(&mut story.endnotes).map(|note| &mut Arc::make_mut(note).text));
        }
    }
    fn swap(attrs: &mut CharAttrs, fonts: &designcraft_fonts::ScopedFonts<'_>, family: &str, replaced: &mut BTreeSet<String>) {
        if let Some(original) = attrs.font_family.as_ref().filter(|name| !name.is_empty() && !fonts.has_family(name)) {
            replaced.insert(original.clone());
            attrs.font_family = Some(family.to_string());
            if let Some(style) = &attrs.font_style {
                attrs.font_style = Some(fonts.face(family, style).style.clone());
            }
        }
    }
    let styles = doc.styles_mut();
    for style in &mut styles.paragraph {
        swap(&mut style.chars, &fonts, family, &mut replaced);
    }
    for style in &mut styles.character {
        swap(&mut style.chars, &fonts, family, &mut replaced);
    }
    for composite in &mut styles.composite_fonts {
        for entry in &mut composite.entries {
            if !entry.family.is_empty() && !fonts.has_family(&entry.family) {
                replaced.insert(entry.family.clone());
                entry.style = fonts.face(family, &entry.style).style.clone();
                entry.family = family.to_string();
            }
        }
    }
    Ok(replaced.into_iter().collect())
}
