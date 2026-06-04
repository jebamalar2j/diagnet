import gradio as gr
import json
import pandas as pd
import folium
import os

def load_results():
    if os.path.exists("results.json"):
        with open("results.json") as f:
            return json.load(f)
    return {"alerts":[],"predictions":[],"anomalies":[],"routing":{},"generated_at":"Not yet generated"}

def load_facs():
    return pd.read_csv("data/facilities.csv")

def load_naat():
    return pd.read_csv("data/naat_facilities.csv")

def make_map():
    facs  = load_facs()
    naat  = load_naat()
    R     = load_results()
    alert_ids    = {a["facility_id"] for a in R["alerts"]}
    critical_ids = {a["facility_id"] for a in R["alerts"] if a["risk_level"]=="CRITICAL"}
    pred_ids     = {p["facility_id"] for p in R.get("predictions",[])}
    naat_alert   = {n["id"] for _,n in naat.iterrows() if n["naat_stock"]<10}

    m = folium.Map(location=[facs["lat"].mean(), facs["lon"].mean()],
                   zoom_start=8, tiles="OpenStreetMap")

    # Testing facilities
    for _, f in facs.iterrows():
        if f["id"] in critical_ids:
            color, status = "red",    "🔴 CRITICAL — Out of stock"
        elif f["id"] in alert_ids:
            color, status = "orange", "🟠 HIGH — Stock very low"
        elif f["id"] in pred_ids:
            color, status = "beige",  "🟡 WARNING — Predicted stockout <14 days"
        else:
            color, status = "green",  "🟢 OK"
        rt = R["routing"].get(f["id"], {})
        folium.CircleMarker(
            location=[f["lat"], f["lon"]], radius=9,
            color=color, fill=True, fill_opacity=0.85,
            tooltip=f"{f['name']} ({f['district']})",
            popup=folium.Popup(
                f"<b>{f['name']}</b><br>District: {f['district']}<br>"
                f"Status: {status}<br>Tests 2025: {f['presumptive_tests']}<br>"
                f"Best referral: {rt.get('dest_name','N/A')} ({rt.get('dest_district','')})<br>"
                f"Best NAAT: {rt.get('naat_name','N/A')} — stock: {rt.get('naat_stock','N/A')}",
                max_width=280)
        ).add_to(m)

    # NAAT facilities — diamond shape via DivIcon
    for _, n in naat.iterrows():
        color = "darkred" if n["id"] in naat_alert else "darkblue"
        stock_status = "🔴 Low stock" if n["id"] in naat_alert else "🔵 Stocked"
        folium.Marker(
            location=[n["lat"], n["lon"]],
            tooltip=f"NAAT: {n['name']} ({n['district']})",
            popup=folium.Popup(
                f"<b>🔬 {n['name']}</b><br>District: {n['district']}<br>"
                f"NAAT Stock: {n['naat_stock']} cartridges<br>"
                f"Active TB cases: {n['current_cases']}<br>"
                f"Capacity: {n['monthly_capacity']}/month<br>"
                f"Stock status: {stock_status}",
                max_width=250),
            icon=folium.Icon(color=color, icon="plus-sign", prefix="glyphicon")
        ).add_to(m)

    # Legend
    legend = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
    background:white;padding:12px;border-radius:8px;font-size:12px;
    border:1px solid #ccc;line-height:1.8">
    <b>Testing Sites</b><br>
    🔴 Critical (out of stock)<br>
    🟠 High risk (stock &lt;15)<br>
    🟡 Predicted stockout &lt;14 days<br>
    🟢 OK<br><br>
    <b>NAAT Sites (+ marker)</b><br>
    🔵 Dark blue — stocked<br>
    🔴 Dark red — low stock
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))
    return m._repr_html_()

def show_alerts():
    R = load_results()
    if not R["alerts"]:
        return pd.DataFrame({"message":["No stockout alerts today"]})
    df = pd.DataFrame(R["alerts"]).rename(columns={
        "facility_name":"Facility","district":"District",
        "cartridges_left":"Cartridges Left",
        "presumptive_tests":"Tests 2025","risk_level":"Risk","date":"As of"})
    return df[["Facility","District","Cartridges Left","Tests 2025","Risk","As of"]]

def show_predictions():
    R = load_results()
    preds = R.get("predictions",[])
    if not preds:
        return pd.DataFrame({"message":["No facilities predicted to stock out in 14 days"]})
    df = pd.DataFrame(preds).rename(columns={
        "facility_name":"Facility","district":"District",
        "current_stock":"Stock Now","daily_consumption":"Daily Use",
        "days_to_stockout":"Days Left","predicted_date":"Stockout By","urgency":"Urgency"})
    return df[["Facility","District","Stock Now","Daily Use","Days Left","Stockout By","Urgency"]]

