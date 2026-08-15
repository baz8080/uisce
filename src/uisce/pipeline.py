import argparse
import json
import os
import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from pyproj import Transformer

from uisce.config import (
    CASES_MAPPED_PATH,
    CASES_RAW_PATH,
    DB_PATH,
    DEFAULT_TIMEOUT,
    make_session,
)

ARCGIS_QUERY_URL = (
    "https://services2.arcgis.com/OqejhVam51LdtxGa/arcgis/rest/services/"
    "WaterAdvisoryCR021_DeptView/FeatureServer/0/query"
)
ARCGIS_PAGE_SIZE = 1000
ARCGIS_PAGE_SLEEP = 0.3

LOCATIONIQ_REVERSE_URL = "https://us1.locationiq.com/v1/reverse"
LOCATIONIQ_GEOCODE_SLEEP = 1
COORD_PRECISION = 4  # ~10 meter

USABLE_CASE_THRESHOLD_FIELDS = ["TITLE", "DESCRIPTION"]

# Stamped into PRAGMA user_version. The `cases` schema is declared once, in
# create_db; bump this only when that declaration changes, and add the matching
# step to MIGRATIONS so DBs already in the wild can be carried forward.
SCHEMA_VERSION = 3

# The `cases` schema, declared once: every column in table order, with its SQL
# type. create_db renders this into the CREATE TABLE, the migration guard derives
# its required set from it, and the test fixtures build their throwaway tables
# from the same keys. Adding a column is one entry here (plus a MIGRATIONS step,
# below, so DBs already in the wild can reach it).
CASE_COLUMNS = {
    "id": "INTEGER PRIMARY KEY",
    "work_type": "TEXT",
    "title": "TEXT",
    "start_date": "TEXT",
    "end_date": "TEXT",
    "description": "TEXT",
    "status": "TEXT",
    "global_id": "TEXT",
    "approval_status": "TEXT",
    "location": "TEXT",
    "county": "TEXT",
    "reference_num": "TEXT",
    "boil_water_notice": "INTEGER",
    "traffic_disruptions": "INTEGER",
    "pollution": "INTEGER",
    "water_outage": "INTEGER",
    "do_not_drink": "INTEGER",
    "discolouration": "INTEGER",
    "reduced_pressure": "INTEGER",
    "water_restrictions": "INTEGER",
    "work_category": "TEXT",
    "first_seen": "TEXT",
    "last_seen": "TEXT",
    "closed_at": "TEXT",
    "first_start_date": "TEXT",
    "full_lat": "REAL NOT NULL",
    "full_lon": "REAL NOT NULL",
    "rounded_lat": "REAL NOT NULL",
    "rounded_lon": "REAL NOT NULL",
}

# Derived or stamped by this pipeline rather than fed by the ArcGIS response, so
# they carry no value in a mapped case and are never part of the INSERT's value
# tuple. load_cases sets first_seen / last_seen / closed_at / first_start_date
# explicitly; backfill_work_category fills work_category.
STAMPED_CASE_COLUMNS = frozenset(
    {"work_category", "first_seen", "last_seen", "closed_at", "first_start_date"}
)

# The columns fed straight from the feed, in table order. This is the INSERT's
# column list and the source of its placeholders, so its order is load-bearing.
DB_CASE_COLUMNS = [c for c in CASE_COLUMNS if c not in STAMPED_CASE_COLUMNS]

# v(n-1) -> v(n), as {version: {column: decl}}. Additive nullable columns only:
# SQLite adds those without rewriting a single row, which is what keeps the
# 20MB release DB migratable in place. Anything that would rewrite or drop data
# does not belong here — that is a rebuild, and rebuilds cost the accumulated
# archive (cases the feed no longer serves, and the geocode cache).
MIGRATIONS = {
    2: {"closed_at": "TEXT"},
    3: {"first_start_date": "TEXT"},
}

