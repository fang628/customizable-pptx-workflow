"""Offline regressions for change propagation, approvals, caches and bounded reads."""
import contextlib
import copy
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared/scripts"))
import workflow
from workflow_lib import STAGES, collect, digest, read_json, write_json, content_plan_ready_errors
from dependency_scope import snapshot, difference, scoped_approval_errors, review_dependencies
from read_context import select

runner_spec = importlib.util.spec_from_file_location("scoped_runner", ROOT / "stages/21-concepts/scripts/run_generation.py")
runner = importlib.util.module_from_spec(runner_spec)
runner_spec.loader.exec_module(runner)


class DependencyScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.content = {"include_toc": False, "progress_bar": {"enabled": False}, "sections": [],
                        "slides": [{"id": p, "page_type": "content", "title": p,
                                    "texts": [{"id": p + "-BODY-01", "text": "Original"}], "materials": []}
                                   for p in ("S01", "S02", "S03")]}
        write_json(self.project / "02_design/content.json", self.content)
        self.design = "# Design\n## Shared\nBlue theme\n## Pages\n### S01：First\nOriginal one\n### S02：Second\nOriginal two\n### S03：Third\nOriginal three\n"
        (self.project / "02_design/design-spec.md").write_text(self.design, encoding="utf-8")
        for path in ("02_design/image-intent-plan.json", "02_design/image-plan.json", "02_design/claim-map.json"):
            write_json(self.project / path, {"version": 1, "slides": [{"id": p, "images": [], "claims": []} for p in ("S01", "S02", "S03")]})
        write_json(self.project / "01_inventory/materials.json", {"materials": []})
        write_json(self.project / "02_design/generated-assets.json", {"version": 1, "assets": []})
        write_json(self.project / "06_build/deck-spec.json", {"meta": {"theme": "blue"}, "slides": [{"id": p, "elements": []} for p in ("S01", "S02", "S03")]})
        for option in "abc":
            write_json(self.project / f"03_concepts/option-{option}/preview.json", {"pages": [{"id": "S01", "jobId": "C-S01", "file": f"03_concepts/option-{option}/S01.png"}]})
        write_json(self.project / "04_full-preview/previews.json", {"styleDirection": "b", "pages": [{"id": p, "file": f"04_full-preview/slides/{p}.png"} for p in ("S01", "S02", "S03")]})
        write_json(self.project / "03_concepts/approval.json", {"option": "b"})

    def edit_page(self, identifier="S02"):
        content = copy.deepcopy(self.content)
        next(p for p in content["slides"] if p["id"] == identifier)["texts"][0]["text"] = "Changed"
        write_json(self.project / "02_design/content.json", content)
        (self.project / "02_design/design-spec.md").write_text(self.design.replace("Original two", "Changed two"), encoding="utf-8")

    def test_page_copy_and_markdown_only_invalidate_that_page(self):
        old = snapshot(self.project, "2.2")
        self.edit_page()
        self.assertEqual(difference(old, snapshot(self.project, "2.2"))["pages"], ["S02"])
        self.assertFalse(difference(old, snapshot(self.project, "2.2"))["global"])

    def test_nonrepresentative_page_keeps_concept_approval(self):
        scope = snapshot(self.project, "2.1", option="b")
        approval = {"kind": "concept", "option": "b", "scope": scope,
                    "page_confirmations": {p: {"sha256": h, "evidence": "OFFLINE FIXTURE", "confirmed_at": "fixture"} for p,h in scope["pages"].items()}}
        self.edit_page()
        self.assertEqual(scoped_approval_errors(self.project, approval), [])
        self.content["slides"][0]["title"] = "New representative"
        write_json(self.project / "02_design/content.json", self.content)
        self.assertTrue(scoped_approval_errors(self.project, approval))

    def test_shared_style_order_and_legacy_records_are_conservative(self):
        old = snapshot(self.project, "2.2")
        (self.project / "02_design/design-spec.md").write_text(self.design.replace("Blue theme", "Red theme"), encoding="utf-8")
        changed = difference(old, snapshot(self.project, "2.2"))
        self.assertTrue(changed["global"])
        self.assertEqual(changed["pages"], ["S01", "S02", "S03"])
        self.assertTrue(difference(None, old)["global"])

    def test_shared_material_bytes_invalidate_all_using_pages(self):
        material = self.project / "evidence.png"
        material.write_bytes(b"original bytes")
        write_json(self.project / "01_inventory/materials.json", {"materials": [{"id": "PHOTO-001", "path": "evidence.png", "sha256": digest(material)}]})
        content = copy.deepcopy(self.content)
        for row in content["slides"][:2]:
            row["materials"] = ["PHOTO-001"]
        write_json(self.project / "02_design/content.json", content)
        old = snapshot(self.project, "2.2")
        material.write_bytes(b"changed bytes")
        self.assertEqual(difference(old, snapshot(self.project, "2.2"))["pages"], ["S01", "S02"])

    def test_cache_key_is_stable_when_another_page_changes(self):
        job = {"id": "FULL-S01", "page_id": "S01", "prompt": "Blue page", "output": "unused"}
        args = (self.project, {"id": "2.2"}, job, {}, {"provider": "mock", "model": "mock"}, Path(__file__))
        old = runner._version_key(*args)
        self.edit_page()
        self.assertEqual(old, runner._version_key(*args))
        changed = dict(job, prompt="Red page")
        self.assertNotEqual(old, runner._version_key(self.project, {"id": "2.2"}, changed, {}, {"provider": "mock", "model": "mock"}, Path(__file__)))

    def test_review_depends_on_native_objects_even_when_render_does_not_change(self):
        old = review_dependencies(self.project)
        deck = read_json(self.project / "06_build/deck-spec.json")
        deck["slides"][1]["elements"] = [{"type": "text", "text": "Same pixels but now editable"}]
        write_json(self.project / "06_build/deck-spec.json", deck)
        new = review_dependencies(self.project)
        self.assertEqual(old["S01"], new["S01"])
        self.assertNotEqual(old["S02"], new["S02"])

    def test_complete_keeps_unaffected_downstream_records_and_noop_is_idempotent(self):
        for name in ("element-inventory.md", "slide-elements.md"):
            path = self.project / "05_reconstruction" / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("# Inventory\n### S01\nOne\n### S02\nTwo\n### S03\nThree\n", encoding="utf-8")
        write_json(self.project / "05_reconstruction/assets.json", {"assets": []})
        state = {"version": 2, "stages": {s: {"status": "not_started"} for s in STAGES}}
        for stage in ("1.3", "3.1", "3.2"):
            state["stages"][stage] = {"status": "complete", "files": collect(self.project, stage), "dependencies": snapshot(self.project, stage)}
        write_json(self.project / "workflow-state.json", state)
        with patch.object(workflow, "gate_errors", return_value=[]), patch.object(workflow, "design_errors", return_value=[]), patch.object(workflow, "stage_preview_errors", return_value=[]):
            workflow.complete(self.project, "1.3")
        self.assertEqual(read_json(self.project / "workflow-state.json"), state)
        self.edit_page()
        state["stages"]["1.3"]["status"] = "awaiting_user"
        write_json(self.project / "workflow-state.json", state)
        with patch.object(workflow, "gate_errors", return_value=[]), patch.object(workflow, "design_errors", return_value=[]), patch.object(workflow, "stage_preview_errors", return_value=[]):
            workflow.complete(self.project, "1.3")
        changed = read_json(self.project / "workflow-state.json")
        self.assertEqual(changed["stages"]["3.1"]["pending_pages"], ["S02"])
        self.assertEqual(changed["stages"]["3.2"]["pending_pages"], ["S02"])
        self.assertEqual(changed["stages"]["3.1"]["files"], state["stages"]["3.1"]["files"])

    def test_content_plan_is_required_before_any_image_attempt(self):
        self.assertTrue(content_plan_ready_errors(self.project))
        with patch.object(runner, "gate_errors", return_value=[]), patch.object(runner, "call_provider") as provider:
            with self.assertRaisesRegex(ValueError, "先生成 content-plan"):
                runner.execute(self.project, "content", None, sys.executable, True, 300)
            provider.assert_not_called()
        plan = self.project / "02_design/content-plan.md"
        plan.write_text("# 内容清单\n## 文案\n- 文案 CP-001：测试说明\n## 文案与材料原文索引\n"
                        "| 文案编号 | PPT候选文案 | 材料ID | 原文定位 | 原文摘录 | 整理方式 |\n"
                        "|---|---|---|---|---|---|\n| CP-001 | 测试说明 | 结构文案 | 不适用 | 不适用 | 结构文案 |\n", encoding="utf-8")
        write_json(self.project / "02_design/generation-jobs.json", {"jobs": [{"asset_id": "GEN-001"}]})
        self.assertTrue(any("GEN-001" in e for e in content_plan_ready_errors(self.project)))
        plan.write_text(plan.read_text(encoding="utf-8") + "\n- 候选图片 GEN-001：拟生成背景\n", encoding="utf-8")
        self.assertEqual(content_plan_ready_errors(self.project), [])

    def test_section_reader_ignores_example_headings_and_fails_on_missing_pages(self):
        text = "# Root\n## First\nA\n```python\n## Not a heading\n```\n## Second\nB\n### S03：Page\nC\n"
        self.assertIn("Not a heading", select(text, ["First"]))
        self.assertNotIn("Second", select(text, ["First"]))
        self.assertEqual(select(text, page="S03"), "### S03：Page\nC\n")
        with self.assertRaises(ValueError):
            select(text, page="S04")


