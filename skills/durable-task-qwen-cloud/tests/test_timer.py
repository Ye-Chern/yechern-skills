"""CLI tests for the finite checkpoint timer (all waits are deliberately short)."""
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path, PurePosixPath


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "checkpoint_timer.py"


class CheckpointTimerCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.record = self.root / "state" / "tick.json"
        self.budget = self.root / "state" / "window.json"

    def write_budget(self, *, until=60, reserve=5):
        self.budget.parent.mkdir(parents=True, exist_ok=True)
        self.budget.write_text(json.dumps({
            "deadline_epoch": time.time() + until,
            "reserve_seconds": reserve,
        }), encoding="utf-8")

    def cli(self, command, *args, record=None):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), command, "--record", str(record or self.record), *map(str, args)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode:
            return result, None
        return result, json.loads(result.stdout)

    def arm(self, interval, *, record=None, budget=None):
        return self.cli("arm", "--budget", str(budget or self.budget),
                        "--interval-seconds", interval, record=record)

    def test_short_interval_triggers_checkpoint(self):
        self.write_budget()
        result, armed = self.arm(0.06)
        self.assertEqual(result.returncode, 0, result.stderr)
        result, event = self.cli("wait", "--max-seconds", 0.4)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(event["phase"], "checkpoint")
        self.assertEqual(event["id"], armed["id"])
        self.assertTrue((self.record.with_name(self.record.name + ".result.json")).exists())

    def test_same_record_cannot_be_rearmed_or_delayed(self):
        self.write_budget()
        result, armed = self.arm(4)
        self.assertEqual(result.returncode, 0, result.stderr)
        original = self.record.read_bytes()
        result, _ = self.arm(20)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.record.read_bytes(), original)
        self.assertEqual(json.loads(self.record.read_text())["target_epoch"], armed["target_epoch"])

    def test_pending_wait_slices_keep_the_original_target(self):
        self.write_budget()
        result, armed = self.arm(10)
        self.assertEqual(result.returncode, 0, result.stderr)
        for _ in range(2):
            result, event = self.cli("wait", "--max-seconds", 0.01)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(event["phase"], "pending")
            self.assertEqual(json.loads(self.record.read_text())["target_epoch"], armed["target_epoch"])
            self.assertFalse(self.record.with_name(self.record.name + ".result.json").exists())

    def test_budget_change_is_rejected_by_wait_and_cancel(self):
        self.write_budget()
        result, _ = self.arm(10)
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.budget.open("a", encoding="utf-8") as f:
            f.write(" ")
        for command, args in (("wait", ("--max-seconds", 0.01)), ("cancel", ())):
            result, _ = self.cli(command, *args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Budget changed", result.stderr)

    def test_cancelled_record_returns_without_waiting_or_triggering(self):
        self.write_budget()
        result, armed = self.arm(20)
        self.assertEqual(result.returncode, 0, result.stderr)
        result, cancelled = self.cli("cancel")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cancelled["phase"], "cancel_requested")
        started = time.monotonic()
        result, event = self.cli("wait", "--max-seconds", 0.5)
        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(event, {"id": armed["id"], "phase": "cancelled", "rearm": False})
        self.assertLess(elapsed, 0.3)
        self.assertFalse(self.record.with_name(self.record.name + ".result.json").exists())

    def test_delivery_window_truncates_tick_and_expired_budget_cannot_arm(self):
        # Leave enough startup margin for two separate CLI processes while
        # still exercising a tick clipped to the delivery boundary.
        self.write_budget(until=2, reserve=1.5)
        result, armed = self.arm(5)
        self.assertEqual(result.returncode, 0, result.stderr)
        budget = json.loads(self.budget.read_text())
        self.assertAlmostEqual(armed["target_epoch"], budget["deadline_epoch"] - budget["reserve_seconds"], delta=0.05)
        result, event = self.cli("wait", "--max-seconds", 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(event["phase"], "deliver")

        self.budget.write_text(json.dumps({
            "deadline_epoch": time.time() - 1,
            "reserve_seconds": 0.1,
        }), encoding="utf-8")
        result, _ = self.arm(0.01, record=self.root / "expired.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already in delivery/expired", result.stderr)

    def test_relative_budget_path_survives_copying_whole_directory(self):
        self.write_budget()
        self.record = self.root / "state" / "jobs" / "tick.json"
        result, armed = self.arm(10)
        self.assertEqual(result.returncode, 0, result.stderr)
        record_data = json.loads(self.record.read_text())
        self.assertEqual(record_data["budget_relative_path"], "../window.json")

        copied = self.root / "copied-project"
        shutil.copytree(self.root / "state", copied)
        copied_record = copied / "jobs" / self.record.name
        copied_budget = copied_record.parent.joinpath(*PurePosixPath(record_data["budget_relative_path"]).parts)
        self.assertTrue(copied_budget.is_file())
        self.assertEqual(json.loads(copied_budget.read_text())["reserve_seconds"],
                         json.loads(self.budget.read_text())["reserve_seconds"])
        result, event = self.cli("wait", "--max-seconds", 0.01, record=copied_record)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(event["phase"], "pending")
        self.assertEqual(json.loads(copied_record.read_text())["target_epoch"], armed["target_epoch"])


if __name__ == "__main__":
    unittest.main()
