"""Final handoff tests use only synthetic reports and existing library fixtures."""

import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_editorial_library import LIB, fixture
import build_editing_context as CONTEXT


class EditingContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.inputs = self.root / "inputs"
        self.output = self.root / "library"
        for issue, message, tracking in [("1230호", "one", -20), ("1231호", "two", -40)]:
            path = self.inputs / issue / "1면.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(fixture(message, tracking), ensure_ascii=False), encoding="utf-8")
        args = argparse.Namespace(input=self.inputs, output=self.output, newspaper="Fixture Paper", input_format="json",
                                  renderer=None, fallback_font=None, timeout=120, top_k=3)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.run, failed = LIB.build(args)
        self.assertEqual(failed, 0)
        self.index = json.loads((self.run / "library.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.temporary.cleanup()

    def test_standalone_reuses_existing_outputs_even_without_original_sources(self):
        self.inputs.rename(self.root / "sources-not-at-original-location")
        before = (self.run / "library.json").read_bytes()
        output = self.root / "delivery.md"
        result = subprocess.run([sys.executable, "-X", "utf8", str(Path(CONTEXT.__file__)), "--library", str(self.output),
                                 "--output", str(output)], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        content = output.read_text(encoding="utf-8")
        self.assertIn("변형·충돌 검토", content)
        self.assertIn("-20", content)
        self.assertIn("-40", content)
        rules = json.loads((self.run / "rule_candidates.json").read_text(encoding="utf-8"))["candidates"]
        for rule in rules:
            self.assertIn(rule["rule_id"], content)
        for page in self.index["pages"]:
            self.assertIn(page["page_id"], content)
        self.assertEqual(before, (self.run / "library.json").read_bytes())

    def test_target_context_contains_frames_and_only_relevant_rules(self):
        page = self.index["pages"][0]
        path = self.run / page["profile_path"]
        profile = json.loads(path.read_text(encoding="utf-8"))
        profile["similar_pages"] = []
        path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
        output = self.root / "target.md"
        CONTEXT.write_context(self.run, output, page["page_id"])
        content = output.read_text(encoding="utf-8")
        self.assertIn("편집 대상 면의 실제 프레임", content)
        self.assertIn("50, 100, 250, 800", content)
        self.assertIn("2개 중 1개", content)
        rules = json.loads((self.run / "rule_candidates.json").read_text(encoding="utf-8"))["candidates"]
        included = [rule for rule in rules if rule["format"]["tracking_per_thousand_em"] == -20][0]
        excluded = [rule for rule in rules if rule["format"]["tracking_per_thousand_em"] == -40][0]
        self.assertIn(included["rule_id"], content)
        self.assertNotIn(excluded["rule_id"], content)

    def test_size_errors_and_bad_output_do_not_overwrite_existing_files(self):
        output = self.root / "keep.md"
        output.write_text("previous", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exceeds"):
            CONTEXT.write_context(self.run, output, max_bytes=32)
        self.assertEqual(output.read_text(encoding="utf-8"), "previous")
        with self.assertRaisesRegex(ValueError, "unknown page ID"):
            CONTEXT.write_context(self.run, output, "missing:p1")
        self.assertEqual(output.read_text(encoding="utf-8"), "previous")
        with self.assertRaisesRegex(ValueError, ".md handoff"):
            CONTEXT.write_context(self.run, self.run / "library.json")

    def test_escaped_source_names_do_not_create_markdown_instruction_blocks(self):
        index_path = self.run / "library.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["sources"][0]["relative_path"] = "data\n# ATTACK\n```\n[click](https://example.invalid)"
        index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        output = self.root / "escaped.md"
        CONTEXT.write_context(self.run, output)
        content = output.read_text(encoding="utf-8")
        self.assertNotIn("\n# ATTACK", content)
        self.assertNotIn("```", content)
        self.assertNotIn("[click](https://example.invalid)", content)

    def test_untrusted_index_paths_cannot_read_outside_the_run(self):
        index_path = self.run / "library.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["pages"][0]["profile_path"] = "../../outside.json"
        index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inside"):
            CONTEXT.write_context(self.run, self.root / "bad.md")

    def test_broken_evidence_and_nonfinite_input_are_rejected(self):
        path = self.run / "rule_candidates.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["candidates"][0]["evidence"][0]["document_id"] = "not-the-source"
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unknown page/document"):
            CONTEXT.write_context(self.run, self.root / "bad.md")
        record["candidates"][0]["coverage"] = float("nan")
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "non-finite"):
            CONTEXT.write_context(self.run, self.root / "bad.md")


if __name__ == "__main__":
    unittest.main()