class ScopedApprovalIntegrationTests(unittest.TestCase):
    def test_partial_preview_confirmation_retains_other_evidence_and_rejects_omissions(self):
        # Use the established offline provider/real validation fixture end to end.
        from tests.test_workflow import WorkflowTests
        fixture = WorkflowTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.approved_fixture(through="2.2")
        project = fixture.project
        old = read_json(project / "04_full-preview/approval.json")
        previews = read_json(project / "04_full-preview/previews.json")
        changed_ids = [page["id"] for page in previews["pages"][:2]]
        for page in previews["pages"][:2]:
            page["review"] = "OFFLINE FIXTURE: reviewed changed local metadata"
        write_json(project / "04_full-preview/previews.json", previews)
        fixture.workflow("await", "2.2", "--notes", "OFFLINE FIXTURE")
        rejected = fixture.workflow("approve", "preview", "--pages", changed_ids[0], "--evidence", "OFFLINE FIXTURE", success=False)
        self.assertIn("未确认", rejected.stderr)
        fixture.workflow("approve", "preview", "--pages", *changed_ids, "--evidence", "OFFLINE FIXTURE changed pages")
        fixture.workflow("complete", "2.2")
        current = read_json(project / "04_full-preview/approval.json")
        for identifier in set(old["page_confirmations"]) - set(changed_ids):
            self.assertEqual(current["page_confirmations"][identifier], old["page_confirmations"][identifier])
        self.assertEqual(scoped_approval_errors(project, current), [])
        self.assertTrue(list((project / "04_full-preview/approval-history").glob("*.json")))


if __name__ == "__main__":
    unittest.main()