# V1 is the floor: a DB carrying these is structurally sound and can be migrated
# forward, whatever it is stamped. A DB missing any of them predates the archive
# and is a rebuild, not a migration. It is the declared schema minus everything
# MIGRATIONS knows how to add, so a new column lands on the right side of the
# floor by construction rather than by being remembered.
_MIGRATED_COLUMNS = {column for step in MIGRATIONS.values() for column in step}
V1_CASE_COLUMNS = set(CASE_COLUMNS) - _MIGRATED_COLUMNS
REQUIRED_CASE_COLUMNS = set(CASE_COLUMNS)


def cases_ddl(sql_type=None):
    """The CREATE TABLE body for `cases`, from the single column declaration.

    `sql_type(name, declared)` may rewrite a column's SQL type — the test
    fixtures relax everything to TEXT so a throwaway record of Nones does not
    trip `REAL NOT NULL`. It cannot change the set of columns or their order,
    which always come from CASE_COLUMNS, and it is applied per column as the
    string is built so there is no snapshot to go stale.
    """
    sql_type = sql_type or (lambda name, declared: declared)
    return ",\n                ".join(
        f"{name} {sql_type(name, declared)}" for name, declared in CASE_COLUMNS.items()
    )

FIELD_MAP = {
    "OBJECTID": "id",
    "WORKTYPE": "work_type",
    "TITLE": "title",
    "STARTDATE": "start_date",  # low trust - start / end often ~60s apart
    "ENDDATE": "end_date",  # low trust - start / end often ~60s apart
    "DESCRIPTION": "description",
    "STATUS": "status",
    "GLOBALID": "global_id",
    "APPROVALSTATUS": "approval_status",
    "LOCATION": "location",
    "COUNTY": "county",
    "REFERENCENUM": "reference_num",
    "BOILWATERNOTICE": "boil_water_notice",
    "TRAFFICDISRUPTIONS": "traffic_disruptions",
    "POLLUTION": "pollution",
    "WATEROUTAGE": "water_outage",
    "DONOTDRINK": "do_not_drink",
    "DISCOLOURATION": "discolouration",
    "REDUCEDPRESSURE": "reduced_pressure",
    "WATERRESTRICTIONS": "water_restrictions",
    # The ones below are used so seldomly that they aren't worth mapping
    # "CONTACTDETAILS": "contact_details",
    # "AFFECTEDPREMISES": "affected_premises",
    # "TRAFFICIMPLICATIONS": "traffic_implications",
    # "CREATEDBY": "created_by",
    # "CREATEDATE": "create_date",
    # "LASTEDITOR": "last_editor",
    # "LASTUPDATE": "last_update",
    # "PRIORITY": "priority",
    # "PROJECTNUMBER": "project_number",
    # "PROJECT": "project",
}


def require_api_key():
    load_dotenv(Path(".env"))
    api_key = os.getenv("LOCATIONIQ_API_KEY")
    if not api_key:
        raise RuntimeError("LOCATIONIQ_API_KEY not set, check your .env file")
    return api_key


def download_cases(session):
    all_features = []
    offset = 0

    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "orderByFields": "OBJECTID",
            "resultOffset": offset,
            "resultRecordCount": ARCGIS_PAGE_SIZE,
            "f": "json",
        }

        resp = session.get(ARCGIS_QUERY_URL, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"ArcGIS error at offset {offset}: {data['error']}")

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        print(f"Fetched {len(all_features)}")

        if not data.get("exceededTransferLimit", False):
            break

        offset += ARCGIS_PAGE_SIZE
        time.sleep(ARCGIS_PAGE_SLEEP)

    print(f"Done: {len(all_features)} records")
    return all_features


def read_arcgis_cases():
    return json.loads(CASES_RAW_PATH.read_text())


def read_mapped_cases():
    return json.loads(CASES_MAPPED_PATH.read_text())


