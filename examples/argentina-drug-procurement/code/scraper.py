# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.31", "beautifulsoup4>=4.12"]
# ///
"""COMPR.AR: todas las ofertas de cada proceso (cuadro comparativo), no sólo las órdenes de compra.

Para cada número de proceso:
  1. BuscarAvanzado.aspx → busca por número (postback ASP.NET).
  2. VistaPreviaPliegoCiudadano.aspx → datos del proceso: proveedores participantes, ofertas confirmadas.
  3. EVALUACIONOFERTA/VerCuadroComparativo.aspx → renglones (código de catálogo, droga, cantidad) y TODAS las
     ofertas por renglón (oferente, CUIT, precio unitario, cantidad, total, moneda, bien nacional).

Salida: data/ofertas.db (SQLite) - tablas proceso, renglon, oferta. HTML crudo en data/raw/<proceso>/*.html.gz.
Reanudable: los procesos ya bajados se saltean. Cortés: --delay segundos entre pedidos (default 2).

  uv run scraper.py --procesos 80-0006-LPU23 80-0066-LPU23
  uv run scraper.py --lista procesos.txt            # un número por línea
"""
from __future__ import annotations

import argparse
import gzip
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://comprar.gob.ar"
UA = "Mozilla/5.0 (compatible; investigacion-compras-publicas; respeta 1 pedido cada 2 s)"
DATA = Path(__file__).parent / "data"
LNK_CUADRO = "ctl00$CPH1$UCVistaPreviaPliego$UC_OfertasProceso$lnkVerCuadroComparativo"

SCHEMA = """
CREATE TABLE IF NOT EXISTS proceso (
  numero TEXT PRIMARY KEY, expediente TEXT, nombre TEXT, uoc TEXT,
  participantes INTEGER, ofertas_confirmadas INTEGER, tiene_cuadro INTEGER,
  estado TEXT,                 -- ok | sin_resultado | sin_cuadro | error
  error TEXT, bajado TEXT
);
CREATE TABLE IF NOT EXISTS renglon (
  numero TEXT, renglon INTEGER, codigo TEXT, descripcion TEXT, droga TEXT,
  cantidad REAL, um TEXT, ofertas INTEGER,
  PRIMARY KEY (numero, renglon)
);
CREATE TABLE IF NOT EXISTS oferta (
  numero TEXT, renglon INTEGER, oferente TEXT, cuit TEXT, alternativa INTEGER,
  precio_unitario REAL, cantidad_ofertada REAL, total REAL, moneda TEXT,
  especificaciones TEXT, bien_nacional TEXT
);
CREATE INDEX IF NOT EXISTS ix_oferta_num ON oferta(numero, renglon);
CREATE TABLE IF NOT EXISTS oferente_total (   -- resumen "Mostrar ofertas" del cuadro
  numero TEXT, oferente TEXT, cuit TEXT, total REAL, moneda TEXT
);
"""

RX_PROV = re.compile(r"^(.*?)\s+-\s+(\d{11})$")
RX_BN = re.compile(r"^(S[ií]|No)(\s+\d+([.,]\d+)?\s*%)?$")
OFFER_HDR = ["Alternativa", "Precio Unitario", "Cantidad ofertada", "Total por renglón", "Moneda",
             "Especificaciones técnicas", "Bien Nacional"]
RENGLON_HDR = ["Renglón", "Código del renglón", "Descripción", "Cantidad solicitada", "UM"]


