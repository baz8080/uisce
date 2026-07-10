import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from uisce.config import DB_PATH, JSONL_PATH, make_session

MODEL_URL = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "gemma-4-12b-qat"
PROMPT_VERSION = 1
LLM_TIMEOUT = 120  # local model; long descriptions can take well over 15s

# might also need {%- set enable_thinking = false %} in system prompt for LM studio
PROMPT = """
You are a data extraction assistant. You read a single water outage / works notice and extract the raw end-time signal. You do NOT do any date maths or timezone conversion. Python does that afterwards. Your job is to read the text, decide which end-time signal is present, and report the date and a 24-hour local time.

You will be given two fields as comma separated values:
start_date: the start time of the event in UTC ISO 8601 format
description: free text describing the event. Update blocks are prepended to the original notice, newest first.

Rules for choosing the signal:
- A completion update reports that the works have finished. Look for phrases like "Works are now complete" or, in Irish, "Ta crioch leis an obair". This is the strongest signal.
- A scheduled end time is only an estimate of when works will finish.
- If both a completion update and a scheduled end time are present, always use the completion update.
- Descriptions may be in English, Irish, or both.

Reading Irish time-of-day words:
- "rn" or "ar maidin" means AM.
- "in" or "iarnoin" means PM.

Reporting the time:
- Report the time as a 24-hour clock string "HH:MM" in Ireland local time. Do NOT convert the timezone. Just rewrite the local time in 24-hour form.
- 1pm is 13:00, 5:19pm is 17:19, 9am is 09:00.
- 12 noon (12:00pm) is 12:00. 12 midnight (12:00am) is 00:00.
- If the text already gives a 24-hour time such as 17:00, report it unchanged.

Report the date using the day/month/year in the text, rewritten as YYYY-MM-DD. Irish dates are day/month/year.

Set end_source to exactly one of:
- "completion_update": a completion update with a specific time was found
- "scheduled_end_with_time": a scheduled end with a specific time of day was found
- "scheduled_end_date_only": an end date was found but no time of day
- "not_found": no usable end-time signal
- "lifted_immediate": the notice says a previous order or restriction has been lifted with immediate effect, with no separate end time given.

Output format:
Return exactly one JSON object and nothing else. No preamble, no explanation, no markdown fences. Write the notes field FIRST, as your reasoning, then fill the remaining fields to match that reasoning.

Fields:
- notes: string. Your reasoning: what phrase you found, in which block, and why you chose that end_source.
- end_source: one of the four values above.
- local_date: "YYYY-MM-DD", or null only when end_source is "not_found".
- local_time: "HH:MM" in 24-hour Ireland local time, or null when only a date was found or nothing was found.

Do not include inferred_end or confidence. Those are computed later in Python.

Example (completion update, "Works are now complete at 4:13pm on 28/04/2026"):
{"notes":"Newest update block states works complete at 4:13pm on 28/04/2026. Completion update takes priority, so end_source is completion_update.","end_source":"completion_update","local_date":"2026-04-28","local_time":"16:13"}

Example (nothing found):
{"notes":"No completion phrase and no scheduled end time or date in any block.","end_source":"not_found","local_date":null,"local_time":null}
""" # noqa: E501


def hash_description(description):
    return hashlib.sha256(description.encode("utf-8")).hexdigest()


def get_last_hash_by_case_id(jsonl_path):
    if not jsonl_path.exists():
        return {}
    latest = {}
    with open(jsonl_path) as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            current = latest.get(record["case_id"])
            if current is None or record["inferred_at"] > current["inferred_at"]:
                latest[record["case_id"]] = record
    return {case_id: record["description_hash"] for case_id, record in latest.items()}


def get_cases_needing_inference(db_path, last_hash_by_case_id):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT id, start_date, description FROM cases WHERE description IS NOT NULL"
    )
    cases = [
        row
        for row in cur
        if last_hash_by_case_id.get(row["id"]) != hash_description(row["description"])
    ]
    conn.close()
    return cases


def call_llm(session, start_date, description):
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": f"{PROMPT}\n\nstart_date: {start_date}\ndescription: {description}",
            }
        ],
        "temperature": 0,
    }
    resp = session.post(MODEL_URL, json=payload, timeout=LLM_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def parse_response(response_text):
    result = json.loads(response_text)
    if not isinstance(result, dict):
        raise ValueError(f"Expected a JSON object, got: {response_text[:80]!r}")
    return result


def build_record(case_id, description, start_date, result, inferred_at=None):
    return {
        "case_id": case_id,
        "description_hash": hash_description(description),
        "start_date": start_date,
        "model": MODEL_NAME,
        "prompt_version": PROMPT_VERSION,
        "notes": result.get("notes"),
        "end_source": result.get("end_source"),
        "local_date": result.get("local_date"),
        "local_time": result.get("local_time"),
        "inferred_at": inferred_at or datetime.now(timezone.utc).isoformat(),
    }


def run():
    last_hash_by_case_id = get_last_hash_by_case_id(JSONL_PATH)
    cases = get_cases_needing_inference(DB_PATH, last_hash_by_case_id)
    print(f"{len(cases)} cases to process")

    session = make_session()
    results_by_hash = {}

    with open(JSONL_PATH, "a") as out:
        for i, case in enumerate(cases):
            try:
                description_hash = hash_description(case["description"])

                # Multi-pin events share one description; infer it once.
                result = results_by_hash.get(description_hash)
                if result is None:
                    raw = call_llm(session, case["start_date"], case["description"])
                    result = parse_response(raw)
                    results_by_hash[description_hash] = result

                record = build_record(
                    case["id"], case["description"], case["start_date"], result
                )

                out.write(json.dumps(record) + "\n")
                out.flush()
                if i % 5 == 0:
                    print(f"{i}/{len(cases)} done")
            except Exception as e:
                print(f"Failed case {case['id']}: {e}")
                out.flush()
