//! Bounded source evidence for relationship analysis, never inferred editing permissions.

use designcraft_doc::{ContourType, Document, Fitting, Item, ItemId, LayerId, TextWrap, WrapMode, WrapSide};
use serde::Serialize;

use super::{finite, name};

#[derive(Clone, Serialize)]
pub(super) struct WrapEvidence {
    mode: WrapMode,
    side: WrapSide,
    contour: ContourType,
    offsets_pt: [f64; 4],
    invert: bool,
    custom_boundary: bool,
}

impl WrapEvidence {
    fn new(wrap: &TextWrap) -> Result<Self, String> {
        finite(&wrap.offsets)?;
        Ok(Self {
            mode: wrap.mode,
            side: wrap.side,
            contour: wrap.contour,
            offsets_pt: wrap.offsets,
            invert: wrap.invert,
            custom_boundary: wrap.path.is_some(),
        })
    }
}

#[derive(Clone, Serialize)]
pub(super) struct GraphicEvidence {
    asset_name: Option<String>,
    source_link: Option<String>,
    source_link_relative: Option<String>,
    natural_size_pt: [f64; 2],
    graphic_to_frame_transform: [f64; 6],
    crop_amounts_pt: [f64; 4],
    fitting: Fitting,
    clipping_path_present: bool,
    text_wrap: WrapEvidence,
}

#[derive(Clone, Serialize)]
pub(super) struct LayoutEvidence {
    layer_id: LayerId,
    spread_leaf_order: usize,
    item_locked: bool,
    layer_locked: bool,
    ancestor_locked: bool,
    ancestor_wrap_present: bool,
    frame_to_parent_transform: [f64; 6],
    text_wrap: WrapEvidence,
    ignore_text_wrap: Option<bool>,
    live_caption_source_item_id: Option<ItemId>,
    graphic: Option<GraphicEvidence>,
}

pub(super) fn observe(
    doc: &Document,
    item: &Item,
    ancestor_locked: bool,
    ancestor_wrap_present: bool,
    order: usize,
) -> Result<LayoutEvidence, String> {
    let graphic = item
        .graphic()
        .map(|g| {
            let asset = doc.assets.get(&g.asset);
            let size = [g.size.0, g.size.1];
            let transform = g.xf.as_coeffs();
            finite(&size)?;
            finite(&transform)?;
            finite(&g.crop)?;
            Ok::<_, String>(GraphicEvidence {
                asset_name: asset.map(|a| name(&a.name)).transpose()?,
                source_link: asset.and_then(|a| a.link.as_deref()).map(name).transpose()?,
                source_link_relative: asset.and_then(|a| a.link_relative.as_deref()).map(name).transpose()?,
                natural_size_pt: size,
                graphic_to_frame_transform: transform,
                crop_amounts_pt: g.crop,
                fitting: g.auto_fit,
                clipping_path_present: g.clip.is_some(),
                text_wrap: WrapEvidence::new(&g.wrap)?,
            })
        })
        .transpose()?;
    Ok(LayoutEvidence {
        layer_id: item.layer,
        spread_leaf_order: order,
        item_locked: item.locked,
        layer_locked: doc.layer(item.layer).is_some_and(|layer| layer.locked),
        ancestor_locked,
        ancestor_wrap_present,
        frame_to_parent_transform: item.xf.as_coeffs(),
        text_wrap: WrapEvidence::new(&item.wrap)?,
        ignore_text_wrap: item.text_frame().map(|frame| frame.options.ignore_wrap),
        live_caption_source_item_id: item.live_caption.as_ref().map(|caption| caption.source),
        graphic,
    })
}
