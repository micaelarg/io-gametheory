# Privacy policy

_Last updated: November 12, 2026_

`io-gametheory` is an open-source skill that runs on your own computer. Its author operates no server, collects no data, and receives nothing from you.

## What the plugin handles

- **Your questions and files** stay inside your agent session and your working directory. The plugin's scripts write results (tables, charts, maps) only to files in your working directory.
- **Personal data:** the plugin does not ask for it. If you give the geocoding script addresses, they are sent to OpenStreetMap Nominatim to turn them into coordinates, and the results are saved only on your computer.
- **No telemetry, no analytics, no accounts, no API keys or credentials.**

## What is sent to outside services

The game solvers (`scripts/solvers/`) run offline. Only the location scripts contact outside services, and only with the inputs you pass them:

| Script | Service | What is sent |
|---|---|---|
| `competitors_osm.py`, `demand.py`, `isochrones.py` | OpenStreetMap Overpass API (`overpass-api.de`, fallback `overpass.private.coffee`) | a bounding box or a point and radius, and map tags |
| `geocode.py` | OpenStreetMap Nominatim (`nominatim.openstreetmap.org`) | the addresses you ask it to geocode |
| `competitors_overture.py` | Overture Maps public dataset (`s3://overturemaps-us-west-2`, read-only) | a bounding-box query |
| `map.py` (when you open the HTML map) | OpenStreetMap tile servers and jsDelivr | the map area being viewed |

Running a script with `uv run` downloads the Python packages it declares from PyPI.

These services are run by third parties under their own policies, including how long they keep request logs:

- OpenStreetMap Foundation: https://osmfoundation.org/wiki/Privacy_Policy
- Overture Maps Foundation: https://overturemaps.org/privacy/ (data hosted on Amazon S3: https://aws.amazon.com/privacy/)
- jsDelivr: https://www.jsdelivr.com/terms/privacy-policy-jsdelivr-net
- PyPI: https://policies.python.org/pypi.org/Privacy-Notice/

## Retention

The plugin's author retains no data, because none is received.

## Contact

Questions about this policy: open an issue at https://github.com/micaelarg/io-gametheory/issues.
