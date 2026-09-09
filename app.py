import gradio as gr
import json
import pandas as pd
import folium
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import numpy as np

# ── Load data ─────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))

def load_results():
    p = os.path.join(BASE, "data/chennai_results.json")
    if os.path.exists(p):
        with open(p) as f: return json.load(f)
    return {"alerts":[],"predictions":[],"naat_alerts":[],"routing":{},"generated_at":"Not yet generated","city":"Chennai"}

def load_facs():    return pd.read_csv(os.path.join(BASE,"data/chennai_facilities.csv"))
def load_naat():    return pd.read_csv(os.path.join(BASE,"data/chennai_naat.csv"))
def load_stock():   return pd.read_csv(os.path.join(BASE,"data/chennai_stock.csv"))

# ── Tab 1: Facility Map ───────────────────────────────────────
def make_map():
    facs  = load_facs()
    naat  = load_naat()
    R     = load_results()
    alert_ids    = {a["facility_id"] for a in R["alerts"]}
    critical_ids = {a["facility_id"] for a in R["alerts"] if a["risk_level"]=="CRITICAL"}
    pred_ids     = {p["facility_id"] for p in R.get("predictions",[])}
    choked_ids   = {n["hub_name"] for n in R.get("naat_alerts",[])}

    m = folium.Map(location=[13.06,80.24], zoom_start=11, tiles="OpenStreetMap")

    # NAAT hubs
    for _, n in naat.iterrows():
        choked = n["name"] in choked_ids
        color  = "red" if n["naat_stock"]<10 else ("orange" if choked else "darkblue")
        status = "🔴 Stock critical" if n["naat_stock"]<10 else ("🟠 CHOKED (>240 tests/month)" if choked else "🔵 OK")
        folium.Marker(
            location=[n["lat"],n["lon"]],
            tooltip=f"NAAT: {n['name']}",
            popup=folium.Popup(
                f"<b>🔬 {n['name']}</b><br>TU: {n['tu']}<br>"
                f"Status: {status}<br>NAAT stock: {n['naat_stock']} cartridges<br>"
                f"Current utilization: {n['current_monthly']}/month<br>"
                f"Optimal capacity: {n['optimal_monthly']}/month<br>"
                f"Modules: {n['modules']} | Techs: {n['techs']}",
                max_width=260),
            icon=folium.Icon(color=color, icon="plus-sign", prefix="glyphicon")
        ).add_to(m)

    # Feeder sites
    for _, f in facs.iterrows():
        rt = R["routing"].get(f["id"],{})
        if f["id"] in critical_ids:
            color,status = "red","🔴 CRITICAL — Uniamp out of stock"
        elif f["id"] in alert_ids:
            color,status = "orange","🟠 HIGH — Uniamp stock low"
        elif f["id"] in pred_ids:
            color,status = "beige","🟡 WARNING — Stockout predicted <14 days"
        elif f["device_type"]=="Uniamp":
            color,status = "green","🟢 Uniamp deployed — OK"
        else:
            color,status = "gray","⚪ No device"

        folium.CircleMarker(
            location=[f["lat"],f["lon"]],
            radius=7, color=color, fill=True, fill_opacity=0.85,
            tooltip=f"{f['name']} ({f['tu']})",
            popup=folium.Popup(
                f"<b>{f['name']}</b><br>TU: {f['tu']}<br>"
                f"Device: {f['device_type']}<br>Status: {status}<br>"
                f"Population: {f['population']:,}<br>"
                f"Presumptive TB 2025: {f['presumptive_tests']:,}<br>"
                f"Best NAAT hub: {rt.get('naat_name','N/A')}<br>"
                f"NAAT stock: {rt.get('naat_stock','N/A')} cartridges",
                max_width=260)
        ).add_to(m)

    # Legend
    legend = """<div style='position:fixed;bottom:30px;left:30px;z-index:1000;
    background:white;padding:10px;border-radius:8px;font-size:12px;border:1px solid #ccc;line-height:1.8'>
    <b>Feeder sites (circles)</b><br>
    🔴 Critical — out of Uniamp stock<br>🟠 High — stock low<br>
    🟡 Predicted stockout &lt;14 days<br>🟢 Uniamp OK<br>⚪ No device<br><br>
    <b>NAAT hubs (+ markers)</b><br>
    🔴 Stock critical<br>🟠 Choked (&gt;240/month)<br>🔵 OK</div>"""
    m.get_root().html.add_child(folium.Element(legend))
    return m._repr_html_()

