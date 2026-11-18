"""Relationship extraction tests cover ambiguous semantics and structural facts separately."""

import copy
import unittest
from unittest.mock import patch

from test_editorial_library import fixture
import layout_relations as REL


def wrap(mode="none"):
    return {"mode": mode, "side": "bothSides", "contour": "sameAsClipping", "offsets_pt": [2, 2, 2, 2],
            "invert": False, "custom_boundary": False}


def layout(graphic=False):
    value = {"layer_id": 1, "spread_leaf_order": 0, "item_locked": False, "layer_locked": False,
             "ancestor_locked": False, "ancestor_wrap_present": False, "ignore_text_wrap": False,
             "live_caption_source_item_id": None, "text_wrap": wrap(), "graphic": None}
    if graphic:
        value["graphic"] = {"asset_name": "photo.jpg", "source_link": "old/Links/photo.jpg", "source_link_relative": None,
                            "natural_size_pt": [640, 480], "graphic_to_frame_transform": [1, 0, 0, 1, -10, -5],
                            "crop_amounts_pt": [1, 2, 3, 4], "fitting": "fillProportionally", "clipping_path_present": False,
                            "text_wrap": wrap()}
    return value


def article_fixture():
    data = fixture("Body source")
    data["layout_evidence_version"] = 1
    data["stories"][0]["rendered_overset_characters"] = 5
    data["stories"][0]["rendered_overset_start"] = 6
    body = data["pages"][0]["elements"][0]
    body["group_id"] = 7
    body["layout"] = layout()
    caption = copy.deepcopy(data["stories"][0])
    caption.update(story_id=2, frame_ids=[20], text_excerpt="Caption", text_bytes=7, rendered_overset_characters=0)
    caption["spans"][0].update(paragraph_style="[Basic Paragraph]", character_style="사진설명", range={"start": 0, "end": 7})
    heading = copy.deepcopy(caption)
    heading.update(story_id=3, frame_ids=[40])
    heading["spans"][0].update(character_style="제목_고딕")
    data["stories"].extend([caption, heading])
    data["pages"][0]["elements"].extend([
        {"item_id": 20, "kind": "text", "story_id": 2, "group_id": 7, "bounds_pt": [300, 302, 500, 330], "layout": layout()},
        {"item_id": 30, "kind": "graphic", "story_id": None, "group_id": 7, "asset_id": 9, "asset_available": False,
         "bounds_pt": [300, 100, 500, 300], "layout": layout(True)},
        {"item_id": 40, "kind": "text", "story_id": 3, "group_id": 7, "bounds_pt": [50, 70, 250, 95], "layout": layout()},
    ])
    return data


