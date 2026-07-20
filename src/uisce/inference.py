import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from uisce.config import DB_PATH, JSONL_PATH, make_session

MODEL_URL = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "gemma-4-12b-qat"
PROMPT_VERSION = 2
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

Step 1, do this before anything else: scan the WHOLE description for a completion phrase, top to bottom.
A completion phrase can appear anywhere, including inside an update block that sits above a longer
original notice that still talks about scheduled works. The original notice is stale text; it is not
a correction of the update. So:
- If a completion phrase appears ANYWHERE in the description, end_source is "completion_update", and
  the date and time you report are the ones attached to THAT phrase.
- Ignore every scheduled end time in the description once you have found a completion phrase. Do not
  report a scheduled date or time. Do not blend the two.
- Only if there is no completion phrase anywhere may you consider a scheduled end.

Recurring windows: works are often scheduled to repeat daily or nightly over a range of dates, for
example "works are scheduled to take place nightly from 10pm until 7am, from 08 July until 17 August"
or "daily from 9am until 6pm from 12 June until 15 June". These describe a repeating time window
across a date range. The end of the event is the LAST date in the range, at the window's closing time
(the time after "until" or "to" in the time-of-day part). In the first example that is 2026-08-17 at
07:00, so end_source is "scheduled_end_with_time", not "scheduled_end_date_only". Watch for typos
such as "unil" for "until", and for ranges written as "between 9 July and 27 July". Use only dates
that actually appear in the text.

Read dates carefully. A day may be written with one digit or two ("3/05/2026" and "03/05/2026" are
the same date), and a time of day sits nearby in the same block. A single-digit day does not mean the
time is missing. If the block gives a time, report it.

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
- "lifted_immediate": the notice says a previous order or restriction has been lifted with immediate effect, with no separate end time given. Report local_time as null unless the text itself states a time of day for the lift. Do not copy a time from start_date.

Output format:
Return exactly one JSON object and nothing else. No preamble, no explanation, no markdown fences. Write the notes field FIRST, as your reasoning, then fill the remaining fields to match that reasoning.

Fields:
- notes: string. Your reasoning: state whether a completion phrase appears anywhere in the description, then what phrase you used and why you chose that end_source.
- end_source: one of the five values above.
- local_date: "YYYY-MM-DD", or null only when end_source is "not_found".
- local_time: "HH:MM" in 24-hour Ireland local time, or null when only a date was found or nothing was found.

Do not include inferred_end or confidence. Those are computed later in Python.

Example (completion update, "Works are now complete at 4:13pm on 28/04/2026"):
{"notes":"Newest update block states works complete at 4:13pm on 28/04/2026. Completion update takes priority, so end_source is completion_update.","end_source":"completion_update","local_date":"2026-04-28","local_time":"16:13"}

Example (completion update above a longer scheduled notice — the completion still wins):
Text: "Update 9:37am 13/07/2026: Works are now complete. ... Original notice: Works are scheduled to finish at 7:00am on 12/07/2026."
{"notes":"A completion phrase appears in the update block at the top: works complete at 9:37am on 13/07/2026. The scheduled 7:00am 12/07/2026 end below it is stale original text, so it is ignored.","end_source":"completion_update","local_date":"2026-07-13","local_time":"09:37"}

Example (recurring nightly window):
Text: "Works are scheduled to take place nightly from 10pm until 8am from 08 July until 17 August."
{"notes":"No completion phrase. A repeating nightly window from 10pm to 8am runs until 17 August, so the event ends on the last date of the range at the window's closing time of 8am.","end_source":"scheduled_end_with_time","local_date":"2026-08-17","local_time":"08:00"}

Example (single-digit day, time still present):
Text: "Update 9:17am 2/06/2026: Works are now complete."
{"notes":"Completion phrase with time 9:17am on 2/06/2026. The single-digit day is still a valid date and the time is present.","end_source":"completion_update","local_date":"2026-06-02","local_time":"09:17"}

Example (nothing found):
{"notes":"No completion phrase and no scheduled end time or date in any block.","end_source":"not_found","local_date":null,"local_time":null}
""" # noqa: E501


def hash_description(description):
    return hashlib.sha256(description.encode("utf-8")).hexdigest()


def get_last_hash_by_case_id(jsonl_path):
    """Latest (description_hash, prompt_version) per case. A case is up to date only
    when both still match, so bumping PROMPT_VERSION re-infers the whole corpus."""
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
    return {
        case_id: (record["description_hash"], record.get("prompt_version"))
        for case_id, record in latest.items()
    }


def get_cases_needing_inference(db_path, last_state_by_case_id, force=False):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT id, start_date, description FROM cases WHERE description IS NOT NULL"
    )
    cases = [
        row
        for row in cur
        if force
        or last_state_by_case_id.get(row["id"])
        != (hash_description(row["description"]), PROMPT_VERSION)
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


def run(argv=None):
    parser = argparse.ArgumentParser(description="Infer end-time signals for cases")
    parser.add_argument("--force", action="store_true",
                        help="re-infer every case, even if description and prompt version match")
    parser.add_argument("--limit", type=int, default=None,
                        help="stop after N cases (useful on slow local hardware)")
    args = parser.parse_args(argv)

    last_state_by_case_id = get_last_hash_by_case_id(JSONL_PATH)
    cases = get_cases_needing_inference(DB_PATH, last_state_by_case_id, force=args.force)
    if args.limit is not None:
        cases = cases[: args.limit]
    print(f"{len(cases)} cases to process (prompt v{PROMPT_VERSION}, model {MODEL_NAME})")

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
