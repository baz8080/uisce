"""Shared paths and constants. Paths are relative to the working directory,
matching how the scripts have always been run (from the repo root)."""

from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Notices state wall-clock Irish local times. Both build.py (turning a reported
# end into a UTC instant) and site.py (expanding a recurring window) need it, and
# site.py importing it from build.py would invert the pipeline's direction.
DUBLIN = ZoneInfo("Europe/Dublin")

DB_PATH = Path("out/uisce.db")
CASES_RAW_PATH = Path("out/cases.json")
CASES_MAPPED_PATH = Path("out/cases_mapped.json")
JSONL_PATH = Path("data/inferred_end_times.jsonl")
SA_POP_PATH = Path("data/sa_pop.csv")
SA_TOWNS_PATH = Path("data/sa_towns.csv")
SITE_DIR = Path("out/site")

DEFAULT_TIMEOUT = 15


def make_session():
    session = requests.Session()
    session.headers.update({"User-Agent": "uisce/1.0 https://github.com/baz8080/uisce"})

    # transparent backoff-and-retry for transient failures; honours
    # Retry-After on 429/503, so no manual rate-limit handling needed
    retry = Retry(
        total=4,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