class LayoutRelationTests(unittest.TestCase):
    def test_article_caption_and_heading_links_are_candidates_with_evidence(self):
        graph = REL.extract_structure(article_fixture(), "doc-fixture")
        self.assertEqual(len(graph["article_units"]), 1)
        self.assertEqual(graph["article_units"][0]["status"], "article_boundary_candidate")
        links = graph["image_relationships"]["links"]
        self.assertEqual({link["kind"] for link in links}, {"caption_of_image", "image_of_article", "heading_of_article"})
        self.assertTrue(all(link["status"] == "candidate" for link in links))
        caption = next(link for link in links if link["kind"] == "caption_of_image")
        self.assertEqual((caption["from_item_id"], caption["to_item_id"]), (20, 30))
        self.assertEqual(caption["evidence"]["shared_group_id"], 7)
        self.assertTrue(caption["evidence"]["caption_style_hint"])

    def test_source_thread_crosses_pages_without_inventing_global_reading_order(self):
        data = fixture(shared=True)
        graph = REL.extract_structure(data, "doc-thread")
        self.assertEqual(graph["reading_order"]["threads"][0]["ordered_frame_ids"], [10, 11])
        self.assertEqual(graph["reading_order"]["between_stories"], "unresolved")
        second = REL.structure_for_page(graph, 2, data["pages"][1]["elements"])
        frame = second["reading_order"]["threads"][0]["frames_on_page_in_source_order"][0]
        self.assertEqual(frame["item_id"], 11)
        self.assertEqual(frame["previous_item_id"], 10)
        self.assertIsNone(frame["next_item_id"])

    def test_live_caption_reference_is_distinct_from_semantic_inference(self):
        data = article_fixture()
        data["pages"][0]["elements"][1]["layout"]["live_caption_source_item_id"] = 30
        graph = REL.extract_structure(data, "doc-explicit")
        link = next(item for item in graph["image_relationships"]["links"] if item["kind"] == "caption_of_image")
        self.assertEqual(link["status"], "observed_live_caption_reference")
        self.assertTrue(all(item["status"] == "article_boundary_candidate" for item in graph["article_units"]))

    def test_overlap_and_wrap_settings_do_not_claim_glyph_collisions(self):
        data = article_fixture()
        image = data["pages"][0]["elements"][2]
        image["bounds_pt"] = [100, 120, 200, 300]
        image["layout"]["text_wrap"] = wrap("boundingBox")
        graph = REL.extract_structure(data, "doc-overlap")
        self.assertTrue(graph["spatial"]["frame_overlaps"])
        self.assertTrue(all(item["actual_glyph_collision"] == "unresolved" for item in graph["spatial"]["frame_overlaps"]))
        self.assertEqual(graph["spatial"]["wrap_settings"][0]["frame_wrap"]["mode"], "boundingBox")
        self.assertEqual(graph["spatial"]["wrap_settings"][0]["effective_contour"], "unresolved")

    def test_missing_assets_overset_and_original_crop_are_preserved(self):
        graph = REL.extract_structure(article_fixture(), "doc-quality")
        self.assertEqual(graph["quality"]["missing_image_item_ids"], [30])
        self.assertEqual(graph["quality"]["missing_font_families"], ["Fixture Font"])
        self.assertEqual(graph["quality"]["overset_stories"][0]["characters"], 5)
        graphic = graph["image_relationships"]["images"][0]["layout"]["graphic"]
        self.assertEqual(graphic["source_link"], "old/Links/photo.jpg")
        self.assertEqual(graphic["crop_amounts_pt"], [1, 2, 3, 4])
        self.assertTrue(graph["layout_evidence_available"])

    def test_old_json_is_partial_and_blank_observation_is_not_asserted_blank_page(self):
        data = fixture()
        data["pages"][0]["elements"] = []
        graph = REL.extract_structure(data, "doc-old")
        self.assertFalse(graph["layout_evidence_available"])
        self.assertEqual(graph["quality"]["no_observed_elements_pages"], [1])
        self.assertEqual(graph["spatial"]["wrap_settings"], [])

    def test_pair_budget_is_reported_without_losing_thread_or_quality_observations(self):
        with patch.object(REL, "MAX_PAIRS", 1):
            graph = REL.extract_structure(article_fixture(), "doc-budget")
        self.assertTrue(graph["limits"]["relations_truncated"])
        self.assertEqual(graph["limits"]["pair_comparisons"], 1)
        self.assertEqual(len(graph["reading_order"]["threads"]), 3)
        self.assertEqual(graph["quality"]["missing_image_item_ids"], [30])

    def test_image_crossing_pages_uses_each_pages_local_bounds(self):
        data = fixture(shared=True)
        image = {"item_id": 30, "kind": "graphic", "asset_id": 9, "asset_available": False,
                 "story_id": None, "bounds_pt": [500, 30, 1100, 200]}
        data["pages"][0]["elements"].append(copy.deepcopy(image))
        image["bounds_pt"] = [-500, 30, 100, 200]
        data["pages"][1]["elements"].append(image)
        graph = REL.extract_structure(data, "doc-spanning")
        second = REL.structure_for_page(graph, 2, data["pages"][1]["elements"])
        self.assertEqual(second["image_relationships"]["images"][0]["bounds_pt"], [-500, 30, 100, 200])
        self.assertEqual(graph["quality"]["missing_image_item_ids"], [30])

    def test_invalid_thread_and_nonfinite_layout_are_rejected(self):
        data = article_fixture()
        data["stories"][0]["frame_ids"].append(20)
        with self.assertRaisesRegex(ValueError, "another story"):
            REL.extract_structure(data, "doc-invalid")
        data = article_fixture()
        data["pages"][0]["elements"][2]["layout"]["graphic"]["crop_amounts_pt"][0] = float("inf")
        with self.assertRaisesRegex(ValueError, "geometry"):
            REL.extract_structure(data, "doc-invalid")
