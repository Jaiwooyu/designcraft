"""Five bounded structural observations; semantic article ownership remains a candidate."""

from __future__ import annotations

from collections import defaultdict
import math

MAX_ITEMS = 50_000
MAX_PAIRS = 200_000
MAX_RELATIONS = 10_000
ROLE_WORDS = {
    "caption": ("사진설명", "사진 설명", "캡션", "caption"),
    "byline": ("기자명", "byline"),
    "heading": ("제목", "headline", "heading", "subtitle"),
    "body": ("본문", "body"),
}


def identifier(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2**63 - 1:
        raise ValueError("invalid structure identifier")
    return value


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e9:
        raise ValueError("invalid structural geometry")
    return value


def bounds(element):
    value = element["bounds_pt"]
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("invalid frame bounds")
    result = [finite(item) for item in value]
    if result[2] < result[0] or result[3] < result[1]:
        raise ValueError("inverted frame bounds")
    return result


def role_hint(story):
    weights = defaultdict(int)
    for span in story["spans"]:
        names = (span["paragraph_style"] + " " + span["character_style"]).casefold()
        if len(names) > 8193:
            raise ValueError("style name exceeds structure limit")
        # A byline paragraph may reuse the caption character style.
        for role in ("byline", "caption", "heading", "body"):
            if any(word in names for word in ROLE_WORDS[role]):
                weights[role] += max(1, span["range"]["end"] - span["range"]["start"])
                break
    return max(weights, key=weights.get) if weights else "unresolved"


def relation_geometry(left, right):
    a, b = bounds(left), bounds(right)
    dx = max(0, b[0] - a[2], a[0] - b[2])
    dy = max(0, b[1] - a[3], a[1] - b[3])
    width = min(a[2] - a[0], b[2] - b[0])
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) / width if width > 0 else 0
    group = left.get("group_id")
    shared = group if group is not None and group == right.get("group_id") else None
    return {"shared_group_id": shared, "horizontal_overlap_ratio": round(overlap, 4),
            "vertical_gap_pt": round(dy, 4), "distance_pt": round(math.hypot(dx, dy), 4)}


def wrap_facts(value):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("mode") not in {"none", "boundingBox", "contour", "jumpObject", "jumpToNextColumn"}:
        raise ValueError("invalid source wrap evidence")
    offsets = value.get("offsets_pt")
    if not isinstance(offsets, list) or len(offsets) != 4:
        raise ValueError("invalid wrap offsets")
    for offset in offsets:
        finite(offset)
    return {key: value.get(key) for key in ("mode", "side", "contour", "offsets_pt", "invert", "custom_boundary")}


def layout_facts(element):
    value = element.get("layout")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("invalid source layout evidence")
    result = {}
    for key in ("item_locked", "layer_locked", "ancestor_locked", "ancestor_wrap_present", "ignore_text_wrap"):
        item = value.get(key)
        if item is not None and not isinstance(item, bool):
            raise ValueError("invalid source lock/wrap flag")
        result[key] = item
    for key in ("layer_id", "spread_leaf_order", "live_caption_source_item_id"):
        result[key] = identifier(value[key]) if value.get(key) is not None else None
    result["text_wrap"] = wrap_facts(value.get("text_wrap"))
    transform = value.get("frame_to_parent_transform")
    if transform is not None and (not isinstance(transform, list) or len(transform) != 6):
        raise ValueError("invalid frame transform")
    result["frame_to_parent_transform"] = [finite(item) for item in transform] if transform is not None else None
    graphic = value.get("graphic")
    result["graphic"] = None
    if graphic is not None:
        if not isinstance(graphic, dict):
            raise ValueError("invalid source graphic evidence")
        data = {}
        for key in ("asset_name", "source_link", "source_link_relative"):
            item = graphic.get(key)
            if item is not None and (not isinstance(item, str) or len(item) > 4096):
                raise ValueError("invalid graphic reference")
            data[key] = item
        for key, length in (("natural_size_pt", 2), ("graphic_to_frame_transform", 6), ("crop_amounts_pt", 4)):
            items = graphic[key]
            if not isinstance(items, list) or len(items) != length:
                raise ValueError("invalid graphic geometry")
            data[key] = [finite(item) for item in items]
        data["fitting"] = graphic.get("fitting")
        data["clipping_path_present"] = graphic.get("clipping_path_present")
        data["text_wrap"] = wrap_facts(graphic.get("text_wrap"))
        result["graphic"] = data
    return result


