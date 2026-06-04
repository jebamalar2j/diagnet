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

import plotly.graph_objects as go
from plotly.subplots import make_subplots

def make_prevalence_html():
    sites = [
        {"name":"Lakshmipuram","presumptive":2200,"positives":176},
        {"name":"Neelangkarai","presumptive":1773,"positives":142},
        {"name":"Taramani","presumptive":1762,"positives":141},
        {"name":"Sasthri Nagar","presumptive":1740,"positives":139},
        {"name":"Korrukupet","presumptive":1646,"positives":132},
        {"name":"BRN Garden","presumptive":1681,"positives":134},
        {"name":"Samy Nagar","presumptive":1316,"positives":105},
        {"name":"Virugambakkam","presumptive":1354,"positives":108},
        {"name":"Sharma Nagar","presumptive":1484,"positives":119},
        {"name":"Kolathur","presumptive":1436,"positives":115},
    ]
    rows = ""
    for s in sites:
        neg = s["presumptive"] - s["positives"]
        pct = round(s["positives"]/s["presumptive"]*100,1)
        neg_pct = round(neg/s["presumptive"]*100,1)
        rows += f"""
        <tr>
          <td style='padding:6px 8px;font-size:12px;color:#ffffff'>{s["name"]}</td>
          <td style='padding:6px 8px;font-size:12px;text-align:right'>{s["presumptive"]:,}</td>
          <td style='padding:6px 8px'>
            <div style='display:flex;height:16px;border-radius:4px;overflow:hidden;min-width:120px'>
              <div style='width:{neg_pct}%;background:#5DCAA5;' title='Negative: {neg}'></div>
              <div style='width:{pct}%;background:#E24B4A;' title='Positive: {s["positives"]}'></div>
            </div>
          </td>
          <td style='padding:6px 8px;font-size:12px;color:#ffb3b3;text-align:right'>{s["positives"]} ({pct}%)</td>
          <td style='padding:6px 8px;font-size:12px;color:#ffffff;text-align:right'>{neg} go home</td>
        </tr>"""

    return f"""
<div style='font-family:sans-serif;padding:12px 0'>
  <p style='font-size:13px;font-weight:500;margin:0 0 4px'>Peripheral UPHC — why Uniamp is sufficient here</p>
  <p style='font-size:11px;color:#cccccc;margin:0 0 12px'>At 8% positivity, 92% of presumptive cases are MTB negative — they do not need NAAT. Uniamp correctly rules them out at the peripheral site, saving a needless journey. Only the red band (positives) travels to NAAT for drug sensitivity testing.</p>
  <table style='width:100%;border-collapse:collapse'>
    <thead>
      <tr style='border-bottom:1px solid #e0e0e0'>
        <th style='padding:6px 8px;font-size:11px;color:#cccccc;text-align:left;font-weight:500'>Site</th>
        <th style='padding:6px 8px;font-size:11px;color:#cccccc;text-align:right;font-weight:500'>Presumptive</th>
        <th style='padding:6px 8px;font-size:11px;color:#cccccc;font-weight:500'>Split (green=neg, red=pos)</th>
        <th style='padding:6px 8px;font-size:11px;color:#ffb3b3;text-align:right;font-weight:500'>To NAAT</th>
        <th style='padding:6px 8px;font-size:11px;color:#ffffff;text-align:right;font-weight:500'>Saved travel</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <div style='margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:12px'>
    <div style='background:#6e0c2e;border-radius:8px;padding:12px;border-left:3px solid #F4C0D1'>
      <p style='font-size:12px;font-weight:500;color:#ffffff;margin:0 0 4px'>Tertiary setting — different logic</p>
      <p style='font-size:11px;color:#ffffff;margin:0'>At ITM/MMC Thoracic, prevalence among referred patients is 40-60%. Uniamp-first means most patients would need a second NAAT test anyway. Diagnostic delay = treatment delay. Direct NAAT is the right first-line test here.</p>
    </div>
    <div style='background:#0a4a32;border-radius:8px;padding:12px;border-left:3px solid #5DCAA5'>
      <p style='font-size:12px;font-weight:500;color:#ffffff;margin:0 0 4px'>Peripheral setting — Uniamp justified</p>
      <p style='font-size:11px;color:#ffffff;margin:0'>At peripheral UPHCs, 8% positivity means NAAT capacity is wasted on 92% of tests that return negative. Uniamp screens cheaply and quickly. Only confirmed positives proceed to NAAT for drug resistance — targeted, not blanket.</p>
    </div>
  </div>
</div>"""


