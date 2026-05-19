#!/usr/bin/env python3
"""Prune old raw GPS points from the SR500 SQLite database.

Keeps trip summaries in the `trips` table and external export files intact,
while deleting old point-level rows from `gps_points` for completed trips.

Default behavior is a dry-run so it is safe to inspect first.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB = "/home/johnny/mc-gps/gps.db"
DEFAULT_RETENTION_DAYS = 90


@dataclass
class CandidateTrip:
    trip_id: str
    end_ts: str
    point_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Delete old gps_points rows for completed trips while keeping the "
            "trips table and exported files."
        )
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=f"Path to SQLite database (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help=(
            "Retention window in days; completed trips older than this are "
            f"eligible for point pruning (default: {DEFAULT_RETENTION_DAYS})"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete rows. Without this flag the script is dry-run only.",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run VACUUM after deleting rows (only meaningful together with --apply).",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run ANALYZE after deleting rows (only meaningful together with --apply).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print candidate trip IDs as well as totals.",
    )
    return parser.parse_args()


def parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_candidates(conn: sqlite3.Connection, cutoff_iso: str) -> list[CandidateTrip]:
    rows = conn.execute(
        """
        SELECT t.trip_id, t.end_ts, COUNT(g.id) AS point_count
        FROM trips AS t
        JOIN gps_points AS g ON g.trip_id = t.trip_id
        WHERE t.end_ts IS NOT NULL
          AND t.end_ts < ?
        GROUP BY t.trip_id, t.end_ts
        ORDER BY t.end_ts ASC
        """,
        (cutoff_iso,),
    ).fetchall()
    return [CandidateTrip(row[0], row[1], row[2]) for row in rows]


def ensure_schema(conn: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    required = {"gps_points", "trips"}
    missing = required - tables
    if missing:
        raise RuntimeError(f"Missing required tables: {', '.join(sorted(missing))}")


def delete_candidates(conn: sqlite3.Connection, cutoff_iso: str) -> int:
    cur = conn.execute(
        """
        DELETE FROM gps_points
        WHERE trip_id IN (
            SELECT trip_id
            FROM trips
            WHERE end_ts IS NOT NULL
              AND end_ts < ?
        )
        """,
        (cutoff_iso,),
    )
    return cur.rowcount if cur.rowcount is not None else 0


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).expanduser()
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2
    if args.days < 1:
        print("--days must be >= 1", file=sys.stderr)
        return 2
    if args.vacuum and not args.apply:
        print("--vacuum requires --apply", file=sys.stderr)
        return 2
    if args.analyze and not args.apply:
        print("--analyze requires --apply", file=sys.stderr)
        return 2

    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=args.days)
    cutoff_iso = cutoff_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        candidates = load_candidates(conn, cutoff_iso)
        candidate_trip_count = len(candidates)
        candidate_point_count = sum(c.point_count for c in candidates)

        print(f"Database: {db_path}")
        print(f"Retention: keep completed trips newer than {args.days} days")
        print(f"Cutoff: {cutoff_iso}")
        print(f"Candidate trips: {candidate_trip_count}")
        print(f"Candidate gps_points rows: {candidate_point_count}")

        if args.verbose and candidates:
            for candidate in candidates:
                print(
                    f"  {candidate.trip_id} end={candidate.end_ts} points={candidate.point_count}"
                )

        if not args.apply:
            print("Dry-run only. Re-run with --apply to delete rows.")
            return 0

        deleted_rows = delete_candidates(conn, cutoff_iso)
        conn.commit()
        print(f"Deleted gps_points rows: {deleted_rows}")

        if args.analyze:
            conn.execute("ANALYZE")
            conn.commit()
            print("Ran ANALYZE")

        if args.vacuum:
            conn.execute("VACUUM")
            print("Ran VACUUM")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
