#!/usr/bin/env python3
"""Owner-only local SQLite export and anonymous telemetry aggregates."""
import argparse
import json
import math
import statistics
from pathlib import Path
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)]


def duration(values):
    values = sorted(values)
    return {"count": len(values), "minMs": values[0] if values else None,
            "medianMs": statistics.median(values) if values else None, "p90Ms": percentile(values, .9),
            "maxMs": values[-1] if values else None}


def read_events(database):
    try:
        with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)) as db:
            rows = db.execute("SELECT body FROM events ORDER BY received, session_id, seq").fetchall()
    except sqlite3.Error as error:
        raise ValueError("telemetry database is unavailable or has no events table") from error
    events = []
    for (body,) in rows:
        try:
            event = json.loads(body)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("telemetry database contains an unreadable event record") from error
        if not isinstance(event, dict):
            raise ValueError("telemetry database contains an unreadable event record")
        events.append(event)
    return events


def summary(events):
    """Aggregate only approved event fields; default output has no session IDs."""
    sessions = {}
    for event in events:
        required = {"sessionId", "seq", "elapsedMs", "gameVersion", "protocolVersion", "type", "detail"}
        if not required <= event.keys() or not isinstance(event["detail"], dict):
            raise ValueError("telemetry database contains an incomplete event record")
        sessions.setdefault(event["sessionId"], []).append(event)

    releases = defaultdict(lambda: {"sessions": 0, "events": 0, "completed": 0})
    phases, errors = Counter(), Counter()
    help_opens = explanations = 0
    completed_durations, session_durations = [], []
    phase_durations = defaultdict(list)
    for records in sessions.values():
        records.sort(key=lambda event: event["seq"])
        first = records[0]
        release = releases[(first["gameVersion"], first["protocolVersion"])]
        release["sessions"] += 1
        release["events"] += len(records)
        session_durations.append(max(event["elapsedMs"] for event in records))
        phase_start = None
        reached = set()
        final_at = None
        for event in records:
            event_type, detail, elapsed = event["type"], event["detail"], event["elapsedMs"]
            if event_type == "phase_entered":
                phase = detail.get("phase")
                if isinstance(phase, str):
                    reached.add(phase)
                    if phase_start:
                        name, started = phase_start
                        phase_durations[name].append(max(0, elapsed - started))
                    phase_start = (phase, elapsed)
            elif event_type == "help_opened":
                help_opens += 1
            elif event_type == "explanation_opened":
                explanations += 1
            elif event_type == "known_error" and isinstance(detail.get("code"), str):
                errors[detail["code"]] += 1
            elif event_type == "final_opened" and final_at is None:
                final_at = elapsed
        if final_at is not None:
            release["completed"] += 1
            completed_durations.append(final_at)
        for phase in reached:
            phases[phase] += 1

    return {
        "events": len(events), "sessions": len(sessions), "completed": len(completed_durations),
        "completionRate": len(completed_durations) / len(sessions) if sessions else None,
        "byVersion": [{"gameVersion": game, "protocolVersion": protocol, **values}
                      for (game, protocol), values in sorted(releases.items())],
        "phasesReached": dict(sorted(phases.items())), "helpOpens": help_opens,
        "explanationOpens": explanations, "knownErrors": dict(sorted(errors.items())),
        "durations": {"session": duration(session_durations), "toFinal": duration(completed_durations),
                      "betweenPhaseEntries": {phase: duration(values) for phase, values in sorted(phase_durations.items())}},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read local anonymous Galaxy telemetry")
    parser.add_argument("database")
    parser.add_argument("--json", action="store_true", help="also include local raw records")
    args = parser.parse_args(argv)
    try:
        events = read_events(args.database)
        report = summary(events)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({"summary": report, "events": events} if args.json else report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