def map_cases(cases_to_map):
    """Map raw ArcGIS features to flat case dicts.

    Returns (mapped_cases, skipped_ids) and performs no I/O.
    """
    skipped = []

    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    all_cases = []
    for case in cases_to_map:
        attrs = case["attributes"]

        if not _is_usable_case(attrs):
            skipped.append(attrs.get("OBJECTID"))
            continue

        # attrs.get: a feature missing a field entirely maps to None rather
        # than producing a case dict with missing keys (which would KeyError
        # later in load_cases). The feed uses '' and null interchangeably;
        # normalise to None so DB queries only need one representation.
        mapped_case = {
            mapped: (None if attrs.get(source) == "" else attrs.get(source))
            for source, mapped in FIELD_MAP.items()
        }

        mapped_case["start_date"] = _epoch_ms_to_iso(mapped_case["start_date"])
        mapped_case["end_date"] = _epoch_ms_to_iso(mapped_case["end_date"])

        lon, lat = transformer.transform(case["geometry"]["x"], case["geometry"]["y"])
        mapped_case["full_lat"] = lat
        mapped_case["full_lon"] = lon

        mapped_case["rounded_lat"] = round(lat, COORD_PRECISION)
        mapped_case["rounded_lon"] = round(lon, COORD_PRECISION)

        if mapped_case["county"] == "Dnegal":
            mapped_case["county"] = "Donegal"

        # titles frequently carry leading/trailing whitespace in the feed;
        # trim so the stored value is clean and category matching is exact
        title = (mapped_case["title"] or "").strip()
        mapped_case["title"] = title or "unknown"

        all_cases.append(mapped_case)

    return all_cases, skipped


def _epoch_ms_to_iso(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


# this many failures in a row means the service is down, not that a handful
# of individual coords are ungeocodable
GEOCODE_CIRCUIT_BREAKER = 10

_GEOCODE_INSERT = """
    INSERT OR REPLACE INTO geocode_cache (
        rounded_lat, rounded_lon, display_name,
        road, town, village, hamlet, suburb, city_district,
        county, postcode, city, municipality, region, raw_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def geocode_all(cases_to_geocode, api_key, db_path=DB_PATH, session=None):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    session = session or make_session()

    with sqlite3.connect(db_path) as conn:
        _create_geocode_cache_table(conn)

        # placeholder rows from earlier failures don't count as done, so
        # they get retried (and replaced, via INSERT OR REPLACE) each run
        rows = conn.execute("""
            SELECT rounded_lat, rounded_lon FROM geocode_cache
            WHERE json_extract(raw_json, '$.geocode_failed') IS NULL
        """)
        done = {(row[0], row[1]) for row in rows}
        print(f"{len(done)} coords already geocoded, resuming")

        unique_coords = {(c["rounded_lat"], c["rounded_lon"]) for c in cases_to_geocode}
        remaining = unique_coords - done
        print(f"{len(remaining)} coords left to geocode")

        failed = []
        consecutive_failures = 0
        for lat, lon in remaining:
            try:
                result = call_locationiq(session, lat, lon, api_key)
            except requests.RequestException as e:
                consecutive_failures += 1
                if consecutive_failures >= GEOCODE_CIRCUIT_BREAKER:
                    raise RuntimeError(
                        f"{consecutive_failures} geocode failures in a row — the "
                        f"geocoding service looks down, failing the build. Last error: {e}"
                    ) from e
                print(f"Failed at ({lat}, {lon}), storing a placeholder: {e}")
                failed.append((lat, lon))
                conn.execute(_GEOCODE_INSERT, geocode_failure_row(lat, lon, e))
            else:
                consecutive_failures = 0
                conn.execute(_GEOCODE_INSERT, geocode_cache_row(lat, lon, result))

            conn.commit()
            time.sleep(LOCATIONIQ_GEOCODE_SLEEP)

        if failed:
            print(
                f"{len(failed)} coord(s) have a placeholder geocode row (location "
                f"unknown) and will be retried on the next run: {failed}"
            )


def geocode_failure_row(lat, lon, error):
    """A row that satisfies the cases FK but is recognisably not a real
    geocode result, so the next run retries it."""
    return (lat, lon) + (None,) * 12 + (json.dumps({"geocode_failed": str(error)}),)


def geocode_cache_row(lat, lon, result):
    address = result.get("address", {})
    return (
        lat,
        lon,
        result.get("display_name"),
        address.get("road"),
        address.get("town"),
        address.get("village"),
        address.get("hamlet"),
        address.get("suburb"),
        address.get("city_district"),
        address.get("county"),
        address.get("postcode"),
        address.get("city"),
        address.get("municipality"),
        address.get("region"),
        json.dumps(result),
    )


def call_locationiq(session, lat, lon, api_key):
    # rate limiting and transient errors are retried by the session's
    # Retry adapter (see make_session), which honours Retry-After on 429
    params = {"key": api_key, "lat": lat, "lon": lon, "format": "json"}
    resp = session.get(LOCATIONIQ_REVERSE_URL, params=params, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _create_geocode_cache_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geocode_cache (
            rounded_lat REAL NOT NULL,
            rounded_lon REAL NOT NULL,
            display_name TEXT,
            road TEXT,
            town TEXT,
            village TEXT,
            hamlet TEXT,
            suburb TEXT,
            city_district TEXT,
            county TEXT,
            postcode TEXT,
            city TEXT,
            municipality TEXT,
            region TEXT,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (rounded_lat, rounded_lon)
        )
    """)


