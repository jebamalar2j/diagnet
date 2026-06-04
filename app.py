import gradio as gr
import json
import pandas as pd
import folium
import os

def load_results():
    if os.path.exists("results.json"):
        with open("results.json") as f:
            return json.load(f)
    return {"alerts": [], "anomalies": [], "routing": {}, "generated_at": "Not yet generated"}

def make_map():
    facs = pd.read_csv("data/facilities.csv")
    R = load_results()
    alert_ids = {a["facility_id"] for a in R["alerts"]}

    m = folium.Map(
        location=[facs["lat"].mean(), facs["lon"].mean()],
        zoom_start=10,
        tiles="OpenStreetMap"
    )

    for _, f in facs.iterrows():
        is_alert = f["id"] in alert_ids
        color = "red" if is_alert else "green"
        status = "⚠ Stockout risk" if is_alert else "✓ OK"
        routing = R["routing"].get(f["id"], {})
        best = routing.get("dest_name", "N/A")
        folium.CircleMarker(
            location=[f["lat"], f["lon"]],
            radius=10,
            color=color,
            fill=True,
            fill_opacity=0.8,
            popup=folium.Popup(
                f"<b>{f['name']}</b><br>"
                f"Status: {status}<br>"
                f"Cartridges: {f.get('current_cases','N/A')}<br>"
                f"Best referral: {best}",
                max_width=200
            )
        ).add_to(m)

    map_path = "map.html"
    m.save(map_path)
    return map_path

def show_alerts():
    R = load_results()
    if not R["alerts"]:
        return pd.DataFrame({"message": ["No stockout alerts today"]})
    return pd.DataFrame(R["alerts"])

def show_anomalies():
    R = load_results()
    if not R["anomalies"]:
        return pd.DataFrame({"message": ["No anomalies detected"]})
    return pd.DataFrame(R["anomalies"])

def show_routing():
    R = load_results()
    if not R["routing"]:
        return pd.DataFrame({"message": ["No routing data yet"]})
    rows = []
    for src, val in R["routing"].items():
        if "error" not in val:
            rows.append({
                "from_facility": src,
                "best_referral": val.get("dest_name", ""),
                "estimated_cost": val.get("estimated_cost", "")
            })
    return pd.DataFrame(rows)

# ── Build dashboard ───────────────────────────────────────────
with gr.Blocks(title="DiagNet TB Dashboard", theme=gr.themes.Soft()) as demo:

    gr.Markdown("# DiagNet — TB Diagnostic Network Monitor")
    R = load_results()
    gr.Markdown(f"*Last updated: {R['generated_at']}*")

    with gr.Row():
        gr.Metric(label="Stockout Alerts",  value=len(R["alerts"]))
        gr.Metric(label="Anomalies Flagged", value=len(R["anomalies"]))
        gr.Metric(label="Facilities Mapped", value=len(R["routing"]))

    with gr.Tab("Facility Map"):
        map_path = make_map()
        gr.HTML(open(map_path).read())

    with gr.Tab("Stockout Alerts"):
        gr.Dataframe(value=show_alerts())

    with gr.Tab("Anomaly Flags"):
        gr.Dataframe(value=show_anomalies())

    with gr.Tab("Referral Routing"):
        gr.Dataframe(value=show_routing())

demo.launch()