# ── Tab 2: Stockout Alerts ────────────────────────────────────
def show_alerts():
    R = load_results()
    if not R["alerts"]: return pd.DataFrame({"message":["No Uniamp stockout alerts today"]})
    df = pd.DataFrame(R["alerts"]).rename(columns={
        "facility_name":"Facility","tu":"TU","naat_hub":"NAAT Hub",
        "cartridges_left":"Cartridges Left","presumptive_tests":"Presumptive 2025",
        "risk_level":"Risk","date":"As of"})
    return df[["Facility","TU","NAAT Hub","Cartridges Left","Presumptive 2025","Risk","As of"]]

def show_naat_alerts():
    R = load_results()
    if not R.get("naat_alerts"): return pd.DataFrame({"message":["No choked NAAT hubs"]})
    df = pd.DataFrame(R["naat_alerts"]).rename(columns={
        "hub_name":"NAAT Hub","tu":"TU","current_monthly":"Current/Month",
        "optimal_monthly":"Optimal/Month","naat_stock":"NAAT Stock","modules":"Modules","risk":"Status"})
    return df[["NAAT Hub","TU","Current/Month","Optimal/Month","NAAT Stock","Modules","Status"]]

# ── Tab 3: 14-Day Prediction ──────────────────────────────────
def show_predictions():
    R = load_results()
    if not R.get("predictions"): return pd.DataFrame({"message":["No stockout predictions"]})
    df = pd.DataFrame(R["predictions"]).rename(columns={
        "facility_name":"Facility","tu":"TU","naat_hub":"NAAT Hub",
        "current_stock":"Stock Now","daily_consumption":"Daily Use",
        "days_to_stockout":"Days Left","predicted_date":"Stockout By","urgency":"Urgency"})
    return df[["Facility","TU","NAAT Hub","Stock Now","Daily Use","Days Left","Stockout By","Urgency"]]

def make_prediction_plot():
    R = load_results()
    preds = R.get("predictions",[])
    if not preds: return go.Figure()
    df = pd.DataFrame(preds).sort_values("days_to_stockout")
    colors = ["#f85149" if u=="CRITICAL" else "#d29922" for u in df["urgency"]]
    fig = go.Figure(go.Bar(
        x=df["facility_name"], y=df["days_to_stockout"],
        marker_color=colors,
        text=df["days_to_stockout"].astype(str)+" days",
        textposition="outside"
    ))
    fig.update_layout(
        title="Days until Uniamp stockout — sites at risk",
        height=350, paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color":"#cccccc"},
        xaxis={"tickangle":35,"tickfont":{"size":10},"gridcolor":"rgba(128,128,128,0.1)"},
        yaxis={"title":"Days left","gridcolor":"rgba(128,128,128,0.15)"},
        margin={"t":50,"b":120,"l":40,"r":20}
    )
    fig.add_hline(y=7, line_dash="dash", line_color="#f85149",
                  annotation_text="Critical threshold (7 days)")
    return fig

# ── Tab 4: Referral Lookup ────────────────────────────────────
def get_referral(facility_name):
    if not facility_name: return "*Select a facility above.*"
    R    = load_results()
    facs = load_facs()
    naat = load_naat()
    match = facs[facs["name"]==facility_name]
    if len(match)==0: return "Facility not found."
    fac = match.iloc[0]
    fac_id = fac["id"]
    rt = R["routing"].get(fac_id,{})
    if "error" in rt: return f"Routing error: {rt['error']}"
    hub = naat[naat["name"]==rt.get("naat_name","")]
    hub_row = hub.iloc[0] if len(hub)>0 else None
    lines = [
        f"### {facility_name}",
        f"**TU:** {fac['tu']} | **Device:** {fac['device_type']}",
        f"**Population:** {int(fac['population']):,} | **Presumptive TB 2025:** {int(fac['presumptive_tests']):,}",
        "",
        "---",
        "#### 🔬 Best NAAT Hub",
        f"**Hub:** {rt.get('naat_name','N/A')}",
        f"**TU:** {rt.get('naat_tu','N/A')}",
        f"**NAAT cartridges remaining:** {rt.get('naat_stock','N/A')}",
        f"**Routing cost score:** {rt.get('estimated_cost','N/A')}",
    ]
    if hub_row is not None:
        choked = hub_row["current_monthly"] > 240
        lines += [
            f"**Hub status:** {'🔴 CHOKED — consider alternate hub' if choked else '🟢 Within capacity'}",
            f"**Current utilization:** {hub_row['current_monthly']}/month of {hub_row['optimal_monthly']} optimal",
        ]
    if fac["device_type"] == "Uniamp":
        lines += ["","#### ✅ This site has Uniamp","Positive cases go to NAAT hub for DST. Negatives (92%) ruled out locally — no travel needed."]
    else:
        lines += ["","#### ⚠️ No device at this site","All presumptive TB cases currently travel to NAAT hub. Consider deploying Uniamp/QP to reduce hub load."]
    return "\n".join(lines)

