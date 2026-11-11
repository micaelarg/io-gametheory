# /// script
# requires-python = ">=3.10"
# dependencies = ["folium>=0.15", "pandas>=2.1", "numpy>=1.26", "branca>=0.7"]
# ///
"""Interactive location map (Folium / Leaflet, OpenStreetMap tiles).

Layers (each optional, toggleable):
  --demand points.csv       heat map of demand (weight) - or of captured demand if the CSV has 'captured'
  --stores rivals.csv       competitors (grey) and own stores (blue, with --owner)
  --candidates results.csv  candidate sites coloured by score (column --score, e.g. net / profit / captured)
                            needs lat, lon: if the results CSV lacks them, pass --candidates-geo with id, lat, lon
  --isochrones iso.geojson  catchment polygons from isochrones.py
  --annotate "lat,lon,text" free annotations (repeatable): e.g. where the rival would answer

  uv run map.py --demand demand.csv --stores rivals.csv --owner Us --candidates huff_results.csv \
      --candidates-geo candidates.csv --score net --isochrones iso.geojson --title "Dónde abrir" --out map.html

The map is the picture of a location game: annotate it so the reader finds the answer in 3 seconds.
"""
from __future__ import annotations

import argparse
import html
import json

import folium
import numpy as np
import pandas as pd
from branca.colormap import LinearColormap
from folium.plugins import HeatMap


