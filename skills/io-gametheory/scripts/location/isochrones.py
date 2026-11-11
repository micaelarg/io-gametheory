# /// script
# requires-python = ">=3.10"
# dependencies = ["osmnx>=2.0", "networkx>=3.2", "scikit-learn>=1.4", "geopandas>=0.14", "shapely>=2.0", "pandas>=2.1", "numpy>=1.26"]
# ///
"""Walk / drive isochrones on the real OSM street network, and the demand they cover.

  uv run isochrones.py --lat -34.598 --lon -58.443 --minutes 5,10,15 --mode walk --demand demand.csv --out iso.geojson
  uv run isochrones.py --sites candidates.csv --minutes 10 --mode walk --demand demand.csv --out iso.geojson

Walk = 4.8 km/h. Drive = osmnx imputed free-flow speeds (no traffic: optimistic at rush hour).
Output GeoJSON (one polygon per site × minutes) with properties: site, minutes, mode, demand.
Isochrones that overlap between candidates show where they would compete for the same customers.
"""
from __future__ import annotations

import argparse
import os
import sys

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import osm_graph, read_points, snap_bbox  # noqa: E402

WALK_MS = 4.8 / 3.6


def build_graph(lats, lons, max_min, mode):
    """One network covering every site plus the maximum reach (downloaded once, cached)."""
    reach_km = max_min * 60 * (WALK_MS if mode == "walk" else 14.0) * 1.15 / 1000
    dlat = reach_km / 111.0
    dlon = reach_km / (111.0 * np.cos(np.radians(np.mean(lats))))
    bbox = (min(lons) - dlon, min(lats) - dlat, max(lons) + dlon, max(lats) + dlat)
    G = osm_graph(ox.graph_from_bbox, snap_bbox(*bbox), network_type="walk" if mode == "walk" else "drive")
    if mode == "walk":
        for *_, d in G.edges(keys=True, data=True):
            d["travel_time"] = d["length"] / WALK_MS
        G = G.to_undirected()
    else:
        G = ox.add_edge_speeds(G)
        G = ox.add_edge_travel_times(G)
    return G


def isochrone(G, lat, lon, minutes, mode):
    src = ox.distance.nearest_nodes(G, X=lon, Y=lat)
    sub = nx.ego_graph(G, src, radius=minutes * 60, distance="travel_time")
    if sub.number_of_edges() == 0:
        return None
    edges = ox.projection.project_gdf(ox.graph_to_gdfs(sub, nodes=False))
    poly = shapely.union_all(edges.geometry.buffer(50 if mode == "walk" else 80).values)
    # fill holes (city blocks inside the reachable area) and drop slivers
    parts = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
    parts = [shapely.Polygon(p.exterior) for p in parts if p.area > 2e4]
    poly = shapely.simplify(shapely.union_all(parts), 15)
    return gpd.GeoSeries([poly], crs=edges.crs).to_crs(4326).iloc[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--sites", help="CSV with id, lat, lon (one isochrone set per site)")
    ap.add_argument("--minutes", default="5,10,15")
    ap.add_argument("--mode", choices=["walk", "drive"], default="walk")
    ap.add_argument("--demand", help="demand CSV (lat, lon, weight) to count coverage")
    ap.add_argument("--out", default="isochrones.geojson")
    a = ap.parse_args()

    mins = sorted(float(m) for m in a.minutes.split(","))
    if a.sites:
        sites = read_points(a.sites)
        if "id" not in sites.columns:
            sites["id"] = [f"site{i}" for i in range(len(sites))]
    elif a.lat is not None:
        sites = pd.DataFrame({"id": ["site"], "lat": [a.lat], "lon": [a.lon]})
    else:
        sys.exit("Give --lat/--lon or --sites.")
    dem = read_points(a.demand, need=("lat", "lon", "weight")) if a.demand else None

    feats = []
    G = build_graph(sites.lat.tolist(), sites.lon.tolist(), max(mins), a.mode)
    for _, s in sites.iterrows():
        for m in mins:
            poly = isochrone(G, s.lat, s.lon, m, a.mode)
            if poly is None:
                continue
            cov = np.nan
            if dem is not None:
                inside = shapely.contains_xy(poly, dem.lon.values, dem.lat.values)
                cov = float(dem.weight.values[inside].sum())
            feats.append({"site": str(s["id"]), "minutes": m, "mode": a.mode, "demand": cov, "geometry": poly})
    gdf = gpd.GeoDataFrame(feats, crs=4326)
    gdf.to_file(a.out, driver="GeoJSON")

    print(f"# Isochrones ({a.mode}) → `{a.out}`\n")
    print("| site | " + " | ".join(f"{m:g} min" for m in mins) + " |")
    print("|---|" + "---|" * len(mins))
    for sid, grp in gdf.groupby("site", sort=False):
        vals = []
        for m in mins:
            r = grp[grp.minutes == m]
            if r.empty:
                vals.append("-")
            elif dem is not None:
                vals.append(f"{r.demand.iloc[0]:,.0f}")
            else:
                area = gpd.GeoSeries([r.geometry.iloc[0]], crs=4326).to_crs(3857).area.iloc[0] / 1e6
                vals.append(f"{area:.2f} km²")
        print(f"| {sid} | " + " | ".join(vals) + " |")
    if dem is not None:
        print("\nCells = demand weight inside each isochrone (cumulative).")
    if len(sites) > 1 and dem is not None:
        m = mins[-1]
        polys = gdf[gdf.minutes == m].set_index("site").geometry
        ids = list(polys.index)
        print(f"\n## Overlap of {m:g}-minute catchments (shared demand)\n")
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                inter = polys.iloc[i].intersection(polys.iloc[j])
                if inter.is_empty:
                    continue
                inside = shapely.contains_xy(inter, dem.lon.values, dem.lat.values)
                print(f"- {ids[i]} ∩ {ids[j]}: {dem.weight.values[inside].sum():,.0f}")
    print("\n_Drive times are free-flow (no traffic). Walk 4.8 km/h. Network from OpenStreetMap._")


if __name__ == "__main__":
    main()
