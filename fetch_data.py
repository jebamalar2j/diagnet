import os
import requests
import pandas as pd

# Using DHIS2 demo server for now
# Replace with real server URL and credentials when you have MOU
BASE = os.environ.get("DHIS2_URL", "https://play.dhis2.org/40")
AUTH = (
    os.environ.get("DHIS2_USER", "admin"),
    os.environ.get("DHIS2_PASS", "district")
)

print(f"Connecting to {BASE}...")

# Fetch facility list
facilities = requests.get(
    f"{BASE}/api/organisationUnits.json",
    params={
        "level": 4,
        "fields": "id,name,coordinates",
        "paging": "false"
    },
    auth=AUTH
)

if facilities.status_code == 200:
    data = facilities.json()
    units = data.get("organisationUnits", [])
    rows = []
    for u in units:
        coords = u.get("coordinates", "")
        lat, lon = 0.0, 0.0
        if coords:
            try:
                import json
                c = json.loads(coords)
                lon, lat = c[0], c[1]
            except:
                pass
        rows.append({
            "id": u["id"],
            "name": u["name"],
            "lat": lat,
            "lon": lon,
            "monthly_capacity": 50,
            "current_cases": 0
        })
    df = pd.DataFrame(rows)
    df.to_csv("data/facilities.csv", index=False)
    print(f"Saved {len(df)} facilities to data/facilities.csv")
else:
    print(f"Failed to connect: {facilities.status_code}")
    print("Creating sample facilities for testing...")
    sample = pd.DataFrame([
        {"id": "F001", "name": "District Hospital A", "lat": 13.08, "lon": 80.27, "monthly_capacity": 120, "current_cases": 45},
        {"id": "F002", "name": "CHC Block B",         "lat": 13.12, "lon": 80.20, "monthly_capacity": 60,  "current_cases": 55},
        {"id": "F003", "name": "PHC Village C",       "lat": 13.05, "lon": 80.32, "monthly_capacity": 30,  "current_cases": 8},
        {"id": "F004", "name": "CHC Block D",         "lat": 13.18, "lon": 80.15, "monthly_capacity": 60,  "current_cases": 20},
        {"id": "F005", "name": "PHC Village E",       "lat": 12.98, "lon": 80.24, "monthly_capacity": 30,  "current_cases": 5},
    ])
    sample.to_csv("data/facilities.csv", index=False)
    print("Saved sample facilities.")

# Fetch stock data
stock = requests.get(
    f"{BASE}/api/dataValueSets.json",
    params={
        "dataSet": "BfMAe6Itzgt",
        "period": "LAST_12_WEEKS",
        "orgUnit": "ImspTQPwCqd",
        "children": "true"
    },
    auth=AUTH
)

if stock.status_code == 200:
    values = stock.json().get("dataValues", [])
    if values:
        df_stock = pd.DataFrame(values)
        df_stock.to_csv("data/stock.csv", index=False)
        print(f"Saved {len(df_stock)} stock records.")
    else:
        print("No stock data returned, creating sample...")
        _create_sample_stock()
else:
    print("Stock fetch failed, creating sample data...")
    import numpy as np
    dates = pd.date_range(end=pd.Timestamp.today(), periods=84).tolist()
    rows = []
    for fid in ["F001","F002","F003","F004","F005"]:
        stock_level = 100
        for d in dates:
            consumption = max(0, int(np.random.normal(5, 2)))
            stock_level = max(0, stock_level - consumption)
            rows.append({
                "facility_id": fid,
                "date": d.strftime("%Y-%m-%d"),
                "cartridges": stock_level
            })
    pd.DataFrame(rows).to_csv("data/stock.csv", index=False)
    print("Saved sample stock data.")

print("fetch_data.py complete.")