# ── Tab 5: Routing Table ──────────────────────────────────────
def show_routing():
    R    = load_results()
    facs = load_facs()
    if not R["routing"]: return pd.DataFrame({"message":["No routing data"]})
    id_to_name = dict(zip(facs["id"],facs["name"]))
    id_to_tu   = dict(zip(facs["id"],facs["tu"]))
    id_to_dev  = dict(zip(facs["id"],facs["device_type"]))
    rows = []
    for src,val in R["routing"].items():
        if "error" not in val:
            rows.append({
                "Facility":       id_to_name.get(src,src),
                "TU":             id_to_tu.get(src,""),
                "Device":         id_to_dev.get(src,"None"),
                "Best NAAT Hub":  val.get("naat_name",""),
                "Hub TU":         val.get("naat_tu",""),
                "NAAT Stock":     val.get("naat_stock",""),
                "Routing Score":  val.get("estimated_cost",""),
            })
    return pd.DataFrame(rows)

# ── Tab 6: Impact Summary ─────────────────────────────────────
def make_impact_summary():
    R    = load_results()
    facs = load_facs()
    naat = load_naat()

    total_pop       = int(facs["population"].sum())
    uniamp_pop      = int(facs[facs["device_type"]=="Uniamp"]["population"].sum())
    no_device_pop   = total_pop - uniamp_pop
    total_presump   = int(facs["presumptive_tests"].sum())
    alerts          = len(R["alerts"])
    predictions     = len(R.get("predictions",[]))
    choked_hubs     = len(R.get("naat_alerts",[]))

    positivity      = 0.08
    naat_saved_mo   = int(total_presump * (1-positivity) / 12)
    travel_hrs_mo   = int(naat_saved_mo * 0.92 * 2.5)
    cost_before_yr  = int(total_presump * 1800)
    cost_after_yr   = int(total_presump * 450 + total_presump * positivity * 1200)
    cost_saving_yr  = cost_before_yr - cost_after_yr
    coverage_before = round(uniamp_pop / total_pop * 100, 1)
    coverage_after  = 100.0

    fig = make_subplots(rows=1, cols=3,
        subplot_titles=["NAAT load — before vs after","Annual cost (Rs Lakhs)","Population coverage (%)"])

    fig.add_trace(go.Bar(
        x=["Before Uniamp","After Uniamp"],
        y=[int(total_presump/12), int(total_presump*positivity/12)],
        marker_color=["#f85149","#3fb950"],
        text=[f"{int(total_presump/12):,}/mo",f"{int(total_presump*positivity/12):,}/mo"],
        textposition="outside", showlegend=False
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=["Before","After"],
        y=[round(cost_before_yr/100000,1), round(cost_after_yr/100000,1)],
        marker_color=["#f85149","#3fb950"],
        text=[f"Rs {round(cost_before_yr/100000,1)}L",f"Rs {round(cost_after_yr/100000,1)}L"],
        textposition="outside", showlegend=False
    ), row=1, col=2)

    fig.add_trace(go.Bar(
        x=["Before","After"],
        y=[coverage_before, coverage_after],
        marker_color=["#f85149","#3fb950"],
        text=[f"{coverage_before}%","100%"],
        textposition="outside", showlegend=False
    ), row=1, col=3)

    fig.update_layout(
        height=320, paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color":"#cccccc","size":11},
        margin={"t":50,"b":20,"l":30,"r":20},
        annotations=[dict(font=dict(color="#cccccc")) for _ in range(3)]
    )
    fig.update_xaxes(showgrid=False, tickfont=dict(color="#cccccc"))
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", tickfont=dict(color="#cccccc"))
    return fig