def make_chennai_map():
    peripheral = [
        {"id":"P001","name":"Thangal UPHC","naat":"Eranavoor UPHC","lat":13.1882,"lon":80.3089,"presumptive":844},
        {"id":"P002","name":"Lakshmipuram UPHC","naat":"Puzhal UPHC","lat":13.1587,"lon":80.2311,"presumptive":2200},
        {"id":"P003","name":"Samy Nagar UPHC","naat":"Puzhal UPHC","lat":13.1502,"lon":80.2198,"presumptive":1316},
        {"id":"P004","name":"Korrukupet UPHC","naat":"CDH","lat":13.1241,"lon":80.2934,"presumptive":1646},
        {"id":"P005","name":"Sharma Nagar UPHC","naat":"Kodungaiyur UPHC","lat":13.1367,"lon":80.2456,"presumptive":1484},
        {"id":"P006","name":"BRN Garden UPHC","naat":"Basin Bridge UPHC","lat":13.1089,"lon":80.2812,"presumptive":1681},
        {"id":"P007","name":"Kolathur UPHC","naat":"GPH Periyar Nagar","lat":13.1149,"lon":80.2237,"presumptive":1436},
        {"id":"P008","name":"Veeramamunivar UPHC","naat":"Padi Round Building","lat":13.0987,"lon":80.1923,"presumptive":1325},
        {"id":"P009","name":"Chetpet UPHC","naat":"ITM","lat":13.0726,"lon":80.2378,"presumptive":1085},
        {"id":"P010","name":"Bharathipuram UPHC","naat":"MMDA UPHC","lat":13.0834,"lon":80.2112,"presumptive":900},
        {"id":"P011","name":"Krishnampet UPHC","naat":"Beemanampet UPHC","lat":13.0456,"lon":80.2534,"presumptive":506},
        {"id":"P012","name":"Virugambakkam UPHC","naat":"Koyembedu UPHC","lat":13.0567,"lon":80.1978,"presumptive":1354},
        {"id":"P013","name":"K.K. Nagar UPHC","naat":"Kodambakkam UPHC","lat":13.0389,"lon":80.2123,"presumptive":1141},
        {"id":"P014","name":"Ragava Colony UPHC","naat":"ESIC KK Nagar","lat":13.0312,"lon":80.2089,"presumptive":1365},
        {"id":"P015","name":"Sakthinagar UPHC","naat":"Chinnaporur UPHC","lat":13.0378,"lon":80.1712,"presumptive":1158},
        {"id":"P016","name":"Appavu Street UPHC","naat":"Nanganallur UPHC","lat":12.9812,"lon":80.1923,"presumptive":1314},
        {"id":"P017","name":"Sasthri Nagar UPHC","naat":"Adambakkam UPHC","lat":12.9934,"lon":80.2134,"presumptive":1740},
        {"id":"P018","name":"Taramani UPHC","naat":"Adambakkam UPHC","lat":12.9867,"lon":80.2312,"presumptive":1762},
        {"id":"P019","name":"Puzhithivakkam UPHC","naat":"Jaladiyanpettai UPHC","lat":12.9245,"lon":80.1978,"presumptive":1512},
        {"id":"P020","name":"Neelangkarai UPHC","naat":"Palavakkam UPHC","lat":12.9523,"lon":80.2423,"presumptive":1773},
    ]
    naat_sites = [
        {"name":"Eranavoor UPHC","lat":13.1866,"lon":80.3124,"tertiary":False},
        {"name":"Puzhal UPHC","lat":13.1645,"lon":80.2047,"tertiary":False},
        {"name":"CDH","lat":13.1276,"lon":80.2916,"tertiary":False},
        {"name":"Kodungaiyur UPHC","lat":13.1389,"lon":80.2512,"tertiary":False},
        {"name":"Basin Bridge UPHC","lat":13.1046,"lon":80.2752,"tertiary":False},
        {"name":"GPH Periyar Nagar","lat":13.1149,"lon":80.2237,"tertiary":False},
        {"name":"Padi Round Building","lat":13.1023,"lon":80.1834,"tertiary":False},
        {"name":"ITM","lat":13.0737,"lon":80.2495,"tertiary":True},
        {"name":"MMDA UPHC","lat":13.0823,"lon":80.2134,"tertiary":False},
        {"name":"Beemanampet UPHC","lat":13.0489,"lon":80.2456,"tertiary":False},
        {"name":"Koyembedu UPHC","lat":13.0582,"lon":80.1930,"tertiary":False},
        {"name":"Kodambakkam UPHC","lat":13.0521,"lon":80.2189,"tertiary":False},
        {"name":"ESIC KK Nagar","lat":13.0370,"lon":80.2121,"tertiary":False},
        {"name":"Chinnaporur UPHC","lat":13.0366,"lon":80.1702,"tertiary":False},
        {"name":"Nanganallur UPHC","lat":12.9745,"lon":80.1815,"tertiary":False},
        {"name":"Adambakkam UPHC","lat":12.9912,"lon":80.2119,"tertiary":False},
        {"name":"Jaladiyanpettai UPHC","lat":12.9124,"lon":80.1967,"tertiary":False},
        {"name":"Palavakkam UPHC","lat":12.9609,"lon":80.2565,"tertiary":False},
        {"name":"MMC Thoracic","lat":13.0823,"lon":80.2789,"tertiary":True},
    ]

    m = folium.Map(location=[13.06, 80.23], zoom_start=11, tiles="OpenStreetMap")
    naat_coords = {n["name"]:(n["lat"],n["lon"]) for n in naat_sites}

    for p in peripheral:
        naat_name = p["naat"]
        if naat_name in naat_coords:
            folium.PolyLine(
                [(p["lat"],p["lon"]), naat_coords[naat_name]],
                color="#378ADD", weight=1.5, opacity=0.5,
                tooltip=f"{p['name']} -> {naat_name}"
            ).add_to(m)

    for p in peripheral:
        folium.CircleMarker(
            location=[p["lat"],p["lon"]],
            radius=8, color="#1D9E75", fill=True, fill_opacity=0.85,
            tooltip=p["name"],
            popup=folium.Popup(
                f"<b>{p['name']}</b><br>"
                f"Presumptive TB 2025: {p['presumptive']:,}<br>"
                f"Linked NAAT: {p['naat']}<br>"
                f"NAAT referrals BEFORE Uniamp: {p['presumptive']:,}<br>"
                f"NAAT referrals AFTER Uniamp (positives only): {int(p['presumptive']*0.08)}<br>"
                f"<b>Reduction: {round((1-0.08)*100)}%</b>",
                max_width=240)
        ).add_to(m)

    for n in naat_sites:
        color = "darkred" if n["tertiary"] else "darkblue"
        label = "Tertiary NAAT" if n["tertiary"] else "NAAT hub"
        folium.Marker(
            location=[n["lat"],n["lon"]],
            tooltip=f"{label}: {n['name']}",
            popup=folium.Popup(
                f"<b>{n['name']}</b><br>Type: {label}<br>"
                + ("<i>NAAT direct — no Uniamp pre-screening</i>" if n["tertiary"] else "Receives only Uniamp-positive referrals"),
                max_width=220),
            icon=folium.Icon(color=color, icon="plus-sign", prefix="glyphicon")
        ).add_to(m)

    legend = """
    <div style='position:fixed;bottom:30px;left:30px;z-index:1000;
    background:white;padding:10px;border-radius:8px;font-size:12px;border:1px solid #ccc;line-height:1.8'>
    <b>Chennai Uniamp sites</b><br>
    <span style='color:#ffffff'>&#9679;</span> Peripheral UPHC (Uniamp)<br>
    <span style='color:darkblue'>+</span> NAAT hub<br>
    <span style='color:darkred'>+</span> Tertiary NAAT (direct)<br>
    <span style='color:#378ADD'>&#8212;</span> Referral linkage
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))
    return m._repr_html_()


def make_impact_charts(positivity_rate, num_sites, uniamp_cost, naat_cost):
    positivity = positivity_rate / 100
    sites_data = [
        {"name":"Lakshmipuram","presumptive":2200,"naat":"Puzhal UPHC"},
        {"name":"Neelangkarai","presumptive":1773,"naat":"Palavakkam UPHC"},
        {"name":"Taramani","presumptive":1762,"naat":"Adambakkam UPHC"},
        {"name":"Sasthri Nagar","presumptive":1740,"naat":"Adambakkam UPHC"},
        {"name":"Korrukupet","presumptive":1646,"naat":"CDH"},
        {"name":"BRN Garden","presumptive":1681,"naat":"Basin Bridge UPHC"},
        {"name":"Samy Nagar","presumptive":1316,"naat":"Puzhal UPHC"},
        {"name":"Virugambakkam","presumptive":1354,"naat":"Koyembedu UPHC"},
        {"name":"Sharma Nagar","presumptive":1484,"naat":"Kodungaiyur UPHC"},
        {"name":"Kolathur","presumptive":1436,"naat":"GPH Periyar Nagar"},
        {"name":"Veeramamunivar","presumptive":1325,"naat":"Padi Round Building"},
        {"name":"Chetpet","presumptive":1085,"naat":"ITM"},
        {"name":"Bharathipuram","presumptive":900,"naat":"MMDA UPHC"},
        {"name":"Krishnampet","presumptive":506,"naat":"Beemanampet UPHC"},
        {"name":"Ragava Colony","presumptive":1365,"naat":"ESIC KK Nagar"},
        {"name":"Sakthinagar","presumptive":1158,"naat":"Chinnaporur UPHC"},
        {"name":"Appavu Street","presumptive":1314,"naat":"Nanganallur UPHC"},
        {"name":"K.K. Nagar","presumptive":1141,"naat":"Kodambakkam UPHC"},
        {"name":"Puzhithivakkam","presumptive":1512,"naat":"Jaladiyanpettai UPHC"},
        {"name":"Thangal","presumptive":844,"naat":"Eranavoor UPHC"},
    ]
    selected          = sites_data[:int(num_sites)]
    total_presumptive = sum(s["presumptive"] for s in selected)
    total_positives   = int(total_presumptive * positivity)
    naat_before       = total_presumptive
    naat_after        = total_positives
    reduction_pct     = round((naat_before - naat_after) / naat_before * 100, 1)
    cost_before       = naat_before * naat_cost
    cost_after        = (total_presumptive * uniamp_cost) + (total_positives * naat_cost) + (50000 * int(num_sites))
    cost_saving       = cost_before - cost_after
    travel_hrs_saved  = (naat_before - naat_after) * 2.5
    cartridge_saving  = naat_before - naat_after

    naat_groups = {}
    for s in selected:
        n = s["naat"]
        if n not in naat_groups:
            naat_groups[n] = {"before":0,"after":0}
        naat_groups[n]["before"] += s["presumptive"]
        naat_groups[n]["after"]  += int(s["presumptive"] * positivity)
    naat_names  = list(naat_groups.keys())
    before_vals = [naat_groups[n]["before"] for n in naat_names]
    after_vals  = [naat_groups[n]["after"]  for n in naat_names]

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            "NAAT load before vs after",
            "Annual cost (Rs lakhs)",
            "NAAT referrals per linked site",
            "Patient travel hours saved"
        ],
        specs=[
            [{"type":"xy"},{"type":"xy"}],
            [{"type":"xy"},{"type":"indicator"}]
        ],
        vertical_spacing=0.20,
        horizontal_spacing=0.12
    )
    fig.add_trace(go.Bar(
        x=["Before Uniamp","After Uniamp"],
        y=[naat_before, naat_after],
        marker_color=["#E24B4A","#1D9E75"],
        text=[f"{naat_before:,}",f"{naat_after:,}"],
        textposition="outside",
        showlegend=False
    ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=["Before","After"],
        y=[round(cost_before/100000,1), round(cost_after/100000,1)],
        marker_color=["#E24B4A","#1D9E75"],
        text=[f"Rs {round(cost_before/100000,1)}L", f"Rs {round(cost_after/100000,1)}L"],
        textposition="outside",
        showlegend=False
    ), row=1, col=2)
    fig.add_trace(go.Bar(name="Before", x=naat_names, y=before_vals, marker_color="#F09595", showlegend=True), row=2, col=1)
    fig.add_trace(go.Bar(name="After",  x=naat_names, y=after_vals,  marker_color="#5DCAA5", showlegend=True), row=2, col=1)
    fig.add_trace(go.Indicator(
        mode="number",
        value=round(travel_hrs_saved),
        title={"text":"patient travel hrs/year saved"},
        number={"valueformat":",.0f","suffix":" hrs"}
    ), row=2, col=2)
    fig.update_layout(
        height=620,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"size":11,"color":"#cccccc"},
        title_font_color="#cccccc",
        margin={"t":60,"b":60,"l":40,"r":40},
        barmode="group",
        legend={"orientation":"h","y":-0.12,"font":{"color":"#cccccc"}},
        annotations=[dict(font=dict(color="#cccccc")) for _ in range(4)]
    )
    fig.update_xaxes(tickfont=dict(color="#cccccc"), title_font=dict(color="#cccccc"))
    fig.update_yaxes(tickfont=dict(color="#cccccc"), title_font=dict(color="#cccccc"))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)")

    summary = f"""