def create_db(cases, db_path=DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        _create_geocode_cache_table(conn)

        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS cases (
                {cases_ddl()},
                FOREIGN KEY (rounded_lat, rounded_lon)
                    REFERENCES geocode_cache (rounded_lat, rounded_lon)
            )
        """)

        check_schema_version(conn, db_path)
        load_cases(conn, cases)


def check_schema_version(conn, db_path=DB_PATH):
    """Runs every build, carrying an older DB forward through MIGRATIONS to the
    schema declared in CREATE TABLE above. Migration is deliberately narrow —
    additive nullable columns only — and a DB missing a V1 column predates the
    archive entirely, so it is rejected rather than migrated: keep a copy
    before rebuilding, since a rebuild costs every case the feed has dropped.

    DBs built before versioning began carry user_version 0 but are structurally
    v1, so they migrate from the v1 floor like any other."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"{db_path} is schema v{version}, newer than this code's "
            f"v{SCHEMA_VERSION}. Update the package."
        )

    columns = {row[1] for row in conn.execute("PRAGMA table_info(cases)")}
    missing = V1_CASE_COLUMNS - columns
    if missing:
        raise RuntimeError(
            f"{db_path} is schema v{version} and is missing {sorted(missing)}. "
            f"This code declares v{SCHEMA_VERSION} and migrates only from v1. Move "
            "the old DB aside and rebuild from the feed with `uv run uisce-pipeline`."
        )

    # v0 is structurally v1, so it starts from the same rung. A freshly created
    # DB already declares every column, so each step no-ops on it — that is why
    # the guard is per-column rather than per-version.
    for target in range(max(version, 1) + 1, SCHEMA_VERSION + 1):
        for column, decl in MIGRATIONS[target].items():
            if column not in columns:
                conn.execute(f"ALTER TABLE cases ADD COLUMN {column} {decl}")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def load_cases(conn, cases, now=None):
    cur = conn.cursor()
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")

    placeholders = ", ".join("?" * len(DB_CASE_COLUMNS))
    columns = ", ".join(DB_CASE_COLUMNS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in DB_CASE_COLUMNS if c != "id")

    rows = [
        tuple(record[col] for col in DB_CASE_COLUMNS) + (now, now, record["start_date"])
        for record in cases
    ]

    # upsert rather than INSERT OR REPLACE so an existing row's first_seen
    # survives; last_seen advances on every download that includes the case.
    #
    # closed_at stamps this build's first observation of the case leaving
    # Open — see notes/data-quality.md ("closed_at is a floor") for what that
    # means, why NULL is ambiguous, and its limits.
    #
    # SQLite evaluates every SET expression against the pre-update row, so
    # `cases.status` here is the previous status even though `{updates}` also
    # assigns it. `IS` / `IS NOT` are the null-safe comparisons: some rows carry
    # a NULL status, and `!= 'Open'` would silently yield NULL for those.
    closed_at = (
        "closed_at = CASE"
        "  WHEN excluded.status IS 'Open' THEN NULL"
        "  WHEN cases.status IS 'Open' THEN excluded.last_seen"
        "  ELSE cases.closed_at"
        " END"
    )
    # start_date is the feed's STARTDATE, and the feed re-stamps it in place when
    # a notice is edited — usually forwards, past the works it describes, which
    # is what produces the negative-span family (notes/data-quality.md,
    # 2026-07-20). `{updates}` overwrites start_date on every download, so the
    # original is lost unless it is kept here.
    #
    # COALESCE, not MIN: first observed, never earliest seen. A backward re-stamp
    # is as real as a forward one (case 238140 moved -30 days), and taking the
    # minimum would let one install a bogus early start and inflate the duration.
    # That rule was measured and rejected; see the same section.
    #
    # This is an instrument, not yet an input: nothing computes a duration from
    # it. build.py's first_start_date_per_case already pins the start seen at the
    # first *inference*, and can only witness a re-stamp when the description
    # changed too — stamping at download time is what closes that gap, and it
    # needs history behind it before it can say anything.
    first_start = "first_start_date = COALESCE(cases.first_start_date, excluded.start_date)"
    cur.executemany(
        f"INSERT INTO cases ({columns}, first_seen, last_seen, first_start_date) "
        f"VALUES ({placeholders}, ?, ?, ?) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}, "
        f"last_seen = excluded.last_seen, {closed_at}, {first_start}",
        rows,
    )


