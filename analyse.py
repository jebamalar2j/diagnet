import pandas as pd
import networkx as nx
import json
import os
import numpy as np

print("Running analysis...")

facs  = pd.read_csv("data/facilities.csv")
stock = pd.read_csv("data/stock.csv")
naat  = pd.read_csv("data/naat_facilities.csv")

# ── 1. Stockout alerts ────────────────────────────────────────
stock["date"] = pd.to_datetime(stock["date"])
stock = stock.sort_values(["facility_id", "date"])
stock["rolling_avg"] = (
    stock.groupby("facility_id")["cartridges"]
         .transform(lambda x: x.rolling(14, min_periods=3).mean())
)
latest = stock.sort_values("date").groupby("facility_id").last().reset_index()
latest["alert"] = (latest["cartridges"] < 15)

alerts = []
for _, row in latest[latest["alert"] == True].iterrows():
    fac = facs[facs["id"] == row["facility_id"]]
    if len(fac) == 0:
        continue
    fac = fac.iloc[0]
    alerts.append({
        "facility_id":      row["facility_id"],
        "facility_name":    fac["name"],
        "district":         fac["district"],
        "cartridges_left":  int(row["cartridges"]),
        "presumptive_tests":int(fac["presumptive_tests"]),
        "risk_level":       "CRITICAL" if row["cartridges"] == 0 else "HIGH",
        "date":             str(row["date"].date())
    })

alerts = sorted(alerts, key=lambda x: x["cartridges_left"])
print(f"Found {len(alerts)} stockout alerts.")

# ── 2. 14-day stockout prediction ─────────────────────────────
predictions = []
for fac_id, grp in stock.groupby("facility_id"):
    grp = grp.sort_values("date")
    if len(grp) < 7:
        continue
    recent = grp.tail(14)
    daily_consumption = max(0.1, (recent["cartridges"].iloc[0] - recent["cartridges"].iloc[-1]) / len(recent))
    current_stock = grp["cartridges"].iloc[-1]
    days_to_stockout = current_stock / daily_consumption if daily_consumption > 0 else 999
    fac = facs[facs["id"] == fac_id]
    if len(fac) == 0:
        continue
    fac = fac.iloc[0]
    if days_to_stockout <= 14:
        predictions.append({
            "facility_id":       fac_id,
            "facility_name":     fac["name"],
            "district":          fac["district"],
            "current_stock":     int(current_stock),
            "daily_consumption": round(daily_consumption, 1),
            "days_to_stockout":  int(days_to_stockout),
            "predicted_date":    str((pd.Timestamp.today() + pd.Timedelta(days=int(days_to_stockout))).date()),
            "urgency":           "CRITICAL" if days_to_stockout <= 3 else "WARNING"
        })

predictions = sorted(predictions, key=lambda x: x["days_to_stockout"])
print(f"Found {len(predictions)} facilities predicted to stock out within 14 days.")

# ── 3. Anomaly flags ──────────────────────────────────────────
anomalies = []
if os.path.exists("data/tests.csv"):
    tests = pd.read_csv("data/tests.csv")
    for episode_id, ep in tests.groupby("episode_id"):
        seq = list(ep.sort_values("date")["test_code"])
        if seq.count("GeneXpert") > 1:
            anomalies.append({"episode": str(episode_id), "facility": str(ep["facility_id"].iloc[0]), "reason": "Duplicate GeneXpert before result"})
        if "DST" in seq and "Culture" not in seq:
            anomalies.append({"episode": str(episode_id), "facility": str(ep["facility_id"].iloc[0]), "reason": "DST ordered without Culture confirmation"})
print(f"Found {len(anomalies)} anomalies.")

# ── 4. Routing — testing referral + NAAT linkage ──────────────
all_facs = pd.concat([
    facs.assign(type="Testing"),
    naat.rename(columns={"naat_stock": "cartridges_left"}).assign(type="NAAT")
], ignore_index=True)

G = nx.DiGraph()
for _, f in all_facs.iterrows():
    G.add_node(f["id"], name=f["name"], lat=f["lat"], lon=f["lon"], type=f["type"])

for _, src in facs.iterrows():
    # Testing → Testing routing
    for _, dst in facs.iterrows():
        if src["id"] == dst["id"]:
            continue
        travel = (abs(src["lat"]-dst["lat"]) + abs(src["lon"]-dst["lon"])) * 111 * 2
        penalty = (dst.get("current_cases",0) / max(dst["monthly_capacity"],1)) * 30
        G.add_edge(src["id"], dst["id"], weight=round(travel+penalty,2))
    # Testing → NAAT routing
    for _, dst in naat.iterrows():
        travel = (abs(src["lat"]-dst["lat"]) + abs(src["lon"]-dst["lon"])) * 111 * 2
        naat_penalty = (dst["current_cases"] / max(dst["monthly_capacity"],1)) * 30
        naat_stock_penalty = 50 if dst["naat_stock"] < 10 else 0
        G.add_edge(src["id"], dst["id"], weight=round(travel+naat_penalty+naat_stock_penalty,2))

routing = {}
for _, src in facs.iterrows():
    try:
        lengths = nx.single_source_dijkstra_path_length(G, src["id"], weight="weight")
        # Best testing referral
        test_options = {k:v for k,v in lengths.items() if k != src["id"] and k.startswith("F")}
        best_test = min(test_options.items(), key=lambda x: x[1])
        dest_test = facs[facs["id"]==best_test[0]]
        # Best NAAT linkage
        naat_options = {k:v for k,v in lengths.items() if k.startswith("N")}
        best_naat = min(naat_options.items(), key=lambda x: x[1])
        dest_naat = naat[naat["id"]==best_naat[0]]
        routing[src["id"]] = {
            "best_dest":         best_test[0],
            "dest_name":         dest_test["name"].values[0] if len(dest_test)>0 else best_test[0],
            "dest_district":     dest_test["district"].values[0] if len(dest_test)>0 else "",
            "estimated_cost":    round(best_test[1],1),
            "best_naat":         best_naat[0],
            "naat_name":         dest_naat["name"].values[0] if len(dest_naat)>0 else best_naat[0],
            "naat_district":     dest_naat["district"].values[0] if len(dest_naat)>0 else "",
            "naat_cost":         round(best_naat[1],1),
            "naat_stock":        int(dest_naat["naat_stock"].values[0]) if len(dest_naat)>0 else 0,
        }
    except Exception as e:
        routing[src["id"]] = {"error": str(e)}

print("Routing complete.")

# ── 5. Save ───────────────────────────────────────────────────
results = {
    "generated_at": str(pd.Timestamp.today()),
    "alerts":       alerts,
    "predictions":  predictions,
    "anomalies":    anomalies,
    "routing":      routing
}
with open("results.json","w") as f:
    json.dump(results, f, indent=2)

print(f"Results saved: {len(alerts)} alerts, {len(predictions)} predictions, {len(routing)} routes.")