| Metric | Value |
|---|---|
| Total presumptive cases/year | {total_presumptive:,} |
| NAAT tests before Uniamp | {naat_before:,} |
| NAAT tests after Uniamp | {naat_after:,} |
| NAAT load reduction | **{reduction_pct}%** |
| NAAT cartridges saved/year | {cartridge_saving:,} |
| Annual cost before | Rs {round(cost_before/100000,1)} Lakh |
| Annual cost after | Rs {round(cost_after/100000,1)} Lakh |
| **Cost saving/year** | **Rs {round(cost_saving/100000,1)} Lakh** |
| Patient travel hours saved | {round(travel_hrs_saved):,} hrs/year |
"""
    return fig, summary


def make_pathway_html():
    return """
<div style='display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:12px 0;font-family:sans-serif'>
<div style='border:1px solid #444;border-radius:10px;padding:16px;background:#1a2a3a'>
  <div style='background:#1a4a7a;border-radius:6px;padding:8px 12px;margin-bottom:10px'>
    <strong style='color:#ffffff;font-size:13px'>Peripheral UPHC — low prevalence OPD</strong>
    <p style='color:#add4f7;font-size:11px;margin:4px 0 0'>Uniamp first — sufficient for screening</p>
  </div>
  <div style='border-left:3px solid #378ADD;padding:6px 10px;margin:8px 0;font-size:12px;color:#ffffff'>Patient presents with symptoms</div>
  <div style='border-left:3px solid #378ADD;padding:6px 10px;margin:8px 0;font-size:12px;color:#ffffff'>Uniamp test same day at UPHC — no travel</div>
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px'>
    <div style='background:#0a4a32;border-radius:6px;padding:8px;font-size:11px;color:#9FE1CB;border:1px solid #1D9E75;border:1px solid #1D9E75'><strong>MTB negative (~92%)</strong><br>Reassured, no referral.<br>Travel saved: 2.5 hrs</div>
    <div style='background:#4a1a0a;border-radius:6px;padding:8px;font-size:11px;color:#F5C4B3;border:1px solid #D85A30'><strong>MTB positive (~8%)</strong><br>Refer to NAAT for DST only</div>
  </div>
  <div style='background:#2a2a2a;border-radius:6px;padding:8px;margin-top:8px;font-size:11px;color:#cccccc;border:1px solid #444'>NAAT site receives only confirmed positives — load reduced 92%</div>
