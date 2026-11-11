# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas>=2.1", "numpy>=1.26"]
# ///
"""Merge competitor lists from several sources (OSM, Overture, registries, your own) and deduplicate.

  uv run merge_competitors.py rivals_osm.csv rivals_overture.csv --radius 50 --out rivals.csv

Two places are the same store if they are within --radius meters AND their normalized brand/name share a
word of ≥3 letters (or one of them is unnamed and they are within radius/2). Keeps the richest record,
records which sources saw it ('sources' column) - stores seen by only one source deserve a manual check.
Output is ready for huff.py / location_game.py / map.py (attractiveness preserved, default 1).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import haversine_km  # noqa: E402

STOP = {"supermercado", "supermarket", "super", "market", "mercado", "store", "tienda", "the", "drogueria", "farmacia",
        "pharmacy", "sa", "srl", "ltd", "inc", "express", "de", "la", "el", "los"}


def words(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return {w for w in re.findall(r"[a-z0-9]{3,}", s) if w not in STOP}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--radius", type=float, default=50, help="meters")
    ap.add_argument("--out", default="competitors_merged.csv")
    a = ap.parse_args()
    frames = []
    for f in a.files:
        d = pd.read_csv(f)
        d.columns = [c.lower() for c in d.columns]
        d["source"] = os.path.basename(f)
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    for c in ("name", "brand"):
        if c not in df.columns:
            df[c] = ""
    if "attractiveness" not in df.columns:
        df["attractiveness"] = 1.0
    W = [words(n) | words(b) for n, b in zip(df.name, df.brand)]
    D = haversine_km(df.lat, df.lon, df.lat, df.lon) * 1000
    parent = list(range(len(df)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i in range(len(df)):
        for j in np.where(D[i, i + 1:] <= a.radius)[0] + i + 1:
            if df.source[i] == df.source[j]:
                continue
            if (W[i] & W[j]) or ((not W[i] or not W[j]) and D[i, j] <= a.radius / 2):
                parent[find(j)] = find(i)
    df["cluster"] = [find(i) for i in range(len(df))]
    df["richness"] = df.name.fillna("").astype(str).str.len() + df.brand.fillna("").astype(str).str.len()
    src = df.groupby("cluster").source.apply(lambda s: "+".join(sorted(set(s))))
    out = df.sort_values("richness", ascending=False).groupby("cluster").first()
    out["sources"] = src
    out = out.reset_index(drop=True)
    out = out.drop(columns=["richness", "source"], errors="ignore")
    out.to_csv(a.out, index=False)
    print(f"# Merged competitors → `{a.out}`\n")
    for f in a.files:
        print(f"- {os.path.basename(f)}: {sum(df.source == os.path.basename(f))} records")
    print(f"- Unique stores after dedup (≤ {a.radius:.0f} m, matching name/brand): **{len(out)}**")
    print("- By sources: " + ", ".join(f"{k}: {v}" for k, v in out.sources.value_counts().items()))
    print("\n_Stores seen by a single source are the ones to verify (Google Maps / Street View)._")


if __name__ == "__main__":
    main()
