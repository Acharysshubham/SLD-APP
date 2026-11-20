"""SLD engine: node table -> tree layout -> primitives -> SVG / DXF, plus BESS generator and checks."""
import math, io
import pandas as pd

TYPES = ["grid", "bus", "breaker", "transformer", "pcs", "battery", "load", "pv", "generator", "motor"]
COLS = ["id", "type", "label", "spec1", "spec2", "cable", "parent"]
STD_A = [16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250,
         1600, 2000, 2500, 3200, 4000, 5000, 6300]
STD_MVA = [1, 1.25, 1.6, 2, 2.5, 3.15, 4, 5, 6.3, 8, 10, 12.5, 16, 20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250]
COLW, ROW, M = 190, 130, 80


def nxt(v, table):
    return next((a for a in table if a >= v), table[-1])


def ln(x1, y1, x2, y2, w=2):
    return ("line", x1, y1, x2, y2, w)


def _sym(t):
    """-> (half_height, half_width, local primitives)"""
    R = lambda x, y, w, h: ("rect", x, y, w, h)
    C = lambda x, y, r: ("circle", x, y, r)
    T = lambda x, y, s: ("text", x, y, s, 10, "")
    if t == "grid":
        return 26, 26, [R(-26, -26, 52, 52), ("poly", [(-16, 4), (-8, -8), (0, 4), (8, -8), (16, 4)], False)]
    if t == "breaker":
        return 24, 14, [ln(0, -24, 0, -12), ln(0, 12, 0, 24), R(-9, -12, 18, 24), ln(-9, -12, 9, 12), ln(9, -12, -9, 12)]
    if t == "transformer":
        return 28, 22, [ln(0, -28, 0, -23), C(0, -9, 14), C(0, 9, 14), ln(0, 23, 0, 28)]
    if t == "pcs":
        return 26, 32, [R(-28, -26, 56, 52), ln(-28, 26, 28, -26), T(-24, -14, "AC"), T(10, 20, "DC")]
    if t == "battery":
        return 26, 32, [R(-28, -26, 56, 52), R(-16, -6, 28, 14), R(12, -2, 4, 6), ln(-8, -2, -8, 4)]
    if t == "load":
        return 24, 18, [ln(0, -24, 0, -10), ("poly", [(-14, -10), (14, -10), (0, 16)], True)]
    if t == "pv":
        return 26, 28, [R(-26, -26, 52, 52), ln(-26, 26, 26, -26), C(-12, -12, 6)]
    if t in ("generator", "motor"):
        return 22, 24, [ln(0, -22, 0, -22), C(0, 0, 22), T(-5, 4, "G" if t == "generator" else "M")]
    return 0, 40, []  # bus


def _tf(p, dx, dy):
    k = p[0]
    if k == "line": return ("line", p[1] + dx, p[2] + dy, p[3] + dx, p[4] + dy, p[5])
    if k == "rect": return ("rect", p[1] + dx, p[2] + dy, p[3], p[4])
    if k == "circle": return ("circle", p[1] + dx, p[2] + dy, p[3])
    if k == "poly": return ("poly", [(a + dx, b + dy) for a, b in p[1]], p[2])
    if k == "text": return ("text", p[1] + dx, p[2] + dy) + tuple(p[3:])
    return p


def layout(df):
    N = {}
    for r in df.fillna("").astype(str).to_dict("records"):
        r = {k: v.strip() for k, v in r.items()}
        if r.get("id") and r.get("type") in TYPES and r["id"] not in N:
            N[r["id"]] = r
    for n in N.values(): n["kids"] = []
    roots = []
    for n in N.values():
        p = n.get("parent", "")
        (N[p]["kids"] if p in N and p != n["id"] else roots).append(n)

    def w(n):
        n["w"] = max(COLW, sum(w(k) for k in n["kids"]))
        return n["w"]

    def place(n, left, d):
        n["d"], x = d, left
        for k in n["kids"]:
            place(k, x, d + 1); x += k["w"]
        n["x"] = (n["kids"][0]["x"] + n["kids"][-1]["x"]) / 2 if n["kids"] else left + n["w"] / 2
        n["y"] = M + d * ROW
        n["hh"] = _sym(n["type"])[0]

    x = 0
    for r in roots:
        w(r); place(r, x, 0); x += r["w"]
    return roots, N


