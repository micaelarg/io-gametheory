# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas>=2.1", "numpy>=1.26"]
# ///
"""Resumen de competencia por renglón a partir de data/ofertas.db.

Unidad = renglón (cada droga/presentación pedida es una mini-licitación).
Sólo ofertas en pesos, alternativa 1 por oferente (la más barata si cotiza varias), precio unitario comparable
(misma unidad del renglón). "Ganador" = oferta más baja (= ganador probable; la adjudicación puede diferir por
requisitos técnicos).

Escribe data/renglones.csv, data/panel_bids.csv (formato collusion.py bids / auctions.py gpv) y data/resumen.json.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"


def main():
    con = sqlite3.connect(DATA / "ofertas.db")
    proc = pd.read_sql("SELECT * FROM proceso", con)
    ren = pd.read_sql("SELECT * FROM renglon", con)
    of = pd.read_sql("SELECT * FROM oferta", con)
    of = of[(of.moneda == "Peso Argentino") & (of.precio_unitario > 0)]
    of = of.sort_values("precio_unitario").drop_duplicates(["numero", "renglon", "cuit"])
    of["item"] = of.numero + "#" + of.renglon.astype(str)
    g = of.groupby("item")
    R = pd.DataFrame({
        "n": g.size(),
        "p1": g.precio_unitario.min(),
        "p2": g.precio_unitario.apply(lambda s: np.sort(s.values)[1] if len(s) > 1 else np.nan),
        "pmax": g.precio_unitario.max(),
        "winner": g.apply(lambda d: d.loc[d.precio_unitario.idxmin(), "oferente"]),
    })
    R["lead"] = R.p2 / R.p1 - 1
    R["spread"] = R.pmax / R.p1
    # drop incomparable items (different units of measure across bids)
    R["comparable"] = R.spread <= 5
    ren["item"] = ren.numero + "#" + ren.renglon.astype(str)
    ren = ren.merge(R, left_on="item", right_index=True, how="left")
    ren["n"] = ren.n.fillna(0).astype(int)
    ren["year"] = 2000 + ren.numero.str.extract(r"(\d{2})$")[0].astype(int)
    ren["ms"] = ren.numero.str.startswith("80-")
    ren.to_csv(DATA / "renglones.csv", index=False)

    ok = proc[proc.estado == "ok"]
    comp = ren[ren.comparable.fillna(False) & (ren.n >= 2)]
    bins = pd.cut(comp.n, [1, 2, 3, 5, 100], labels=["2", "3", "4-5", "6+"])
    lead = comp.groupby(bins, observed=False).lead.agg(["median", "size"])
    dist = ren.n.clip(upper=6).value_counts().sort_index()
    res = {
        "procesos_bajados": int(len(proc)), "procesos_ok": int(len(ok)),
        "procesos_sin_cuadro": int((proc.estado == "sin_cuadro").sum()),
        "renglones": int(len(ren)), "ofertas": int(len(of)),
        "oferentes": int(of.cuit.nunique()),
        "participantes_mediana": float(ok.participantes.median()) if len(ok) else None,
        "share_desierto": float((ren.n == 0).mean()), "share_una_oferta": float((ren.n == 1).mean()),
        "share_2mas": float((ren.n >= 2).mean()),
        "dist_n": {str(int(k)) + ("+" if k == 6 else ""): int(v) for k, v in dist.items()},
        "lead_by_n": {str(k): {"median_pct": round(100 * v["median"], 1) if pd.notna(v["median"]) else None,
                                "items": int(v["size"])} for k, v in lead.iterrows()},
        "procesos_ms": int(ok.numero.str.startswith("80-").sum()),
        "ms_renglones": int(ren.ms.sum()), "ms_share_desierto_o_una": float((ren[ren.ms].n <= 1).mean()) if ren.ms.any() else None, "ms_share_una_o_ninguna": float((ren[ren.ms].n <= 1).mean()),
        "years": sorted(ren.year.dropna().unique().astype(int).tolist()),
    }
    (DATA / "resumen.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    pb = of[of.item.isin(comp.item)][["item", "numero", "cuit", "oferente", "precio_unitario"]].rename(
        columns={"item": "tender", "numero": "process", "cuit": "bidder", "precio_unitario": "bid"})
    pb["norm"] = pb.bid / pb.groupby("tender").bid.transform("median")
    pb.to_csv(DATA / "panel_bids.csv", index=False)
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
