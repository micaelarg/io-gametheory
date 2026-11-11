# Data acquisition: what to get, from where (worldwide), and why

Principle: **every dataset must change a number in the game.** For each one, say which payoff, parameter or player it disciplines. Order of preference: **ask the user → open data → official APIs → paid APIs → scraping**. Source URLs and formats change: verify before relying on one, and record URL + access date for every number used.

## 0. Ask the user first (nobody else has it)
Own costs and margins, rents, sales by store/period/ticket (calibrates Huff β and attractiveness), loyalty/card data with customer postcodes (true catchments), reservation prices and BATNAs, past bids and auction results, contract terms.

## 1. Global sources (work in any country)
| Need | Source | Notes |
|---|---|---|
| Competitors / POIs | **OpenStreetMap** via Overpass (`competitors_osm.py`) | Free, everywhere; coverage varies (great in Europe, patchy in small towns and informal retail). |
| Competitors / POIs | **Overture Maps Places** (`competitors_overture.py`) | Free, global, built from Meta/Microsoft/Amazon/TomTom; often better than OSM for businesses outside Europe. Categories are coarse/noisy (grocery_store mixes supermarkets and specialty shops): filter by brand/name; merge with OSM. |
| Competitors / POIs (commercial) | Google Places, Foursquare OS Places (open), SafeGraph | Google is paid and restricts storage: only with the user's key and consent. |
| Population grids | **Kontur Population** (H3 ~400 m, HDX, per country), **GHSL GHS-POP** (100 m, EU JRC), WorldPop, Meta HRSL | Use when no census by small area. |
| Street network, travel times | OSM via osmnx (`isochrones.py`, `huff.py --distance network`) | Free-flow; no traffic. |
| Buildings | OSM, Overture buildings, Microsoft/Google Open Buildings | Open Buildings covers Africa/Asia/LatAm well (footprints, no floors). |
| Night lights (economic activity proxy) | NASA Black Marble / VIIRS | Coarse; useful for developing regions. |
| Public procurement | **OCDS** publishers (data.open-contracting.org) - 50+ countries in one format | Bid-level data in many (Chile, Colombia, Paraguay, Ukraine, UK…). |
| Firms & ownership | OpenCorporates, GLEIF (LEI), national registries | For collusion networks, groups of bidders. |
| Competition cases | Authority decisions (see §3) | Market definitions, shares, cartel evidence. |

## 2. Country/region sources by need

### Small-area population and income (demand)
| Country/region | Source |
|---|---|
| EU | Eurostat GEOSTAT 1 km grid; national: INE Spain (secciones censales + Atlas de distribución de renta), INSEE France (Filosofi 200 m grids with income), Destatis Zensus 100 m grid (DE), ISTAT sezioni (IT), CBS 100 m squares (NL) |
| UK | ONS Output Areas / LSOA (census + income estimates) |
| US | Census Bureau ACS (block groups, API), LEHD LODES (daytime/workplace population) |
| Canada | Statistics Canada dissemination areas |
| Mexico | INEGI AGEB/manzana census + **DENUE** (geolocated business directory - competitors by NAICS code, official) |
| Brazil | IBGE setores censitários; **CNPJ** open company registry with addresses (competitors) |
| Argentina | INDEC Censo 2022 radios censales |
| Chile | INE manzanas/zonas censales; SII business registry |
| Colombia | DANE manzanas (CNPV 2018); RUES/Confecámaras |
| Peru | INEI manzanas |
| Australia/NZ | ABS Mesh Blocks / SA1; Stats NZ meshblocks |
| India | Census villages/wards; SHRUG (development data platform) |
| Elsewhere | Kontur / GHSL / WorldPop grids |

### Retail and fuel prices (competition, price response to entry)
| Country | Open price data |
|---|---|
| Argentina | **SEPA** - daily prices per product per supermarket branch, with coordinates |
| Spain | Geoportal de Gasolineras (MITECO) - station-level fuel prices, real time |
| France | prix-carburants.gouv.fr (fuel, real time); Open Food Facts prices (crowd) |
| Germany | MTS-K / Tankerkönig (fuel, real time) |
| Italy | MIMIT Osservaprezzi carburanti |
| UK | CMA-mandated fuel price feeds (retailer open data) |
| Chile | CNE Bencina en Línea (fuel) |
| Mexico | CRE / CNE fuel prices; PROFECO "Quién es Quién en los precios" (groceries) |
| Australia | NSW FuelCheck, WA FuelWatch, QLD fuel prices |
| Greece | e-katanalotis (supermarket prices) |
| US | EIA (aggregates); state gas price feeds; BLS microdata (restricted) |
| Anywhere | Retailer websites / apps (scraping - see §4); Numbeo (crowd, rough) |
Fuel is the textbook dataset for spatial competition and collusion (Edgeworth cycles, rockets-and-feathers).

### Rents
Listing portals (Idealista ES/IT/PT, Rightmove UK, Zillow/LoopNet US, Zonaprop/Argenprop AR, Inmuebles24 MX, ZAP/VivaReal BR, Portal Inmobiliario CL, Domain AU). Scrape only aggregates, respecting ToS; or ask brokers.

### Footfall / mobility
Paid (Placer.ai, Unacast, telco data); Google Popular Times (no API); public transit ridership by stop (open in many cities: GTFS + ridership) as a proxy.

## 3. Competition authorities (market definitions, shares, cartel cases)
EU DG COMP; UK CMA; US FTC/DOJ; Germany Bundeskartellamt; France Autorité de la concurrence; Spain CNMC; Italy AGCM; Brazil CADE; Mexico COFECE (now CNA); Argentina CNDC; Chile FNE; Colombia SIC; Peru INDECOPI; Australia ACCC; India CCI; Japan JFTC; Korea KFTC; South Africa Competition Commission. Their decisions contain the data a model needs (shares, diversion, margins) and real collusion patterns.

## 4. Scraping rules
1. Look for an open dataset or API first (often exists: SEPA, fuel feeds, OCDS).
2. Read robots.txt and ToS; if prohibited, say so and propose an alternative.
3. Rate-limit (≥1 s between requests), cache, generic User-Agent, no login bypass, no CAPTCHAs.
4. Store raw + timestamp; record URL and date for every number.
5. No personal data; aggregate. Mind GDPR/LGPD and local equivalents.

## 5. When data is missing
Proceed with labeled assumptions and ranges, run the sensitivity, and end with: *"The single number that would most change this conclusion is X; you can get it from Y."*