</div>
<div style='border:1px solid #444;border-radius:10px;padding:16px;background:#2a1a2a'>
  <div style='background:#6e0c2e;border-radius:6px;padding:8px 12px;margin-bottom:10px'>
    <strong style='color:#ffffff;font-size:13px'>Tertiary care — ITM / MMC Thoracic</strong>
    <p style='color:#ffffff;font-size:11px;margin:4px 0 0'>High risk — NAAT directly, no two-step delay</p>
  </div>
  <div style='border-left:3px solid #D4537E;padding:6px 10px;margin:8px 0;font-size:12px;color:#ffffff'>High-risk patient — immunocompromised, close contact</div>
  <div style='border-left:3px solid #D4537E;padding:6px 10px;margin:8px 0;font-size:12px;color:#ffffff'>TrueNAAT / CBNAAT directly — MTB + RIF resistance in one test</div>
  <div style='background:#5a3a00;border-radius:6px;padding:8px;margin:8px 0;font-size:11px;color:#ffd699;border:1px solid #BA7517'><strong>Why not Uniamp here?</strong> Uniamp detects MTB only. Resistance result needs a second NAAT — extra 24-48 hr delay before treatment.</div>
  <div style='background:#0a4a32;border-radius:6px;padding:8px;margin-top:8px;font-size:11px;color:#9FE1CB;border:1px solid #1D9E75'>Treatment started same day — DS-TB or DR-TB regimen without waiting</div>
