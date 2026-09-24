"""CPU rule-based end-time extraction for the templated majority of notices.

`uisce-infer` sends every description to a local LLM (inference.py), but the
corpus is rigidly templated: most notices are a handful of fixed sentences
with a time and a date slotted in. This module extracts the same end-time
signal as prompt v3 for those templates and abstains on everything else, so a
caller can fall back to the LLM for the residue only — the shape
notes/data-quality.md already recommends for the overrun metric ("regex first
with an LLM fallback"). Coverage and agreement against the LLM are measured
corpus-wide by `uisce-eval-rules-shadow`; see notes/rules-vs-llm-end-times.md.

The contract mirrors parse_response() in inference.py: extract() returns the
same seven-field dict the prompt asks the model for, or None to abstain.
Abstention is the only failure mode — the extractor never guesses:

- Only "completion_update" and "scheduled_end_with_time" are ever emitted.
- "not_found" is never emitted: failing to match a template is evidence about
  these rules, not about the notice.
- "lifted_immediate" wording and recurring windows abstain: the window
  *values* are what needed a language model (site.py:recurring_events), and a
  lift's semantics are too varied to pattern-match safely.
- "scheduled_end_date_only" is never emitted: a date read without its time
  becomes 23:59:59 in build.py:reported_end_utc, silently shifting the end by
  up to a day, so a match that yields no time of day abstains instead.

RULES_VERSION carries the same contract PROMPT_VERSION does for the prompt
(notes/end-time-eval.md): any change to the patterns or precedence below bumps
it, so records stay comparable across runs.
"""

import re
from datetime import date, datetime, timedelta

from uisce.config import describes_recurrence

RULES_VERSION = "rules-v2"

