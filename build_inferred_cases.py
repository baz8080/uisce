import json
import sqlite3
from pathlib import Path

DB_PATH = Path("out/uisce.db")
JSONL_PATH = Path("out/inferred_duration.jsonl")


def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inferred_cases (
            case_id INTEGER PRIMARY KEY REFERENCES cases(id),
            end_description_hash TEXT NOT NULL,
            end_input_start_date TEXT,
            end_model TEXT NOT NULL,
            end_prompt_version INTEGER NOT NULL,
            end_notes TEXT,
            end_source TEXT NOT NULL,
            end_local_date TEXT,
            end_local_time TEXT,
            end_inferred_at TEXT NOT NULL
        )
    """)


def latest_per_case(records):
    latest = {}
    for record in records:
        current = latest.get(record["case_id"])
        if current is None or record["inferred_at"] > current["inferred_at"]:
            latest[record["case_id"]] = record
    return latest.values()


def run():
    with open(JSONL_PATH) as f:
        records = [json.loads(line) for line in f if line.strip()]

    rows = [
        (
            r["case_id"],
            r["description_hash"],
            r["start_date"],
            r["model"],
            r["prompt_version"],
            r["notes"],
            r["end_source"],
            r["local_date"],
            r["local_time"],
            r["inferred_at"],
        )
        for r in latest_per_case(records)
    ]

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        create_table(conn)
        conn.executemany(
            """
            INSERT OR REPLACE INTO inferred_cases (
                case_id, end_description_hash, end_input_start_date, end_model,
                end_prompt_version, end_notes, end_source, end_local_date,
                end_local_time, end_inferred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    print(f"Upserted {len(rows)} rows into inferred_cases")


if __name__ == "__main__":
    run()