def primitives(df, title="Single Line Diagram", notes=(), rev="A", by=""):
    roots, N = layout(df)
    out = []
    for n in N.values():
        if "x" not in n: continue  # unreachable (cycle)
        t, x, y = n["type"], n["x"], n["y"]
        hh, hw, pr = _sym(t)
        if t == "bus":
            xs = [k["x"] for k in n["kids"]] + [x]
            x1, x2 = min(xs) - 40, max(xs) + 40
            out.append(ln(x1, y, x2, y, 5))
            out.append(("text", x1, y - 12, n["label"], 12, "b"))
            out.append(("text", x1, y + 20, f'{n["spec1"]}  {n["spec2"]}'.strip(), 11, ""))
        else:
            out += [_tf(p, x, y) for p in pr]
            tx = x + hw + 8
            for i, s in enumerate([n["label"], n["spec1"], n["spec2"]]):
                if s: out.append(("text", tx, y - 2 + 14 * i, s, 12 if i == 0 else 11, "b" if i == 0 else ""))
        kids = n["kids"]
        if not kids: continue
        if t == "bus":
            for k in kids:
                ky = k["y"] - k["hh"]
                out += [ln(k["x"], y, k["x"], ky), ("dot", k["x"], y)]
                if k["cable"]: out.append(("text", k["x"] + 6, (y + ky) / 2, k["cable"], 9, "i"))
        else:
            by_ = y + hh
            yb = by_ + (min(k["y"] - k["hh"] for k in kids) - by_) / 2
            out.append(ln(x, by_, x, yb))
            if len(kids) > 1:
                out.append(ln(kids[0]["x"], yb, kids[-1]["x"], yb)); out.append(("dot", x, yb))
            for k in kids:
                ky = k["y"] - k["hh"]
                out.append(ln(k["x"], yb, k["x"], ky))
                if k["cable"]: out.append(("text", k["x"] + 6, (yb + ky) / 2 + 8, k["cable"], 9, "i"))
    W = max([p[1] for p in out if p[0] in ("line", "text")] + [400]) + 200
    Hh = max([p[2] for p in out if p[0] in ("text", "dot")] + [200]) + 60 + 14 * len(notes) + 70
    for i, s in enumerate(notes): out.append(("text", 20, Hh - 90 - 14 * (len(notes) - 1 - i), s, 11, ""))
    tb = [("rect", W - 330, Hh - 70, 310, 56), ("line", W - 330, Hh - 42, W - 20, Hh - 42, 1),
          ("text", W - 322, Hh - 50, title, 13, "b"), ("text", W - 322, Hh - 26, f"Rev {rev}   Drawn: {by}", 10, "")]
    return out + tb, W, Hh