MONTH_NUMBERS = {name: i + 1 for i, name in enumerate((
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december"))}
MONTH_NUMBERS.update({name[:3]: number for name, number in list(MONTH_NUMBERS.items())})

# Full names before their own three-letter prefixes, so "june" wins over "jun".
_MONTH_ALT = "|".join(sorted(MONTH_NUMBERS, key=len, reverse=True))

# A time of day as the feed writes one. The bare "rn"/"in" Irish meridiems are
# only accepted glued to the digits ("9in", "4:15in") — with a space allowed,
# "until 5 in Co. Galway" would read as 17:00.
_TIME = r"""(?:
    (?P<h>\d{1,2})(?:[:.](?P<min>\d{2}))?(?:\s*(?P<mer>am|pm|ppm)\b|(?P<gmer>rn|in)\b)
  | (?P<word>midday|noon|midnight)\b
  | (?P<h24>\d{1,2}):(?P<min24>\d{2})\b
)"""

# A date as the feed writes one: "18/05/2026", "28 April", "09 May 2026",
# "28th of April". The year is optional in the spelled form; _resolve_year
# picks the candidate nearest the notice's own start_date.
_DATE = rf"""(?:
    (?P<d1>\d{{1,2}})/(?P<mo1>\d{{1,2}})/(?P<y1>\d{{2,4}})\b
  | (?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<mname>{_MONTH_ALT})\b(?:\s+(?P<y2>\d{{4}})\b)?
)"""

_FLAGS = re.VERBOSE | re.IGNORECASE

# "**Update 10:15am 18/05/2026**" and its observed variants: missing minutes,
# a lost closing "**", "on" before the date, Irish "rn"/"in" meridiems with no
# "update" word, "ppm" for "pm", a "." instead of ":". A header this doesn't
# parse makes its block abstain rather than guess.
UPDATE_START = re.compile(r"\*\*\s*(?=update\b|\d)", re.IGNORECASE)
UPDATE_HEADER = re.compile(
    rf"\*\*\s*(?:update\b[:.\s]*)?{_TIME}\s*(?:on\s+)?{_DATE}\s*:?\s*(?:\*\*)?", _FLAGS)

COMPLETION = re.compile(
    r"\bworks?\s+(?:are|is|were|have\s+been|has\s+been)\s+(?:now\s+)?complete", re.IGNORECASE)

# Bilingual notices state the completion in Irish ("críoch leis an obair") and
# sometimes only there; the English half below it can still carry a stale
# schedule that must not be read as the answer.
IRISH_COMPLETION = re.compile(r"cr[ií]och", re.IGNORECASE)

LIFT = re.compile(r"\blift(?:ed|ing|s)?\b", re.IGNORECASE)

# "until 5pm on 26 May and 27 May" / "on 26 and 27 May": an enumerated day
# list is the recurring-window form that RECURRENCE_TEXT misses
# (site.py:recurring_events), and it needs the model. "\s*" after "and"
# because the feed writes "18 June and19 June" (case 236066).
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
DAY_LIST = re.compile(
    rf"""(?:
        {_DAY}\s+(?:{_MONTH_ALT})\s*(?:,\s*{_DAY}\s+(?:{_MONTH_ALT})\s*)*(?:and|&)\s*{_DAY}\s+(?:{_MONTH_ALT})
      | {_DAY}\s*(?:,\s*{_DAY}\s*)*(?:and|&)\s*{_DAY}\s+(?:{_MONTH_ALT})
    )\b""", _FLAGS)

# The scheduled-end sentence forms: "until 2pm on 28 April" (also after
# "from 10am"), and "works now have an estimated completion time of 5pm on
# 15 July". "unil" is a known feed typo for "until".
UNTIL_WORD = re.compile(r"\b(?:until|unil|till)\b", re.IGNORECASE)
SCHEDULED_END = re.compile(
    rf"\b(?:until|unil|till)\s+{_TIME}\s+on\s+(?:the\s+)?{_DATE}", _FLAGS)
ESTIMATED_END = re.compile(
    rf"\bestimated\s+(?:completion|restoration)\s+time\s+of\s+{_TIME}\s+on\s+(?:the\s+)?{_DATE}",
    _FLAGS)

# The start a midnight end is read against: "from 2pm until midnight on 11
# September" ends as 12 September begins (cases 244089, 245031).
FROM_BEFORE = re.compile(
    rf"\bfrom\s+{_TIME}(?:\s+on\s+(?:the\s+)?{_DATE})?\s*$", _FLAGS)

# "An alternative water supply will be available ... from 4:30pm until 11:59pm
# on 22 July" gives the tanker's hours, not the works' end (case 239696).
ALTERNATIVE_SUPPLY = re.compile(
    r"\b(?:alternative\s+(?:drinking\s+)?water|tankers?|bowsers?|water\s+stations?"
    r"|bottled\s+water|water\s+bottles|standpipes?)\b", re.IGNORECASE)
LEADING_DATE = re.compile(rf"\W*.{{0,40}}?{_DATE}", _FLAGS)
SENTENCE_END = re.compile(r"(?<!\bCo)(?<!\bSt)[.!?](?=\s)")

_TAGS = re.compile(r"<[^>]+>")


def _plain(html):
    return " ".join(_TAGS.sub(" ", html or "").split())


def _match_time(m):
    """The "HH:MM" a _TIME match states, or None if it is not a valid clock time."""
    if m.group("word"):
        return {"midday": "12:00", "noon": "12:00", "midnight": "00:00"}[m.group("word").lower()]
    if m.group("h24"):
        hour, minute = int(m.group("h24")), int(m.group("min24"))
        if hour > 23 or minute > 59:
            return None
        return f"{hour:02d}:{minute:02d}"
    hour, minute = int(m.group("h")), int(m.group("min") or 0)
    meridiem = (m.group("mer") or m.group("gmer")).lower()
    if 13 <= hour <= 23 and meridiem in ("pm", "ppm") and minute <= 59:
        # "16:59pm" (case 245025): a 24-hour time with a redundant meridiem
        return f"{hour:02d}:{minute:02d}"
    if not 1 <= hour <= 12 or minute > 59:
        return None
    hour %= 12
    if meridiem in ("pm", "ppm", "in"):
        hour += 12
    return f"{hour:02d}:{minute:02d}"


def _resolve_year(day, month, start_date):
    """The year a day-month with no year written means: the candidate year that
    lands nearest the notice's own publication date, so a December notice about
    January works still reads forward."""
    try:
        published = datetime.fromisoformat(start_date).date()
    except (TypeError, ValueError):
        return None
    candidates = []
    for year in (published.year - 1, published.year, published.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    if not candidates:
        return None
    return min(candidates, key=lambda d: abs((d - published).days))


def _match_date(m, start_date):
    """The "YYYY-MM-DD" a _DATE match states, or None if invalid."""
    if m.group("d1"):
        day, month, year = int(m.group("d1")), int(m.group("mo1")), int(m.group("y1"))
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    day, month = int(m.group("d2")), MONTH_NUMBERS[m.group("mname").lower()]
    if m.group("y2"):
        try:
            return date(int(m.group("y2")), month, day).isoformat()
        except ValueError:
            return None
    resolved = _resolve_year(day, month, start_date)
    return resolved.isoformat() if resolved else None


def _midnight_end_date(before, end_date, start_date, said_midnight):
    """The date a 00:00 end falls on, or None when the text leaves it open.

    "until midnight on D" alone is either end of D. A start earlier on D makes
    it the end of D, so the instant is D+1 00:00. After a start the day before,
    only "12am on D" is the start of D ("from 9pm on 21 May until 12am on 22
    May"); the word "midnight" there still leaves it open."""
    m = FROM_BEFORE.search(before)
    from_time = m and _match_time(m)
    if not from_time or from_time == "00:00":
        return None
    from_date = _match_date(m, start_date) if m.group("d1") or m.group("d2") else end_date
    if from_date is None:
        return None
    end = date.fromisoformat(end_date)
    if from_date == end_date:
        return (end + timedelta(days=1)).isoformat()
    if from_date == (end - timedelta(days=1)).isoformat() and not said_midnight:
        return end_date
    return None


def _block_date(header, block, start_date):
    """The date an update block is headed with: its parsed header's, else the date
    it opens with, for a time too garbled for UPDATE_HEADER ("** 9:38 rn
    22/09/2026", case 244845)."""
    if header is not None:
        return _match_date(header, start_date)
    m = LEADING_DATE.match(block)
    return _match_date(m, start_date) if m else None


def _about_alternative_supply(before):
    starts = [m.end() for m in SENTENCE_END.finditer(before)]
    return bool(ALTERNATIVE_SUPPLY.search(before[starts[-1] if starts else 0:]))


def _body(header, block):
    return block[header.end():] if header else block


def _segments(text):
    """The description as (header_match_or_None, block_text) pairs, newest
    first — update blocks are prepended by the feed. Text before the first
    header (the whole notice, when there are no updates) gets a None header."""
    starts = [m.start() for m in UPDATE_START.finditer(text)]
    segments = []
    if not starts or starts[0] > 0:
        segments.append((None, text[: starts[0]] if starts else text))
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = text[start:end]
        header = UPDATE_HEADER.match(block)
        segments.append((header, block))
    return segments


def _result(end_source, local_date, local_time, notes):
    return {
        "notes": notes,
        "end_source": end_source,
        "local_date": local_date,
        "local_time": local_time,
        "recurrence": "none",
        "window_open": None,
        "window_close": None,
        "window_first_date": None,
    }


def extract(start_date, description):
    """The prompt-v3 answer for a templated notice, or None to abstain.

    Argument order matches call_llm(session, start_date, description) so the
    two extraction backends read the same way at a call site.
    """
    if not description:
        return None
    text = _plain(description)
    segments = _segments(text)

    # Completion beats schedule, always (the prompt's step 1). The date and
    # time come from the header of the block stating the completion; a
    # completion phrase in a headerless or unparseable block abstains.
    for i, (header, block) in enumerate(segments):
        if COMPLETION.search(block):
            if header is None:
                return None
            local_time = _match_time(header)
            local_date = _match_date(header, start_date)
            if not local_time or not local_date:
                return None
            return _result(
                "completion_update", local_date, local_time,
                f"rules: completion phrase under update header "
                f"{header.group(0).strip()!r}")
        if IRISH_COMPLETION.search(block):
            # The English block of the same update follows the Irish one, and
            # its header is the one to read: the Irish header's time is mistyped
            # often (232673, 236544, 244190). It must be the same day's update,
            # not an older one; otherwise the Irish needs the model.
            following_header, following = next(
                ((h, b) for h, b in segments[i + 1:] if _body(h, b).strip()), (None, ""))
            irish_date = _block_date(header, block, start_date)
            same_day = (following_header is not None and irish_date is not None
                        and irish_date == _match_date(following_header, start_date))
            if not (same_day and COMPLETION.search(following)):
                return None

    # No completion anywhere: consider a scheduled end, unless the notice is
    # one of the shapes settled as model territory.
    if describes_recurrence(description) or LIFT.search(text) or DAY_LIST.search(text):
        return None

    # Only the newest segment may state the schedule. The original notice has
    # no header of its own, so with a single update it shares that update's
    # segment — a revising update over stale text then yields two candidate
    # ends and abstains below, while older *headered* updates are excluded.
    newest = next((block for _, block in segments if block.strip()), "")

    # Every "until" in the block must be one the pattern read in full. An
    # extra one is a schedule these rules cannot see — "until further notice",
    # the garbled "until 6pm on 9 May until 9pm 13 May" (case 232976,
    # site.py:recurring_events), or a date range "until 5pm on 05 August
    # until 07 August" (case 240600) that the model reads as recurring.
    scheduled_matches = list(SCHEDULED_END.finditer(newest))
    if len(UNTIL_WORD.findall(newest)) != len(scheduled_matches):
        return None

    candidates = {}
    for m in scheduled_matches + list(ESTIMATED_END.finditer(newest)):
        before = newest[:m.start()]
        # The tanker's hours are never the works' end, and dropping them could
        # leave one candidate where two would have abstained (a revising update
        # over the original schedule), so the model reads these.
        if _about_alternative_supply(before):
            return None
        local_time = _match_time(m)
        local_date = _match_date(m, start_date)
        if local_time == "00:00" and local_date:
            local_date = _midnight_end_date(
                before, local_date, start_date, (m.group("word") or "").lower() == "midnight")
        if not local_time or not local_date:
            return None
        candidates[(local_date, local_time)] = m.group(0).strip()
    if len(candidates) != 1:
        return None
    (local_date, local_time), matched = candidates.popitem()
    return _result(
        "scheduled_end_with_time", local_date, local_time,
        f"rules: scheduled end {matched!r}")