def read(path):
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    return df.rename(columns={"latitude": "lat", "longitude": "lon", "lng": "lon"})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demand")
    ap.add_argument("--stores")
    ap.add_argument("--owner", help="our chain (blue)")
    ap.add_argument("--rival", help="a named rival chain to highlight (red)")
    ap.add_argument("--candidates")
    ap.add_argument("--candidates-geo")
    ap.add_argument("--score", default="net")
    ap.add_argument("--isochrones")
    ap.add_argument("--annotate", action="append", default=[])
    ap.add_argument("--title", default="Location analysis")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--out", default="map.html")
    a = ap.parse_args()

    pts = []
    layers = {}
    dem = read(a.demand) if a.demand else None
    st = read(a.stores) if a.stores else None
    ca = None
    if a.candidates:
        ca = read(a.candidates)
        if a.candidates_geo:
            geo = read(a.candidates_geo)
            geo["id"] = geo["id"].astype(str)
            ca["id"] = ca["id"].astype(str)
            ca = ca.drop(columns=[c for c in ("lat", "lon") if c in ca.columns]).merge(geo[["id", "lat", "lon"]], on="id")
    for df in (dem, st, ca):
        if df is not None and len(df):
            pts.append(df[["lat", "lon"]].values)
    if not pts:
        raise SystemExit("Nothing to map.")
    allp = np.vstack(pts)
    m = folium.Map(location=allp.mean(axis=0).tolist(), zoom_start=14, tiles="openstreetmap", control_scale=True)

    if dem is not None:
        col = "captured" if "captured" in dem.columns else "weight"
        fg = folium.FeatureGroup(name=f"Demand ({col})")
        mx = dem[col].max() or 1
        HeatMap(dem[["lat", "lon", col]].assign(**{col: dem[col] / mx}).values.tolist(),
                radius=14, blur=18, min_opacity=0.05, max_zoom=13,
                gradient={0.2: "#fde68a", 0.5: "#f59e0b", 0.8: "#ef4444", 1.0: "#991b1b"}).add_to(fg)
        fg.add_to(m)

    if a.isochrones:
        gj = json.load(open(a.isochrones))
        fg = folium.FeatureGroup(name="Catchments (isochrones)")
        mins = sorted({f["properties"].get("minutes") for f in gj["features"]})
        palette = ["#2563eb", "#7c3aed", "#db2777", "#ea580c"]
        for f in sorted(gj["features"], key=lambda f: -f["properties"].get("minutes", 0)):
            p = f["properties"]
            c = palette[mins.index(p.get("minutes")) % len(palette)]
            tip = f"{p.get('site')}: {p.get('minutes'):g} min {p.get('mode', '')}"
            if p.get("demand") is not None and p.get("demand") == p.get("demand"):
                tip += f" - demand {p['demand']:,.0f}"
            folium.GeoJson(f, style_function=lambda _x, c=c: {"color": c, "weight": 2, "fillOpacity": 0.04, "dashArray": "4 3"},
                           tooltip=tip).add_to(fg)
        fg.add_to(m)

    if st is not None and len(st):
        fg = folium.FeatureGroup(name="Existing stores")
        own_col = st["owner"] if "owner" in st.columns else st.get("brand", pd.Series([""] * len(st)))
        for i, r in st.iterrows():
            own = bool(a.owner) and str(own_col.iloc[i]).lower() == a.owner.lower()
            riv = bool(a.rival) and (str(own_col.iloc[i]).lower() == a.rival.lower()
                                     or a.rival.lower() in str(r.get("brand", "")).lower()
                                     or a.rival.lower() in str(r.get("name", "")).lower())
            name = r.get("name") if isinstance(r.get("name"), str) and r.get("name") else r.get("id", "")
            brand = r.get("brand") if isinstance(r.get("brand"), str) else ""
            folium.CircleMarker([r.lat, r.lon], radius=7 if (own or riv) else 6,
                                color="#1d4ed8" if own else "#b91c1c" if riv else "#374151", fill=True,
                                fill_color="#3b82f6" if own else "#ef4444" if riv else "#9ca3af", fill_opacity=0.9,
                                tooltip=html.escape(f"{'OWN · ' if own else 'RIVAL · ' if riv else ''}{name} {('· ' + brand) if brand else ''}")
                                ).add_to(fg)
        fg.add_to(m)

    if ca is not None and len(ca):
        fg = folium.FeatureGroup(name="Candidate sites")
        sc = a.score if a.score in ca.columns else None
        if sc:
            cm = LinearColormap(["#dc2626", "#f59e0b", "#16a34a"], vmin=ca[sc].min(), vmax=ca[sc].max(),
                                caption=f"Candidate score ({sc})")
            cm.add_to(m)
            ca = ca.sort_values(sc, ascending=False).reset_index(drop=True)
        for i, r in ca.iterrows():
            color = cm(r[sc]) if sc else "#16a34a"
            info = "<br>".join(f"<b>{html.escape(str(k))}</b>: {v:,.0f}" if isinstance(v, (int, float, np.floating)) and k not in ("lat", "lon")
                               else f"<b>{html.escape(str(k))}</b>: {html.escape(str(v))}"
                               for k, v in r.items() if k not in ("lat", "lon"))
            folium.Marker([r.lat, r.lon], popup=folium.Popup(info, max_width=320),
                          tooltip=f"#{i+1} {r.get('id', '')}" + (f" · {sc} {r[sc]:,.0f}" if sc else ""),
                          icon=folium.DivIcon(html=f'<div style="background:{color};color:white;border:2px solid white;'
                                                   f'border-radius:50%;width:26px;height:26px;text-align:center;'
                                                   f'font:bold 13px/22px sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.5)">{i+1}</div>',
                                              icon_size=(26, 26), icon_anchor=(13, 13))).add_to(fg)
        fg.add_to(m)

    for ann in a.annotate:
        lat, lon, text = ann.split(",", 2)
        folium.Marker([float(lat), float(lon)], tooltip=text,
                      icon=folium.DivIcon(html=f'<div style="font:600 12px sans-serif;color:#7f1d1d;background:#fff7ed;'
                                               f'border:1px solid #fdba74;border-radius:6px;padding:3px 6px;white-space:nowrap">'
                                               f'{html.escape(text)}</div>')).add_to(m)

    title = (f'<div style="position:fixed;top:12px;left:56px;z-index:9999;background:white;padding:10px 14px;'
             f'border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,.2);font-family:system-ui,sans-serif;max-width:min(520px,70vw)">'
             f'<div style="font-weight:700;font-size:16px">{html.escape(a.title)}</div>'
             f'<div style="font-size:12px;color:#4b5563;margin-top:3px">{html.escape(a.subtitle)}</div>'
             f'<div style="font-size:11px;color:#6b7280;margin-top:6px">● grey = other stores'
             + (f' · ● blue = {html.escape(a.owner)}' if a.owner else '') + (f' · ● red = {html.escape(a.rival)}' if a.rival else '')
             + ' · numbered = candidates (green best) · heat = demand</div></div>')
    m.get_root().html.add_child(folium.Element(title))
    folium.LayerControl(collapsed=True).add_to(m)
    m.fit_bounds([allp.min(axis=0).tolist(), allp.max(axis=0).tolist()])
    m.save(a.out)
    # pin CDN assets to versioned npm/cdnjs URLs and drop unused ones (portable, works under strict content-security policies)
    txt = open(a.out).read()
    txt = txt.replace("https://cdn.jsdelivr.net/gh/python-visualization/folium@main/folium/templates/leaflet_heat.min.js",
                      "https://cdn.jsdelivr.net/npm/leaflet.heat@0.2.0/dist/leaflet-heat.js")
    import re
    txt = re.sub(r'\s*<link[^>]+(bootstrap-glyphicons|leaflet\.awesome\.rotate)[^>]*>', "", txt)
    open(a.out, "w").write(txt)
    print(f"Map saved → `{a.out}` (open in a browser; it is a single self-contained page you can share).")


if __name__ == "__main__":
    main()
