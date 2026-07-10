import json
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from uisce.config import DB_PATH, JSONL_PATH

DUBLIN = ZoneInfo("Europe/Dublin")
NO_DURATION_SOURCES = {"not_found", "lifted_immediate"}


def create_table(conn):
    conn.execute("DROP TABLE IF EXISTS inferred_cases")
    conn.execute("""
        CREATE TABLE inferred_cases (
            case_id INTEGER PRIMARY KEY REFERENCES cases(id),
            end_description_hash TEXT NOT NULL,
            end_input_start_date TEXT,
            end_model TEXT NOT NULL,
            end_prompt_version INTEGER NOT NULL,
            end_notes TEXT,
            end_source TEXT NOT NULL,
            end_local_date TEXT,
            end_local_time TEXT,
            end_inferred_at TEXT NOT NULL,
            end_duration_seconds REAL
        )
    """)


def compute_duration_seconds(start_date, end_source, local_date, local_time):
    if end_source in NO_DURATION_SOURCES or not local_date or not start_date:
        return None

    year, month, day = (int(p) for p in local_date.split("-"))
    if local_time:
        hour, minute = (int(p) for p in local_time.split(":"))
        second = 0
    else:
        hour, minute, second = 23, 59, 59

    end_local = datetime(year, month, day, hour, minute, second, tzinfo=DUBLIN)
    end_utc = end_local.astimezone(timezone.utc)
    start_utc = datetime.fromisoformat(start_date)

    duration = (end_utc - start_utc).total_seconds()
    return duration if duration >= 0 else None


def latest_per_case(records):
    latest = {}
    for record in records:
        current = latest.get(record["case_id"])
        if current is None or record["inferred_at"] > current["inferred_at"]:
            latest[record["case_id"]] = record
    return latest.values()


def first_start_date_per_case(records):
    earliest = {}
    for record in records:
        current = earliest.get(record["case_id"])
        if current is None or record["inferred_at"] < current["inferred_at"]:
            earliest[record["case_id"]] = record
    return {case_id: record["start_date"] for case_id, record in earliest.items()}


def check_cases_cover(conn, case_ids):
    known_ids = {row[0] for row in conn.execute("SELECT id FROM cases")}
    missing = sorted(case_ids - known_ids)
    if missing:
        raise RuntimeError(
            f"{len(missing)} case_id(s) in {JSONL_PATH} are not present in {DB_PATH} "
            f"(range {missing[0]}-{missing[-1]}). The local DB is likely older than "
            "whatever DB the inference run used. Refresh it first, e.g.:\n"
            "  gh release download --pattern uisce.db --dir out/ --clobber"
        )


def run():
    with open(JSONL_PATH) as f:
        records = [json.loads(line) for line in f if line.strip()]

    first_start_dates = first_start_date_per_case(records)
    latest = list(latest_per_case(records))

    rows = [
        (
            r["case_id"],
            r["description_hash"],
            first_start_dates[r["case_id"]],
            r["model"],
            r["prompt_version"],
            r["notes"],
            r["end_source"],
            r["local_date"],
            r["local_time"],
            r["inferred_at"],
            compute_duration_seconds(
                first_start_dates[r["case_id"]], r["end_source"], r["local_date"], r["local_time"]
            ),
        )
        for r in latest
    ]

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        check_cases_cover(conn, {r["case_id"] for r in latest})
        create_table(conn)
        conn.executemany(
            """
            INSERT OR REPLACE INTO inferred_cases (
                case_id, end_description_hash, end_input_start_date, end_model,
                end_prompt_version, end_notes, end_source, end_local_date,
                end_local_time, end_inferred_at, end_duration_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    print(f"Upserted {len(rows)} rows into inferred_cases")
