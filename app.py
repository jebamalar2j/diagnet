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

def load_facs():
    return pd.read_csv("data/facilities.csv")

def make_map():
    facs = load_facs()
    R = load_results()
    alert_ids = {a["facility_id"] for a in R["alerts"]}
    critical_ids = {a["facility_id"] for a in R["alerts"] if a["risk_level"] == "CRITICAL"}

    center_lat = facs["lat"].mean()
    center_lon = facs["lon"].mean()

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=8,
        tiles="OpenStreetMap"
    )

    for _, f in facs.iterrows():
        if f["id"] in critical_ids:
            color = "red"
            status = "🔴 CRITICAL — Out of stock"
        elif f["id"] in alert_ids:
            color = "orange"
            status = "🟠 HIGH — Stock very low"
        else:
            color = "green"
            status = "🟢 OK"

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
                f"District: {f['district']}<br>"
                f"TU: {f.get('tu', '')}<br>"
                f"Status: {status}<br>"
                f"Presumptive tests 2025: {f['presumptive_tests']}<br>"
                f"Best referral: {best}",
                max_width=250
            ),
            tooltip=f"{f['name']} — {status}"
        ).add_to(m)

    return m._repr_html_()

def show_alerts():
    R = load_results()
    if not R["alerts"]:
        return pd.DataFrame({"message": ["No stockout alerts today"]})
    df = pd.DataFrame(R["alerts"])
    df = df.rename(columns={
        "facility_name":     "Facility",
        "district":          "District",
        "cartridges_left":   "Cartridges Left",
        "presumptive_tests": "Tests in 2025",
        "risk_level":        "Risk",
        "date":              "As of"
    })
    return df[["Facility","District","Cartridges Left","Tests in 2025","Risk","As of"]]

def show_routing():
    R = load_results()
    facs = load_facs()
    id_to_name = dict(zip(facs["id"], facs["name"]))
    id_to_district = dict(zip(facs["id"], facs["district"]))
    if not R["routing"]:
        return pd.DataFrame({"message": ["No routing data yet"]})
    rows = []
    for src, val in R["routing"].items():
        if "error" not in val:
            rows.append({
                "From Facility":   id_to_name.get(src, src),
                "From District":   id_to_district.get(src, ""),
                "Best Referral":   val.get("dest_name", ""),
                "Dest District":   val.get("dest_district", ""),
                "Est. Travel Cost":val.get("estimated_cost", "")
            })
    return pd.DataFrame(rows)

R = load_results()

with gr.Blocks(title="DiagNet TB Dashboard", theme=gr.themes.Soft()) as demo:

    gr.Markdown("# 🏥 DiagNet — TB Diagnostic Network Monitor")
    gr.Markdown("**Maharashtra · Uniamp & Quantiplus Device Sites**")
    gr.Markdown(f"*Last updated: {R['generated_at']}*")

    with gr.Row():
        gr.Textbox(label="🔴 Stockout Alerts",   value=str(len(R["alerts"])),    interactive=False)
        gr.Textbox(label="⚠️ Anomalies Flagged", value=str(len(R["anomalies"])), interactive=False)
        gr.Textbox(label="🏥 Facilities Mapped",  value=str(len(R["routing"])),   interactive=False)

    with gr.Tab("Facility Map"):
        gr.Markdown("🔴 Critical (out of stock) · 🟠 High risk · 🟢 OK — Click any marker for details")
        gr.HTML(make_map())

    with gr.Tab("Stockout Alerts"):
        gr.Dataframe(value=show_alerts())

    with gr.Tab("Anomaly Flags"):
        gr.Markdown("No test sequence data loaded yet. Connect to NIKSHAY for live anomaly detection.")

    with gr.Tab("Referral Routing"):
        gr.Markdown("Optimal referral destination per facility — weighted by travel time + caseload penalty")
        gr.Dataframe(value=show_routing())

demo.launch()
