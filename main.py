import json
import os
import time
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from pyproj import Transformer

LOCATIONIQ_GEOCODE_SLEEP = 1
load_dotenv(Path(__file__).parent / ".env")
LOCATIONIQ_API_KEY = os.getenv("LOCATIONIQ_API_KEY")
if not LOCATIONIQ_API_KEY:
    raise RuntimeError("LOCATIONIQ_API_KEY not set, check your .env file")

DEFAULT_TIMEOUT = 15


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
            "f": "json"
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
    coord_to_cases = defaultdict(list)
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
        "WATERRESTRICTIONS": "water_restrictions"

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

    for case in arcgis_cases:

        mapped_case = {
            field_map[k]: v
            for k, v in case["attributes"].items()
            if k in field_map
        }

        mapped_case["start_date"] = epoch_ms_to_iso(mapped_case["start_date"])
        mapped_case["end_date"] = epoch_ms_to_iso(mapped_case["end_date"])

        lon, lat = transformer.transform(case["geometry"]["x"], case["geometry"]["y"])
        mapped_case["full_lat"] = lat
        mapped_case["full_lon"] = lon

        precision = 4 # ~10 meter
        rounded_lat = round(lat, precision)
        rounded_lon = round(lon, precision)

        mapped_case["rounded_lat"] = rounded_lat
        mapped_case["rounded_lon"] = rounded_lon

        key = (rounded_lat, rounded_lon)

        coord_to_cases[key].append(mapped_case)

        attrs = case["attributes"]
        for field_key, val in attrs.items():
            if val not in (None, "", 0):
                populated[field_key] += 1

    all_cases = [case for cases_list in coord_to_cases.values() for case in cases_list]
    out_path = Path("out/cases_mapped.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_cases, indent=2))

    print_debug_info(field_map, arcgis_cases, coord_to_cases, populated, total)

    return all_cases


def print_debug_info(
    field_map: dict[str, str],
    arcgis_cases: list[dict],
    coord_to_cases: dict[tuple[float, float], list[dict]],
    populated: Counter,
    total: int,
):
    for key in field_map:
        pct = populated.get(key, 0) / total * 100
        print(f"{key:25s} {populated.get(key, 0):5d}/{total} ({pct:.1f}%)")


    

    print(f"{len(arcgis_cases)} cases, {len(coord_to_cases)} unique coords")
    print(f"{len(arcgis_cases) - len(coord_to_cases)} duplicates thrown out")


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

    # unique coords from cases, same pattern as your earlier dedup
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
    params = {
        "key": LOCATIONIQ_API_KEY,
        "lat": lat,
        "lon": lon,
        "format": "json"
    }

    resp = session.get("https://us1.locationiq.com/v1/reverse", params=params, timeout=DEFAULT_TIMEOUT)

    if resp.status_code == 429:
        print(f"Rate limited at ({lat}, {lon}), backing off")
        time.sleep(5)
        resp = session.get("https://us1.locationiq.com/v1/reverse", params=params, timeout=DEFAULT_TIMEOUT)

    resp.raise_for_status()

    data = resp.json()
    return data

def make_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "uisce/1.0 https://github.com/baz8080/uisce"
    })
    return session

if __name__ == "__main__":
    download_cases()
    arcgis_cases = read_arcgis_cases()
    mapped_cases = map_cases(arcgis_cases)
    geocode_all(mapped_cases)
