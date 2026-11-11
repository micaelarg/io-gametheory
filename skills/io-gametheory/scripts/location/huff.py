# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas>=2.1", "numpy>=1.26", "osmnx>=2.0", "networkx>=3.2", "scikit-learn>=1.4", "requests>=2.31"]
# ///
"""Huff gravity model: market shares, demand captured by candidate sites, cannibalization,
and robustness of the ranking to the distance-decay parameter β.

  P_ij = A_j^α d_ij^-β / (Σ_k A_k^α d_ik^-β + O)        O = outside option (default 0)

Inputs (CSV):
  --demand      lat, lon, weight                       (demand.py)
  --stores      id, name, lat, lon, attractiveness [, owner | brand]   (competitors_osm.py)
  --candidates  id, lat, lon [, attractiveness, rent]
Options:
  --owner NAME          stores whose owner/brand == NAME are ours → cannibalization is netted out
  --distance euclid|network   network = OSM street travel time in minutes (--mode walk|drive)
  --beta 2 --beta-sweep 1,1.5,2,2.5,3 --alpha 1
  --outside O           outside option (online, other formats); >0 lets a new store expand the market
  --spend S --margin M  money per unit of weight per period, and gross margin → profit = net·S·M − rent
  --out results.csv  --out-points points.csv (per-point probability of choosing the best candidate)

Distances: euclid is great-circle km (floor 0.05 km); network is minutes (floor 1 min).
β values are on different scales for km vs minutes: always sweep.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import haversine_km, network_times, read_points  # noqa: E402


def huff_probs(D, attract, alpha, beta, outside=0.0):
    """D: (n_points, n_sites) distances; attract: (n_sites,). Returns probabilities (n_points, n_sites)."""
    U = (np.asarray(attract, float) ** alpha)[None, :] * np.power(D, -beta)
    U = np.where(np.isfinite(D), U, 0.0)
    den = U.sum(axis=1, keepdims=True) + outside
    return np.divide(U, den, out=np.zeros_like(U), where=den > 0)


def distances(dem, sites, how, mode):
    if how == "network":
        T, _ = network_times(dem.lat, dem.lon, sites.lat, sites.lon, mode=mode)
        return np.maximum(T, 1.0), "minutes"
    return np.maximum(haversine_km(dem.lat, dem.lon, sites.lat, sites.lon), 0.05), "km"


def evaluate(dem, stores, cands, D_all, beta, alpha, outside, own_mask):
    """For each candidate added alone: captured, stolen by store, cannibalized, net."""
    ns = len(stores)
    w = dem.weight.values
    A_st = stores.attractiveness.values
    base_P = huff_probs(D_all[:, :ns], A_st, alpha, beta, outside)
    base_dem = w @ base_P
    rows = []
    for c in range(len(cands)):
        cols = list(range(ns)) + [ns + c]
        A = np.concatenate([A_st, [cands.attractiveness.values[c]]])
        P = huff_probs(D_all[:, cols], A, alpha, beta, outside)
        dem_new = w @ P
        captured = dem_new[-1]
        stolen = base_dem - dem_new[:-1]
        cannib = stolen[own_mask].sum()
        rows.append({"captured": captured, "cannibalized": cannib, "net": captured - cannib,
                     "share": captured / w.sum(), "stolen": stolen,
                     "market_expansion": captured - stolen.sum()})
    return base_dem, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demand", required=True)
    ap.add_argument("--stores", required=True)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--owner")
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--beta", type=float, default=2.0)
    ap.add_argument("--beta-sweep", default="1,1.5,2,2.5,3")
    ap.add_argument("--outside", type=float, default=0.0)
    ap.add_argument("--distance", choices=["euclid", "network"], default="euclid")
    ap.add_argument("--mode", choices=["walk", "drive"], default="walk")
    ap.add_argument("--spend", type=float)
    ap.add_argument("--margin", type=float)
    ap.add_argument("--out", default="huff_results.csv")
    ap.add_argument("--out-points")
    a = ap.parse_args()

    dem = read_points(a.demand, need=("lat", "lon", "weight"))
    stores = read_points(a.stores)
    cands = read_points(a.candidates)
    for df in (stores, cands):
        if "attractiveness" not in df.columns:
            df["attractiveness"] = 1.0
        df["attractiveness"] = df["attractiveness"].fillna(1.0)
        if "id" not in df.columns:
            df["id"] = [f"s{i}" for i in range(len(df))]
    stores["label"] = stores.get("name", stores["id"]).fillna("").astype(str)
    stores.loc[stores.label == "", "label"] = stores["id"].astype(str)
    if a.owner:
        col = stores["owner"] if "owner" in stores.columns else stores.get("brand", pd.Series([""] * len(stores)))
        own = col.fillna("").astype(str).str.lower().eq(a.owner.lower()).values
    else:
        own = np.zeros(len(stores), bool)

    sites = pd.concat([stores[["lat", "lon"]], cands[["lat", "lon"]]], ignore_index=True)
    D, unit = distances(dem, sites, a.distance, a.mode)
    betas = sorted(set([a.beta] + [float(b) for b in a.beta_sweep.split(",") if b.strip()]))

    results = {}
    for b in betas:
        results[b] = evaluate(dem, stores, cands, D, b, a.alpha, a.outside, own)

    base_dem, rows = results[a.beta]
    W = dem.weight.sum()
    tab = cands[["id"]].copy()
    tab["captured"] = [r["captured"] for r in rows]
    tab["share_%"] = [100 * r["share"] for r in rows]
    tab["cannibalized"] = [r["cannibalized"] for r in rows]
    tab["net"] = [r["net"] for r in rows]
    tab["expansion"] = [r["market_expansion"] for r in rows]
    if a.spend and a.margin:
        rent = cands["rent"].fillna(0).values if "rent" in cands.columns else np.zeros(len(cands))
        tab["profit"] = tab.net * a.spend * a.margin - rent
        key = "profit"
    else:
        key = "net"
    for b in betas:
        nets = np.array([r["net"] for r in results[b][1]])
        if key == "profit":
            nets = nets * a.spend * a.margin - (cands["rent"].fillna(0).values if "rent" in cands.columns else 0)
        tab[f"rank_b{b:g}"] = (-nets).argsort().argsort() + 1
    tab = tab.sort_values(key, ascending=False).reset_index(drop=True)
    tab.to_csv(a.out, index=False)

    print("# Huff analysis\n")
    print(f"- Demand: {len(dem)} points, total weight {W:,.0f}. Rivals/own stores: {len(stores)} "
          f"({own.sum()} own). Candidates: {len(cands)}.")
    print(f"- Distance: {a.distance} ({unit}{', ' + a.mode if a.distance == 'network' else ''}); "
          f"α={a.alpha:g}, β={a.beta:g}, outside option={a.outside:g}. β sweep: {', '.join(f'{b:g}' for b in betas)}.")
    # edge effect: candidates whose catchment extends beyond the study area
    clat, clon = dem.lat.mean(), dem.lon.mean()
    R = haversine_km([clat], [clon], dem.lat, dem.lon)[0].max()
    dc = haversine_km([clat], [clon], cands.lat, cands.lon)[0]
    edge = cands.id[dc > 0.6 * R].astype(str).tolist()
    if edge:
        print(f"- ⚠ **Edge effect**: {', '.join(edge)} sit(s) > 60% of the way to the edge of the demand area "
              f"(radius ≈ {R:.1f} km): part of their catchment and rivals lie outside the data, so they are "
              "mis-measured. Extend demand AND competitors one catchment radius beyond the farthest candidate.")
    print("\n## Current market (β = %g)\n" % a.beta)
    cur = stores[["label"]].copy()
    cur["demand"] = base_dem
    cur["share_%"] = 100 * base_dem / W
    cur["own"] = own
    print("| store | demand | share | own |\n|---|---|---|---|")
    for _, r in cur.sort_values("demand", ascending=False).head(15).iterrows():
        print(f"| {r['label']} | {r['demand']:,.0f} | {r['share_%']:.1f}% | {'✓' if r['own'] else ''} |")
    print(f"\n## Candidates (β = {a.beta:g}), ranked by {key}\n")
    hdr = "| rank | candidate | captured | share | cannibalized | net |" + (" profit |" if key == "profit" else "")
    hdr += " ranks across β |"
    print(hdr)
    print("|" + "---|" * (hdr.count("|") - 1))
    for i, r in tab.iterrows():
        ranks = "/".join(str(int(r[f"rank_b{b:g}"])) for b in betas)
        line = (f"| {i+1} | {r['id']} | {r['captured']:,.0f} | {r['share_%']:.1f}% | {r['cannibalized']:,.0f} "
                f"| {r['net']:,.0f} |")
        if key == "profit":
            line += f" {r['profit']:,.0f} |"
        print(line + f" {ranks} |")

    # robustness
    winners = {b: tab.loc[tab[f"rank_b{b:g}"] == 1, "id"].iloc[0] for b in betas}
    top = tab.iloc[0]["id"]
    agree = sum(1 for v in winners.values() if v == top)
    print("\n## Robustness to β\n")
    print("- Winner by β: " + ", ".join(f"β={b:g}: **{v}**" for b, v in winners.items()))
    v1, v2 = tab.iloc[0][key], tab.iloc[1][key] if len(tab) > 1 else None
    if v2 is not None and v1 > 0 and (v1 - v2) / v1 < 0.05:
        print(f"- ⚠ **Near tie**: #1 ({tab.iloc[0]['id']}) beats #2 ({tab.iloc[1]['id']}) by only "
              f"{100*(v1-v2)/v1:.1f}% - well inside the model's error. Do not pick a winner on Huff alone: "
              "decide on rent negotiation, rival response (location_game.py), visibility, parking, lease terms.")
    if agree == len(betas):
        print(f"- ✅ **{top}** wins for every β tested - the ranking is robust to distance decay.")
    else:
        print(f"- ⚠ The winner depends on β ({agree}/{len(betas)} agree with {top}). Calibrate β with the client's "
              "sales by store, or treat the choice as uncertain and decide on other criteria (rent, rival response).")

    # who loses from the top candidate
    best_idx = int(cands.index[cands["id"] == top][0])
    stolen = rows[best_idx]["stolen"]
    order = np.argsort(-stolen)[:5]
    print(f"\n## Where {top}'s customers come from (β = {a.beta:g})\n")
    for j in order:
        if stolen[j] <= 0:
            continue
        print(f"- {stores.label.iloc[j]}{' (OWN)' if own[j] else ''}: −{stolen[j]:,.0f} "
              f"({100*stolen[j]/max(base_dem[j],1e-9):.0f}% of its demand)")
    if a.outside > 0:
        print(f"- Market expansion (from the outside option): {rows[best_idx]['market_expansion']:,.0f}")
    print("\n_Huff caveat (IIA): a new store steals proportionally from all rivals; in reality it steals more from the "
          "nearest one. Read 'where customers come from' as a lower bound for the nearest rival's loss._")

    if a.out_points:
        cols = list(range(len(stores))) + [len(stores) + best_idx]
        A = np.concatenate([stores.attractiveness.values, [cands.attractiveness.values[best_idx]]])
        P = huff_probs(D[:, cols], A, a.alpha, a.beta, a.outside)
        pts = dem.copy()
        pts["p_best"] = P[:, -1]
        pts["captured"] = pts.weight * pts.p_best
        pts.to_csv(a.out_points, index=False)
        print(f"\nPer-point capture probabilities for {top} → `{a.out_points}`")
    print(f"Results → `{a.out}`")


if __name__ == "__main__":
    main()
