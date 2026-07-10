import json
import os
import re
import sqlite3
import time
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

        if mapped_case["title"] is None:
            mapped_case["title"] = "unknown"

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
                full_lat REAL NOT NULL,
                full_lon REAL NOT NULL,
                rounded_lat REAL NOT NULL,
                rounded_lon REAL NOT NULL,
                FOREIGN KEY (rounded_lat, rounded_lon)
                    REFERENCES geocode_cache (rounded_lat, rounded_lon)
            )
        """)

        load_cases(conn, cases)


def load_cases(conn, cases):
    cur = conn.cursor()

    placeholders = ", ".join("?" * len(DB_CASE_COLUMNS))
    columns = ", ".join(DB_CASE_COLUMNS)

    rows = [tuple(record[col] for col in DB_CASE_COLUMNS) for record in cases]

    cur.executemany(
        f"INSERT OR REPLACE INTO cases ({columns}) VALUES ({placeholders})",
        rows,
    )


def _is_usable_case(attrs):
    return any(attrs.get(f) for f in USABLE_CASE_THRESHOLD_FIELDS)


# Titles are structured "Category – County". These are the categories whose
# Planned/Unplanned split was at least 95% one-sided among the cases where
# the feed did populate work_type, with at least 20 such labelled cases
# (2026-07 snapshot; counts are unplanned/planned). Ambiguous categories
# (Essential Works 125/227, Mains Repair Works 119/93, Leak Detection Works,
# Power Outage, Mains Flushing, ...) are deliberately absent and stay NULL.
# Keys are lowercase; lookups go through _normalise_category.
WORK_TYPE_BY_TITLE_CATEGORY = {
    "burst water main": "Unplanned",  # 540/3
    "burst water mains": "Unplanned",  # 49/0
    "burst main": "Unplanned",  # abbreviation of burst water main
    "reservoir interruption": "Unplanned",  # 131/2
    "under investigation": "Unplanned",  # 82/0
    "water treatment plant interruption": "Unplanned",  # 58/1
    "investigation works": "Unplanned",  # 47/0
    "valve repair works": "Unplanned",  # 33/1
    "valve repair": "Unplanned",  # abbreviation of valve repair works
    "low pressure": "Unplanned",  # 31/0
    "discolouration": "Unplanned",  # 31/0
    "new connection works": "Planned",  # 2/56
    "mains rehabilitation works": "Planned",  # 0/30
}

# titles use an en-dash or hyphen between category and county, inconsistently,
# and sometimes without the space before the dash ("...Works– Roscommon");
# the trailing space is required so hyphenated words don't split
_TITLE_CATEGORY_SPLIT = re.compile(r"\s*[–-]\s+")


def _normalise_category(category):
    return " ".join(category.lower().split())


def infer_work_type(title):
    if not title:
        return None
    category = _TITLE_CATEGORY_SPLIT.split(title, maxsplit=1)[0]
    return WORK_TYPE_BY_TITLE_CATEGORY.get(_normalise_category(category))


def normalise_legacy_empty_strings(conn):
    """map_cases normalises '' to NULL for cases still in the feed, but rows
    that dropped out of the feed before that normalisation existed are never
    remapped, so clean them up in the DB directly."""
    for column in ("work_type", "status"):
        conn.execute(f"UPDATE cases SET {column} = NULL WHERE {column} = ''")


def backfill_work_type(conn):
    rows = conn.execute(
        "SELECT id, title FROM cases WHERE work_type IS NULL OR work_type = ''"
    ).fetchall()

    updates = [
        (work_type, case_id)
        for case_id, title in rows
        if (work_type := infer_work_type(title))
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


def run():
    api_key = require_api_key()

    features = download_cases(make_session())
    CASES_RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    CASES_RAW_PATH.write_text(json.dumps(features, indent=2))

    mapped_cases, skipped = map_cases(read_arcgis_cases())
    if skipped:
        print(f"Skipped {len(skipped)} cases with no usable data: {skipped}")
    CASES_MAPPED_PATH.parent.mkdir(parents=True, exist_ok=True)
    CASES_MAPPED_PATH.write_text(json.dumps(mapped_cases, indent=2))

    geocode_all(mapped_cases, api_key)
    backfill_county(mapped_cases)
    create_db(mapped_cases)

    with sqlite3.connect(DB_PATH) as conn:
        normalise_legacy_empty_strings(conn)
        filled = backfill_work_type(conn)
    print(f"Backfilled work_type for {filled} cases from title categories")
