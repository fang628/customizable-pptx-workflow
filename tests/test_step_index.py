"""Check routing coverage and prevent invalid execution positions."""
import argparse
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shared/scripts'))
import workflow
from step_index import load_step_index, validate_checkpoint
from workflow_lib import STAGES, read_json, write_json


class StepIndexTests(unittest.TestCase):
    def test_stage_coverage_and_step_files(self):
        index = load_step_index()
        self.assertEqual(list(index), STAGES)
        self.assertEqual(sum(len(steps) for steps in index.values() if len(steps) > 1), 21)
        for stage, steps in index.items():
            for step in steps:
                validate_checkpoint(stage, step)

    def test_checkpoint_accepts_nested_id_and_preserves_status(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write_json(project / 'workflow-state.json', {'stages': {'1.3': {'status': 'in_progress'}}})
            workflow._dispatch(project, argparse.Namespace(command='checkpoint', stage='1.3', step='1.3b-2'))
            self.assertEqual(read_json(project / 'workflow-state.json')['stages']['1.3'],
                             {'status': 'in_progress', 'active_step': '1.3b-2'})

    def test_invalid_ids_cannot_mutate_state(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path = project / 'workflow-state.json'
            write_json(path, {'stages': {'1.3': {'status': 'complete'}}})
            original = path.read_bytes()
            for step in ('1.2a', '1.3b', '1.3z', '', ' 1.3a '):
                with self.subTest(step=step), self.assertRaises(ValueError):
                    workflow._dispatch(project, argparse.Namespace(command='checkpoint', stage='1.3', step=step))
                self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
