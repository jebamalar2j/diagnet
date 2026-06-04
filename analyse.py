import pandas as pd
import networkx as nx
import json
import os

print("Running analysis...")

# ── 1. Load data ──────────────────────────────────────────────
facs  = pd.read_csv("data/facilities.csv")
stock = pd.read_csv("data/stock.csv")

# ── 2. Stockout alerts ────────────────────────────────────────
stock["date"] = pd.to_datetime(stock["date"])
stock = stock.sort_values(["facility_id", "date"])
stock["rolling_avg"] = (
    stock.groupby("facility_id")["cartridges"]
         .transform(lambda x: x.rolling(14, min_periods=3).mean())
)
stock["alert"] = stock["cartridges"] < 2 * (stock["rolling_avg"] / 14)

latest = stock.sort_values("date").groupby("facility_id").last().reset_index()
alerts = []
for _, row in latest[latest["alert"] == True].iterrows():
    fac_name = facs[facs["id"] == row["facility_id"]]["name"].values
    alerts.append({
        "facility_id":   row["facility_id"],
        "facility_name": fac_name[0] if len(fac_name) > 0 else row["facility_id"],
        "cartridges":    int(row["cartridges"]),
        "rolling_avg":   round(float(row["rolling_avg"]), 1),
        "date":          str(row["date"].date())
    })

print(f"Found {len(alerts)} stockout alerts.")

# ── 3. Anomaly flags (rule-based) ─────────────────────────────
anomalies = []
if os.path.exists("data/tests.csv"):
    tests = pd.read_csv("data/tests.csv")
    for episode_id, ep in tests.groupby("episode_id"):
        seq = list(ep.sort_values("date")["test_code"])
        if seq.count("GeneXpert") > 1:
            anomalies.append({
                "episode":  str(episode_id),
                "facility": str(ep["facility_id"].iloc[0]),
                "reason":   "Duplicate GeneXpert before result"
            })
        if "DST" in seq and "Culture" not in seq:
            anomalies.append({
                "episode":  str(episode_id),
                "facility": str(ep["facility_id"].iloc[0]),
                "reason":   "DST ordered without Culture confirmation"
            })
else:
    print("No tests.csv found, skipping anomaly detection.")

print(f"Found {len(anomalies)} anomalies.")

# ── 4. Routing with caseload penalty ─────────────────────────
G = nx.DiGraph()
for _, f in facs.iterrows():
    G.add_node(f["id"], name=f["name"], lat=f["lat"], lon=f["lon"])

for _, src in facs.iterrows():
    for _, dst in facs.iterrows():
        if src["id"] == dst["id"]:
            continue
        travel_time = (
            abs(src["lat"] - dst["lat"]) +
            abs(src["lon"] - dst["lon"])
        ) * 111 * 2
        caseload_penalty = (
            dst.get("current_cases", 0) /
            max(dst["monthly_capacity"], 1)
        ) * 30
        G.add_edge(src["id"], dst["id"],
                   weight=round(travel_time + caseload_penalty, 2))

routing = {}
for src in facs["id"]:
    try:
        lengths = nx.single_source_dijkstra_path_length(G, src, weight="weight")
        best = min(
            ((cost, nid) for nid, cost in lengths.items() if nid != src)
        )
        dest_name = facs[facs["id"] == best[1]]["name"].values
        routing[src] = {
            "best_dest":      best[1],
            "dest_name":      dest_name[0] if len(dest_name) > 0 else best[1],
            "estimated_cost": round(best[0], 1)
        }
    except Exception as e:
        routing[src] = {"error": str(e)}

print("Routing complete.")

# ── 5. Save results ───────────────────────────────────────────
results = {
    "generated_at": str(pd.Timestamp.today()),
    "alerts":       alerts,
    "anomalies":    anomalies,
    "routing":      routing
}
with open("results.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"Results saved: {len(alerts)} alerts, {len(anomalies)} anomalies, {len(routing)} routes.")
