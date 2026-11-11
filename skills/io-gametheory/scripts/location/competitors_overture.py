# /// script
# requires-python = ">=3.10"
# dependencies = ["duckdb>=1.1", "pandas>=2.1", "numpy>=1.26", "pyarrow>=15"]
# ///
"""Competitors anywhere in the world from Overture Maps Places (open data, CC BY / CDLA; built
from Meta, Microsoft, Amazon, TomTom and others). Often more complete than OSM for businesses,
especially outside Europe. Read directly from the public S3 bucket - no account needed.

  uv run competitors_overture.py --lat -34.5995 --lon -58.4395 --radius 1300 --match supermarket,grocery --out rivals_ov.csv
  uv run competitors_overture.py --lat 40.4168 --lon -3.7038 --radius 800 --list-categories    # what exists here

--match: comma-separated keywords matched against basic_category, taxonomy primary and hierarchy
(e.g. supermarket, grocery, pharmacy, gas_station, cafe, gym, bank, hardware). Use --list-categories
first to see the exact category names present in the area.
--min-confidence: drop low-confidence places (default 0.5). Closed places are dropped.

Output CSV is compatible with huff.py (id, name, brand, category, lat, lon, confidence, attractiveness=1).
First query takes ~30-90 s (scans parquet metadata over the network); results are cached locally.
Compare with competitors_osm.py and merge/deduplicate (same brand within ~50 m = same store).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import haversine_km  # noqa: E402

BUCKET = "s3://overturemaps-us-west-2/release"
CACHE = os.path.expanduser("~/.cache/io-gametheory/overture")


def connect():
    import duckdb
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    return con


def latest_release(con):
    files = con.execute(f"SELECT file FROM glob('{BUCKET}/*/theme=places/type=place/part-00000*')").fetchall()
    rels = sorted({f[0].split("/release/")[1].split("/")[0] for f in files})
    if not rels:
        sys.exit("Could not list Overture releases (network?).")
    return rels[-1]


def fetch(con, rel, lat, lon, radius_m):
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * np.cos(np.radians(lat)))
    key = hashlib.md5(f"{rel}{lat:.5f}{lon:.5f}{radius_m:.0f}".encode()).hexdigest()[:16]
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{key}.parquet")
    if os.path.exists(path):
        return pd.read_parquet(path)
    cols = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{BUCKET}/{rel}/theme=places/type=place/part-00000*')").fetchall()
    names = {c[0] for c in cols}
    cat = ("basic_category AS basic, taxonomy.primary AS cat, array_to_string(taxonomy.hierarchy, '>') AS hier"
           if "taxonomy" in names else
           "NULL AS basic, categories.primary AS cat, array_to_string(categories.alternate, '>') AS hier")
    status = "operating_status AS status" if "operating_status" in names else "NULL AS status"
    q = f"""
      SELECT id, names.primary AS name, brand.names.primary AS brand, {cat}, confidence, {status},
             (bbox.xmin + bbox.xmax) / 2 AS lon, (bbox.ymin + bbox.ymax) / 2 AS lat,
             addresses[1].freeform AS address
      FROM read_parquet('{BUCKET}/{rel}/theme=places/type=place/*.parquet')
      WHERE bbox.xmin BETWEEN {lon - dlon} AND {lon + dlon}
        AND bbox.ymin BETWEEN {lat - dlat} AND {lat + dlat}"""
    df = con.execute(q).df()
    df.to_parquet(path)
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--radius", type=float, default=1500)
    ap.add_argument("--match", help="comma-separated category keywords")
    ap.add_argument("--list-categories", action="store_true")
    ap.add_argument("--name-match", help="keep only places whose name/brand contains one of these words (e.g. 'super,market,coto,dia,carrefour')")
    ap.add_argument("--min-confidence", type=float, default=0.5)
    ap.add_argument("--release")
    ap.add_argument("--out", default="competitors_overture.csv")
    a = ap.parse_args()

    con = connect()
    rel = a.release or latest_release(con)
    df = fetch(con, rel, a.lat, a.lon, a.radius)
    df["dist_km"] = haversine_km([a.lat], [a.lon], df.lat, df.lon)[0]
    df = df[df.dist_km <= a.radius / 1000].copy()
    if "status" in df.columns:
        df = df[df.status.fillna("open").str.lower().ne("closed") & df.status.fillna("").str.lower().ne("permanently_closed")]
    df = df[df.confidence.fillna(0) >= a.min_confidence]

    if a.list_categories or not a.match:
        col = df.basic.fillna(df.cat) if df.basic.notna().any() else df.cat
        print(f"# Overture {rel}: {len(df):,} places within {a.radius:.0f} m (confidence ≥ {a.min_confidence})\n")
        print("| category | count |\n|---|---|")
        for k, v in col.value_counts().head(60).items():
            print(f"| {k} | {v} |")
        if not a.match:
            return
    kws = [k.strip().lower() for k in a.match.split(",") if k.strip()]
    SYN = {"supermarket": ["grocery", "supermarket", "hypermarket"], "pharmacy": ["pharmacy", "drugstore", "chemist"],
           "gas_station": ["gas_station", "fuel"], "fuel": ["gas_station", "fuel"]}
    kws = sorted({x for k in kws for x in SYN.get(k, [k])})
    hay = (df.basic.fillna("") + "|" + df.cat.fillna("") + "|" + df.hier.fillna("")).str.lower()
    sel = df[hay.apply(lambda s: any(k in s for k in kws))].copy()
    if a.name_match:
        nm = [x.strip().lower() for x in a.name_match.split(",")]
        lab_ = (sel.name.fillna("") + " " + sel.brand.fillna("")).str.lower()
        sel = sel[lab_.apply(lambda s: any(k in s for k in nm))]
    sel["category"] = sel.cat
    sel["attractiveness"] = 1.0
    sel = sel.sort_values("dist_km")
    sel[["id", "name", "brand", "category", "lat", "lon", "dist_km", "confidence", "address", "attractiveness"]].to_csv(a.out, index=False)
    print(f"# Overture {rel}: {len(sel)} places matching {kws} within {a.radius:.0f} m → `{a.out}`\n")
    lab = sel.brand.fillna(sel.name).fillna("(unnamed)")
    print("- By brand/name: " + ", ".join(f"{k} {v}" for k, v in lab.value_counts().head(12).items()))
    print("- By category: " + ", ".join(f"{k} {v}" for k, v in sel.category.value_counts().items()))
    print(f"- Median confidence {sel.confidence.median():.2f}. Low-confidence or stale entries exist: verify a sample.")
    print("\n_Cross-check with competitors_osm.py: same brand within ~50 m = same store. Report both counts._")


if __name__ == "__main__":
    main()