def _is_usable_case(attrs):
    return any(attrs.get(f) for f in USABLE_CASE_THRESHOLD_FIELDS)


# Titles are structured "Category – County"; each rule normalises the category
# to a stable work_category slug and carries a work_type policy — Planned/
# Unplanned overrides the feed, None leaves it as reported. See
# notes/data-quality.md ("work_category and work_type derivation") for why.
# This is the single categorisation mechanism; there is no separate fill tier.
@dataclass(frozen=True)
class CategoryRule:
    slug: str
    work_type: str | None
    # normalised category strings (lowercase, single-spaced) that map here
    variants: tuple[str, ...]


CATEGORY_RULES = (
    CategoryRule(
        "burst_main",
        "Unplanned",
        ("burst water main", "burst water mains", "burst main"),
    ),
    CategoryRule(
        "essential_works",
        "Planned",
        (
            "essential works",
            "essential maintenance works",
            "essential maintrnance works",  # the feed's own typo, twice
            "maintenance works",
        ),
    ),
    CategoryRule(
        "leak_detection",
        "Planned",
        ("leak detection works", "leak detection/step testing", "step testing works"),
    ),
    CategoryRule(
        "mains_flushing",
        "Planned",
        ("mains flushing", "main flushing"),
    ),
    CategoryRule(
        "boil_notice_issued",
        "Unplanned",
        ("boil water notice",),
    ),
    CategoryRule(
        "boil_notice_lifted",
        "Unplanned",
        ("lifting of boil water notice", "lifting of the boil water notice"),
    ),
    CategoryRule(
        "valve_installation",
        "Planned",
        ("valve installation", "valve installation works"),
    ),
    CategoryRule(
        "valve_repair",
        "Unplanned",
        (
            "valve repair works",
            "valve repair",
            "valve replacement works",
            "valve replacement",
            # a failure is nearer pump_failure in spirit, but this rule already
            # forces Unplanned and is in REPAIR_CATS, so classify() agrees either
            # way — one fewer slug to maintain
            "valve failure",
        ),
    ),
    CategoryRule(
        "water_conservation",
        "Unplanned",  # supply-shortage restrictions, not deliberate works
        (
            "water conservation restrictions",
            "water conservation",
            "water conservation/restrictions",
            "water conservation works",
            # the singular spellings are the common ones in the feed and were
            # missing, so 19 restriction notices carried no slug and accrued as
            # hard outages — see notes/data-quality.md
            "water conservation/restriction",
            "water conservation restriction",
        ),
    ),
    CategoryRule(
        "hydrant_repair",
        "Unplanned",
        ("hydrant repair works", "hydrant repair", "hydrant replacement works"),
    ),
    CategoryRule(
        "hydrant_installation",
        "Planned",
        ("hydrant installation works",),
    ),
    CategoryRule(
        "meter_installation",
        "Planned",
        ("meter installation works", "meter installation", "meter exchange works"),
    ),
    CategoryRule(
        "new_connection",
        "Planned",
        ("new connection works", "new connections", "mains tie-in"),
    ),
    CategoryRule(
        "pump_station_interruption",
        "Unplanned",  # "interruption" family, like reservoir/WTP interruption
        ("pump station interruption",),
    ),
    CategoryRule(
        "pump_failure",
        "Unplanned",
        ("pump failure", "pump failure issue"),
    ),
    CategoryRule(
        "pump_repair",
        "Unplanned",
        ("pump repair works", "pump repair"),
    ),
    CategoryRule(
        "pump_installation",
        "Planned",
        ("pump installation works",),
    ),
    CategoryRule(
        "discolouration",
        "Unplanned",
        ("discolouration", "discoloration"),  # the feed uses both spellings
    ),
    CategoryRule(
        "low_pressure",
        "Unplanned",
        ("low pressure",),
    ),
    CategoryRule(
        "consumption_notice_issued",
        "Unplanned",
        ("do not consume", "do not consume notice"),
    ),
    CategoryRule(
        "investigation",
        "Unplanned",
        ("investigation works", "under investigation"),
    ),
    CategoryRule(
        "mains_rehabilitation",
        "Planned",
        ("mains rehabilitation works", "mains rehabilitation"),
    ),
    CategoryRule(
        "reservoir_interruption",
        "Unplanned",  # "interruption" family; 131/2 in the feed
        ("reservoir interruption",),
    ),
    CategoryRule(
        # deliberately not reservoir_interruption: the feed's title grammar
        # reserves "Interruption" for lost supply, so cleaning and upgrade works
        # on a reservoir are works, and must not accrue downtime
        "reservoir_works",
        None,
        ("reservoir works", "reservoir cleaning", "reservoir upgrade works"),
    ),
    CategoryRule(
        "water_treatment_plant_interruption",
        "Unplanned",  # "interruption" family; 58/1 in the feed
        ("water treatment plant interruption", "a water treatment plant interruption"),
    ),
    CategoryRule(
        # likewise: an upgrade is not an interruption, and must not land in
        # HARD_CATS by sharing a slug with one
        "water_treatment_plant_upgrade",
        "Planned",
        ("water treatment plant upgrade",),
    ),
    CategoryRule(
        # the lift is good news, like boil_notice_lifted; site.py ignores both.
        # The "notice" spelling must be listed before consumption_notice_issued
        # can claim it: one case was stored as an *issued* do-not-consume notice,
        # inverting its meaning and knocking a grade off Cork.
        "consumption_notice_lifted",
        "Unplanned",
        ("lifting of do not consume", "lifting of do not consume notice"),
    ),
    # slug-only: the category is clear but planned vs unplanned genuinely isn't,
    # so work_type is left as the feed reported it
    CategoryRule(
        "mains_repair",
        None,
        (
            "mains repair works",
            "mains repair",
            "mains repair work",
            "mains repairs works",
            "main repair works",
        ),
    ),
    CategoryRule(
        "power_outage",
        None,
        ("power outage",),
    ),
)