def extract_structure(report: dict, document_id: str) -> dict:
    pages = report["pages"]
    if len(pages) > 1000 or len(report["stories"]) > MAX_ITEMS:
        raise ValueError("structure page/story limit exceeded")
    stories = {identifier(story["story_id"]): story for story in report["stories"]}
    if len(stories) != len(report["stories"]):
        raise ValueError("duplicate structure story ID")
    hints = {key: role_hint(story) for key, story in stories.items()}
    instances, item_pages, by_page, story_pages = {}, defaultdict(set), {}, defaultdict(set)
    count = 0
    for number, page in enumerate(pages, 1):
        local = []
        seen = set()
        for original in page["elements"]:
            count += 1
            if count > MAX_ITEMS:
                raise ValueError("structure element limit exceeded")
            item = identifier(original["item_id"])
            if item in seen:
                raise ValueError("duplicate page element ID")
            seen.add(item)
            bounds(original)
            node = {"item_id": item, "page_number": number, "kind": original["kind"], "bounds_pt": original["bounds_pt"],
                    "group_id": original.get("group_id"), "story_id": original.get("story_id"), "asset_id": original.get("asset_id"),
                    "asset_available": original.get("asset_available"), "layout": layout_facts(original)}
            if node["group_id"] is not None:
                identifier(node["group_id"])
            if node["asset_id"] is not None:
                identifier(node["asset_id"])
            if node["asset_available"] is not None and not isinstance(node["asset_available"], bool):
                raise ValueError("invalid asset availability")
            if node["story_id"] is not None:
                identifier(node["story_id"])
                if node["story_id"] not in stories:
                    raise ValueError("missing structure story")
                story_pages[node["story_id"]].add(number)
            instances.setdefault(item, node)
            item_pages[item].add(number)
            local.append(node)
        by_page[number] = local
    threads = []
    frame_total = 0
    for key, story in stories.items():
        frames = story["frame_ids"]
        if not isinstance(frames, list):
            raise ValueError("invalid source thread")
        frame_total += len(frames)
        if frame_total > MAX_ITEMS or len(set(frames)) != len(frames):
            raise ValueError("source thread limit or repeated frame")
        for item in frames:
            identifier(item)
            if item in instances and instances[item]["story_id"] != key:
                raise ValueError("thread references another story's frame")
        threads.append({"story_id": key, "status": "observed_source_thread", "ordered_frame_ids": frames,
                        "page_numbers": sorted(story_pages[key]), "unobserved_frame_ids": [item for item in frames if item not in instances],
                        "role_hint": hints[key], "role_status": "candidate"})
    units = [{"unit_id": f"story-{thread['story_id']}", "story_id": thread["story_id"], "frame_ids": thread["ordered_frame_ids"],
              "page_numbers": thread["page_numbers"], "status": "article_boundary_candidate", "basis": "source_story_and_style_hint",
              "role_hint": thread["role_hint"]} for thread in threads if thread["role_hint"] in {"body", "unresolved"}]
    relations, overlaps, wrapping = [], [], []
    comparisons = 0
    truncated = False

    def spend():
        nonlocal comparisons, truncated
        if comparisons >= MAX_PAIRS or len(relations) + len(overlaps) >= MAX_RELATIONS:
            truncated = True
            return False
        comparisons += 1
        return True

    def add(kind, left, right, evidence, status="candidate", rank=None):
        if len(relations) + len(overlaps) >= MAX_RELATIONS:
            return
        relations.append({"relation_id": f"relation-{len(relations) + 1}", "kind": kind, "status": status,
                          "page_numbers": [left["page_number"]], "from_item_id": left["item_id"], "to_item_id": right["item_id"],
                          "from_story_id": left["story_id"], "to_story_id": right["story_id"], "rank": rank, "evidence": evidence})

    for number, local in by_page.items():
        text = [item for item in local if item["kind"] == "text"]
        images = [item for item in local if item["kind"] == "graphic"]
        seeds = [item for item in text if hints[item["story_id"]] in {"body", "unresolved"}]
        for node in local:
            layout = node["layout"]
            if layout and (layout.get("ancestor_wrap_present") or any(wrap and wrap["mode"] != "none" for wrap in
                           (layout.get("text_wrap"), (layout.get("graphic") or {}).get("text_wrap")))):
                wrapping.append({"item_id": node["item_id"], "page_numbers": [number], "status": "observed_settings",
                                 "frame_wrap": layout["text_wrap"], "graphic_wrap": (layout.get("graphic") or {}).get("text_wrap"),
                                 "ancestor_wrap_present": layout["ancestor_wrap_present"], "effective_contour": "unresolved"})
        for node in [item for item in text if hints[item["story_id"]] in {"heading", "byline"}] + images:
            matches = []
            for seed in seeds:
                if seed["story_id"] == node["story_id"]:
                    continue
                if not spend():
                    break
                geometry = relation_geometry(node, seed)
                if geometry["shared_group_id"] is not None or (geometry["horizontal_overlap_ratio"] >= 0.4 and geometry["distance_pt"] <= 72):
                    matches.append((geometry["shared_group_id"] is None, geometry["distance_pt"], seed["item_id"], seed, geometry))
            used = set()
            for match in sorted(matches):
                seed, geometry = match[-2:]
                if seed["story_id"] in used:
                    continue
                used.add(seed["story_id"])
                kind = "image_of_article" if node["kind"] == "graphic" else f"{hints[node['story_id']]}_of_article"
                add(kind, node, seed, geometry, rank=len(used))
                if len(used) == 3:
                    break
        for image in images:
            candidates = []
            for caption in text:
                if not spend():
                    break
                explicit = (caption["layout"] or {}).get("live_caption_source_item_id") == image["item_id"]
                geometry = relation_geometry(image, caption)
                below = bounds(caption)[1] >= bounds(image)[3] - 1
                caption_hint = hints[caption["story_id"]] == "caption"
                if explicit or (caption_hint and (geometry["shared_group_id"] is not None or
                    (below and geometry["horizontal_overlap_ratio"] >= 0.5 and geometry["vertical_gap_pt"] <= 36))):
                    candidates.append((not explicit, geometry["shared_group_id"] is None, geometry["distance_pt"], caption["item_id"], caption, geometry, explicit))
            for rank, match in enumerate(sorted(candidates)[:3], 1):
                caption, geometry, explicit = match[-3:]
                add("caption_of_image", caption, image, geometry | {"caption_style_hint": hints[caption["story_id"]] == "caption"},
                    status="observed_live_caption_reference" if explicit else "candidate", rank=rank)
        for index, left in enumerate(local):
            for right in local[index + 1:]:
                if not spend():
                    break
                if "text" not in {left["kind"], right["kind"]}:
                    continue
                a, b = bounds(left), bounds(right)
                width, height = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
                if width > 0 and height > 0:
                    overlaps.append({"page_numbers": [number], "item_ids": [left["item_id"], right["item_id"]],
                                     "status": "observed_frame_aabb_overlap", "overlap_area_pt2": round(width * height, 4),
                                     "actual_glyph_collision": "unresolved"})
            if truncated:
                break
    caption_status, article_status = {}, set()
    for link in relations:
        if link["kind"] == "caption_of_image":
            key = (link["page_numbers"][0], link["to_item_id"])
            if key not in caption_status or link["status"] == "observed_live_caption_reference":
                caption_status[key] = "observed_reference" if link["status"] == "observed_live_caption_reference" else "candidate"
        elif link["kind"] == "image_of_article":
            article_status.add((link["page_numbers"][0], link["from_item_id"]))
    images = [node | {"caption_status": caption_status.get((number, node["item_id"]), "unresolved"),
                      "article_status": "candidate" if (number, node["item_id"]) in article_status else "unresolved"}
              for number, local in by_page.items() for node in local if node["kind"] == "graphic"]
    overset = []
    for key, story in stories.items():
        characters = story.get("rendered_overset_characters")
        if characters is not None and (isinstance(characters, bool) or not isinstance(characters, int) or characters < 0):
            raise ValueError("invalid overset count")
        overset.append({"story_id": key, "page_numbers": sorted(story_pages[key]), "scope": "whole_source_story",
                       "status": "unmeasured" if characters is None else "rendered_overset" if characters else "no_rendered_overset",
                       "characters": characters, "byte_start": story.get("rendered_overset_start")})
    available = report.get("layout_evidence_version") == 1 and all(item["layout"] is not None for item in instances.values())
    return {"schema_version": 1, "document_id": document_id, "layout_evidence_available": available,
            "article_units": units, "reading_order": {"threads": threads, "between_stories": "unresolved"},
            "image_relationships": {"images": images, "links": relations}, "spatial": {"frame_overlaps": overlaps, "wrap_settings": wrapping,
                "scope": "AABB observations and imported settings, not actual text-flow/collision validation"},
            "quality": {"overset_stories": overset, "missing_image_item_ids": sorted({item["item_id"] for item in images if item["asset_available"] is False}),
                "unresolved_image_item_ids": sorted({item["item_id"] for item in images if item["asset_available"] is None}),
                "no_observed_elements_pages": [number for number, items in by_page.items() if not items],
                "missing_font_families": [font["source_family"] for font in report["fonts"] if not font["family_available"]]},
            "limits": {"pair_comparisons": comparisons, "maximum_pair_comparisons": MAX_PAIRS, "relations_truncated": truncated},
            "notes": ["Article units and semantic relations are candidates, never approved ownership or reading order between stories.",
                      "Source locks are not user editing permissions. Image source links are metadata, not resolved local file paths.",
                      "AABB overlap is not proof of glyph overlap; rotation, clipping and text wrap require rendering.",
                      "Only visible printable document leaves are included; parent, anchored, table-cell and note content remains excluded."]}


