import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

JSONL_PATH = Path("out/inferred_duration.jsonl")
DB_PATH = Path("out/uisce.db")
MODEL_URL = "http://localhost:1234/v1/chat/completions"

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


def get_processed_ids(jsonl_path):
    if not jsonl_path.exists():
        return set()
    with open(jsonl_path) as f:
        return {json.loads(line)["case_id"] for line in f if line.strip()}


def get_unprocessed_cases(db_path, processed_ids):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT id, start_date, description FROM cases WHERE description IS NOT NULL"
    )
    cases = [row for row in cur if row["id"] not in processed_ids]
    conn.close()
    return cases


def call_llm(start_date, description):
    import urllib.request

    payload = {
        "model": "gemma-4-12b-qat",
        "messages": [
            {
                "role": "user",
                "content": f"{PROMPT}\n\nstart_date: {start_date}\ndescription: {description}",
            }
        ],
        "temperature": 0,
    }
    req = urllib.request.Request(
        MODEL_URL, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def parse_response(response_text):
    return json.loads(response_text)


def run():
    processed_ids = get_processed_ids(JSONL_PATH)
    cases = get_unprocessed_cases(DB_PATH, processed_ids)
    print(f"{len(cases)} cases to process")

    with open(JSONL_PATH, "a") as out:
        for i, case in enumerate(cases):
            try:
                raw = call_llm(case["start_date"], case["description"])
                result = parse_response(raw)
                if result is None:
                    raise ValueError("No JSON block found")
                record = {
                    "case_id": case["id"],
                    "notes": result.get("notes"),
                    "end_source": result.get("end_source"),
                    "local_date": result.get("local_date"),
                    "local_time": result.get("local_time"),
                    "inferred_at": datetime.now(timezone.utc).isoformat(),
                }

                out.write(json.dumps(record) + "\n")
                out.flush()
                if i % 5 == 0:
                    print(f"{i}/{len(cases)} done")
            except Exception as e:
                print(f"Failed case {case['id']}: {e}")
                out.flush()


if __name__ == "__main__":
    run()