</div>
</div>"""


def make_chennai_map():
    peripheral = [
        {"id":"P001","name":"Thangal UPHC","naat":"Eranavoor UPHC","lat":13.1882,"lon":80.3089,"presumptive":844},
        {"id":"P002","name":"Lakshmipuram UPHC","naat":"Puzhal UPHC","lat":13.1587,"lon":80.2311,"presumptive":2200},
        {"id":"P003","name":"Samy Nagar UPHC","naat":"Puzhal UPHC","lat":13.1502,"lon":80.2198,"presumptive":1316},
        {"id":"P004","name":"Korrukupet UPHC","naat":"CDH","lat":13.1241,"lon":80.2934,"presumptive":1646},
        {"id":"P005","name":"Sharma Nagar UPHC","naat":"Kodungaiyur UPHC","lat":13.1367,"lon":80.2456,"presumptive":1484},
        {"id":"P006","name":"BRN Garden UPHC","naat":"Basin Bridge UPHC","lat":13.1089,"lon":80.2812,"presumptive":1681},
        {"id":"P007","name":"Kolathur UPHC","naat":"GPH Periyar Nagar","lat":13.1149,"lon":80.2237,"presumptive":1436},
        {"id":"P008","name":"Veeramamunivar UPHC","naat":"Padi Round Building","lat":13.0987,"lon":80.1923,"presumptive":1325},
        {"id":"P009","name":"Chetpet UPHC","naat":"ITM","lat":13.0726,"lon":80.2378,"presumptive":1085},
        {"id":"P010","name":"Bharathipuram UPHC","naat":"MMDA UPHC","lat":13.0834,"lon":80.2112,"presumptive":900},
        {"id":"P011","name":"Krishnampet UPHC","naat":"Beemanampet UPHC","lat":13.0456,"lon":80.2534,"presumptive":506},
        {"id":"P012","name":"Virugambakkam UPHC","naat":"Koyembedu UPHC","lat":13.0567,"lon":80.1978,"presumptive":1354},
        {"id":"P013","name":"K.K. Nagar UPHC","naat":"Kodambakkam UPHC","lat":13.0389,"lon":80.2123,"presumptive":1141},
        {"id":"P014","name":"Ragava Colony UPHC","naat":"ESIC KK Nagar","lat":13.0312,"lon":80.2089,"presumptive":1365},
        {"id":"P015","name":"Sakthinagar UPHC","naat":"Chinnaporur UPHC","lat":13.0378,"lon":80.1712,"presumptive":1158},
        {"id":"P016","name":"Appavu Street UPHC","naat":"Nanganallur UPHC","lat":12.9812,"lon":80.1923,"presumptive":1314},
        {"id":"P017","name":"Sasthri Nagar UPHC","naat":"Adambakkam UPHC","lat":12.9934,"lon":80.2134,"presumptive":1740},
        {"id":"P018","name":"Taramani UPHC","naat":"Adambakkam UPHC","lat":12.9867,"lon":80.2312,"presumptive":1762},
        {"id":"P019","name":"Puzhithivakkam UPHC","naat":"Jaladiyanpettai UPHC","lat":12.9245,"lon":80.1978,"presumptive":1512},
        {"id":"P020","name":"Neelangkarai UPHC","naat":"Palavakkam UPHC","lat":12.9523,"lon":80.2423,"presumptive":1773},
    ]
    naat_sites = [
        {"name":"Eranavoor UPHC","lat":13.1866,"lon":80.3124,"tertiary":False},
        {"name":"Puzhal UPHC","lat":13.1645,"lon":80.2047,"tertiary":False},
        {"name":"CDH","lat":13.1276,"lon":80.2916,"tertiary":False},
        {"name":"Kodungaiyur UPHC","lat":13.1389,"lon":80.2512,"tertiary":False},
        {"name":"Basin Bridge UPHC","lat":13.1046,"lon":80.2752,"tertiary":False},
        {"name":"GPH Periyar Nagar","lat":13.1149,"lon":80.2237,"tertiary":False},
        {"name":"Padi Round Building","lat":13.1023,"lon":80.1834,"tertiary":False},
        {"name":"ITM","lat":13.0737,"lon":80.2495,"tertiary":True},
        {"name":"MMDA UPHC","lat":13.0823,"lon":80.2134,"tertiary":False},
        {"name":"Beemanampet UPHC","lat":13.0489,"lon":80.2456,"tertiary":False},
        {"name":"Koyembedu UPHC","lat":13.0582,"lon":80.1930,"tertiary":False},
        {"name":"Kodambakkam UPHC","lat":13.0521,"lon":80.2189,"tertiary":False},
        {"name":"ESIC KK Nagar","lat":13.0370,"lon":80.2121,"tertiary":False},
        {"name":"Chinnaporur UPHC","lat":13.0366,"lon":80.1702,"tertiary":False},
        {"name":"Nanganallur UPHC","lat":12.9745,"lon":80.1815,"tertiary":False},
        {"name":"Adambakkam UPHC","lat":12.9912,"lon":80.2119,"tertiary":False},
        {"name":"Jaladiyanpettai UPHC","lat":12.9124,"lon":80.1967,"tertiary":False},
        {"name":"Palavakkam UPHC","lat":12.9609,"lon":80.2565,"tertiary":False},
        {"name":"MMC Thoracic","lat":13.0823,"lon":80.2789,"tertiary":True},
    ]

    m = folium.Map(location=[13.06, 80.23], zoom_start=11, tiles="OpenStreetMap")
    naat_coords = {n["name"]:(n["lat"],n["lon"]) for n in naat_sites}

    for p in peripheral:
        naat_name = p["naat"]
        if naat_name in naat_coords:
            folium.PolyLine(
                [(p["lat"],p["lon"]), naat_coords[naat_name]],
                color="#378ADD", weight=1.5, opacity=0.5,
                tooltip=f"{p['name']} -> {naat_name}"
            ).add_to(m)

    for p in peripheral:
        folium.CircleMarker(
            location=[p["lat"],p["lon"]],
            radius=8, color="#1D9E75", fill=True, fill_opacity=0.85,
            tooltip=p["name"],
            popup=folium.Popup(
                f"<b>{p['name']}</b><br>"
                f"Presumptive TB 2025: {p['presumptive']:,}<br>"
                f"Linked NAAT: {p['naat']}<br>"
                f"NAAT referrals BEFORE Uniamp: {p['presumptive']:,}<br>"
                f"NAAT referrals AFTER Uniamp (positives only): {int(p['presumptive']*0.08)}<br>"
                f"<b>Reduction: {round((1-0.08)*100)}%</b>",
                max_width=240)
        ).add_to(m)

    for n in naat_sites:
        color = "darkred" if n["tertiary"] else "darkblue"
        label = "Tertiary NAAT" if n["tertiary"] else "NAAT hub"
        folium.Marker(
            location=[n["lat"],n["lon"]],
            tooltip=f"{label}: {n['name']}",
            popup=folium.Popup(
                f"<b>{n['name']}</b><br>Type: {label}<br>"
                + ("<i>NAAT direct — no Uniamp pre-screening</i>" if n["tertiary"] else "Receives only Uniamp-positive referrals"),
                max_width=220),
            icon=folium.Icon(color=color, icon="plus-sign", prefix="glyphicon")
        ).add_to(m)

    legend = """
    <div style='position:fixed;bottom:30px;left:30px;z-index:1000;
    background:white;padding:10px;border-radius:8px;font-size:12px;border:1px solid #ccc;line-height:1.8'>
    <b>Chennai Uniamp sites</b><br>
    <span style='color:#ffffff'>&#9679;</span> Peripheral UPHC (Uniamp)<br>
    <span style='color:darkblue'>+</span> NAAT hub<br>
    <span style='color:darkred'>+</span> Tertiary NAAT (direct)<br>
    <span style='color:#378ADD'>&#8212;</span> Referral linkage
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))
    return m._repr_html_()