def structure_for_page(structure, number, page_elements):
    ids = {item["item_id"] for item in page_elements}
    units = []
    for unit in structure["article_units"]:
        if number in unit["page_numbers"]:
            units.append({key: value for key, value in unit.items() if key != "frame_ids"} |
                         {"frame_ids_on_page": [item for item in unit["frame_ids"] if item in ids], "source_frame_count": len(unit["frame_ids"])})
    threads = []
    for thread in structure["reading_order"]["threads"]:
        if number not in thread["page_numbers"]:
            continue
        frames = thread["ordered_frame_ids"]
        sequence = [{"item_id": item, "source_index": position, "previous_item_id": frames[position - 1] if position else None,
                     "next_item_id": frames[position + 1] if position + 1 < len(frames) else None}
                    for position, item in enumerate(frames) if item in ids]
        threads.append({"story_id": thread["story_id"], "status": thread["status"], "source_frame_count": len(frames),
                        "page_numbers": thread["page_numbers"], "frames_on_page_in_source_order": sequence})
    return {"schema_version": 1, "document_id": structure["document_id"], "layout_evidence_available": structure["layout_evidence_available"],
            "article_units": units, "reading_order": {"threads": threads, "between_stories": "unresolved"},
            "image_relationships": {"images": [item for item in structure["image_relationships"]["images"] if item["page_number"] == number],
                "links": [link for link in structure["image_relationships"]["links"] if number in link["page_numbers"]]},
            "spatial": {key: [item for item in structure["spatial"][key] if number in item["page_numbers"]] for key in ("frame_overlaps", "wrap_settings")},
            "quality": {"overset_stories": [story for story in structure["quality"]["overset_stories"] if number in story["page_numbers"]],
                "missing_image_item_ids": [item for item in structure["quality"]["missing_image_item_ids"] if item in ids],
                "unresolved_image_item_ids": [item for item in structure["quality"]["unresolved_image_item_ids"] if item in ids],
                "no_observed_elements": number in structure["quality"]["no_observed_elements_pages"],
                "missing_font_families": structure["quality"]["missing_font_families"]},
            "limits": structure["limits"], "notes": structure["notes"]}