def to_svg(pr, W, H, scale=1.0):
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W*scale:.0f}" height="{H*scale:.0f}">'
         '<rect width="100%" height="100%" fill="#fff"/><g stroke="#111" fill="none" stroke-width="2" stroke-linecap="round" font-family="Arial,sans-serif">']
    for p in pr:
        k = p[0]
        if k == "line": s.append(f'<line x1="{p[1]}" y1="{p[2]}" x2="{p[3]}" y2="{p[4]}" stroke-width="{p[5]}"/>')
        elif k == "rect": s.append(f'<rect x="{p[1]}" y="{p[2]}" width="{p[3]}" height="{p[4]}"/>')
        elif k == "circle": s.append(f'<circle cx="{p[1]}" cy="{p[2]}" r="{p[3]}"/>')
        elif k == "dot": s.append(f'<circle cx="{p[1]}" cy="{p[2]}" r="3.5" fill="#111"/>')
        elif k == "poly":
            pts = " ".join(f"{a},{b}" for a, b in p[1])
            s.append(f'<{"polygon" if p[2] else "polyline"} points="{pts}"/>')
        elif k == "text":
            t = p[3].replace("&", "&amp;").replace("<", "&lt;")
            fw = ' font-weight="bold"' if "b" in p[5] else ""
            fs = ' font-style="italic"' if "i" in p[5] else ""
            s.append(f'<text x="{p[1]}" y="{p[2]}" font-size="{p[4]}" fill="#111" stroke="none"{fw}{fs}>{t}</text>')
    return "".join(s) + "</g></svg>"


def to_dxf(pr, H):
    import ezdxf
    d = ezdxf.new("R2010"); m = d.modelspace()
    for p in pr:
        k = p[0]
        if k == "line": m.add_line((p[1], H - p[2]), (p[3], H - p[4]))
        elif k == "rect":
            x, y, w, h = p[1:5]
            m.add_lwpolyline([(x, H - y), (x + w, H - y), (x + w, H - y - h), (x, H - y - h)], close=True)
        elif k == "circle": m.add_circle((p[1], H - p[2]), p[3])
        elif k == "dot": m.add_circle((p[1], H - p[2]), 3)
        elif k == "poly": m.add_lwpolyline([(a, H - b) for a, b in p[1]], close=p[2])
        elif k == "text": m.add_text(p[3], dxfattribs={"height": p[4], "insert": (p[1], H - p[2])})
    s = io.StringIO(); d.write(s)
    return s.getvalue()


def check(df):
    """Simple rules check; returns list of warning strings."""
    w, d = [], df.fillna("").astype(str)
    ids = d["id"].str.strip()
    for i in ids[ids.duplicated() & (ids != "")].unique(): w.append(f"Duplicate id: {i}")
    T = dict(zip(ids, d["type"].str.strip()))
    for _, r in d.iterrows():
        i, t, p = r["id"].strip(), r["type"].strip(), r["parent"].strip()
        if not i: continue
        if t not in TYPES: w.append(f"{i}: unknown type '{t}'")
        if p and p not in T: w.append(f"{i}: parent '{p}' not found")
        if not p and t not in ("grid", "generator", "pv"): w.append(f"{i}: {t} has no source (parent)")
        if t == "battery" and T.get(p) != "pcs": w.append(f"{i}: battery should connect to a PCS")
        if t == "pcs" and T.get(p) not in ("breaker", "bus", "transformer"): w.append(f"{i}: PCS should be fed via breaker/bus/transformer")
        if T.get(p) in ("load", "battery", "pv", "motor"): w.append(f"{i}: fed from a terminal device ({p})")
    return w


