use std::sync::Arc;

use designcraft_doc::{CharAttrs, Content, Item, LayerId, ParaAttrs, ParaFormat, ParagraphStyle, Shape, SpreadRef};

use super::*;

fn fixture(text: &str) -> (Document, ItemId, StoryId) {
    let mut doc = Document::new(&Default::default());
    let layer = doc.layers[0].id;
    let (frame, story) = doc.add_text_frame(SpreadRef::Doc(0), Rect::new(50.0, 60.0, 300.0, 400.0), layer, text, ParaFormat::default()).unwrap();
    (doc, frame, story)
}

#[test]
fn resolves_inherited_styles_and_overrides_with_utf8_evidence() {
    let (mut doc, frame, story) = fixture("한글 제목\n기사 본문");
    let styles = doc.styles_mut();
    styles.paragraph.push(ParagraphStyle {
        name: "본문 기반".into(),
        based_on: None,
        next_style: None,
        shortcut: String::new(),
        para: ParaAttrs { first_line_indent: Some(7.0), ..Default::default() },
        chars: CharAttrs { font_family: Some("Missing Test Font".into()), size: Some(9.0), ..Default::default() },
    });
    styles.paragraph.push(ParagraphStyle {
        name: "사회면 본문".into(),
        based_on: Some("본문 기반".into()),
        next_style: None,
        shortcut: String::new(),
        para: ParaAttrs::default(),
        chars: CharAttrs::default(),
    });
    let text = doc.story_mut(story).unwrap();
    for para in &mut text.paras {
        para.style = "사회면 본문".into();
    }
    text.format_chars(0..6, |f| f.over.size = Some(18.0));
    let before = doc.clone();
    let report = extract(&doc, &HashMap::from([("uStory".into(), story)])).unwrap();
    assert_eq!(doc, before, "extraction must not mutate source data");
    let observed = &report.stories[0];
    assert_eq!(observed.idml_self.as_deref(), Some("uStory"));
    assert_eq!(observed.frame_ids, vec![frame]);
    assert_eq!(observed.spans[0].range, 0..6);
    assert_eq!(observed.spans[0].format.font_size_pt, 18.0);
    assert_eq!(observed.spans[0].format.first_line_indent_pt, 7.0);
    assert!(observed.spans[0].has_character_overrides);
    assert_eq!(observed.spans[1].format.font_size_pt, 9.0);
    assert_eq!(report.candidates.len(), 2);
    for c in &report.candidates {
        assert_eq!(c.kind, "observed_format");
        assert_eq!(c.scope, "uploaded_document");
        assert!(c.strength.is_none());
        for evidence in &c.evidence {
            assert!(doc.story(evidence.story_id).unwrap().text.get(evidence.range.clone()).is_some());
        }
    }
}

#[test]
fn source_fonts_survive_substitution_and_measurements_are_separate() {
    let (mut doc, _, story) = fixture("A headline");
    doc.story_mut(story).unwrap().format_chars(0..10, |f| f.over.font_family = Some("Missing Analysis Test Font".into()));
    let mut report = extract(&doc, &HashMap::new()).unwrap();
    let replacements = crate::fonts::replace_missing(&mut doc, "Source Serif 4").unwrap();
    let substitutions = replacements.into_iter().map(|source| (source, "Source Serif 4".into())).collect::<Vec<_>>();
    report.measure(&doc, &designcraft_compose::Cache::new(), &substitutions, vec!["test warning".into()]).unwrap();
    assert_eq!(report.stories[0].spans[0].format.font_family, "Missing Analysis Test Font");
    assert_eq!(report.fonts[0].substituted_with.as_deref(), Some("Source Serif 4"));
    assert!(!report.fonts[0].family_available);
    assert!(report.pages[0].elements[0].rendered.as_ref().unwrap().line_count > 0);
    assert_eq!(report.stories[0].rendered_overset_characters, Some(0));
    assert_eq!(report.warnings, ["test warning"]);
}

