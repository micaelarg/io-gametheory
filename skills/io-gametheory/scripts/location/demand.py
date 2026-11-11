# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.31", "pandas>=2.1", "numpy>=1.26"]
# ///
"""Demand points (lat, lon, weight) for location models.

Three modes, best first:
  --from-csv census.csv    Census small areas (e.g. INDEC radios censales centroids) with a
                           population/households column (--weight-col). Best option.
  --osm-buildings          Proxy from OSM residential buildings around a point: dwellings
                           estimated from building type and levels, aggregated to a grid.
                           Use --population-total to scale to a known population.
  --osm-streets            Proxy from the length of residential streets per grid cell. OSM street
                           coverage is near-complete almost everywhere, so this beats the building
                           proxy wherever buildings are poorly mapped (e.g. most Latin American cities).
                           Assumes population ∝ street frontage: wrong for parks, rail yards, industry.
  --uniform                Uniform grid (last resort; only shows geometry, not demand).

Output CSV: lat, lon, weight  (+ dwellings for the OSM mode).
Always state in the analysis which mode was used; the OSM proxy is weak where building
data is incomplete or where tall apartment blocks lack 'building:levels'.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import haversine_km, overpass, read_points  # noqa: E402

UNITS_PER_LEVEL = {"apartments": 4.0, "residential": 2.0, "house": 1.0, "detached": 1.0,
                   "semidetached_house": 1.0, "terrace": 1.0, "bungalow": 1.0, "dormitory": 6.0}
RESIDENTIAL = set(UNITS_PER_LEVEL)


def grid_aggregate(lat, lon, w, cell_m, lat0):
    dlat = cell_m / 111_320.0
    dlon = cell_m / (111_320.0 * np.cos(np.radians(lat0)))
    gi, gj = np.floor(lat / dlat).astype(int), np.floor(lon / dlon).astype(int)
    df = pd.DataFrame({"gi": gi, "gj": gj, "w": w})
    agg = df.groupby(["gi", "gj"], as_index=False)["w"].sum()
    agg["lat"] = (agg.gi + 0.5) * dlat
    agg["lon"] = (agg.gj + 0.5) * dlon
    return agg[["lat", "lon", "w"]].rename(columns={"w": "weight"})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    m = ap.add_mutually_exclusive_group(required=True)
    m.add_argument("--from-csv")
    m.add_argument("--osm-buildings", action="store_true")
    m.add_argument("--osm-streets", action="store_true")
    m.add_argument("--uniform", action="store_true")
    ap.add_argument("--weight-col", default="population")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--radius", type=float, default=2000, help="meters")
    ap.add_argument("--cell", type=float, default=150, help="grid cell size in meters (default 150)")
    ap.add_argument("--population-total", type=float, help="scale weights to sum to this population")
    ap.add_argument("--persons-per-dwelling", type=float, default=2.6,
                    help="AR Censo 2022 ≈ 2.6-2.8; CABA ≈ 2.2 (assumption)")
    ap.add_argument("--out", default="demand.csv")
    a = ap.parse_args()

    if a.from_csv:
        df = read_points(a.from_csv, need=("lat", "lon", a.weight_col.lower()))
        out = df[["lat", "lon", a.weight_col.lower()]].rename(columns={a.weight_col.lower(): "weight"})
        src = f"census CSV `{a.from_csv}` (column {a.weight_col})"
    else:
        if a.lat is None or a.lon is None:
            sys.exit("--lat and --lon required for --osm-buildings / --osm-streets / --uniform")
        if a.osm_streets:
            q = (f"[out:json][timeout:180];(way[\"highway\"~\"^(residential|living_street|unclassified|tertiary|"
                 f"secondary|primary)$\"](around:{int(a.radius)},{a.lat},{a.lon}););out geom tags;")
            els = overpass(q, timeout=240).get("elements", [])
            wt = {"residential": 1.0, "living_street": 1.0, "unclassified": 0.8,
                  "tertiary": 1.2, "secondary": 1.2, "primary": 1.2}
            la, lo, ww = [], [], []
            for el in els:
                g = el.get("geometry") or []
                f = wt.get(el.get("tags", {}).get("highway"), 1.0)
                for p0, p1 in zip(g[:-1], g[1:]):
                    seg = haversine_km([p0["lat"]], [p0["lon"]], [p1["lat"]], [p1["lon"]])[0, 0]
                    la.append((p0["lat"] + p1["lat"]) / 2); lo.append((p0["lon"] + p1["lon"]) / 2); ww.append(seg * f)
            if not ww:
                sys.exit("No streets found. Check coordinates.")
            out = grid_aggregate(np.array(la), np.array(lo), np.array(ww), a.cell, a.lat)
            src = (f"OSM street-frontage proxy: {len(els)} street ways, {sum(ww):.1f} weighted km "
                   "(avenues ×1.2 - assumption); weight ∝ street length per cell")
        elif a.uniform:
            n = int(2 * a.radius / a.cell) + 1
            dlat = a.radius / 111_320.0
            dlon = a.radius / (111_320.0 * np.cos(np.radians(a.lat)))
            LA, LO = np.meshgrid(np.linspace(a.lat - dlat, a.lat + dlat, n), np.linspace(a.lon - dlon, a.lon + dlon, n))
            out = pd.DataFrame({"lat": LA.ravel(), "lon": LO.ravel(), "weight": 1.0})
            src = "uniform grid (NO demand information - geometry only)"
        else:
            q = (f"[out:json][timeout:180];(way[\"building\"](around:{int(a.radius)},{a.lat},{a.lon}););"
                 "out center tags;")
            els = overpass(q, timeout=240).get("elements", [])
            rows = []
            for el in els:
                t = el.get("tags", {})
                b = t.get("building", "yes")
                c = el.get("center")
                if not c:
                    continue
                try:
                    lv = float(str(t.get("building:levels", "")).split(";")[0])
                except ValueError:
                    lv = np.nan
                if b in RESIDENTIAL:
                    units = UNITS_PER_LEVEL[b] * (lv if lv == lv else (4 if b == "apartments" else 1))
                elif b == "yes" and not any(k in t for k in ("shop", "amenity", "office", "industrial")):
                    units = 1.0 * (lv if lv == lv else 1)  # untyped building: weak proxy
                else:
                    continue
                if "flats" in t:
                    try:
                        units = float(t["flats"])
                    except ValueError:
                        pass
                rows.append((c["lat"], c["lon"], units, b, lv == lv))
            if not rows:
                sys.exit("No buildings in OSM here. Use --from-csv with census data or --uniform.")
            b = pd.DataFrame(rows, columns=["lat", "lon", "dwellings", "type", "has_levels"])
            b["persons"] = b.dwellings * a.persons_per_dwelling
            out = grid_aggregate(b.lat.values, b.lon.values, b.persons.values, a.cell, a.lat)
            area_km2 = np.pi * (a.radius / 1000) ** 2
            density = len(b) / area_km2
            share_typed = (b.type != "yes").mean()
            share_levels = b.has_levels.mean()
            src = (f"OSM buildings proxy: {len(b)} buildings, {share_typed:.0%} with residential type, "
                   f"{share_levels:.0%} with levels; {a.persons_per_dwelling} persons/dwelling (assumption)")
            if density < 800 and share_levels < 0.5:
                src += (f"\n- ❌ Only {density:.0f} residential buildings/km² mapped - far below any real city "
                        "and few have floor counts: OSM buildings look INCOMPLETE here. Compare with --osm-streets and a population grid "
                        "(Kontur/GHSL); prefer whichever matches census totals. "
                        "Use --from-csv with census data, or --osm-streets.")
        d = haversine_km([a.lat], [a.lon], out.lat, out.lon)[0]
        out = out[d <= a.radius / 1000.0].reset_index(drop=True)

    if a.population_total:
        out["weight"] *= a.population_total / out.weight.sum()
    out.to_csv(a.out, index=False)
    print(f"# Demand points → `{a.out}`\n")
    print(f"- Source: {src}")
    print(f"- Points: {len(out)}, total weight {out.weight.sum():,.0f}")
    if (a.osm_buildings or a.osm_streets) and not a.population_total:
        print("- ⚠ Weights are an OSM-based population proxy. If the true population of the area is known "
              "(census), rerun with --population-total to calibrate the level; the spatial pattern is what matters for shares.")


if __name__ == "__main__":
    main()