_RULE_BY_VARIANT = {variant: rule for rule in CATEGORY_RULES for variant in rule.variants}

# titles use an en-dash or hyphen between category and county, inconsistently,
# and sometimes without the space before the dash ("...Works– Roscommon");
# the trailing space is required so hyphenated words don't split
_TITLE_CATEGORY_SPLIT = re.compile(r"\s*[–-]\s+")


def _normalise_category(category):
    return " ".join(category.lower().split())


def _title_category(title):
    if not title:
        return None
    return _normalise_category(_TITLE_CATEGORY_SPLIT.split(title, maxsplit=1)[0])


def classify_category(title):
    """Return the CategoryRule for a title, or None if no known rule matches."""
    return _RULE_BY_VARIANT.get(_title_category(title))


def normalise_legacy_empty_strings(conn):
    """map_cases normalises '' to NULL for cases still in the feed, but rows
    that dropped out of the feed before that normalisation existed are never
    remapped, so clean them up in the DB directly."""
    for column in ("work_type", "status"):
        conn.execute(f"UPDATE cases SET {column} = NULL WHERE {column} = ''")


def trim_titles(conn):
    """map_cases trims titles for rows still in the feed; rows that dropped out
    before trimming existed keep their untrimmed title, so clean them in the DB
    too. (Category matching normalises whitespace regardless; this is for the
    stored value.)"""
    conn.execute("UPDATE cases SET title = trim(title) WHERE title != trim(title)")