def show_routing():
    R = load_results()
    facs = load_facs()
    id_to_name     = dict(zip(facs["id"], facs["name"]))
    id_to_district = dict(zip(facs["id"], facs["district"]))
    if not R["routing"]:
        return pd.DataFrame({"message":["No routing data yet"]})
    rows = []
    for src, val in R["routing"].items():
        if "error" not in val:
            rows.append({
                "From Facility":  id_to_name.get(src, src),
                "District":       id_to_district.get(src,""),
                "Best Referral":  val.get("dest_name",""),
                "Referral Dist.": val.get("dest_district",""),
                "Travel Cost":    val.get("estimated_cost",""),
                "Best NAAT":      val.get("naat_name",""),
                "NAAT District":  val.get("naat_district",""),
                "NAAT Stock":     val.get("naat_stock",""),
                "NAAT Cost":      val.get("naat_cost",""),
            })
    return pd.DataFrame(rows)

def get_facility_referral(facility_name):
    if not facility_name:
        return "Select a facility above."
    R  = load_results()
    facs = load_facs()
    match = facs[facs["name"]==facility_name]
    if len(match)==0:
        return "Facility not found."
    fac_id = match.iloc[0]["id"]
    rt = R["routing"].get(fac_id,{})
    if "error" in rt:
        return f"Routing error: {rt['error']}"
    lines = [
        f"### {facility_name}",
        f"**District:** {match.iloc[0]['district']}",
        f"**Presumptive tests 2025:** {match.iloc[0]['presumptive_tests']}",
        "",
        "---",
        "#### 🏥 Best Testing Referral",
        f"**Facility:** {rt.get('dest_name','N/A')}",
        f"**District:** {rt.get('dest_district','N/A')}",
        f"**Travel cost score:** {rt.get('estimated_cost','N/A')}",
        "",
        "#### 🔬 Best NAAT Linkage",
        f"**NAAT Site:** {rt.get('naat_name','N/A')}",
        f"**District:** {rt.get('naat_district','N/A')}",
        f"**NAAT Stock remaining:** {rt.get('naat_stock','N/A')} cartridges",
        f"**Travel cost score:** {rt.get('naat_cost','N/A')}",
    ]
    return "\n".join(lines)

R    = load_results()
facs = load_facs()
facility_names = sorted(facs["name"].tolist())

with gr.Blocks(title="DiagNet TB Dashboard", theme=gr.themes.Soft()) as demo:

    gr.Markdown("# 🏥 DiagNet — TB Diagnostic Network Monitor")
    gr.Markdown("**Maharashtra · Uniamp & Quantiplus Device Sites · Satara, Pune, Sangli**")
    gr.Markdown(f"*Last updated: {R['generated_at']}*")

    with gr.Row():
        gr.Textbox(label="🔴 Stockout Alerts",      value=str(len(R["alerts"])),                interactive=False)
        gr.Textbox(label="📅 14-Day Predictions",    value=str(len(R.get("predictions",[]))),    interactive=False)
        gr.Textbox(label="🏥 Facilities Mapped",     value=str(len(R["routing"])),               interactive=False)
        gr.Textbox(label="🔬 NAAT Sites",            value="8",                                  interactive=False)

    with gr.Tab("Facility Map"):
        gr.Markdown("Click any marker for details · + markers = NAAT sites · See legend bottom-left")
        gr.HTML(make_map())

    with gr.Tab("Stockout Alerts"):
        gr.Markdown("Facilities currently at critically low or zero cartridge stock")
        gr.Dataframe(value=show_alerts())

    with gr.Tab("14-Day Prediction"):
        gr.Markdown("Facilities predicted to run out of stock within 14 days based on consumption rate")
        gr.Dataframe(value=show_predictions())

    with gr.Tab("Referral Lookup"):
        gr.Markdown("### Select a facility to see its best referral and NAAT linkage")
        with gr.Row():
            facility_dropdown = gr.Dropdown(
                choices=facility_names,
                label="Select Facility",
                interactive=True
            )
        referral_output = gr.Markdown("*Select a facility above to see referral details.*")
        facility_dropdown.change(
            fn=get_facility_referral,
            inputs=facility_dropdown,
            outputs=referral_output
        )

    with gr.Tab("Full Routing Table"):
        gr.Markdown("Optimal testing referral + NAAT linkage for every facility — weighted by travel + caseload")
        gr.Dataframe(value=show_routing())

demo.launch()