def num(s):
    s = (s or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def droga_de(desc):
    m = re.search(r"DROGA GENERICA:\s*([^,;]+)", desc or "", re.I)
    return m.group(1).strip().upper() if m else None


class Cliente:
    def __init__(self, delay):
        self.delay = delay
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.last = 0.0

    def _wait(self):
        dt = time.time() - self.last
        if dt < self.delay:
            time.sleep(self.delay - dt)
        self.last = time.time()

    def get(self, url):
        self._wait()
        r = self.s.get(url, timeout=90)
        r.raise_for_status()
        return r

    def post(self, url, data):
        self._wait()
        r = self.s.post(url, data=data, timeout=120)
        r.raise_for_status()
        return r


def formulario(html):
    s = BeautifulSoup(html, "html.parser")
    f = {}
    for i in s.select("input[name]"):
        if i.get("type") in ("submit", "image", "button", "checkbox", "radio"):
            continue
        f[i["name"]] = i.get("value", "")
    for sel in s.select("select[name]"):
        o = sel.select_one("option[selected]") or sel.select_one("option")
        f[sel["name"]] = o.get("value", "") if o else ""
    return f, s


def lineas(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    t = re.sub(r"<br\s*/?>", " ", t)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = t.replace("&nbsp", " ").replace("&amp;", "&").replace("&times;", "")
    return [re.sub(r"\s+", " ", x).strip() for x in t.split("\n") if x.strip()]


def parse_proceso(html):
    L = lineas(html)

    def after(label):
        for i, x in enumerate(L):
            if x.rstrip(":") == label and i + 1 < len(L):
                return L[i + 1]
        return None
    return {
        "expediente": after("Número de expediente") or after("Expediente"),
        "nombre": after("Nombre descriptivo del proceso"),
        "participantes": num(after("Proveedores participantes")),
        "ofertas_confirmadas": num(after("Ofertas confirmadas")),
        "tiene_cuadro": int("Ver cuadro comparativo" in L),
    }


def parse_cuadro(html):
    L = lineas(html)
    out = {"uoc": None, "totales": [], "renglones": [], "ofertas": []}
    try:
        i = L.index("Unidad Operativa de Contrataciones")
        out["uoc"] = L[i + 1]
    except ValueError:
        pass
    # totals per bidder
    if "Mostrar ofertas" in L:
        i = L.index("Mostrar ofertas") + 1
        while i + 1 < len(L) and L[i] != "Renglón":
            m = RX_PROV.match(L[i])
            if m:
                amt = re.match(r"([\d\.,]+)\s*([A-Z]{3})?", L[i + 1])
                out["totales"].append((m.group(1).strip(), m.group(2), num(amt.group(1)) if amt else None,
                                       amt.group(2) if amt else None))
                i += 2
            else:
                i += 1
    i = 0
    cur = None
    while i < len(L):
        if L[i:i + 5] == RENGLON_HDR:
            vals = L[i + 5:i + 12]
            # renglon, codigo, descripcion, [Ver más], cantidad, um
            k = 0
            rn = int(num(vals[k]) or 0); k += 1
            cod = vals[k]; k += 1
            desc = vals[k]; k += 1
            if vals[k] == "Ver más":
                k += 1
            cant = num(vals[k]); k += 1
            um = vals[k]; k += 1
            cur = {"renglon": rn, "codigo": cod, "descripcion": desc, "droga": droga_de(desc),
                   "cantidad": cant, "um": um, "ofertas": 0}
            out["renglones"].append(cur)
            i += 5 + k
            continue
        m = RX_PROV.match(L[i])
        if cur is not None and m and L[i + 1:i + 8] == OFFER_HDR:
            name, cuit = m.group(1).strip(), m.group(2)
            j = i + 8
            while j < len(L):
                if L[j] == "Renglón" or RX_PROV.match(L[j]):
                    break
                # one alternative row: alt, pu, cant, total, moneda, espec, [Ver más], bien nacional
                if re.fullmatch(r"\d+", L[j]) and j + 5 < len(L) and num(L[j + 1]) is not None:
                    alt = int(L[j]); pu = num(L[j + 1]); co = num(L[j + 2]); tot = num(L[j + 3]); mon = L[j + 4]
                    # specifications can span several lines; "Bien Nacional" is the next "Sí NN%" / "No" line
                    k = j + 5
                    esp_parts = []
                    while k < len(L) and not RX_BN.match(L[k]) and L[k] != "Renglón" and not RX_PROV.match(L[k]):
                        if L[k] != "Ver más":
                            esp_parts.append(L[k])
                        k += 1
                    esp = " ".join(esp_parts)[:1000]
                    bn = L[k] if k < len(L) and RX_BN.match(L[k]) else None
                    out["ofertas"].append({"renglon": cur["renglon"], "oferente": name, "cuit": cuit, "alternativa": alt,
                                           "precio_unitario": pu, "cantidad_ofertada": co, "total": tot, "moneda": mon,
                                           "especificaciones": esp, "bien_nacional": bn})
                    cur["ofertas"] += 1
                    j = k + 1
                else:
                    j += 1
            i = j
            continue
        i += 1
    return out


def bajar(cli, numero, raw_dir):
    r = cli.get(f"{BASE}/BuscarAvanzado.aspx")
    f, _ = formulario(r.text)
    f["ctl00$CPH1$txtNumeroProceso"] = numero
    f["__EVENTTARGET"] = "ctl00$CPH1$btnListarPliegoNumero"
    f["__EVENTARGUMENT"] = ""
    r2 = cli.post(r.url, f)
    f2, s2 = formulario(r2.text)
    link = next((a for a in s2.select("a[id$=lnkNumeroProceso]") if a.get_text(strip=True) == numero), None)
    if link is None:
        return {"estado": "sin_resultado"}, None
    target = re.search(r"__doPostBack\('([^']+)'", link["href"].replace("&#39;", "'")).group(1)
    f2["__EVENTTARGET"] = target
    f2["__EVENTARGUMENT"] = ""
    r3 = cli.post(r2.url, f2)
    guardar(raw_dir / "proceso.html.gz", r3.text)
    meta = parse_proceso(r3.text)
    if not meta["tiene_cuadro"]:
        meta["estado"] = "sin_cuadro"
        return meta, None
    f3, _ = formulario(r3.text)
    f3["__EVENTTARGET"] = LNK_CUADRO
    f3["__EVENTARGUMENT"] = ""
    r4 = cli.post(r3.url, f3)
    guardar(raw_dir / "cuadro.html.gz", r4.text)
    meta["estado"] = "ok"
    return meta, parse_cuadro(r4.text)


def guardar(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--procesos", nargs="*", default=[])
    ap.add_argument("--lista")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--db", default=str(DATA / "ofertas.db"))
    ap.add_argument("--reintentar", action="store_true", help="volver a bajar los que dieron error")
    a = ap.parse_args()
    nums = list(a.procesos)
    if a.lista:
        nums += [x.strip() for x in open(a.lista) if x.strip()]
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(a.db)
    con.executescript(SCHEMA)
    hechos = {r[0] for r in con.execute("SELECT numero FROM proceso WHERE estado != 'error'" if a.reintentar
                                         else "SELECT numero FROM proceso")}
    pend = [n for n in dict.fromkeys(nums) if n not in hechos]
    print(f"{len(nums)} procesos, {len(pend)} pendientes", flush=True)
    cli = Cliente(a.delay)
    for k, n in enumerate(pend, 1):
        t0 = time.time()
        try:
            meta, cuadro = bajar(cli, n, DATA / "raw" / n)
            err = None
        except Exception as e:  # noqa: BLE001
            meta, cuadro, err = {"estado": "error"}, None, f"{type(e).__name__}: {e}"[:300]
            cli = Cliente(a.delay)  # sesión nueva
        con.execute("DELETE FROM proceso WHERE numero=?", (n,))
        con.execute("DELETE FROM renglon WHERE numero=?", (n,))
        con.execute("DELETE FROM oferta WHERE numero=?", (n,))
        con.execute("DELETE FROM oferente_total WHERE numero=?", (n,))
        con.execute("INSERT INTO proceso VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
                    (n, meta.get("expediente"), meta.get("nombre"), cuadro["uoc"] if cuadro else None,
                     meta.get("participantes"), meta.get("ofertas_confirmadas"), meta.get("tiene_cuadro"),
                     meta["estado"], err))
        if cuadro:
            con.executemany("INSERT INTO renglon VALUES (?,?,?,?,?,?,?,?)",
                            [(n, r["renglon"], r["codigo"], r["descripcion"], r["droga"], r["cantidad"], r["um"], r["ofertas"])
                             for r in cuadro["renglones"]])
            con.executemany("INSERT INTO oferta VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            [(n, o["renglon"], o["oferente"], o["cuit"], o["alternativa"], o["precio_unitario"],
                              o["cantidad_ofertada"], o["total"], o["moneda"], o["especificaciones"], o["bien_nacional"])
                             for o in cuadro["ofertas"]])
            con.executemany("INSERT INTO oferente_total VALUES (?,?,?,?,?)", [(n, *t) for t in cuadro["totales"]])
        con.commit()
        nof = len(cuadro["ofertas"]) if cuadro else 0
        print(f"[{k}/{len(pend)}] {n}: {meta['estado']} - {len(cuadro['renglones']) if cuadro else 0} renglones, "
              f"{nof} ofertas ({time.time()-t0:.0f}s){' ' + err if err else ''}", flush=True)
    con.close()


if __name__ == "__main__":
    sys.exit(main())
