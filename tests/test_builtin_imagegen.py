"""Offline fixtures only; no real image tool calls or user approvals."""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared/scripts"))
from builtin_imagegen import import_result
from imagegen_adapter import build_command, resolve_script
from workflow_lib import ai_image_config_errors, digest, generation_ledger_errors, read_json, write_json
from preview_originals import compose, insertion_errors, local_frame_errors, repair_blank_frames
from repair_placeholders import repair

spec = importlib.util.spec_from_file_location("native_test_runner", ROOT / "stages/21-concepts/scripts/run_generation.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class BuiltinImagegenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "project"
        subprocess.run([sys.executable, str(ROOT / "stages/00-init/scripts/init_project.py"), str(self.project)],
                       check=True, capture_output=True)
        self.config = read_json(self.project / "00_intake/ai-image-config.json")
        self.config["credentialsReady"] = True  # TEST FIXTURE ONLY
        write_json(self.project / "00_intake/ai-image-config.json", self.config)
        self.source = Path(self.temp.name) / "fixture.png"
        Image.new("RGB", (160, 90), "blue").save(self.source)
        self.job = {"id": "NATIVE-TEST", "asset_id": "GEN-001", "prompt": "横版蓝色抽象主题图，无文字",
                    "output": "02_design/generated-assets/GEN-001.png", "asset_mode": "preserve",
                    "intended_use": "测试背景", "factual_boundary": "非事实抽象图"}
        self.plan = {"jobs": [self.job]}
        write_json(self.project / "02_design/generation-jobs.json", self.plan)
        self.receipt = {"tool": "image_gen", "job_id": self.job["id"],
                        "tool_call_id": "OFFLINE-TEST-FIXTURE-ONLY", "source_file": str(self.source), "tool_result_id": self.source.name,
                        "raw_sha256": digest(self.source), "reference_sha256": {},
                        "prompt_sha256": hashlib.sha256(self.job["prompt"].encode()).hexdigest()}
        self.receipt_path = Path(self.temp.name) / "receipt.json"
        write_json(self.receipt_path, self.receipt)

    def execute(self, run=False, receipt=None):
        # Isolate image registration; upstream gating is tested separately below.
        with patch.object(runner, "gate_errors", return_value=[]), contextlib.redirect_stdout(io.StringIO()):
            runner.execute(self.project, "content", None, sys.executable, run, 300, import_result=receipt)

    def test_no_key_no_cli_and_no_silent_fallback(self):
        self.assertEqual(ai_image_config_errors(self.project), [])
        self.assertTrue(resolve_script(self.config).is_file())
        self.execute()
        with self.assertRaisesRegex(ValueError, "内置 imagegen"):
            self.execute(run=True)
        with self.assertRaisesRegex(ValueError, "不能通过 CLI"):
            build_command(self.config, {})
        self.assertFalse((self.project / self.job["output"]).exists())

    def test_import_is_gated_and_retains_hashes_without_invented_model(self):
        self.receipt.pop("tool_call_id")  # Tool metadata may not expose a call ID.
        write_json(self.receipt_path, self.receipt)
        with self.assertRaisesRegex(ValueError, "阶段 1.1 未完成"):
            runner.execute(self.project, "content", None, sys.executable, False, 300, import_result=self.receipt_path)
        self.execute(receipt=self.receipt_path)
        self.assertEqual(generation_ledger_errors(self.project, "1.2"), [])
        ledger = read_json(self.project / "02_design/generation-ledger.json")
        record = ledger["jobs"][self.job["id"]]
        self.assertEqual(record["model"], "builtin-auto")
        self.assertNotIn("request_id", record)
        self.assertNotIn("tool_call_id", record)
        self.assertNotIn("tool_model", record)
        self.assertEqual(digest(self.project / record["raw_path"]), digest(self.source))
        with self.assertRaisesRegex(ValueError, "不得覆盖"):
            self.execute(receipt=self.receipt_path)
        receipt = self.project / record["tool_receipt_path"]
        data = read_json(receipt)
        data["tool_result_id"] = "ALTERED-FIXTURE.png"
        write_json(receipt, data)
        errors = generation_ledger_errors(self.project, "1.2")
        self.assertTrue(any("回执" in error for error in errors), errors)

    def test_wrong_prompt_or_reference_rejected_before_output(self):
        for field, value in [("prompt_sha256", "0" * 64), ("reference_sha256", {"extra": "0" * 64})]:
            bad = dict(self.receipt)
            bad[field] = value
            write_json(self.receipt_path, bad)
            with self.assertRaises(ValueError):
                self.execute(receipt=self.receipt_path)
            self.assertFalse((self.project / self.job["output"]).exists())

    def test_material_reference_receipts_are_verified(self):
        materials = read_json(self.project / "01_inventory/materials.json")
        materials["materials"] = [{"id": "PHOTO-001", "path": str(self.source), "externalUpload": True}]
        write_json(self.project / "01_inventory/materials.json", materials)
        self.config["allowReferenceUpload"] = True
        write_json(self.project / "00_intake/ai-image-config.json", self.config)
        self.job["references"] = ["PHOTO-001"]
        write_json(self.project / "02_design/generation-jobs.json", self.plan)
        self.receipt["reference_sha256"] = {"PHOTO-001": digest(self.source)}
        write_json(self.receipt_path, self.receipt)
        self.execute(receipt=self.receipt_path)
        self.assertEqual(generation_ledger_errors(self.project, "1.2"), [])
        Image.new("RGB", (160, 90), "red").save(self.source)
        self.assertTrue(any("reference_sha256" in error for error in generation_ledger_errors(self.project, "1.2")))

    def test_wrong_page_ratio_retains_failure_evidence(self):
        Image.new("RGB", (150, 100), "blue").save(self.source)
        self.receipt["raw_sha256"] = digest(self.source)
        write_json(self.receipt_path, self.receipt)
        item = {"job": self.job, "key": "fixture-key", "reference_hashes": {},
                "output": self.project / self.job["output"], "previous": {}}
        path = self.project / "04_full-preview/generation-ledger.json"
        ledger = {"version": 1, "provider": "imagegen", "model": "builtin-auto", "stage": "2.2", "attempts": 0, "jobs": {}}
        with self.assertRaises(ValueError):
            import_result(self.project, {"id": "2.2"}, [item], ledger, path, self.config, resolve_script(self.config), self.receipt_path)
        record = read_json(path)["jobs"][self.job["id"]]
        self.assertEqual(record["status"], "failed")
        self.assertTrue((self.project / record["raw_path"]).is_file())
        self.assertTrue((self.project / record["tool_receipt_path"]).is_file())
        self.assertFalse((self.project / self.job["output"]).exists())

    def frame_fixture(self):
        provider = self.project / "03_concepts/assets/GEN-010.png"
        provider.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1920, 1080), "#FFFFFF").save(provider)
        old_box = {"x": .2, "y": .3, "w": .3, "h": .4}
        new_box = {"x": .2, "y": .3, "w": .3, "h": .3}
        frame = {"imageId": "IMAGE-FIXTURE", "fromBox": old_box, "toBox": new_box,
                 "background": "#FFFFFF", "fill": "#CCCCCC", "revisionAttempts": 2,
                 "note": "OFFLINE TEST ONLY: two fixture revisions; blank region confirmed"}
        image = {"id": "IMAGE-FIXTURE", "sourceId": "PHOTO-FIXTURE", "box": new_box,
                 "path": str(self.source)}
        page = {"id": "S03", "file": provider.relative_to(self.project).as_posix(),
                "sha256": digest(provider), "jobId": "FRAME-FIXTURE", "promptSummary": "OFFLINE FIXTURE",
                "placeholders": [{"imageId": image["id"], "box": new_box}],
                "localPlaceholderRepairs": [frame]}
        return provider, frame, image, page

    def test_local_frame_repair_preserves_provider_and_checks_limited_pixels(self):
        provider, frame, image, page = self.frame_fixture()
        old_hash = digest(provider)
        write_json(self.project / "02_design/image-plan.json", {"slides": [{"id": "S03", "images": [image]}]})
        write_json(self.project / "03_concepts/generation-ledger.json",
                   {"jobs": {"FRAME-FIXTURE": {"status": "complete", "output": page["file"], "sha256": old_hash}}})
        manifest = self.project / "03_concepts/option-b/preview.json"
        write_json(manifest, {"version": 1, "stage": "2.1", "option": "b", "pages": [page]})
        repair(self.project, "2.1", "b")
        updated = read_json(manifest)["pages"][0]
        self.assertEqual(digest(provider), old_hash)
        self.assertNotEqual(updated["file"], updated["providerFile"])
        self.assertEqual(local_frame_errors(self.project, updated, {"images": [image]}, concept=True), [])
        output = self.project / updated["file"]
        with Image.open(output) as img:
            img.putpixel((0, 0), (255, 0, 0))
            img.save(output)
        self.assertTrue(local_frame_errors(self.project, updated, {"images": [image]}, concept=True))
        frame["revisionAttempts"] = 1
        with self.assertRaises(ValueError):
            repair_blank_frames(Image.new("RGB", (1920, 1080)), [frame])

    def test_local_frame_repair_then_original_insertion_is_reproducible(self):
        provider, frame, image, page = self.frame_fixture()
        original = {"imageId": image["id"], "sourceId": image["sourceId"], "path": image["path"],
                    "sha256": digest(self.source), "box": image["box"], "fit": "contain"}
        out = self.project / "04_full-preview/slides/S03.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        compose(self.project, page["file"], [original], [frame]).save(out)
        page.update(providerFile=page["file"], providerSha256=digest(provider), originals=[original],
                    file=out.relative_to(self.project).as_posix())
        self.assertEqual(insertion_errors(self.project, page, {"images": [image]}), [])
        with Image.open(out) as img:
            img.putpixel((0, 0), (255, 0, 0))
            img.save(out)
        self.assertTrue(insertion_errors(self.project, page, {"images": [image]}))


if __name__ == "__main__":
    unittest.main()