def make_impact_html():
    R    = load_results()
    facs = load_facs()
    total_pop     = int(facs["population"].sum())
    uniamp_pop    = int(facs[facs["device_type"]=="Uniamp"]["population"].sum())
    total_presump = int(facs["presumptive_tests"].sum())
    positivity    = 0.08
    naat_saved_mo = int(total_presump*(1-positivity)/12)
    travel_hrs_mo = int(naat_saved_mo*0.92*2.5)
    cost_saving_yr= int(total_presump*1800) - int(total_presump*450+total_presump*positivity*1200)
    paed_mo       = int(total_pop*0.003/12)
    eptb_mo       = int(total_pop*0.002/12)

    return f"""
<div style='font-family:Arial,sans-serif;padding:8px 0'>
<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:12px'>
  <div style='background:#0d2615;border:1px solid #3fb950;border-radius:8px;padding:12px;text-align:center'>
    <div style='font-size:22px;font-weight:700;color:#3fb950'>Rs {round(cost_saving_yr/100000,1)}L</div>
    <div style='font-size:11px;color:#56d364;margin-top:3px'>Annual cost saving</div>
    <div style='font-size:10px;color:#888;margin-top:2px'>QP screening vs all-NAAT</div>
  </div>
  <div style='background:#0d1f3d;border:1px solid #58a6ff;border-radius:8px;padding:12px;text-align:center'>
    <div style='font-size:22px;font-weight:700;color:#58a6ff'>{travel_hrs_mo:,}</div>
    <div style='font-size:11px;color:#79c0ff;margin-top:3px'>Patient travel hrs saved/month</div>
    <div style='font-size:10px;color:#888;margin-top:2px'>Negatives tested locally</div>
  </div>
  <div style='background:#2d1f00;border:1px solid #d29922;border-radius:8px;padding:12px;text-align:center'>
    <div style='font-size:22px;font-weight:700;color:#d29922'>{naat_saved_mo:,}</div>
    <div style='font-size:11px;color:#f0c040;margin-top:3px'>NAAT tests freed/month</div>
    <div style='font-size:10px;color:#888;margin-top:2px'>Available for priority cases</div>
  </div>
</div>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px'>
  <div style='background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px'>
    <p style='font-size:12px;font-weight:600;color:#ccc;margin-bottom:8px'>Diagnostic delay reduction</p>
    <table style='width:100%;font-size:11px;border-collapse:collapse'>
      <tr style='border-bottom:1px solid #21262d'><td style='padding:4px 0;color:#8b949e'>Asymptomatic/vulnerable (negative)</td><td style='color:#f85149;text-align:right'>2.5 days → </td><td style='color:#3fb950;text-align:right'>Same day</td></tr>
      <tr style='border-bottom:1px solid #21262d'><td style='padding:4px 0;color:#8b949e'>Symptomatic (positive → DST)</td><td style='color:#f85149;text-align:right'>2.5 days → </td><td style='color:#d29922;text-align:right'>1.5 days</td></tr>
      <tr style='border-bottom:1px solid #21262d'><td style='padding:4px 0;color:#ffa09e'>⚡ Paediatric TB (~{paed_mo}/month)</td><td colspan='2' style='color:#3fb950;text-align:right'>NAAT hub freed → faster slot</td></tr>
      <tr><td style='padding:4px 0;color:#ffa09e'>⚡ EPTB (~{eptb_mo}/month)</td><td colspan='2' style='color:#3fb950;text-align:right'>NAAT direct — no pre-screening delay</td></tr>
    </table>
  </div>
  <div style='background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px'>
    <p style='font-size:12px;font-weight:600;color:#ccc;margin-bottom:8px'>Deployment recommendation</p>
    <table style='width:100%;font-size:11px;border-collapse:collapse'>
      <tr style='border-bottom:1px solid #21262d'><td style='padding:4px 0;color:#8b949e'>Sites with Uniamp</td><td style='color:#58a6ff;text-align:right'>20 of 153</td></tr>
      <tr style='border-bottom:1px solid #21262d'><td style='padding:4px 0;color:#8b949e'>Sites needing device</td><td style='color:#d29922;text-align:right'>133 sites</td></tr>
      <tr style='border-bottom:1px solid #21262d'><td style='padding:4px 0;color:#8b949e'>Population covered (now)</td><td style='color:#f85149;text-align:right'>{round(uniamp_pop/total_pop*100,1)}%</td></tr>
      <tr style='border-bottom:1px solid #21262d'><td style='padding:4px 0;color:#8b949e'>Population covered (after full deploy)</td><td style='color:#3fb950;text-align:right'>100%</td></tr>
      <tr><td style='padding:4px 0;color:#8b949e'>Device cost payback period</td><td style='color:#3fb950;text-align:right'>~4 months (Uniamp)</td></tr>
    </table>
  </div>
</div>
<p style='font-size:10px;color:#555'>All figures based on 8% presumptive positivity, Rs 450 QP cartridge, Rs 1800 NAAT cartridge, 2.5 hrs avg travel. Replace with actual data for precise projections.</p>
</div>"""

