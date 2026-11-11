"""Shared helpers for the location scripts (imported, not run directly)."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.private.coffee/api/interpreter",
            ]
UA = {"User-Agent": "io-gametheory-skill/0.1 (research script)"}
R_EARTH_KM = 6371.0088


def overpass(query: str, timeout: int = 120) -> dict:
    import sys as _sys
    import requests
    last = None
    t0 = time.time()
    for url in OVERPASS * 2:
        for attempt in range(2):
            print(f"[overpass] {url.split('/')[2]} attempt {attempt+1} (elapsed {time.time()-t0:.0f}s)", file=_sys.stderr, flush=True)
            if time.time() - t0 > 900:
                raise RuntimeError("Overpass unavailable for 15 minutes - use census/population-grid demand (demand.py --from-csv) "
                                   "or retry later.")
            try:
                r = requests.post(url, data={"data": query}, headers=UA, timeout=timeout)
                if r.status_code == 200:
                    return r.json()
                last = f"{url} HTTP {r.status_code}"
                if r.status_code in (429, 502, 503, 504):
                    time.sleep(5 * (attempt + 1))
                    continue
                break
            except Exception as e:  # noqa
                last = f"{url} {type(e).__name__}"
    raise RuntimeError(f"All Overpass endpoints failed ({last}). Retry later or reduce the radius.")


def haversine_km(lat1, lon1, lat2, lon2):
    """Pairwise distances: (n,) x (m,) -> (n, m) in km."""
    lat1, lon1 = np.radians(np.asarray(lat1, float))[:, None], np.radians(np.asarray(lon1, float))[:, None]
    lat2, lon2 = np.radians(np.asarray(lat2, float))[None, :], np.radians(np.asarray(lon2, float))[None, :]
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * R_EARTH_KM * np.arcsin(np.sqrt(a))


def read_points(path: str, need=("lat", "lon")) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    ren = {"latitude": "lat", "longitude": "lon", "lng": "lon", "long": "lon"}
    df = df.rename(columns={k: v for k, v in ren.items() if k in df.columns})
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise SystemExit(f"{path}: missing columns {missing} (have {list(df.columns)})")
    return df


OSMNX_ENDPOINTS = ["https://overpass-api.de/api", "https://overpass.private.coffee/api"]


def snap_bbox(west, south, east, north, step=0.02):
    """Round a bbox outward to a 0.02° (~2 km) lattice so nearby analyses reuse the cached network."""
    import math
    return (math.floor(west / step) * step, math.floor(south / step) * step,
            math.ceil(east / step) * step, math.ceil(north / step) * step)


def osm_graph(builder, *args, **kwargs):
    """Call an osmnx graph builder with cache, endpoint fallback and exponential backoff."""
    import os
    import osmnx as ox
    ox.settings.use_cache = True
    ox.settings.cache_folder = os.path.expanduser("~/.cache/io-gametheory/osmnx")
    ox.settings.requests_timeout = 240
    ox.settings.overpass_rate_limit = False
    last = None
    for attempt in range(6):
        ox.settings.overpass_url = OSMNX_ENDPOINTS[attempt % len(OSMNX_ENDPOINTS)]
        try:
            import sys as _sys
            print(f"[osmnx] downloading street network via {ox.settings.overpass_url} (attempt {attempt+1})", file=_sys.stderr, flush=True)
            return builder(*args, **kwargs)
        except Exception as e:  # noqa
            last = e
            if "No data elements" in str(e) or "Found no graph nodes" in str(e):
                raise
            time.sleep(min(60, 5 * 2 ** (attempt // len(OSMNX_ENDPOINTS))))
    raise RuntimeError(f"Street network download failed on all Overpass endpoints: {str(last)[:200]}")


def network_times(points_lat, points_lon, sites_lat, sites_lon, mode="walk", margin_km=1.0):
    """Travel time in minutes from each point to each site over the OSM street network.

    walk: 4.8 km/h on all walkable edges. drive: osmnx imputed speeds (free flow, no traffic).
    Returns (n_points, n_sites) array; unreachable = inf.
    """
    import networkx as nx
    import osmnx as ox
    lats = np.concatenate([np.asarray(points_lat, float), np.asarray(sites_lat, float)])
    lons = np.concatenate([np.asarray(points_lon, float), np.asarray(sites_lon, float)])
    d = margin_km / 111.0
    north, south = lats.max() + d, lats.min() - d
    east, west = lons.max() + d / np.cos(np.radians(lats.mean())), lons.min() - d / np.cos(np.radians(lats.mean()))
    G = osm_graph(ox.graph_from_bbox, snap_bbox(west, south, east, north), network_type="walk" if mode == "walk" else "drive")
    if mode == "walk":
        for u, v, k, data in G.edges(keys=True, data=True):
            data["travel_time"] = data["length"] / (4.8 / 3.6)
    else:
        G = ox.add_edge_speeds(G)
        G = ox.add_edge_travel_times(G)
    Gu = G.to_undirected() if mode == "walk" else G
    pn = ox.distance.nearest_nodes(G, X=np.asarray(points_lon, float), Y=np.asarray(points_lat, float))
    sn = ox.distance.nearest_nodes(G, X=np.asarray(sites_lon, float), Y=np.asarray(sites_lat, float))
    out = np.full((len(pn), len(sn)), np.inf)
    rev = Gu if mode == "walk" else G.reverse(copy=False)
    for j, s in enumerate(sn):
        # time from point to site = shortest path from site on the reversed graph
        dist = nx.single_source_dijkstra_path_length(rev, s, weight="travel_time")
        out[:, j] = [dist.get(p, np.inf) / 60.0 for p in pn]
    return out, G
