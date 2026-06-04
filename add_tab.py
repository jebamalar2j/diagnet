content = open('app.py', encoding='utf-8').read()

new_tab = '''

def update_charts(pos, sites, uc, nc):
    fig, summary = make_impact_charts(pos, sites, uc, nc)
    return fig, summary

with demo:
    with gr.Tab("Chennai Impact Model"):
        gr.Markdown("### Uniamp deployment impact — Chennai peripheral UPHCs")
        gr.Markdown("Adjust parameters to see how NAAT load, cost, and patient travel change")
        with gr.Row():
            positivity_slider = gr.Slider(minimum=2, maximum=25, value=8, step=1, label="TB positivity rate at peripheral sites (%)")
            sites_slider      = gr.Slider(minimum=1, maximum=20, value=20, step=1, label="Number of peripheral sites")
        with gr.Row():
            uniamp_slider = gr.Slider(minimum=300, maximum=700, value=450, step=50, label="Uniamp cartridge cost (Rs)")
            naat_slider   = gr.Slider(minimum=800, maximum=2000, value=1200, step=100, label="NAAT cartridge cost (Rs)")
        summary_md   = gr.Markdown()
        impact_plot  = gr.Plot()
        gr.HTML(value=make_pathway_html())
        gr.Markdown("### Cost per test — device comparison")
        gr.HTML(value="""
<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:12px;padding:8px 0;font-family:sans-serif'>
  <div style='border:1px solid #e0e0e0;border-radius:8px;padding:12px'>
    <p style='font-weight:500;margin:0 0 8px'>Uniamp</p>
    <p style='font-size:20px;font-weight:500;margin:0'>Rs 450</p>
    <p style='font-size:11px;color:#666;margin:4px 0'>per cartridge</p>
    <p style='font-size:11px;color:#666;margin:2px 0'>Machine: Rs 50,000</p>
    <p style='font-size:11px;color:#666;margin:2px 0'>Detects: MTB yes/no</p>
    <p style='font-size:11px;color:#666;margin:2px 0'>Result: ~1 hr</p>
    <p style='font-size:11px;color:#666;margin:2px 0'>Best for: peripheral screening</p>
  </div>
  <div style='border:1px solid #e0e0e0;border-radius:8px;padding:12px'>
    <p style='font-weight:500;margin:0 0 8px'>TrueNAAT</p>
    <p style='font-size:20px;font-weight:500;margin:0'>Rs 1,200</p>
    <p style='font-size:11px;color:#666;margin:4px 0'>per cartridge (approx)</p>
    <p style='font-size:11px;color:#666;margin:2px 0'>Machine: Rs 4.5 lakh</p>
    <p style='font-size:11px;color:#666;margin:2px 0'>Detects: MTB + RIF resistance</p>
    <p style='font-size:11px;color:#666;margin:2px 0'>Result: ~1 hr</p>
    <p style='font-size:11px;color:#666;margin:2px 0'>Best for: NAAT hub sites</p>
  </div>
  <div style='border:1px solid #e0e0e0;border-radius:8px;padding:12px'>
    <p style='font-weight:500;margin:0 0 8px'>CBNAAT (GeneXpert)</p>
    <p style='font-size:20px;font-weight:500;margin:0'>Rs 1,800</p>
    <p style='font-size:11px;color:#666;margin:4px 0'>per cartridge (approx)</p>
    <p style='font-size:11px;color:#666;margin:2px 0'>Machine: Rs 15 lakh+</p>
    <p style='font-size:11px;color:#666;margin:2px 0'>Detects: MTB + RIF resistance</p>
    <p style='font-size:11px;color:#666;margin:2px 0'>Result: ~2 hrs</p>
    <p style='font-size:11px;color:#666;margin:2px 0'>Best for: tertiary/DR-TB centres</p>
  </div>
</div>""")
        for slider in [positivity_slider, sites_slider, uniamp_slider, naat_slider]:
            slider.change(fn=update_charts,
                inputs=[positivity_slider, sites_slider, uniamp_slider, naat_slider],
                outputs=[impact_plot, summary_md])
        init_fig, init_summary = make_impact_charts(8, 20, 450, 1200)
        impact_plot.value  = init_fig
        summary_md.value   = init_summary

demo.launch()
'''

content = content.replace('demo.launch()', new_tab)
open('app.py', 'w', encoding='utf-8').write(content)
print("Done. demo.launch replaced:", 'demo.launch()' not in content)