#[test]
fn threaded_frames_share_source_evidence_and_report_overset() {
    let (mut doc, first, story) = fixture(&"A long body with spaces. ".repeat(100));
    doc.item_mut(first).unwrap().path = designcraft_geom::shapes::rectangle(Rect::new(50.0, 60.0, 150.0, 90.0));
    let (second, _) = doc.add_text_frame(SpreadRef::Doc(0), Rect::new(160.0, 60.0, 260.0, 90.0), doc.layers[0].id, "", Default::default()).unwrap();
    doc.thread(first, second).unwrap();
    let mut report = extract(&doc, &HashMap::new()).unwrap();
    assert_eq!(report.stories.len(), 1);
    assert_eq!(report.stories[0].frame_ids, [first, second]);
    assert_eq!(report.candidates[0].observed_spans, 1);
    report.measure(&doc, &designcraft_compose::Cache::new(), &[], Vec::new()).unwrap();
    let start = report.stories[0].rendered_overset_start.unwrap();
    assert_eq!(report.stories[0].rendered_overset_characters, Some(doc.story(story).unwrap().text[start..].chars().count()));
    assert!(report.stories[0].rendered_overset_characters.unwrap() > 0);
    let ranges: Vec<_> = report.pages[0].elements.iter().map(|e| e.rendered.as_ref().unwrap().story_range.clone()).collect();
    assert_eq!(ranges[0].end, ranges[1].start);
}

#[test]
fn nested_group_transform_and_page_offset_match_evidence_bounds() {
    let (mut doc, frame, _) = fixture("group text");
    let spread = Arc::make_mut(&mut doc.spreads[0]);
    let child = spread.items.pop().unwrap();
    let mut group = Item::new(ItemId(90_000), child.layer, Shape::Group, Default::default());
    group.xf = Affine::translate((20.0, 30.0));
    group.content = Content::Group { items: vec![child] };
    spread.items.push(Arc::new(group));
    spread.pages[0].x = 10.0;
    let report = extract(&doc, &HashMap::new()).unwrap();
    let element = &report.pages[0].elements[0];
    assert_eq!(element.item_id, frame);
    assert_eq!(element.group_id, Some(ItemId(90_000)));
    assert_eq!(element.bounds_pt, [60.0, 90.0, 310.0, 430.0]);
}

#[test]
fn ignores_nonprinting_hidden_and_pasteboard_text_and_unused_styles() {
    let (mut doc, _, _) = fixture("hidden");
    Arc::make_mut(&mut Arc::make_mut(&mut doc.spreads[0]).items[0]).hidden = true;
    let layer = doc.layers[0].id;
    doc.add_text_frame(SpreadRef::Doc(0), Rect::new(10_000.0, 0.0, 10_100.0, 100.0), layer, "pasteboard", Default::default()).unwrap();
    let (nonprinting, _) =
        doc.add_text_frame(SpreadRef::Doc(0), Rect::new(10.0, 10.0, 100.0, 100.0), layer, "nonprinting", Default::default()).unwrap();
    doc.item_mut(nonprinting).unwrap().nonprinting = true;
    let report = extract(&doc, &HashMap::new()).unwrap();
    assert!(report.stories.is_empty());
    assert!(report.candidates.is_empty());
    assert!(report.pages[0].elements.is_empty());
}

#[test]
fn bounds_excerpts_and_examples_without_losing_observation_counts() {
    let long_text = format!("{}\n{}", "한".repeat(600), ["문단"; 12].join("\n"));
    let (doc, _, _) = fixture(&long_text);
    let report = extract(&doc, &HashMap::new()).unwrap();
    assert_eq!(report.stories[0].text_excerpt.chars().count(), MAX_EXCERPT_CHARS);
    assert!(report.stories[0].text_excerpt_truncated);
    assert_eq!(report.candidates.len(), 1);
    assert_eq!(report.candidates[0].observed_spans, 13);
    assert_eq!(report.candidates[0].evidence.len(), MAX_EXAMPLES);
    assert!(report.candidates[0].evidence_truncated);
    let first = report.to_json().unwrap();
    assert_eq!(first, extract(&doc, &HashMap::new()).unwrap().to_json().unwrap());
}

#[test]
fn rejects_nonfinite_geometry_and_malformed_runs_without_panicking() {
    let (mut doc, _, story) = fixture("한글");
    doc.story_mut(story).unwrap().chars[0].len = usize::MAX;
    assert!(extract(&doc, &HashMap::new()).is_err());
    let (mut doc, _, _) = fixture("text");
    Arc::make_mut(&mut Arc::make_mut(&mut doc.spreads[0]).items[0]).xf = Affine::scale(f64::NAN);
    assert!(extract(&doc, &HashMap::new()).is_err());
}

