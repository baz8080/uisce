import json
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from uisce.config import DB_PATH, JSONL_PATH

DUBLIN = ZoneInfo("Europe/Dublin")
NO_END_SIGNAL_SOURCES = {"not_found", "lifted_immediate"}

# end_source values whose end is *observed* (works reported done) rather than
# *scheduled* (a plan that may or may not have been met). Only these support a
# claim about how long something actually took; see notes/statuspage-methodology.md.
OBSERVED_END_SOURCES = {"completion_update"}


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
            notice_to_end_seconds REAL
        )
    """)


def compute_notice_to_end_seconds(start_date, end_source, local_date, local_time):
    """Seconds from notice publication (cases.start_date) to the end the notice
    reports. This is NOT outage duration: the start is when Uisce Éireann
    published the notice, not when supply was lost, and for the scheduled_*
    sources the end is a stated plan rather than an observed completion.
    See notes/data-quality.md."""
    if end_source in NO_END_SIGNAL_SOURCES or not local_date or not start_date:
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

    elapsed = (end_utc - start_utc).total_seconds()
    return elapsed if elapsed >= 0 else None


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


def count_never_inferred(conn):
    """Cases with a description but no inferred_cases row — downloaded since the
    last uisce-infer run. Almost all are open (they are the newest cases), and
    open cases with no end signal accrue to "now" on the site, so the backlog
    lands exactly where it distorts most. See notes/pipeline-dependencies.md."""
    return conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(status = 'Open'), 0) FROM cases "
        "WHERE description IS NOT NULL "
        "AND id NOT IN (SELECT case_id FROM inferred_cases)"
    ).fetchone()


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
            compute_notice_to_end_seconds(
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
                end_local_time, end_inferred_at, notice_to_end_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        never_inferred, never_inferred_open = count_never_inferred(conn)

    print(f"Upserted {len(rows)} rows into inferred_cases")
    if never_inferred:
        print(
            f"{never_inferred} case(s) have no inference yet ({never_inferred_open} open) — "
            "open ones accrue to now on the site until uisce-infer runs"
        )
