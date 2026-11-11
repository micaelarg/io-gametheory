# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas>=2.1", "numpy>=1.26", "osmnx>=2.0", "networkx>=3.2", "scikit-learn>=1.4", "requests>=2.31", "nashpy>=0.0.41"]
# ///
"""Competitive location game: two chains choose sites, anticipating each other.

Payoff of a chain at a site = Huff demand captured (given existing stores AND the other
entrant's choice) × spend × margin − rent.  Builds the full payoff matrix, then reports:
  - Nash equilibria (pure and mixed) via finite_nash.py
  - Stackelberg: each chain as leader (signs the lease first), follower best-responds
  - Value of moving first, and the NAIVE choice (best site ignoring the rival) vs the
    STRATEGIC choice - the gap is what game theory adds to a plain Huff ranking.

  uv run location_game.py --demand demand.csv --stores rivals.csv \
      --a-candidates ours.csv --b-candidates theirs.csv --a-name Us --b-name Rival \
      --spend 120 --margin 0.25 --allow-out --out-game game.json

Candidate CSVs: id, lat, lon [, attractiveness, rent].
Without --spend/--margin, payoffs are in demand units (rent ignored).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "solvers"))
from _common import read_points  # noqa: E402
from huff import distances, huff_probs  # noqa: E402
import finite_nash  # noqa: E402


def prep(df, prefix):
    df = df.copy()
    if "id" not in df.columns:
        df["id"] = [f"{prefix}{i+1}" for i in range(len(df))]
    df["id"] = df["id"].astype(str)
    if "attractiveness" not in df.columns:
        df["attractiveness"] = 1.0
    if "rent" not in df.columns:
        df["rent"] = 0.0
    df["attractiveness"] = df["attractiveness"].fillna(1.0)
    df["rent"] = df["rent"].fillna(0.0)
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demand", required=True)
    ap.add_argument("--stores", help="existing stores (fixed); omit if none")
    ap.add_argument("--a-candidates", required=True)
    ap.add_argument("--b-candidates", required=True)
    ap.add_argument("--a-name", default="A")
    ap.add_argument("--b-name", default="B")
    ap.add_argument("--a-owner", help="value in stores' owner/brand column that marks A's existing stores (cannibalization)")
    ap.add_argument("--b-owner", help="same for B")
    ap.add_argument("--allow-out", action="store_true", help="add 'Stay out' (payoff 0) for both")
    ap.add_argument("--shared-sites", action="store_true",
                    help="allow both chains at the same site (malls, several units); default: one storefront = one lease")
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--beta", type=float, default=2.0)
    ap.add_argument("--outside", type=float, default=0.0)
    ap.add_argument("--distance", choices=["euclid", "network"], default="euclid")
    ap.add_argument("--mode", choices=["walk", "drive"], default="walk")
    ap.add_argument("--spend", type=float, default=1.0)
    ap.add_argument("--margin", type=float, default=1.0)
    ap.add_argument("--out-game", default="location_game.json")
    a = ap.parse_args()

    dem = read_points(a.demand, need=("lat", "lon", "weight"))
    st = prep(read_points(a.stores), "s") if a.stores else prep(pd.DataFrame(columns=["lat", "lon"]), "s")
    ca, cb = prep(read_points(a.a_candidates), "a"), prep(read_points(a.b_candidates), "b")
    money = not (a.spend == 1.0 and a.margin == 1.0)
    sites = pd.concat([st[["lat", "lon"]], ca[["lat", "lon"]], cb[["lat", "lon"]]], ignore_index=True)
    D, unit = distances(dem, sites, a.distance, a.mode)
    ns, na, nb = len(st), len(ca), len(cb)
    w = dem.weight.values
    k = a.spend * a.margin

    def owned(tag):
        if not tag or ns == 0:
            return np.zeros(ns, bool)
        col = st["owner"] if "owner" in st.columns else st.get("brand", pd.Series([""] * ns))
        return col.fillna("").astype(str).str.lower().eq(tag.lower()).values

    own_a, own_b = owned(a.a_owner), owned(a.b_owner)

    def store_demand(ia, ib):
        cols, A = list(range(ns)), list(st.attractiveness.values)
        if ia is not None:
            cols.append(ns + ia); A.append(ca.attractiveness.values[ia])
        if ib is not None:
            cols.append(ns + na + ib); A.append(cb.attractiveness.values[ib])
        if not cols:
            return np.zeros(0)
        return w @ huff_probs(D[:, cols], np.array(A), a.alpha, a.beta, a.outside)

    base_st = store_demand(None, None)[:ns]

    def capture(ia, ib):
        """Chain-level incremental demand: new store's demand minus what the chain's existing stores lose."""
        da, db = _capture(ia, ib)
        if own_a.any() or own_b.any():
            after = store_demand(ia, ib)[:ns]
            loss = base_st - after
            da -= loss[own_a].sum() if ia is not None else 0.0
            db -= loss[own_b].sum() if ib is not None else 0.0
        return da, db

    def _capture(ia, ib):
        cols, A = list(range(ns)), list(st.attractiveness.values)
        pos = {}
        if ia is not None:
            pos["a"] = len(cols); cols.append(ns + ia); A.append(ca.attractiveness.values[ia])
        if ib is not None:
            pos["b"] = len(cols); cols.append(ns + na + ib); A.append(cb.attractiveness.values[ib])
        P = huff_probs(D[:, cols], np.array(A), a.alpha, a.beta, a.outside)
        d = w @ P
        return (d[pos["a"]] if "a" in pos else 0.0), (d[pos["b"]] if "b" in pos else 0.0)

    acts_a = list(range(na)) + ([None] if a.allow_out else [])
    acts_b = list(range(nb)) + ([None] if a.allow_out else [])
    lab_a = [ca.id[i] if i is not None else "Stay out" for i in acts_a]
    lab_b = [cb.id[j] if j is not None else "Stay out" for j in acts_b]
    def same_site(ia, ib):
        if ia is None or ib is None or a.shared_sites:
            return False
        if str(ca.id[ia]) == str(cb.id[ib]):
            return True
        return abs(ca.lat.values[ia] - cb.lat.values[ib]) < 1e-5 and abs(ca.lon.values[ia] - cb.lon.values[ib]) < 1e-5

    def solo(ia, ib):
        pa = 0.0 if ia is None else capture(ia, None)[0] * k - (ca.rent.values[ia] if money else 0)
        pb = 0.0 if ib is None else capture(None, ib)[1] * k - (cb.rent.values[ib] if money else 0)
        return pa, pb

    pay = []
    n_same = 0
    for ia in acts_a:
        row = []
        for ib in acts_b:
            if same_site(ia, ib):
                # one storefront, one lease: each gets it with prob ½; the loser ends up with nothing
                sa, sb = solo(ia, ib)
                pa, pb = 0.5 * sa, 0.5 * sb
                n_same += 1
            else:
                da, db = capture(ia, ib)
                pa = 0.0 if ia is None else da * k - (ca.rent.values[ia] if money else 0)
                pb = 0.0 if ib is None else db * k - (cb.rent.values[ib] if money else 0)
            row.append([round(float(pa), 2), round(float(pb), 2)])
        pay.append(row)
    SAME = np.array([[same_site(ia, ib) for ib in acts_b] for ia in acts_a])

    game = {"title": f"Location game: {a.a_name} vs {a.b_name}", "players": [a.a_name, a.b_name],
            "row_actions": lab_a, "col_actions": lab_b, "payoffs": pay}
    with open(a.out_game, "w") as f:
        json.dump(game, f, indent=1)

    P = np.array(pay)
    PA, PB = P[..., 0], P[..., 1]

    print(f"# Location game: {a.a_name} vs {a.b_name}\n")
    print(f"- Demand {len(dem)} points (weight {w.sum():,.0f}); existing stores {ns}; distance {a.distance} ({unit}); "
          f"α={a.alpha:g}, β={a.beta:g}.")
    if own_a.any() or own_b.any():
        print(f"- Cannibalization netted out: {a.a_name} has {own_a.sum()} existing stores, {a.b_name} {own_b.sum()}. "
              "Payoffs are CHAIN-level increments (new store − losses of own stores).")
    print(f"- Payoffs = " + ("captured demand × spend × margin − rent" if money else
                             "captured demand (no money data: rent ignored - say so)") + ".")
    if n_same:
        print(f"- Exclusive storefronts: {n_same} cells where both pick the same site → each wins the lease with "
              "probability ½ and the loser gets nothing (use --shared-sites for malls/streets with several units).")
    print(f"- Game matrix saved → `{a.out_game}` (feed to finite_nash.py / reuse).\n")

    g = finite_nash.load_game(a.out_game)
    res = finite_nash.analyze(g)
    rep = finite_nash.report(g, res)
    print(rep.split("\n", 1)[1])  # drop duplicate title

    # Stackelberg
    print("\n## Who signs first? (Stackelberg)\n")
    nash_pure = [e["cell"] for e in res["pure"]]
    for leader in ("A", "B"):
        if leader == "A":
            fol = [int(np.argmax(np.where(SAME[i], -np.inf, PB[i]))) for i in range(len(acts_a))]
            vals = [PA[i, fol[i]] for i in range(len(acts_a))]
            i = int(np.argmax(vals)); j = fol[i]
            ln, fn = a.a_name, a.b_name
            lv, fv = PA[i, j], PB[i, j]
            lact, fact = lab_a[i], lab_b[j]
            nash_lv = [PA[c] for c in nash_pure]
        else:
            fol = [int(np.argmax(np.where(SAME[:, j], -np.inf, PA[:, j]))) for j in range(len(acts_b))]
            vals = [PB[fol[j], j] for j in range(len(acts_b))]
            j = int(np.argmax(vals)); i = fol[j]
            ln, fn = a.b_name, a.a_name
            lv, fv = PB[i, j], PA[i, j]
            lact, fact = lab_b[j], lab_a[i]
            nash_lv = [PB[c] for c in nash_pure]
        cmp = ""
        if nash_lv:
            cmp = (f" In the simultaneous game {ln} gets {min(nash_lv):,.0f}–{max(nash_lv):,.0f} depending on which "
                   f"equilibrium; leading guarantees {lv:,.0f} → value of signing first up to "
                   f"**{lv - min(nash_lv):+,.0f}** (vs the worst equilibrium for {ln}).")
        print(f"- **{ln} leads** (signs the lease first; that site is no longer available): opens at **{lact}**, {fn} answers at **{fact}**. {ln} {lv:,.0f}, {fn} {fv:,.0f}.{cmp}")

    # naive vs strategic
    print("\n## Naive vs strategic choice\n")
    for who in ("A", "B"):
        if who == "A":
            solo = [capture(i, None)[0] * k - (ca.rent.values[i] if money else 0) for i in range(na)]
            naive = int(np.argmax(solo)); nm, labs = a.a_name, lab_a
            resp = int(np.argmax(np.where(SAME[naive], -np.inf, PB[naive]))); after = PA[naive, resp]; rlab = lab_b[resp]
        else:
            solo = [capture(None, j)[1] * k - (cb.rent.values[j] if money else 0) for j in range(nb)]
            naive = int(np.argmax(solo)); nm, labs = a.b_name, lab_b
            resp = int(np.argmax(np.where(SAME[:, naive], -np.inf, PA[:, naive]))); after = PB[resp, naive]; rlab = lab_a[resp]
        print(f"- {nm}'s best site ignoring the rival: **{labs[naive]}** ({solo[naive]:,.0f} on paper). "
              f"After the rival's best answer ({rlab}): {after:,.0f} "
              f"({100*(after/solo[naive]-1) if solo[naive] else 0:+.0f}%).")
    print("\nCompare the naive site with the Nash/Stackelberg sites above: if they differ, the plain Huff "
          "ranking would have picked a site the rival can contest. That gap is the story to tell.")


if __name__ == "__main__":
    main()