def make_impact_charts(positivity_rate, num_sites, uniamp_cost, naat_cost):
    positivity = positivity_rate / 100
    sites_data = [
        {"name":"Lakshmipuram","presumptive":2200,"naat":"Puzhal UPHC"},
        {"name":"Neelangkarai","presumptive":1773,"naat":"Palavakkam UPHC"},
        {"name":"Taramani","presumptive":1762,"naat":"Adambakkam UPHC"},
        {"name":"Sasthri Nagar","presumptive":1740,"naat":"Adambakkam UPHC"},
        {"name":"Korrukupet","presumptive":1646,"naat":"CDH"},
        {"name":"BRN Garden","presumptive":1681,"naat":"Basin Bridge UPHC"},
        {"name":"Samy Nagar","presumptive":1316,"naat":"Puzhal UPHC"},
        {"name":"Virugambakkam","presumptive":1354,"naat":"Koyembedu UPHC"},
        {"name":"Sharma Nagar","presumptive":1484,"naat":"Kodungaiyur UPHC"},
        {"name":"Kolathur","presumptive":1436,"naat":"GPH Periyar Nagar"},
        {"name":"Veeramamunivar","presumptive":1325,"naat":"Padi Round Building"},
        {"name":"Chetpet","presumptive":1085,"naat":"ITM"},
        {"name":"Bharathipuram","presumptive":900,"naat":"MMDA UPHC"},
        {"name":"Krishnampet","presumptive":506,"naat":"Beemanampet UPHC"},
        {"name":"Ragava Colony","presumptive":1365,"naat":"ESIC KK Nagar"},
        {"name":"Sakthinagar","presumptive":1158,"naat":"Chinnaporur UPHC"},
        {"name":"Appavu Street","presumptive":1314,"naat":"Nanganallur UPHC"},
        {"name":"K.K. Nagar","presumptive":1141,"naat":"Kodambakkam UPHC"},
        {"name":"Puzhithivakkam","presumptive":1512,"naat":"Jaladiyanpettai UPHC"},
        {"name":"Thangal","presumptive":844,"naat":"Eranavoor UPHC"},
    ]
    selected          = sites_data[:int(num_sites)]
    total_presumptive = sum(s["presumptive"] for s in selected)
    total_positives   = int(total_presumptive * positivity)
    naat_before       = total_presumptive
    naat_after        = total_positives
    reduction_pct     = round((naat_before - naat_after) / naat_before * 100, 1)
    cost_before       = naat_before * naat_cost
    cost_after        = (total_presumptive * uniamp_cost) + (total_positives * naat_cost) + (50000 * int(num_sites))
    cost_saving       = cost_before - cost_after
    travel_hrs_saved  = (naat_before - naat_after) * 2.5
    cartridge_saving  = naat_before - naat_after

    naat_groups = {}
    for s in selected:
        n = s["naat"]
        if n not in naat_groups:
            naat_groups[n] = {"before":0,"after":0}
        naat_groups[n]["before"] += s["presumptive"]
        naat_groups[n]["after"]  += int(s["presumptive"] * positivity)
    naat_names  = list(naat_groups.keys())
    before_vals = [naat_groups[n]["before"] for n in naat_names]
    after_vals  = [naat_groups[n]["after"]  for n in naat_names]

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            "NAAT load before vs after",
            "Annual cost (Rs lakhs)",
            "NAAT referrals per linked site",
            "Patient travel hours saved"
        ],
        specs=[
            [{"type":"xy"},{"type":"xy"}],
            [{"type":"xy"},{"type":"indicator"}]
        ],
        vertical_spacing=0.20,
        horizontal_spacing=0.12
    )
    fig.add_trace(go.Bar(
        x=["Before Uniamp","After Uniamp"],
        y=[naat_before, naat_after],
        marker_color=["#E24B4A","#1D9E75"],
        text=[f"{naat_before:,}",f"{naat_after:,}"],
        textposition="outside",
        showlegend=False
    ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=["Before","After"],
        y=[round(cost_before/100000,1), round(cost_after/100000,1)],
        marker_color=["#E24B4A","#1D9E75"],
        text=[f"Rs {round(cost_before/100000,1)}L", f"Rs {round(cost_after/100000,1)}L"],
        textposition="outside",
        showlegend=False
    ), row=1, col=2)
    fig.add_trace(go.Bar(name="Before", x=naat_names, y=before_vals, marker_color="#F09595", showlegend=True), row=2, col=1)
    fig.add_trace(go.Bar(name="After",  x=naat_names, y=after_vals,  marker_color="#5DCAA5", showlegend=True), row=2, col=1)
    fig.add_trace(go.Indicator(
        mode="number",
        value=round(travel_hrs_saved),
        title={"text":"patient travel hrs/year saved"},
        number={"valueformat":",.0f","suffix":" hrs"}
    ), row=2, col=2)
    fig.update_layout(
        height=620,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"size":11,"color":"#cccccc"},
        title_font_color="#cccccc",
        margin={"t":60,"b":60,"l":40,"r":40},
        barmode="group",
        legend={"orientation":"h","y":-0.12,"font":{"color":"#cccccc"}},
        annotations=[dict(font=dict(color="#cccccc")) for _ in range(4)]
    )
    fig.update_xaxes(tickfont=dict(color="#cccccc"), title_font=dict(color="#cccccc"))
    fig.update_yaxes(tickfont=dict(color="#cccccc"), title_font=dict(color="#cccccc"))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)")

    summary = f"""
| Metric | Value |
|---|---|
| Total presumptive cases/year | {total_presumptive:,} |
| NAAT tests before Uniamp | {naat_before:,} |
| NAAT tests after Uniamp | {naat_after:,} |
| NAAT load reduction | **{reduction_pct}%** |
| NAAT cartridges saved/year | {cartridge_saving:,} |
| Annual cost before | Rs {round(cost_before/100000,1)} Lakh |
| Annual cost after | Rs {round(cost_after/100000,1)} Lakh |
| **Cost saving/year** | **Rs {round(cost_saving/100000,1)} Lakh** |
| Patient travel hours saved | {round(travel_hrs_saved):,} hrs/year |
"""
    return fig, summary


