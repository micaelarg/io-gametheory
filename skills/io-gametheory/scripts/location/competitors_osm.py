# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.31", "pandas>=2.1", "numpy>=1.26"]
# ///
"""Competitors around a point from OpenStreetMap (Overpass API).

Examples:
  uv run competitors_osm.py --lat -34.598 --lon -58.443 --radius 1500 --tag shop=supermarket --tag shop=convenience --out rivals.csv
  uv run competitors_osm.py --lat ... --lon ... --radius 800 --tag amenity=pharmacy

Output CSV columns: id, name, brand, operator, tag, lat, lon, dist_km, opening_hours, address.
Use it directly as --stores for huff.py (adds attractiveness=1; edit it with floor area if known).

Caveat: OSM coverage varies. Small independent stores are often missing. Verify the count
against Google Maps / Street View for the area and say how complete the list looks.
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import haversine_km, overpass  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--radius", type=float, default=1500, help="meters (default 1500)")
    ap.add_argument("--tag", action="append", required=True, help="key=value, repeatable (e.g. shop=supermarket)")
    ap.add_argument("--out", default="competitors.csv")
    a = ap.parse_args()

    parts = []
    for t in a.tag:
        k, _, v = t.partition("=")
        sel = f'["{k}"="{v}"]' if v else f'["{k}"]'
        parts.append(f"nwr{sel}(around:{int(a.radius)},{a.lat},{a.lon});")
    q = f"[out:json][timeout:120];({''.join(parts)});out center tags;"
    data = overpass(q)

    rows = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None:
            continue
        which = next((t for t in a.tag if tags.get(t.partition("=")[0]) == t.partition("=")[2]
                      or (not t.partition("=")[2] and t in tags)), a.tag[0])
        addr = " ".join(x for x in [tags.get("addr:street", ""), tags.get("addr:housenumber", "")] if x)
        rows.append({"id": f"{el['type'][0]}{el['id']}", "name": tags.get("name", ""), "brand": tags.get("brand", ""),
                     "operator": tags.get("operator", ""), "tag": which, "lat": lat, "lon": lon,
                     "opening_hours": tags.get("opening_hours", ""), "address": addr})
    df = pd.DataFrame(rows)
    if df.empty:
        print(f"No features found for {a.tag} within {a.radius:.0f} m. OSM may be incomplete here - verify manually.")
        df = pd.DataFrame(columns=["id", "name", "brand", "operator", "tag", "lat", "lon", "dist_km",
                                   "opening_hours", "address", "attractiveness"])
        df.to_csv(a.out, index=False)
        return
    df["dist_km"] = haversine_km([a.lat], [a.lon], df.lat, df.lon)[0].round(3)
    df["attractiveness"] = 1.0
    df = df.sort_values("dist_km").reset_index(drop=True)
    df.to_csv(a.out, index=False)

    print(f"# Competitors within {a.radius:.0f} m of ({a.lat}, {a.lon})\n")
    print(f"- Found **{len(df)}** features for {', '.join(a.tag)} → `{a.out}`")
    label = df.brand.where(df.brand != "", df.name).replace("", "(unnamed)")
    print("- By brand/name: " + ", ".join(f"{k} {v}" for k, v in label.value_counts().head(12).items()))
    unnamed = (df.name == "").sum()
    if unnamed:
        print(f"- ⚠ {unnamed} without name - weaker data quality.")
    print(f"- Nearest: {df.iloc[0]['name'] or '(unnamed)'} at {df.iloc[0]['dist_km']*1000:.0f} m")
    print("\n| # | name | brand | tag | dist (m) |\n|---|---|---|---|---|")
    for i, r in df.head(25).iterrows():
        print(f"| {i+1} | {r['name']} | {r['brand']} | {r['tag']} | {r['dist_km']*1000:.0f} |")
    print("\n_Attractiveness set to 1 for all. Replace with floor area (m²) or a brand index if known; "
          "verify completeness against Google Maps._")


if __name__ == "__main__":
    main()
