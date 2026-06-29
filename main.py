import json
import os
import sqlite3
import time
from collections import Counter, defaultdict
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

DB_PATH = Path("out/uisce.db")


def download_cases():
    base_url = "https://services2.arcgis.com/OqejhVam51LdtxGa/arcgis/rest/services/WaterAdvisoryCR021_DeptView/FeatureServer/0/query"
    all_features = []
    offset = 0
    page_size = 1000

    session = make_session()

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
    out_path = Path("out/cases.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_features, indent=2))


def read_arcgis_cases():
    return json.loads(Path("out/cases.json").read_text())


def read_mapped_cases():
    return json.loads(Path("out/cases_mapped.json").read_text())


def map_cases(arcgis_cases):
    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    field_map = {
        "OBJECTID": "id",
        "WORKTYPE": "work_type",
        "TITLE": "title",
        "STARTDATE": "start_date",
        "ENDDATE": "end_date",
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

    populated = Counter()
    total = len(arcgis_cases)
    all_cases = []

    for case in arcgis_cases:
        mapped_case = {field_map[k]: v for k, v in case["attributes"].items() if k in field_map}

        mapped_case["start_date"] = epoch_ms_to_iso(mapped_case["start_date"])
        mapped_case["end_date"] = epoch_ms_to_iso(mapped_case["end_date"])

        lon, lat = transformer.transform(case["geometry"]["x"], case["geometry"]["y"])
        mapped_case["full_lat"] = lat
        mapped_case["full_lon"] = lon

        mapped_case["rounded_lat"] = round(lat, COORD_PRECISION)
        mapped_case["rounded_lon"] = round(lon, COORD_PRECISION)

        all_cases.append(mapped_case)

        for field_key, val in case["attributes"].items():
            if val not in (None, "", 0):
                populated[field_key] += 1

    out_path = Path("out/cases_mapped.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_cases, indent=2))

    print_debug_info(field_map, arcgis_cases, all_cases, populated, total)
    return all_cases


def print_debug_info(field_map, arcgis_cases, all_cases, populated, total):
    for key in field_map:
        pct = populated.get(key, 0) / total * 100
        print(f"{key:25s} {populated.get(key, 0):5d}/{total} ({pct:.1f}%)")

    coord_groups = defaultdict(list)
    for case in all_cases:
        key = (case["rounded_lat"], case["rounded_lon"])
        coord_groups[key].append(case)

    for coord, group in coord_groups.items():
        if len(group) > 1:
            print(coord)
            for case in group:
                print(f"  ID:{case['id']}, Location: {case['location']}")

    unique_coords = len(coord_groups)
    print(f"{len(arcgis_cases)} cases, {unique_coords} unique coords")
    print(f"{len(arcgis_cases) - unique_coords} cases share a coordinate with another")


def epoch_ms_to_iso(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def load_done_coords(jsonl_path):
    done = set()
    if not jsonl_path.exists():
        return done

    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            done.add((record["query_lat"], record["query_lon"]))
    return done


def geocode_all(mapped_cases):
    jsonl_path = Path("out/geocodes.jsonl")
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    done = load_done_coords(jsonl_path)
    print(f"{len(done)} coords already geocoded, resuming")

    unique_coords = {(c["rounded_lat"], c["rounded_lon"]) for c in mapped_cases}
    remaining = unique_coords - done
    print(f"{len(remaining)} coords left to geocode")

    with open(jsonl_path, "a") as f:  # append mode, never overwrite
        session = make_session()

        for lat, lon in remaining:
            try:
                result = call_locationiq(session, lat, lon)
            except requests.HTTPError as e:
                print(f"Failed at ({lat}, {lon}), skipping for now: {e}")
                continue

            record = {"query_lat": lat, "query_lon": lon, "result": result}
            f.write(json.dumps(record) + "\n")
            f.flush()
            time.sleep(LOCATIONIQ_GEOCODE_SLEEP)


def call_locationiq(session, lat, lon):
    params = {"key": LOCATIONIQ_API_KEY, "lat": lat, "lon": lon, "format": "json"}

    resp = session.get(LOCATIONIQ_REVERSE_URL, params=params, timeout=DEFAULT_TIMEOUT)

    if resp.status_code == 429:
        print(f"Rate limited at ({lat}, {lon}), backing off")
        time.sleep(5)
        resp = session.get(LOCATIONIQ_REVERSE_URL, params=params, timeout=DEFAULT_TIMEOUT)

    resp.raise_for_status()

    data = resp.json()
    return data


def make_session():
    session = requests.Session()
    session.headers.update({"User-Agent": "uisce/1.0 https://github.com/baz8080/uisce"})
    return session


def create_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executescript("""
        DROP TABLE IF EXISTS cases;
        DROP TABLE IF EXISTS geocode_cache;

        CREATE TABLE geocode_cache (
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
        );

        CREATE TABLE cases (
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
        );
    """)
    conn.commit()

    load_geocode_cache(conn)
    load_cases(conn)

    conn.close()


def load_cases(conn):
    cur = conn.cursor()
    cases = json.loads(Path("out/cases_mapped.json").read_text())

    for record in cases:
        case_id = record["id"]
        work_type = record["work_type"]
        title = record["title"]
        start_date = record["start_date"]
        end_date = record["end_date"]
        description = record["description"]
        status = record["status"]
        global_id = record["global_id"]
        approval_status = record["approval_status"]
        location = record["location"]
        county = record["county"]
        reference_num = record["reference_num"]
        boil_water_notice = record["boil_water_notice"]
        traffic_disruptions = record["traffic_disruptions"]
        pollution = record["pollution"]
        water_outage = record["water_outage"]
        do_not_drink = record["do_not_drink"]
        discolouration = record["discolouration"]
        reduced_pressure = record["reduced_pressure"]
        water_restrictions = record["water_restrictions"]
        full_lat = record["full_lat"]
        full_lon = record["full_lon"]
        rounded_lat = record["rounded_lat"]
        rounded_lon = record["rounded_lon"]

        cur.execute(
            """
            INSERT INTO cases (
                id, work_type, title, start_date, end_date, description,
                status, global_id, approval_status, location, county, reference_num,
                boil_water_notice, traffic_disruptions, pollution, water_outage, do_not_drink,
                discolouration, reduced_pressure, water_restrictions, full_lat, full_lon,
                rounded_lat, rounded_lon
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                case_id,
                work_type,
                title,
                start_date,
                end_date,
                description,
                status,
                global_id,
                approval_status,
                location,
                county,
                reference_num,
                boil_water_notice,
                traffic_disruptions,
                pollution,
                water_outage,
                do_not_drink,
                discolouration,
                reduced_pressure,
                water_restrictions,
                full_lat,
                full_lon,
                rounded_lat,
                rounded_lon,
            ),
        )

    conn.commit()


def load_geocode_cache(conn):
    cur = conn.cursor()
    field_counts = Counter()

    with open("out/geocodes.jsonl") as f:
        for line in f:
            record = json.loads(line)
            result = record["result"]
            address = result.get("address", {})
            field_counts.update(address.keys())

            cur.execute(
                """
                INSERT INTO geocode_cache (
                    rounded_lat, rounded_lon, display_name,
                    road, town, village, hamlet, suburb, city_district,
                    county, postcode, region, city, municipality, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    record["query_lat"],
                    record["query_lon"],
                    result.get("display_name"),
                    address.get("road"),
                    address.get("town"),
                    address.get("village"),
                    address.get("hamlet"),
                    address.get("suburb"),
                    address.get("city_district"),
                    address.get("county"),
                    address.get("postcode"),
                    address.get("region"),
                    address.get("city"),
                    address.get("municipality"),
                    json.dumps(result),
                ),
            )

        for field, count in field_counts.most_common():
            print(f"{field:20s} {count}")

    conn.commit()


if __name__ == "__main__":
    download_cases()
    arcgis_cases = read_arcgis_cases()
    mapped_cases = map_cases(arcgis_cases)
    geocode_all(mapped_cases)
    create_db()
