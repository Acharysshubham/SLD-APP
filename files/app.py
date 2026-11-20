import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import sld_engine as E

st.set_page_config(page_title="SLD Studio", page_icon="⚡", layout="wide")
ss = st.session_state
if "df" not in ss:
    ss.df, ss.summ, ss.notes = E.bess_df(100, 400, 2.5, 5, 33, 0.69, 220)

with st.sidebar:
    st.title("⚡ SLD Studio")
    title = st.text_input("Drawing title", "BESS Single Line Diagram")
    rev = st.text_input("Revision", "A")
    by = st.text_input("Drawn by", "")
    zoom = st.slider("Preview zoom", 0.3, 1.5, 0.7, 0.05)

tab_b, tab_e, tab_c, tab_x = st.tabs(["BESS generator", "Diagram editor", "Checks & BOM", "Export"])

with tab_b:
    st.caption("Generates an AC-coupled BESS SLD: grid, optional HV transformer, MV bus, PCS blocks, batteries, auxiliary supply.")
    c = st.columns(4)
    MW = c[0].number_input("Power (MW)", 1.0, 5000.0, 100.0)
    MWh = c[1].number_input("Energy (MWh)", 1.0, 20000.0, 400.0)
    pm = c[2].number_input("PCS unit (MW)", 0.1, 20.0, 2.5, 0.05)
    cm = c[3].number_input("Container (MWh)", 0.1, 20.0, 5.0, 0.05)
    c = st.columns(4)
    gk = c[0].number_input("Grid / POI (kV)", 0.4, 765.0, 220.0)
    mv = c[1].number_input("MV bus (kV)", 3.3, 66.0, 33.0)
    lv = c[2].number_input("PCS AC (kV)", 0.4, 3.3, 0.69, 0.01)
    pf = c[3].number_input("PCS power factor", 0.8, 1.0, 0.95, 0.01)
    c = st.columns(3)
    isc = c[0].number_input("Fault level (kA)", 1.0, 100.0, 25.0)
    nd = c[1].number_input("Max blocks drawn", 1, 20, 4)
    aux = c[2].number_input("Aux transformer (kVA, 0 = none)", 0.0, 5000.0, 250.0)
    if st.button("Generate SLD", type="primary"):
        ss.df, ss.summ, ss.notes = E.bess_df(MW, MWh, pm, cm, mv, lv, gk, pf, isc, int(nd), aux)

with tab_e:
    st.caption("Each row is a device; `parent` is the id of the device feeding it. Layout is automatic.")
    c = st.columns(3)
    if c[0].button("Load LV distribution example"):
        ss.df, ss.summ, ss.notes = E.example_lv(), None, []; st.rerun()
    up = c[1].file_uploader("Load CSV", type="csv", label_visibility="collapsed")
    if up is not None and ss.get("loaded") != up.name:
        ss.df, ss.summ, ss.notes, ss.loaded = pd.read_csv(up).fillna("")[E.COLS], None, [], up.name; st.rerun()
    ss.df = st.data_editor(
        ss.df, num_rows="dynamic", width="stretch", hide_index=True,
        column_config={"type": st.column_config.SelectboxColumn(options=E.TYPES, required=True)})

pr, W, H = E.primitives(ss.df, title, ss.notes, rev, by)
svg = E.to_svg(pr, W, H, zoom)
with tab_e:
    page = f'<div style="overflow:auto;background:#fff;border:1px solid #ccc">{svg}</div>'
    if hasattr(st, "iframe"):
        st.iframe(page, height=720)
    else:
        components.html(page, height=720, scrolling=True)

with tab_c:
    w = E.check(ss.df)
    st.subheader("Rules check")
    for m in w: st.warning(m)
    if not w: st.success("No issues found.")
    if ss.get("summ"):
        s = ss.summ
        st.subheader("BESS summary")
        st.table(pd.DataFrame({"Item": ["PCS blocks", "Containers per PCS", "Total containers", "Installed energy (MWh)",
                                        "Block transformer (MVA)", "MV current per block (A)", "LV current per block (A)", "Total MV current (A)"],
                               "Value": [s["blocks"], s["containers_per_pcs"], s["containers"], f'{s["installed_mwh"]:.1f}',
                                         s["tr_mva"], f'{s["i_mv_block"]:.0f}', f'{s["i_lv_block"]:.0f}', f'{s["i_mv_total"]:.0f}']}).astype(str))
        st.caption("Breaker ratings use 1.25 x load current rounded to a standard size. Cable and protection sizing still need a detailed study.")
    st.subheader("Bill of materials (as drawn)")
    d = ss.df.fillna("")
    st.dataframe(d.groupby(["type", "spec1", "spec2"]).size().reset_index(name="qty"), hide_index=True, width="stretch")

with tab_x:
    st.download_button("Download SVG", svg, "sld.svg", "image/svg+xml")
    st.download_button("Download project CSV", ss.df.to_csv(index=False), "sld_project.csv", "text/csv")
    try:
        st.download_button("Download DXF (CAD)", E.to_dxf(pr, H), "sld.dxf", "application/dxf")
    except ImportError:
        st.info("Install `ezdxf` to enable DXF export.")
