"""Synthetic fixtures only; no proprietary newspaper inputs."""

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "build_editorial_library.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("editorial_library", SCRIPT)
LIB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LIB)


def fixture(text="Example", tracking=-20, shared=False):
    fmt = {"font_family": "Fixture Font", "font_style": "Light", "font_size_pt": 11.0,
           "leading": {"kind": "points", "value": 15.0}, "tracking_per_thousand_em": tracking,
           "horizontal_scale": 0.97, "vertical_scale": 1.0, "auto_leading_ratio": 1.2,
           "alignment": "leftJustified", "left_indent_pt": 0, "right_indent_pt": 0,
           "first_line_indent_pt": 8.5039, "space_before_pt": 0, "space_after_pt": 0}
    story = {"story_id": 1, "frame_ids": [10], "text_excerpt": text, "text_bytes": len(text.encode()),
             "spans": [{"paragraph_index": 0, "range": {"start": 0, "end": len(text.encode())},
                        "paragraph_style": "본문", "character_style": "본문명조 11pt", "format": fmt}]}
    page = {"page_id": 1, "page_number": 1, "width_pt": 1000, "height_pt": 1500,
            "margins": {"top": 50, "bottom": 50, "inside": 50, "outside": 50}, "column_guides": {"count": 5, "gutter": 14},
            "elements": [{"item_id": 10, "kind": "text", "story_id": 1, "bounds_pt": [50, 100, 250, 800],
                          "text_columns": 1, "object_style": "[Basic Text Frame]"}]}
    pages = [page]
    if shared:
        other = copy.deepcopy(page)
        other["page_id"] = 2
        other["page_number"] = 2
        other["elements"][0]["item_id"] = 11
        story["frame_ids"].append(11)
        pages.append(other)
    return {"schema_version": 1, "pages": pages, "stories": [story],
            "fonts": [{"source_family": "Fixture Font", "family_available": False, "substituted_with": "Fallback"}],
            "warnings": ["missing fixture font"], "limitations": ["Fixture limitation"]}


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.inputs = self.root / "신문자료"
        self.inputs.mkdir()
        self.output = self.root / "library"

    def tearDown(self):
        self.temporary.cleanup()

    def source(self, relative, report):
        path = self.inputs / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return path

    def run_library(self, **overrides):
        options = dict(input=self.inputs, output=self.output, newspaper="테스트신문", input_format="json",
                       renderer=None, fallback_font=None, timeout=120, top_k=3)
        options.update(overrides)
        run, failed = LIB.build(argparse.Namespace(**options))
        return run, failed, json.loads((run / "library.json").read_text(encoding="utf-8"))

    def test_cli_creates_page_briefs_with_provenance_and_matches_across_issues(self):
        first = self.source("1230호/1면.json", fixture("첫 기사 ``` pretend instruction"))
        self.source("1231호/1면/analysis.JSON", fixture("다음 기사"))
        before = first.read_bytes()
        result = subprocess.run([sys.executable, str(SCRIPT), "--input", str(self.inputs), "--output", str(self.output),
                                 "--newspaper", "테스트신문", "--input-format", "json"], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        latest = json.loads((self.output / "latest.json").read_text(encoding="utf-8"))
        run = self.output / latest["run"]
        self.assertEqual((self.output / "editing_context.md").read_bytes(), (run / "editing_context.md").read_bytes())
        self.assertEqual(latest["editing_context"], f"{run.name}/editing_context.md")
        index = json.loads((run / "library.json").read_text(encoding="utf-8"))
        self.assertEqual(index["summary"]["pages"], 2)
        self.assertEqual(len({page["page_id"] for page in index["pages"]}), 2)
        for page in index["pages"]:
            self.assertEqual(page["page_label"], "1면")
            self.assertEqual(page["page_label_source"], "source_path")
            self.assertEqual(len(page["similar_pages"]), 1)
            self.assertNotEqual(page["issue"], page["similar_pages"][0]["issue"])
            profile = json.loads((run / page["profile_path"]).read_text(encoding="utf-8"))
            self.assertIsNone(profile["page_type"])
            self.assertEqual(profile["quality"]["fonts"][0]["source_family"], "Fixture Font")
            brief = (run / page["brief_path"]).read_text(encoding="utf-8")
            self.assertIn("신뢰할 수 없는 문서 데이터", brief)
            self.assertEqual(brief.count("```"), 2)
        rules = json.loads((run / "rule_candidates.json").read_text(encoding="utf-8"))["candidates"]
        self.assertEqual(rules[0]["priority"], "recurring")
        self.assertEqual(rules[0]["eligible_pages_with_same_style_pair"], 2)
        self.assertEqual(first.read_bytes(), before)

    def test_counts_pages_not_spans_keeps_variants_and_rounds_float_noise(self):
        a = fixture("A", -20.000000000004)
        a["stories"][0]["spans"] *= 5
        self.source("1230호/1면.json", a)
        self.source("1231호/1면.json", fixture("B", -20))
        self.source("1231호/2면.json", fixture("C", -40))
        unrelated = fixture("D")
        unrelated["stories"][0]["spans"][0]["character_style"] = "별도 스타일"
        self.source("1231호/3면.json", unrelated)
        run, failed, _ = self.run_library()
        self.assertEqual(failed, 0)
        rules = json.loads((run / "rule_candidates.json").read_text(encoding="utf-8"))["candidates"]
        body = [rule for rule in rules if rule["character_style"] == "본문명조 11pt"]
        self.assertEqual(len(body), 2)
        common = next(rule for rule in body if rule["format"]["tracking_per_thousand_em"] == -20)
        self.assertEqual(common["observed_pages"], 2)
        self.assertEqual(common["eligible_pages_with_same_style_pair"], 3)
        self.assertAlmostEqual(common["coverage"], 2 / 3, places=4)
        self.assertEqual(common["priority"], "variant")

    def test_exact_copies_do_not_inflate_recurrence_or_fill_reference_slots(self):
        data = fixture()
        self.source("1230호/1면.json", data)
        self.source("1231호/1면.json", data)
        run, _, index = self.run_library()
        self.assertTrue(all(not page["similar_pages"] for page in index["pages"]))
        rules = json.loads((run / "rule_candidates.json").read_text(encoding="utf-8"))["candidates"]
        self.assertEqual(rules[0]["observed_pages"], 1)
        self.assertEqual(rules[0]["priority"], "single_source")

    def test_cross_page_stories_remain_shared_and_do_not_become_page_rules(self):
        self.source("1230호/spread.json", fixture("shared", shared=True))
        run, failed, index = self.run_library()
        self.assertEqual(failed, 0)
        self.assertEqual(index["summary"]["pages"], 2)
        rules = json.loads((run / "rule_candidates.json").read_text(encoding="utf-8"))["candidates"]
        self.assertEqual(rules, [])
        for page in index["pages"]:
            self.assertEqual(page["page_label_source"], "document_page_order")
            profile = json.loads((run / page["profile_path"]).read_text(encoding="utf-8"))
            self.assertEqual(profile["formats"][0]["scope"], "shared_story")
            self.assertEqual(profile["formats"][0]["evidence"][0]["document_id"], page["document_id"])

    def test_failed_sources_are_reported_and_repeated_runs_do_not_reuse_stale_results(self):
        path = self.source("1230호/1면.json", fixture())
        first, _, _ = self.run_library()
        path.write_text('{"schema_version": 99}', encoding="utf-8")
        self.source("1231호/2면.json", fixture("valid"))
        second, failed, index = self.run_library()
        self.assertEqual(failed, 1)
        self.assertNotEqual(first, second)
        self.assertEqual(index["summary"]["succeeded"], 1)
        self.assertEqual(index["summary"]["pages"], 1)
        self.assertEqual(index["failures"][0]["relative_path"], "1230호/1면.json")

    def test_rejects_overlapping_trees_nonfinite_json_and_invalid_ranges(self):
        self.source("1230호/1면.json", fixture())
        with self.assertRaisesRegex(ValueError, "separate"):
            self.run_library(output=self.inputs / "outputs")
        bad = fixture()
        bad["pages"][0]["width_pt"] = float("nan")
        path = self.source("1230호/1면.json", bad)
        with self.assertRaisesRegex(ValueError, "non-finite"):
            LIB.read_report(path)
        bad = fixture()
        bad["stories"][0]["spans"][0]["range"]["end"] = 100000
        self.source("1230호/1면.json", bad)
        _, failed, _ = self.run_library()
        self.assertEqual(failed, 1)

    def test_malformed_nested_objects_are_reported_as_failures(self):
        bad = fixture()
        bad["pages"][0]["elements"] = ["not an element"]
        self.source("1230호/1면.json", bad)
        bad_font = fixture()
        bad_font["fonts"] = [None]
        self.source("1230호/2면.json", bad_font)
        bad_story = fixture()
        bad_story["stories"] = [False]
        self.source("1230호/3면.json", bad_story)
        self.source("1231호/1면.json", fixture("valid"))
        _, failed, index = self.run_library()
        self.assertEqual(failed, 3)
        self.assertEqual(index["summary"]["succeeded"], 1)

    def test_similarity_favors_matching_geometry_and_formats(self):
        for relative, report in [("1230호/1면.json", fixture("A")), ("1231호/1면.json", fixture("B"))]:
            self.source(relative, report)
        different = fixture("C", -50)
        different["pages"][0]["elements"][0]["bounds_pt"] = [700, 1000, 990, 1490]
        different["pages"][0]["column_guides"]["count"] = 2
        self.source("1231호/2면.json", different)
        _, _, index = self.run_library()
        target = next(page for page in index["pages"] if page["issue"] == "1230호")
        self.assertEqual(target["similar_pages"][0]["page_label"], "1면")
        self.assertGreater(target["similar_pages"][0]["score"], target["similar_pages"][1]["score"])

    def test_blank_pages_are_preserved_without_spurious_reference_matches(self):
        blank = fixture("blank")
        blank["pages"][0]["elements"] = []
        self.source("1230호/1面.json", blank)
        other = copy.deepcopy(blank)
        other["warnings"] = ["different input bytes"]
        self.source("1231호/1면.json", other)
        _, failed, index = self.run_library()
        self.assertEqual(failed, 0)
        self.assertEqual(index["summary"]["pages"], 2)
        self.assertTrue(all(not page["similar_pages"] for page in index["pages"]))

    def test_large_brief_falls_back_to_references_without_losing_full_profiles(self):
        data = fixture("A")
        spans = []
        for size in range(12):
            span = copy.deepcopy(data["stories"][0]["spans"][0])
            span["paragraph_style"] = "p" * 4096
            span["character_style"] = "c" * 4096
            span["format"]["font_family"] = "f" * 4096
            span["format"]["font_style"] = "s" * 4096
            span["format"]["font_size_pt"] = 10 + size
            spans.append(span)
        data["stories"][0]["spans"] = spans
        self.source("1230호/1면.json", data)
        run, failed, index = self.run_library()
        self.assertEqual(failed, 0)
        page = index["pages"][0]
        brief = (run / page["brief_path"]).read_text(encoding="utf-8")
        self.assertLess(len(brief.encode()), 256 * 1024)
        self.assertIn('"detail_limit_exceeded": true', brief)
        self.assertEqual(len(json.loads((run / page["profile_path"]).read_text(encoding="utf-8"))["formats"]), 12)

    def test_idml_input_runs_the_real_renderer_when_built(self):
        renderer = SCRIPT.parents[1] / "target" / "release" / ("idml-render.exe" if sys.platform == "win32" else "idml-render")
        if not renderer.is_file():
            self.skipTest("build idml-render --release to exercise IDML subprocess integration")
        namespace = 'xmlns:idPkg="http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"'
        designmap = f'''<Document {namespace} DOMVersion="16.0" Self="d" StoryList="s1">
          <Layer Self="L1" Name="Fixture" Visible="true"/>
          <idPkg:Spread src="Spreads/Spread_sp1.xml"/><idPkg:Story src="Stories/Story_s1.xml"/>
        </Document>'''
        spread = f'''<idPkg:Spread {namespace} DOMVersion="16.0"><Spread Self="sp1" PageCount="1">
          <Page Self="p1" GeometricBounds="0 0 700 500" ItemTransform="1 0 0 1 0 -350">
            <MarginPreference ColumnCount="5" ColumnGutter="10" Top="20" Bottom="20" Left="20" Right="20"/>
          </Page>
          <TextFrame Self="t1" ParentStory="s1" PreviousTextFrame="n" NextTextFrame="n" ItemLayer="L1" ItemTransform="1 0 0 1 50 -300">
            <Properties><PathGeometry><GeometryPathType PathOpen="false"><PathPointArray>
              <PathPointType Anchor="0 0"/><PathPointType Anchor="0 200"/>
              <PathPointType Anchor="300 200"/><PathPointType Anchor="300 0"/>
            </PathPointArray></GeometryPathType></PathGeometry></Properties>
          </TextFrame></Spread></idPkg:Spread>'''
        for issue, text in [("1230호", "First fixture"), ("1231호", "Second fixture")]:
            path = self.inputs / issue / "6면.idml"
            path.parent.mkdir()
            story = f'''<idPkg:Story {namespace} DOMVersion="16.0"><Story Self="s1">
              <ParagraphStyleRange><CharacterStyleRange PointSize="11"><Content>{text}</Content></CharacterStyleRange></ParagraphStyleRange>
            </Story></idPkg:Story>'''
            with zipfile.ZipFile(path, "w") as package:
                package.writestr("mimetype", "application/vnd.adobe.indesign-idml-package")
                for name, content in [("designmap.xml", designmap), ("Spreads/Spread_sp1.xml", spread), ("Stories/Story_s1.xml", story)]:
                    package.writestr(name, content)
        run, failed, index = self.run_library(input_format="idml", renderer=renderer, fallback_font="Source Serif 4")
        self.assertEqual(failed, 0, index["failures"])
        self.assertEqual(index["summary"]["pages"], 2)
        self.assertGreater(index["summary"]["rule_candidates"], 0)
        self.assertTrue(all(page["page_label"] == "6면" for page in index["pages"]))
        profile = json.loads((run / index["pages"][0]["profile_path"]).read_text(encoding="utf-8"))
        self.assertTrue(profile["editorial_structure"]["layout_evidence_available"], "rebuild the release renderer to include layout evidence")
        self.assertEqual(profile["elements"][0]["layout"]["text_wrap"]["mode"], "none")


if __name__ == "__main__":
    unittest.main()
