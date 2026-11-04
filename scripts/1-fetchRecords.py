
import json
import time
import requests
import pandas as pd
from html.parser import HTMLParser

URL = (
    "https://data.kreston.vn/wp-admin/admin-ajax.php"
    "?action=get_wdtable&table_id=1"
)
REFERER = "https://data.kreston.vn/tra-cuu-bao-cao-viet-nam/"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": REFERER,
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
})

column_names = [
    "id",
    "id_report",
    "ky_bao_cao",
    "cong_ty",
    "mo_ta",
    "loai_bctc",
    "cong_ty_kiem_toan",
    "y_kien_kiem_toan",
    "link_gdrive",
    "link_vnreport",
]

def build_payload(start, length, draw):
    payload = {
        "draw": str(draw),
        "start": str(start),
        "length": str(length),
        "search[value]": "",
        "search[regex]": "false",
        "wdtNonce": "1e1ea73a36",
        "sRangeSeparator": "|",
    }

    for i, name in enumerate(column_names):
        payload.update({
            f"columns[{i}][data]": str(i),
            f"columns[{i}][name]": name,
            f"columns[{i}][searchable]": "true",
            f"columns[{i}][orderable]": "false",
            f"columns[{i}][search][value]": "",
            f"columns[{i}][search][regex]": "false",
        })

    payload["columns[2][search][value]"] = (
        "2015|2016|2017|2018|2019|2020|"
        "2021|2022|2023|2024|2025"
    )
    payload["columns[2][search][regex]"] = "true"

    return payload

def fetch_page(start, length, draw):
    response = session.post(
        URL,
        data=build_payload(start, length, draw),
        timeout=60,
    )
    response.raise_for_status()

    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(
            f"Expected JSON, got: {response.text[:500]}"
        )

    if not isinstance(result, dict) or "data" not in result:
        raise RuntimeError(
            f"Unexpected response: {json.dumps(result)[:1000]}"
        )

    return result

class HrefParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None

    def handle_starttag(self, tag, attrs):
        if tag == "a" and self.href is None:
            self.href = dict(attrs).get("href")

def extract_href(value):
    if not value:
        return ""

    parser = HrefParser()
    parser.feed(str(value))
    return parser.href or ""


all_rows = []
page_size = 1000
start = 0
draw = 1
total = None

while True:
    result = fetch_page(start, page_size, draw)
    rows = result.get("data", [])

    if total is None:
        total = result.get("recordsFiltered")
        print("Filtered records:", total)
        print("Total records:", result.get("recordsTotal"))

    if not rows:
        break

    all_rows.extend(rows)
    start += len(rows)
    draw += 1

    print(f"Retrieved {len(all_rows)} records")

    if total is not None and len(all_rows) >= int(total):
        break

    time.sleep(0.3)

if all_rows and isinstance(all_rows[0], list):
    df = pd.DataFrame(
        all_rows,
        columns=column_names[:len(all_rows[0])]
    )
else:
    df = pd.DataFrame(all_rows)

for col in ["link_gdrive", "link_vnreport"]:
    if col in df.columns:
        df[col] = df[col].apply(extract_href)

df["id"] = (
    df["id"]
    .astype(str)
    .str.replace(".", "", regex=False)
)

df.to_csv("kreston_records.csv", index=False, encoding="utf-8-sig")

print(f"Saved {len(all_rows)} records.")