def unmatched_categories(conn):
    """Counter of title prefixes no CategoryRule claims, commonest first.

    An unmatched title gets work_category = NULL, which classify() reads as
    "not a disruption" and silently drops from the metrics — see
    notes/data-quality.md ("A missing variant was silently inventing supply
    outages") for why this must be printed on every backfill rather than
    handled as a one-off cleanup.
    """
    counts = Counter(
        prefix
        for (title,) in conn.execute("SELECT title FROM cases")
        if classify_category(title) is None and (prefix := _title_category(title))
    )
    return counts


UNMATCHED_SHOWN = 15


def backfill_work_category(conn):
    """Derive work_category from the title for every case matching a known
    CategoryRule. Pure normalisation of an existing column, so it lives in
    cases rather than inferred_cases.

    Only ever sets a slug, never clears one, so rule changes must be additive —
    the same discipline MIGRATIONS documents. Renaming a slug leaves stale
    values behind and needs its own migration."""
    rows = conn.execute("SELECT id, title FROM cases").fetchall()
    updates = [
        (rule.slug, case_id)
        for case_id, title in rows
        if (rule := classify_category(title))
    ]
    conn.executemany("UPDATE cases SET work_category = ? WHERE id = ?", updates)

    unmatched = unmatched_categories(conn)
    if unmatched:
        print(f"{sum(unmatched.values())} cases with no category rule:")
        for prefix, n in unmatched.most_common(UNMATCHED_SHOWN):
            print(f"  {n:>4}x {prefix}")
    return len(updates)


def backfill_work_type(conn):
    """Override work_type from the title category: each CategoryRule with a
    definitive work_type sets it regardless of the feed value (a burst main is
    never planned). Rules with work_type=None give a slug but leave work_type
    untouched. Returns the number of rows changed."""
    rows = conn.execute("SELECT id, title, work_type FROM cases").fetchall()
    updates = [
        (rule.work_type, case_id)
        for case_id, title, work_type in rows
        if (rule := classify_category(title)) and rule.work_type and work_type != rule.work_type
    ]
    conn.executemany("UPDATE cases SET work_type = ? WHERE id = ?", updates)
    return len(updates)


# "may cause low pressure to Ballyduff and surrounding areas" — the notice
# describes reduced pressure and no loss of supply. The far commoner
# "...low pressure AND supply disruptions to..." (100 cases) is deliberately not
# matched: those announce both, and the supply loss is the part that accrues.
_PRESSURE_ONLY = re.compile(r"may cause (?:severe )?low pressure to\b", re.I)