def make_pathway_html():
    return """
<div style='display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:12px 0;font-family:sans-serif'>
<div style='border:1px solid #444;border-radius:10px;padding:16px;background:#1a2a3a'>
  <div style='background:#1a4a7a;border-radius:6px;padding:8px 12px;margin-bottom:10px'>
    <strong style='color:#ffffff;font-size:13px'>Peripheral UPHC — low prevalence OPD</strong>
    <p style='color:#add4f7;font-size:11px;margin:4px 0 0'>Uniamp first — sufficient for screening</p>
  </div>
  <div style='border-left:3px solid #378ADD;padding:6px 10px;margin:8px 0;font-size:12px;color:#ffffff'>Patient presents with symptoms</div>
  <div style='border-left:3px solid #378ADD;padding:6px 10px;margin:8px 0;font-size:12px;color:#ffffff'>Uniamp test same day at UPHC — no travel</div>
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px'>
    <div style='background:#0a4a32;border-radius:6px;padding:8px;font-size:11px;color:#9FE1CB;border:1px solid #1D9E75'><strong>MTB negative (~92%)</strong><br>Reassured, no referral.<br>Travel saved: 2.5 hrs</div>
    <div style='background:#4a1a0a;border-radius:6px;padding:8px;font-size:11px;color:#F5C4B3;border:1px solid #D85A30'><strong>MTB positive (~8%)</strong><br>Refer to NAAT for DST only</div>
  </div>
  <div style='background:#2a2a2a;border-radius:6px;padding:8px;margin-top:8px;font-size:11px;color:#cccccc;border:1px solid #444'>NAAT site receives only confirmed positives — load reduced 92%</div>
</div>
<div style='border:1px solid #444;border-radius:10px;padding:16px;background:#2a1a2a'>
  <div style='background:#6e0c2e;border-radius:6px;padding:8px 12px;margin-bottom:10px'>
    <strong style='color:#ffffff;font-size:13px'>Tertiary care — ITM / MMC Thoracic</strong>
    <p style='color:#ffccd8;font-size:11px;margin:4px 0 0'>High risk — NAAT directly, no two-step delay</p>
  </div>
  <div style='border-left:3px solid #D4537E;padding:6px 10px;margin:8px 0;font-size:12px;color:#ffffff'>High-risk patient — immunocompromised, close contact</div>
  <div style='border-left:3px solid #D4537E;padding:6px 10px;margin:8px 0;font-size:12px;color:#ffffff'>TrueNAAT / CBNAAT directly — MTB + RIF resistance in one test</div>
  <div style='background:#5a3a00;border-radius:6px;padding:8px;margin:8px 0;font-size:11px;color:#ffd699;border:1px solid #BA7517'><strong>Why not Uniamp here?</strong> Uniamp detects MTB only. Resistance result needs a second NAAT — extra 24-48 hr delay before treatment.</div>
  <div style='background:#0a4a32;border-radius:6px;padding:8px;margin-top:8px;font-size:11px;color:#9FE1CB;border:1px solid #1D9E75'>Treatment started same day — DS-TB or DR-TB regimen without waiting</div>
</div>
</div>"""