#[test]
fn rejects_excessive_nesting_and_text() {
    let (mut doc, _, story) = fixture("text");
    doc.story_mut(story).unwrap().text = "x".repeat(MAX_TEXT_BYTES + 1);
    assert!(extract(&doc, &HashMap::new()).is_err());
    let (mut doc, _, _) = fixture("deep");
    let spread = Arc::make_mut(&mut doc.spreads[0]);
    let mut child = spread.items.pop().unwrap();
    for i in 0..65 {
        let mut group = Item::new(ItemId(80_000 + i), LayerId(1), Shape::Group, Default::default());
        group.layer = doc.layers[0].id;
        group.content = Content::Group { items: vec![child] };
        child = Arc::new(group);
    }
    spread.items.push(child);
    assert!(extract(&doc, &HashMap::new()).is_err());
}

#[test]
fn layout_evidence_keeps_group_locks_and_wrap_without_inferring_permissions() {
    let (mut doc, _, _) = fixture("Grouped body");
    let spread = Arc::make_mut(&mut doc.spreads[0]);
    let child = spread.items.pop().unwrap();
    let mut group = Item::new(ItemId(90_001), child.layer, Shape::Group, Default::default());
    group.locked = true;
    group.wrap.mode = designcraft_doc::WrapMode::BoundingBox;
    group.content = Content::Group { items: vec![child] };
    spread.items.push(Arc::new(group));
    let before = doc.clone();
    let report = extract(&doc, &HashMap::new()).unwrap();
    let json: serde_json::Value = serde_json::from_slice(&report.to_json().unwrap()).unwrap();
    let layout = &json["pages"][0]["elements"][0]["layout"];
    assert_eq!(json["layout_evidence_version"], 1);
    assert_eq!(layout["ancestor_locked"], true);
    assert_eq!(layout["ancestor_wrap_present"], true);
    assert_eq!(layout["item_locked"], false);
    assert_eq!(layout["text_wrap"]["mode"], "none");
    assert_eq!(doc, before);
}

#[test]
fn layout_evidence_preserves_asset_crop_transform_and_rejects_nonfinite_wrap() {
    use designcraft_doc::{Asset, AssetId, Fitting, Graphic};
    let (mut doc, frame, _) = fixture("replace frame with graphic");
    let asset = AssetId(42);
    doc.assets.insert(asset, Arc::new(Asset { id: asset, name: "photo.jpg".into(), link: Some("old/Links/photo.jpg".into()), ..Default::default() }));
    let item = doc.item_mut(frame).unwrap();
    item.content = Content::Graphic(Graphic {
        layer_options: None,
        asset,
        size: (640.0, 480.0),
        xf: Affine::translate((-12.0, -7.0)),
        clip: None,
        auto_fit: Fitting::FillProportionally,
        fit_align: 4,
        crop: [1.0, 2.0, 3.0, 4.0],
        wrap: Default::default(),
        fill: Default::default(),
    });
    item.wrap.mode = designcraft_doc::WrapMode::BoundingBox;
    item.wrap.offsets = [5.0; 4];
    let json: serde_json::Value = serde_json::from_slice(&extract(&doc, &HashMap::new()).unwrap().to_json().unwrap()).unwrap();
    let element = &json["pages"][0]["elements"][0];
    assert_eq!(element["asset_available"], false);
    assert_eq!(element["layout"]["graphic"]["source_link"], "old/Links/photo.jpg");
    assert_eq!(element["layout"]["graphic"]["crop_amounts_pt"], serde_json::json!([1.0, 2.0, 3.0, 4.0]));
    assert_eq!(element["layout"]["graphic"]["graphic_to_frame_transform"], serde_json::json!([1.0, 0.0, 0.0, 1.0, -12.0, -7.0]));
    assert_eq!(element["layout"]["text_wrap"]["offsets_pt"], serde_json::json!([5.0, 5.0, 5.0, 5.0]));
    doc.item_mut(frame).unwrap().wrap.offsets[0] = f64::NAN;
    assert!(extract(&doc, &HashMap::new()).is_err());
}