def backfill_reduced_pressure(conn):
    """Set the reduced_pressure flag where the notice text says so and the feed
    did not. Returns the number of rows changed.

    Same principle as the work_type override above: the feed's own field is
    corrected from its own notice, where the notice is unambiguous — see
    notes/data-quality.md ("The notice title is not a reliable severity signal").

    Only ever sets the flag, never clears it, matching the additive discipline of
    every other backfill.
    """
    rows = conn.execute(
        "SELECT id, description FROM cases WHERE description IS NOT NULL AND NOT reduced_pressure"
    ).fetchall()
    updates = [
        (case_id,) for case_id, description in rows if _PRESSURE_ONLY.search(description)
    ]
    conn.executemany("UPDATE cases SET reduced_pressure = 1 WHERE id = ?", updates)
    return len(updates)


def backfill_county(cases):
    with sqlite3.connect(DB_PATH) as conn:
        for case in cases:
            if not case.get("county"):
                row = conn.execute(
                    "SELECT county FROM geocode_cache WHERE rounded_lat = ? AND rounded_lon = ?",
                    (case["rounded_lat"], case["rounded_lon"]),
                ).fetchone()
                if row and row[0]:
                    case["county"] = row[0].removeprefix("County ")


def skip_geocoding(cases, db_path=DB_PATH):
    """Populate geocode_cache with placeholder rows instead of calling
    LocationIQ. Coords already cached are left untouched; any new coord gets
    the same placeholder a failed lookup would leave, which satisfies the cases
    FK and is retried on the next real run. Lets you rebuild the cases table
    against fresh source data (and re-apply the backfills) without spending
    geocoding calls."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        _create_geocode_cache_table(conn)
        cached = {
            (row[0], row[1])
            for row in conn.execute("SELECT rounded_lat, rounded_lon FROM geocode_cache")
        }
        missing = {(c["rounded_lat"], c["rounded_lon"]) for c in cases} - cached
        conn.executemany(
            _GEOCODE_INSERT,
            [geocode_failure_row(lat, lon, "geocode skipped") for lat, lon in missing],
        )
    print(f"Skipped geocoding: {len(missing)} new coord(s) got placeholder rows")


def backfill(db_path=DB_PATH):
    """Re-derive the computed columns (trimmed title, work_category, work_type,
    reduced_pressure) on an existing DB. Pure DB work — no download, mapping, or geocoding — so
    it's safe to re-run on its own after editing the category rules to
    re-derive against data that's already been downloaded."""
    with sqlite3.connect(db_path) as conn:
        check_schema_version(conn, db_path)
        normalise_legacy_empty_strings(conn)
        trim_titles(conn)
        categorised = backfill_work_category(conn)
        overridden = backfill_work_type(conn)
        pressure = backfill_reduced_pressure(conn)
    print(f"Set work_category for {categorised} cases from title categories")
    print(f"Overrode work_type for {overridden} cases from title categories")
    if pressure:
        print(
            f"Set reduced_pressure for {pressure} case(s) whose text describes "
            "pressure, not supply loss"
        )


def run(skip_geocode=False):
    features = download_cases(make_session())
    CASES_RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    CASES_RAW_PATH.write_text(json.dumps(features, indent=2))

    mapped_cases, skipped = map_cases(read_arcgis_cases())
    if skipped:
        print(f"Skipped {len(skipped)} cases with no usable data: {skipped}")
    CASES_MAPPED_PATH.parent.mkdir(parents=True, exist_ok=True)
    CASES_MAPPED_PATH.write_text(json.dumps(mapped_cases, indent=2))

    if skip_geocode:
        skip_geocoding(mapped_cases)
    else:
        geocode_all(mapped_cases, require_api_key())
    backfill_county(mapped_cases)
    create_db(mapped_cases)

    backfill()


def main():
    parser = argparse.ArgumentParser(description="Build the uisce cases database.")
    parser.add_argument(
        "--skip-geocode",
        action="store_true",
        help="don't call LocationIQ; give new coordinates placeholder geocode rows "
        "(retried on the next real run). Rebuilds cases without spending calls.",
    )
    run(skip_geocode=parser.parse_args().skip_geocode)