# ── Load QP tool ──────────────────────────────────────────────
def load_qp_tool():
    return """
<div style='font-family:Arial,sans-serif;padding:24px;background:#161b22;border-radius:8px;border:1px solid #30363d;max-width:600px'>
  <p style='font-size:16px;font-weight:600;color:#fff;margin-bottom:10px'>QP / Uniamp NAAT Load Optimiser</p>
  <p style='font-size:12px;color:#8b949e;line-height:1.8;margin-bottom:14px'>
    Interactive tool with:<br>
    &bull; Chennai map &mdash; 18 NAAT hubs + 153 feeder sites<br>
    &bull; Vulnerability-based demand calculator (44 NTEP categories)<br>
    &bull; Auto device recommendation &mdash; Uniamp vs QP-14 vs QP-24<br>
    &bull; Scenario 1: NAAT load, gap, utilization, cost benefit<br>
    &bull; Scenario 2: DR-TB stratified detection vs upfront NAAT
  </p>
  <a href='https://jebamalar2j.github.io/disha/qp_tool.html' target='_blank'
     style='display:inline-block;background:#1f6feb;color:#fff;padding:10px 20px;
            border-radius:6px;text-decoration:none;font-size:13px;font-weight:600'>
    Launch QP/Uniamp Optimiser &#8599;
  </a>
  <p style='font-size:10px;color:#555;margin-top:10px'>Opens in a new tab &mdash; best on desktop Chrome or Firefox</p>
</div>"""

# ── Build Gradio app ──────────────────────────────────────────
R    = load_results()
facs = load_facs()
facility_names = sorted(facs["name"].tolist())

with gr.Blocks(title="DISHA — Chennai TB Diagnostic Network") as demo:

    gr.Markdown("# 🏥 DISHA — Diagnostic Intelligence for Systematic Health Alerts")
    gr.Markdown("**Chennai · 18 NAAT hubs · 153 peripheral sites · Tamil Nadu NTEP**")
    gr.Markdown(f"*Last updated: {R['generated_at']}*")

    with gr.Row():
        gr.Textbox(label="🔴 Uniamp Stockout Alerts",  value=str(len(R["alerts"])),                 interactive=False)
        gr.Textbox(label="📅 14-Day Predictions",       value=str(len(R.get("predictions",[]))),     interactive=False)
        gr.Textbox(label="🔬 Choked NAAT Hubs",         value=str(len(R.get("naat_alerts",[]))),     interactive=False)
        gr.Textbox(label="🏥 Feeder Sites",              value="153",                                 interactive=False)
        gr.Textbox(label="🗺 NAAT Hubs",                 value="18",                                  interactive=False)

    with gr.Tab("Facility Map"):
        gr.Markdown("**Circles** = feeder sites · **+ markers** = NAAT hubs · Click any pin for details")
        gr.HTML(make_map())

    with gr.Tab("Stockout Alerts"):
        gr.Markdown("### Uniamp cartridge stockout alerts — feeder sites")
        gr.Dataframe(value=show_alerts(), label="Uniamp sites — critical/high stock alerts")
        gr.Markdown("### Choked NAAT hubs (>240 tests/month)")
        gr.Dataframe(value=show_naat_alerts(), label="NAAT hubs exceeding capacity")

    with gr.Tab("14-Day Prediction"):
        gr.Markdown("### Uniamp sites predicted to stock out within 14 days")
        gr.Plot(value=make_prediction_plot())
        gr.Dataframe(value=show_predictions())

    with gr.Tab("Referral Lookup"):
        gr.Markdown("### Select a peripheral site — see best NAAT hub referral")
        facility_dropdown = gr.Dropdown(choices=facility_names, label="Select facility", interactive=True)
        referral_output   = gr.Markdown("*Select a facility above.*")
        facility_dropdown.change(fn=get_referral, inputs=facility_dropdown, outputs=referral_output)

    with gr.Tab("Routing Table"):
        gr.Markdown("### Optimal NAAT hub routing for all 153 feeder sites")
        gr.Markdown("Weighted by travel distance + hub load + NAAT stock penalty")
        gr.Dataframe(value=show_routing())

    with gr.Tab("Impact Summary"):
        gr.Markdown("### QuantiPlus/Uniamp deployment impact — Chennai")
        gr.Plot(value=make_impact_summary())
        gr.HTML(value=make_impact_html())

    with gr.Tab("QP/Uniamp Optimiser"):
        gr.Markdown("### NAAT load optimiser — select hub, adjust prevalence, get device recommendations")
        gr.HTML(value=load_qp_tool())

demo.launch()
