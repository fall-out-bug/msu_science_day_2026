#!/usr/bin/env python3
"""Tests for owner-local telemetry aggregates; no collector is started."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).parent
EXPORT = HERE / "admin_export.py"


def event(session, seq, elapsed, kind, detail=None, game="2026.10.08-complete.1", protocol="2026-10-08-cnn-constructor-v1"):
    return {"schema": 1, "eventId": f"event-{session}-{seq}", "sessionId": session,
            "seq": seq, "elapsedMs": elapsed, "gameVersion": game, "protocolVersion": protocol,
            "channel": "web", "type": kind, "detail": detail or {}}


class AdminExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "events.sqlite3"
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("CREATE TABLE events (session_id TEXT, seq INTEGER, received INTEGER, body TEXT)")

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, records):
        with closing(sqlite3.connect(self.db)) as db, db:
            for received, record in enumerate(records, 1):
                db.execute("INSERT INTO events VALUES (?,?,?,?)", (record["sessionId"], record["seq"], received, json.dumps(record)))

    def command(self, *extra):
        return subprocess.run([sys.executable, str(EXPORT), str(self.db), *extra], text=True, capture_output=True)

    def test_e2e_like_records_aggregate_stages_versions_completion_help_errors_and_durations(self):
        records = [
            event("s1", 1, 0, "session_started"), event("s1", 2, 10, "phase_entered", {"phase": "intro"}),
            event("s1", 3, 20, "phase_entered", {"phase": "collect"}), event("s1", 4, 30, "map_target_collected", {"imageId": "child_m85"}),
            event("s1", 5, 50, "phase_entered", {"phase": "labels"}), event("s1", 6, 60, "help_opened"),
            event("s1", 7, 70, "explanation_opened"), event("s1", 8, 90, "known_error", {"code": "timeout"}),
            event("s1", 9, 100, "final_opened"), event("s1", 10, 110, "phase_entered", {"phase": "final"}),
            event("s2", 1, 0, "session_started", game="2026.10.09-complete.1"), event("s2", 2, 25, "phase_entered", {"phase": "intro"}, game="2026.10.09-complete.1"),
        ]
        self.add(records)
        result = self.command()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual((report["events"], report["sessions"], report["completed"], report["completionRate"]), (12, 2, 1, .5))
        self.assertEqual(report["phasesReached"], {"collect": 1, "final": 1, "intro": 2, "labels": 1})
        self.assertEqual((report["helpOpens"], report["explanationOpens"], report["knownErrors"]), (1, 1, {"timeout": 1}))
        self.assertEqual(report["durations"]["session"], {"count": 2, "minMs": 25, "medianMs": 67.5, "p90Ms": 110, "maxMs": 110})
        self.assertEqual(report["durations"]["toFinal"]["medianMs"], 100)
        self.assertEqual(len(report["byVersion"]), 2)
        self.assertNotIn("s1", result.stdout)

    def test_empty_database_is_a_valid_zero_summary(self):
        result = self.command()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual((report["events"], report["sessions"], report["completed"]), (0, 0, 0))
        self.assertIsNone(report["completionRate"])
        self.assertEqual(report["durations"]["session"]["count"], 0)

    def test_phase_reach_counts_sessions_not_returns_to_the_same_stage(self):
        self.add([event("s1", 1, 0, "session_started"),
                  event("s1", 2, 10, "phase_entered", {"phase": "labels"}),
                  event("s1", 3, 20, "phase_entered", {"phase": "review"}),
                  event("s1", 4, 30, "phase_entered", {"phase": "labels"})])
        result = self.command()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["phasesReached"], {"labels": 1, "review": 1})

    def test_malformed_or_incomplete_rows_fail_without_echoing_content(self):
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("INSERT INTO events VALUES (?,?,?,?)", ("x", 1, 1, "{not json"))
        result = self.command()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unreadable event record", result.stderr)
        self.assertNotIn("{not json", result.stderr)
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("DELETE FROM events")
            db.execute("INSERT INTO events VALUES (?,?,?,?)", ("x", 1, 1, json.dumps({"sessionId": "x"})))
        result = self.command()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete event record", result.stderr)

    def test_json_retains_owner_only_raw_export(self):
        self.add([event("s1", 1, 0, "session_started")])
        result = self.command("--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["summary"]["events"], 1)
        self.assertEqual(report["events"][0]["sessionId"], "s1")


if __name__ == "__main__":
    unittest.main()
