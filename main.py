import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from pyproj import Transformer

LOCATIONIQ_REVERSE_URL = "https://us1.locationiq.com/v1/reverse"
LOCATIONIQ_GEOCODE_SLEEP = 1
COORD_PRECISION = 4  # ~10 meter
load_dotenv(Path(__file__).parent / ".env")
LOCATIONIQ_API_KEY = os.getenv("LOCATIONIQ_API_KEY")
if not LOCATIONIQ_API_KEY:
    raise RuntimeError("LOCATIONIQ_API_KEY not set, check your .env file")

DEFAULT_TIMEOUT = 15
USABLE_CASE_THRESHOLD_FIELDS = ["TITLE", "DESCRIPTION"]
DB_PATH = Path("out/uisce.db")
CASES_RAW_PATH = Path("out/cases.json")
CASES_MAPPED_PATH = Path("out/cases_mapped.json")

DB_CASE_COLUMNS = [
    "id", "work_type", "title", "start_date", "end_date", "description",
    "status", "global_id", "approval_status", "location", "county", "reference_num",
    "boil_water_notice", "traffic_disruptions", "pollution", "water_outage", "do_not_drink",
    "discolouration", "reduced_pressure", "water_restrictions", "full_lat", "full_lon",
    "rounded_lat", "rounded_lon",
]


def download_cases():
    base_url = "https://services2.arcgis.com/OqejhVam51LdtxGa/arcgis/rest/services/WaterAdvisoryCR021_DeptView/FeatureServer/0/query"
    all_features = []
    offset = 0
    page_size = 1000

    session = _make_session()

    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "f": "json",
        }

        resp = session.get(base_url, params=params, timeout=DEFAULT_TIMEOUT)
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

        offset += page_size
        time.sleep(0.3)

    print(f"Done: {len(all_features)} records")
    CASES_RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    CASES_RAW_PATH.write_text(json.dumps(all_features, indent=2))


def read_arcgis_cases():
    return json.loads(CASES_RAW_PATH.read_text())


def read_mapped_cases():
    return json.loads(CASES_MAPPED_PATH.read_text())


def map_cases(cases_to_map):
    skipped = []

    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    field_map = {
        "OBJECTID": "id",
        "WORKTYPE": "work_type",
        "TITLE": "title",
        "STARTDATE": "start_date",      # low trust - start / end often ~60s apart
        "ENDDATE": "end_date",          # low trust - start / end often ~60s apart
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

    all_cases = []
    for case in cases_to_map:
        attrs = case["attributes"]

        if not _is_usable_case(attrs):
            skipped.append(attrs.get("OBJECTID"))
            continue
        
        mapped_case = {field_map[k]: v for k, v in attrs.items() if k in field_map}

        mapped_case["start_date"] = _epoch_ms_to_iso(mapped_case["start_date"])
        mapped_case["end_date"] = _epoch_ms_to_iso(mapped_case["end_date"])

        lon, lat = transformer.transform(case["geometry"]["x"], case["geometry"]["y"])
        mapped_case["full_lat"] = lat
        mapped_case["full_lon"] = lon

        mapped_case["rounded_lat"] = round(lat, COORD_PRECISION)
        mapped_case["rounded_lon"] = round(lon, COORD_PRECISION)

        if mapped_case["county"] == "Dnegal":
            mapped_case["county"] = "Donegal"

        if mapped_case["title"] is None or mapped_case["title"] == "":
            mapped_case["title"] = "unknown"

        all_cases.append(mapped_case)

    if skipped:
        print(f"Skipped {len(skipped)} cases with no usable data: {skipped}")

    CASES_MAPPED_PATH.parent.mkdir(parents=True, exist_ok=True)
    CASES_MAPPED_PATH.write_text(json.dumps(all_cases, indent=2))

    return all_cases

def _epoch_ms_to_iso(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()

def geocode_all(cases_to_geocode):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        _create_geocode_cache_table(conn)

        rows = conn.execute("SELECT rounded_lat, rounded_lon FROM geocode_cache")
        done = {(row[0], row[1]) for row in rows}
        print(f"{len(done)} coords already geocoded, resuming")

        unique_coords = {(c["rounded_lat"], c["rounded_lon"]) for c in cases_to_geocode}
        remaining = unique_coords - done
        print(f"{len(remaining)} coords left to geocode")

        session = _make_session()
        for lat, lon in remaining:
            try:
                result = _call_locationiq(session, lat, lon)
            except requests.HTTPError as e:
                print(f"Failed at ({lat}, {lon}), skipping for now: {e}")
                continue

            address = result.get("address", {})
            conn.execute(
                """
                INSERT OR IGNORE INTO geocode_cache (
                    rounded_lat, rounded_lon, display_name,
                    road, town, village, hamlet, suburb, city_district,
                    county, postcode, city, municipality, region, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lat, lon,
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
                ),
            )
            conn.commit()
            time.sleep(LOCATIONIQ_GEOCODE_SLEEP)


def _call_locationiq(session, lat, lon):
    params = {"key": LOCATIONIQ_API_KEY, "lat": lat, "lon": lon, "format": "json"}

    resp = session.get(LOCATIONIQ_REVERSE_URL, params=params, timeout=DEFAULT_TIMEOUT)

    if resp.status_code == 429:
        print(f"Rate limited at ({lat}, {lon}), backing off")
        time.sleep(5)
        resp = session.get(LOCATIONIQ_REVERSE_URL, params=params, timeout=DEFAULT_TIMEOUT)

    resp.raise_for_status()

    data = resp.json()
    return data

def _make_session():
    session = requests.Session()
    session.headers.update({"User-Agent": "uisce/1.0 https://github.com/baz8080/uisce"})
    return session

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

        _load_cases(conn, cases)

def _load_cases(conn, cases):
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


def _backfill_county(cases):
    with sqlite3.connect(DB_PATH) as conn:
        for case in cases:
            if not case.get("county"):
                row = conn.execute(
                    "SELECT county FROM geocode_cache WHERE rounded_lat = ? AND rounded_lon = ?",
                    (case["rounded_lat"], case["rounded_lon"]),
                ).fetchone()
                if row and row[0]:
                    case["county"] = row[0].removeprefix("County ")

if __name__ == "__main__":
    download_cases()
    arcgis_cases = read_arcgis_cases()
    mapped_cases = map_cases(arcgis_cases)
    geocode_all(mapped_cases)
    _backfill_county(mapped_cases)
    create_db(mapped_cases)