def bess_df(MW, MWh, pm, cm, mv, lv, grid_kv, pf=0.95, isc=25.0, max_draw=4, aux_kva=250):
    """Generate node table + summary for an AC-coupled BESS plant."""
    B = math.ceil(MW / pm); per = math.ceil(MWh / B / cm); nd = min(B, max_draw)
    mva = nxt(pm / pf, STD_MVA)
    i_mv = mva * 1e3 / (math.sqrt(3) * mv); i_lv = mva * 1e3 / (math.sqrt(3) * lv)
    i_tot = B * i_mv; plant_mva = B * mva
    rows = []
    a = lambda *r: rows.append(dict(zip(COLS, r)))
    a("G", "grid", "Grid", f"{grid_kv:g} kV", f"Isc {isc:g} kA", "", "")
    up = "G"
    if abs(grid_kv - mv) > 1e-6:
        hv_mva = nxt(plant_mva * 1.0, STD_MVA)
        a("HVCB", "breaker", "HV CB", f"{grid_kv:g} kV", f"In {nxt(1.25*hv_mva*1e3/(math.sqrt(3)*grid_kv), STD_A)} A", "", up)
        a("TRHV", "transformer", "TR-HV", f"{hv_mva:g} MVA", f"{grid_kv:g}/{mv:g} kV YNd11", "", "HVCB"); up = "TRHV"
    a("MCB", "breaker", "Main CB", f"{mv:g} kV", f"In {nxt(1.25*i_tot, STD_A)} A", "", up)
    a("MVB", "bus", "MV Bus", f"{mv:g} kV", f"{nxt(1.25*i_tot, STD_A)} A, {isc:g} kA", "", "MCB")
    for k in range(1, nd + 1):
        a(f"VCB{k}", "breaker", f"VCB-{k}", f"{mv:g} kV", f"In {nxt(1.25*i_mv, STD_A)} A", f"I = {i_mv:.0f} A", "MVB")
        a(f"TR{k}", "transformer", f"TR-{k}", f"{mva:g} MVA", f"{mv:g}/{lv:g} kV Dyn11", "", f"VCB{k}")
        a(f"ACB{k}", "breaker", f"ACB-{k}", f"{lv:g} kV", f"In {nxt(1.25*i_lv, STD_A)} A", f"I = {i_lv:.0f} A", f"TR{k}")
        a(f"PCS{k}", "pcs", f"PCS-{k}", f"{pm:g} MW", f"AC {lv:g} kV", "", f"ACB{k}")
        a(f"BESS{k}", "battery", f"BESS-{k}", f"{per} x {cm:g} MWh", "LFP, 1500 V DC", "", f"PCS{k}")
    if aux_kva > 0:
        a("AUXCB", "breaker", "AUX CB", f"{mv:g} kV", "In 63 A", "", "MVB")
        a("AUXTR", "transformer", "AUX TR", f"{aux_kva:g} kVA", f"{mv:g}/0.415 kV", "", "AUXCB")
        a("AUXB", "bus", "LV Aux Bus", "415 V", "", "", "AUXTR")
        a("HVAC", "load", "HVAC / Fire", "", "", "", "AUXB"); a("LTG", "load", "Lighting / SCADA", "", "", "", "AUXB")
    summ = dict(blocks=B, containers_per_pcs=per, containers=B * per, installed_mwh=B * per * cm, tr_mva=mva,
                i_mv_block=i_mv, i_lv_block=i_lv, i_mv_total=i_tot, plant_mva=plant_mva, drawn=nd)
    notes = [f"{MW:g} MW / {MWh:g} MWh BESS: {B} PCS blocks x {pm:g} MW, {B*per} containers x {cm:g} MWh = {B*per*cm:.1f} MWh installed"]
    if B > nd: notes.append(f"Representative drawing: {nd} of {B} identical blocks shown")
    return pd.DataFrame(rows, columns=COLS), summ, notes


def example_lv():
    r = [("G", "grid", "Utility", "11 kV", "Isc 20 kA", "", ""), ("CB1", "breaker", "VCB", "11 kV", "In 400 A", "", "G"),
         ("T1", "transformer", "T1", "1.6 MVA", "11/0.415 kV Dyn11", "", "CB1"), ("ACB", "breaker", "ACB", "415 V", "In 2500 A", "", "T1"),
         ("MDB", "bus", "MDB", "415 V", "2500 A, 50 kA", "", "ACB"), ("F1", "breaker", "MCCB-1", "400 A", "", "3C x 240 sqmm", "MDB"),
         ("M1", "motor", "Pump", "90 kW", "", "", "F1"), ("F2", "breaker", "MCCB-2", "250 A", "", "3C x 120 sqmm", "MDB"),
         ("L1", "load", "Lighting", "120 kW", "", "", "F2"), ("DG", "generator", "DG Set", "500 kVA", "", "", "MDB")]
    return pd.DataFrame(r, columns=COLS)
