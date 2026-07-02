import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

JSONL_PATH = Path("out/inferred_duration.jsonl")
DB_PATH = Path("out/uisce.db")
MODEL_URL = "http://localhost:1234/v1/chat/completions"

# might also need {%- set enable_thinking = false %} in system prompt for LM studio
PROMPT = """
/no_think
You are a data extraction assistant. Your task is to extract the estimated end time of a water outage or works event from a description field, and return it as a structured JSON object.

You will be given these fields as comma separated values:
start_date: the start time of the event in UTC ISO 8601 format
description: free text describing the event, which may contain update blocks prepended to the original notice

Important context:

All times in the description are Ireland local time and must be converted to UTC for output. Ireland observes UTC+0 (GMT) from the last Sunday of October until the last Sunday of March, and UTC+1 (IST) from the last Sunday of March until the last Sunday of October. For 2026, UTC+1 applies from 29 March to 25 October. Use the event's start_date to determine which offset applies. Convert all local times to UTC by subtracting the applicable offset. The inferred_end value must always use +00:00 as the timezone suffix. For example, 5:19pm IST (UTC+1) becomes 16:19:00+00:00, not 17:19:00+01:00. To convert IST (UTC+1) to UTC: take the local time and subtract 1 hour. So 4:17pm local = 3:17pm UTC = 15:17:00+00:00. To convert GMT (UTC+0) to UTC: no change needed. The inferred_end value must always end with +00:00.

Dates are in Irish format: day/month/year
Descriptions may be in English, Irish, or both
In Irish language text, rn or ar maidin indicates AM, and in or iarnóin indicates PM
Update blocks are prepended to the description, newest first. A completion update will contain phrases like "Works are now complete" or in Irish "Tá críoch leis an obair"
A scheduled end time is an estimate only, not a confirmed completion
If both a scheduled end time and a confirmed completion timestamp exist, prefer the confirmed completion timestamp

Confidence levels:

high: a confirmed completion timestamp was found in an update block
medium: a scheduled end time with a specific time of day was found
low: only a date was found with no specific time
none: no useful end time signal found

You must populate the notes field first with your reasoning, then derive inferred_end from that reasoning. The inferred_end must be consistent with the conclusion in notes.

Return only one JSON object, no preamble, no explanation, no markdown code fences. Example output:
{
  "inferred_end": "2026-04-28T15:13:00+00:00",
  "end_source": "completion_update",
  "confidence": "high",
  "notes": "Update block states works complete at 4:13pm 28/04/2026, converted from UTC+1 (IST)"
}

end_source must be one of: completion_update, scheduled_end_with_time, scheduled_end_date_only, duration_calculation, not_found
If no end time can be inferred, return null for inferred_end and not_found for end_source.
"""  # your working prompt

def get_processed_ids(jsonl_path):
    if not jsonl_path.exists():
        return set()
    with open(jsonl_path) as f:
        return {json.loads(line)["case_id"] for line in f if line.strip()}

def get_unprocessed_cases(db_path, processed_ids):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT id, start_date, description FROM cases WHERE description IS NOT NULL")
    cases = [row for row in cur if row["id"] not in processed_ids]
    conn.close()
    return cases

def call_llm(start_date, description):
    import urllib.request
    payload = {
        "model": "gemma-4-12b-qat",
        "messages": [
            {"role": "user", "content": f"{PROMPT}\n\nstart_date: {start_date}\ndescription: {description}"}
        ],
        "temperature": 0.1
    }
    req = urllib.request.Request(
        MODEL_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
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
                    "inferred_end": result.get("inferred_end"),
                    "end_source": result.get("end_source"),
                    "end_confidence": result.get("confidence"),
                    "end_notes": result.get("notes"),
                    "inferred_at": datetime.now(timezone.utc).isoformat()
                }

                if record["inferred_end"] and record["inferred_end"] < case["start_date"]:
                    record["end_confidence"] = "error"
                    record["end_notes"] = f"inferred_end before start_date: {record['end_notes']}"

                out.write(json.dumps(record) + "\n")
                out.flush()
                if i % 10 == 0:
                    print(f"{i}/{len(cases)} done")
            except Exception as e:
                print(f"Failed case {case['id']}: {e}")
                # out.write(json.dumps({"case_id": case["id"], "end_source": "error", "end_confidence": "error", "end_notes": str(e), "inferred_at": datetime.now(timezone.utc).isoformat()}) + "\n")
                out.flush()

if __name__ == "__main__":
    run()