R    = load_results()
facs = load_facs()
facility_names = sorted(facs["name"].tolist())

with gr.Blocks(title="DISHA") as demo:

    gr.Markdown("# DISHA — Diagnostic Intelligence for Systematic Health Alerts")
    gr.Markdown("**Maharashtra · Tamil Nadu · TB Diagnostic Network**")
    gr.Markdown(f"*Last updated: {R['generated_at']}*")

    with gr.Row():
        gr.Textbox(label="Stockout Alerts",      value=str(len(R["alerts"])),             interactive=False)
        gr.Textbox(label="14-Day Predictions",   value=str(len(R.get("predictions",[]))), interactive=False)
        gr.Textbox(label="Facilities Mapped",    value=str(len(R["routing"])),            interactive=False)
        gr.Textbox(label="NAAT Sites",           value="8",                               interactive=False)

    with gr.Tab("Facility Map"):
        gr.Markdown("Maharashtra — click any marker for details")
        gr.HTML(make_map())

    with gr.Tab("Stockout Alerts"):
        gr.Dataframe(value=show_alerts())

    with gr.Tab("14-Day Prediction"):
        gr.Dataframe(value=show_predictions())

    with gr.Tab("Referral Lookup"):
        gr.Markdown("### Select a facility to see its best referral and NAAT linkage")
        facility_dropdown = gr.Dropdown(choices=facility_names, label="Select Facility", interactive=True)
        referral_output   = gr.Markdown("*Select a facility above.*")
        facility_dropdown.change(fn=get_facility_referral, inputs=facility_dropdown, outputs=referral_output)

    with gr.Tab("Full Routing Table"):
        gr.Dataframe(value=show_routing())

    with gr.Tab("Chennai — Site Map"):
        gr.Markdown("20 peripheral Uniamp sites linked to NAAT hubs — lines show referral linkage")
        gr.HTML(make_chennai_map())

    with gr.Tab("Chennai Impact Model"):
        gr.Markdown("### Uniamp deployment impact — Chennai peripheral UPHCs")
        gr.Markdown("Adjust parameters to see how NAAT load, cost, and patient travel change")
        with gr.Row():
            positivity_slider = gr.Slider(minimum=2, maximum=25, value=8,    step=1,   label="TB positivity rate (%)")
            sites_slider      = gr.Slider(minimum=1, maximum=20, value=20,   step=1,   label="Number of peripheral sites")
        with gr.Row():
            uniamp_slider     = gr.Slider(minimum=300, maximum=700, value=450,  step=50,  label="Uniamp cartridge cost (Rs)")
            naat_slider       = gr.Slider(minimum=800, maximum=2000, value=1200, step=100, label="NAAT cartridge cost (Rs)")
        init_fig, init_summary = make_impact_charts(8, 20, 450, 1200)
        summary_md  = gr.Markdown(value=init_summary)
        impact_plot = gr.Plot(value=init_fig)
        gr.HTML(value=make_pathway_html())
        gr.HTML(value=make_prevalence_html())

        def update_charts(pos, sites, uc, nc):
            return make_impact_charts(pos, sites, uc, nc)

        for slider in [positivity_slider, sites_slider, uniamp_slider, naat_slider]:
            slider.change(
                fn=update_charts,
                inputs=[positivity_slider, sites_slider, uniamp_slider, naat_slider],
                outputs=[impact_plot, summary_md]
            )

demo.launch()
