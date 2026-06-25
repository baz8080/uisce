import json
import time
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
from pyproj import Transformer


def download_cases():
    base_url = "https://services2.arcgis.com/OqejhVam51LdtxGa/arcgis/rest/services/WaterAdvisoryCR021_DeptView/FeatureServer/0/query"
    all_features = []
    offset = 0
    page_size = 1000

    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "f": "json"
        }
        resp = requests.get(base_url, params=params, timeout=15)
        data = resp.json()

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

def read_cases():
    cases = json.loads(Path("out/cases.json").read_text())

    coord_to_cases = defaultdict(list)
    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    FIELD_MAP = {
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
    total = len(cases)

    for case in cases:

        mapped_case = {
            FIELD_MAP[k]: v
            for k, v in case["attributes"].items()
            if k in FIELD_MAP
        }

        mapped_case["start_date"] = epoch_ms_to_iso(mapped_case["start_date"])
        mapped_case["end_date"] = epoch_ms_to_iso(mapped_case["end_date"])

        lon, lat = transformer.transform(case["geometry"]["x"], case["geometry"]["y"])
        mapped_case["lat"] = lat
        mapped_case["lon"] = lon

        precision = 5 # ~1 meter
        key = (round(lat, precision), round(lon, precision))

        coord_to_cases[key].append(mapped_case)

        attrs = case["attributes"]
        for field_key, val in attrs.items():
            if val not in (None, "", 0):  # adjust 0 exclusion if 0 is meaningful for that field
                populated[field_key] += 1

    all_cases = [case for cases_list in coord_to_cases.values() for case in cases_list]
    out_path = Path("out/cases_mapped.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_cases, indent=2))

    for key in FIELD_MAP:
        pct = populated.get(key, 0) / total * 100
        print(f"{key:25s} {populated.get(key, 0):5d}/{total} ({pct:.1f}%)")

    # Just to check dupes
    for coord, group in coord_to_cases.items():
        if len(group) > 1:
            print(coord)
            for c in group:
                print("  ", c["id"], c["location"])

    print(f"{len(cases)} cases, {len(coord_to_cases)} unique coords")
    print(f"{len(cases) - len(coord_to_cases)} duplicates thrown out")

def epoch_ms_to_iso(ms):
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()

if __name__ == "__main__":
    # download_cases()
    read_cases()
