import argparse
import json
import os
import re
import sqlite3
import time
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
# create_db; bump this only when that declaration changes, and see
# check_schema_version for why there is deliberately no migration ladder.
SCHEMA_VERSION = 1

DB_CASE_COLUMNS = [
    "id",
    "work_type",
    "title",
    "start_date",
    "end_date",
    "description",
    "status",
    "global_id",
    "approval_status",
    "location",
    "county",
    "reference_num",
    "boil_water_notice",
    "traffic_disruptions",
    "pollution",
    "water_outage",
    "do_not_drink",
    "discolouration",
    "reduced_pressure",
    "water_restrictions",
    "full_lat",
    "full_lon",
    "rounded_lat",
    "rounded_lon",
]

# Columns not in DB_CASE_COLUMNS (they are derived or stamped, not fed) but
# still required by the declared schema, so an unstamped older DB can be
# recognised as structurally v1.
REQUIRED_CASE_COLUMNS = set(DB_CASE_COLUMNS) | {"work_category", "first_seen", "last_seen"}

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


def create_db(cases):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        _create_geocode_cache_table(conn)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY,
                work_type TEXT,
                work_category TEXT,
                title TEXT,
                start_date TEXT,
                end_date TEXT,
                description TEXT,
                status TEXT,
                global_id TEXT,
                approval_status TEXT,
                location TEXT,
                county TEXT,
                reference_num TEXT,
                boil_water_notice INTEGER,
                traffic_disruptions INTEGER,
                pollution INTEGER,
                water_outage INTEGER,
                do_not_drink INTEGER,
                discolouration INTEGER,
                reduced_pressure INTEGER,
                water_restrictions INTEGER,
                work_category TEXT,
                first_seen TEXT,
                last_seen TEXT,
                full_lat REAL NOT NULL,
                full_lon REAL NOT NULL,
                rounded_lat REAL NOT NULL,
                rounded_lon REAL NOT NULL,
                FOREIGN KEY (rounded_lat, rounded_lon)
                    REFERENCES geocode_cache (rounded_lat, rounded_lon)
            )
        """)

        check_schema_version(conn)
        load_cases(conn, cases)


def check_schema_version(conn, db_path=DB_PATH):
    """The full `cases` schema is declared in CREATE TABLE above; there is no
    migration ladder. The published DB is downloaded and updated in place each
    build, so this guards against writing into a DB that predates the declared
    schema — which would fail confusingly on the missing columns instead.

    DBs built before versioning began carry user_version 0 but are structurally
    identical to SCHEMA_VERSION 1 (work_category / first_seen / last_seen were
    added by the ALTER TABLE helpers this replaced). Those are stamped in place
    rather than rejected. Anything genuinely older is a rebuild, not a migration:
    the DB is an accumulating archive, so keep a copy before rebuilding."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"{db_path} is schema v{version}, newer than this code's "
            f"v{SCHEMA_VERSION}. Update the package."
        )

    columns = {row[1] for row in conn.execute("PRAGMA table_info(cases)")}
    missing = REQUIRED_CASE_COLUMNS - columns
    if missing:
        raise RuntimeError(
            f"{db_path} is schema v{version} and is missing {sorted(missing)}. "
            f"This code declares v{SCHEMA_VERSION} and does not migrate. Move the "
            "old DB aside and rebuild from the feed with `uv run uisce-pipeline`."
        )
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def load_cases(conn, cases, now=None):
    cur = conn.cursor()
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")

    placeholders = ", ".join("?" * len(DB_CASE_COLUMNS))
    columns = ", ".join(DB_CASE_COLUMNS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in DB_CASE_COLUMNS if c != "id")

    rows = [
        tuple(record[col] for col in DB_CASE_COLUMNS) + (now, now) for record in cases
    ]

    # upsert rather than INSERT OR REPLACE so an existing row's first_seen
    # survives; last_seen advances on every download that includes the case
    cur.executemany(
        f"INSERT INTO cases ({columns}, first_seen, last_seen) "
        f"VALUES ({placeholders}, ?, ?) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}, last_seen = excluded.last_seen",
        rows,
    )


def _is_usable_case(attrs):
    return any(attrs.get(f) for f in USABLE_CASE_THRESHOLD_FIELDS)


# titles are structured "Category – County". Each rule normalises the category
# part to a stable slug for work_category, and carries a work_type policy:
#   - "Unplanned"/"Planned": set work_type to this, OVERRIDING the feed, because
#     the label is editorially unambiguous (a burst main is never planned; the
#     odd contradicting row is the completion update at the end of the job).
#   - None: give a work_category slug but leave work_type as the feed reported it
#     (e.g. mains repair / power outage — genuinely both planned and unplanned).
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
        ("essential works", "essential maintenance works"),
    ),
    CategoryRule(
        "leak_detection",
        "Planned",
        ("leak detection works", "leak detection/step testing", "step testing works"),
    ),
    CategoryRule(
        "mains_flushing",
        "Planned",
        ("mains flushing",),
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
        ("valve repair works", "valve repair", "valve replacement works"),
    ),
    CategoryRule(
        "water_conservation",
        "Unplanned",  # supply-shortage restrictions, not deliberate works
        (
            "water conservation restrictions",
            "water conservation",
            "water conservation/restrictions",
            "water conservation works",
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
        ("meter installation works",),
    ),
    CategoryRule(
        "new_connection",
        "Planned",
        ("new connection works", "new connections"),
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
        ("discolouration",),
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
        ("mains rehabilitation works",),
    ),
    CategoryRule(
        "reservoir_interruption",
        "Unplanned",  # "interruption" family; 131/2 in the feed
        ("reservoir interruption",),
    ),
    CategoryRule(
        "water_treatment_plant_interruption",
        "Unplanned",  # "interruption" family; 58/1 in the feed
        ("water treatment plant interruption",),
    ),
    # slug-only: the category is clear but planned vs unplanned genuinely isn't,
    # so work_type is left as the feed reported it
    CategoryRule(
        "mains_repair",
        None,
        ("mains repair works", "mains repair", "mains repair work", "mains repairs works"),
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


def backfill_work_category(conn):
    """Derive work_category from the title for every case matching a known
    CategoryRule. Pure normalisation of an existing column, so it lives in
    cases rather than inferred_cases."""
    rows = conn.execute("SELECT id, title FROM cases").fetchall()
    updates = [
        (rule.slug, case_id)
        for case_id, title in rows
        if (rule := classify_category(title))
    ]
    conn.executemany("UPDATE cases SET work_category = ? WHERE id = ?", updates)
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
    """Re-derive the computed columns (trimmed title, work_category, work_type)
    on an existing DB. Pure DB work — no download, mapping, or geocoding — so
    it's safe to re-run on its own after editing the category rules to
    re-derive against data that's already been downloaded."""
    with sqlite3.connect(db_path) as conn:
        check_schema_version(conn, db_path)
        normalise_legacy_empty_strings(conn)
        trim_titles(conn)
        categorised = backfill_work_category(conn)
        overridden = backfill_work_type(conn)
    print(f"Set work_category for {categorised} cases from title categories")
    print(f"Overrode work_type for {overridden} cases from title categories")


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
