# Location: where to open, and what the rivals will do about it

## 1. Identify which location question it is

| Question | Core model | Main script |
|---|---|---|
| Best site for one new store, rivals fixed | Huff gravity + rent | `huff.py` |
| Adding a store to my own chain | Huff with cannibalization; p-median / coverage | `huff.py --owner` |
| A rival will respond / is also looking | Location game (simultaneous or leader-follower) | `location_game.py` + `finite_nash.py` |
| Should I enter this town at all / how many stores fit | Entry thresholds (Bresnahan-Reiss), Salop free entry | `continuous_br.py` / back-of-envelope |
| Cluster with rivals or stay away? | Hotelling (with vs without price competition), agglomeration - see `hotelling.md` | `hotelling.py` + data on product type |
| Coverage ("everyone within 10 minutes") | Isochrones, maximal covering | `isochrones.py` |

Most real questions combine the first and the third: **rank sites with Huff, then check the rival's best response.** A site ranked first that invites a rival to open next door may lose to a site ranked second that is hard to contest.

## 2. The models (what each one teaches)

### Hotelling - linear city
Consumers uniform on [0,1], two firms, transport cost.
- **Prices fixed (or regulated)** → both firms move to the center: *minimum differentiation* (why gas stations, pharmacies and fast food cluster when prices barely differ).
- **Prices chosen after locations, quadratic transport cost** → firms locate at the extremes: *maximum differentiation* (d'Aspremont-Gabszewicz-Thisse, 1979). Moving closer triggers a price war that costs more than the customers gained.
- **Linear transport cost** → no pure price equilibrium when firms are close (discontinuous demand): a warning that "close + price competition" is unstable.
- Lesson for the client: **whether to cluster depends on how much price competition the proximity triggers.** Ask: do these stores compete on price (groceries, fuel) or on assortment/variety (clothing, restaurants)?

Equilibrium prices with quadratic cost t·d², firms at a and 1−b: pᵢ = c + t(1−a−b)(1 ± (a−b)/3). Use `continuous_br.py` to solve variants.

### Salop - circular city, free entry
n firms equally spaced, linear transport cost t, fixed cost F, market size L.
- Price p = c + t/n. Free entry: n* = √(tL/F).
- **Excess entry**: the social optimum is n*/2 - the market gets too many stores because entrants steal business (a business-stealing externality). Useful for "is this market saturated?".

### Huff - gravity model (the workhorse)
Probability that a consumer at i shops at store j:

  P_ij = A_j^α · d_ij^(−β) / Σ_k A_k^α · d_ik^(−β)

- A_j attractiveness (floor area m², number of checkouts, brand index), α its elasticity (~1).
- d_ij distance or travel time, β distance decay.
- Expected demand of j = Σ_i w_i · P_ij, with w_i the demand weight at i (population × spend per capita).
- **β calibration**: convenience/grocery β ≈ 1.5–3 (people won't go far); destination/shopping β ≈ 0.5–1.5. With the user's sales by store, calibrate β (and α) by matching predicted to actual sales. Without it, **always sweep β** and report whether the ranking survives (`huff.py --beta-sweep`).
- **Known flaw (IIA)**: a new store steals proportionally from all rivals, even if it is next to one of them. In reality it steals mostly from the nearby one. Mitigate with network distance and high β; mention it in the referee step when a candidate is adjacent to a rival.
- **Cannibalization**: if the client already has stores, the relevant number is **net** gain: captured demand − demand taken from own stores.

### Leader-follower / competitive location
Two (or more) chains choosing among candidate sites:
- **Simultaneous**: payoff matrix (Huff demand × margin − rent), find Nash equilibria. Often several - coordination on "you take north, I take south".
- **Sequential**: the leader anticipates the follower's best response. **Value of moving first = leader payoff − simultaneous payoff.** If it is large, speed (signing the lease first) is worth money - say how much.
- **Preemption**: sometimes the best move is to take the site the rival needs, even if it is not your best stand-alone site.
- **Entry deterrence**: an incumbent can open a store that is unprofitable alone because it makes entry unprofitable for the rival. Check credibility: would the incumbent keep it open after entry?

### Entry thresholds - Bresnahan-Reiss
Across comparable towns, the population needed to support 1, 2, 3... stores. If S₂/S₁ ≫ 2, the second entrant cuts margins a lot (strong competition). Practical use: "This town has 12,000 people and 2 supermarkets; comparable towns support a 3rd at ~15,000."

### Agglomeration vs dispersion
Cluster when consumers compare/search (car dealers, furniture, clothing, restaurants: the cluster attracts more total demand). Disperse for convenience goods bought by proximity (grocery, pharmacy, bakery). Mixed: anchor-tenant logic in malls.

## 3. Workflow (real decision)

0. **Can you legally open there? (regulated entry - check FIRST)** Many formats need a licence whose rules decide the
   answer before any demand model: pharmacies (Spain, France, Italy, Portugal, Austria, parts of LatAm: population
   modules and minimum distances, e.g. 250 m), tobacconists/estancos, lottery outlets, petrol stations (distance
   rules, environmental permits), liquor licences, cannabis retail, gambling, schools, clinics; plus zoning/land use
   and heritage districts everywhere. Check the national/regional rule, then measure the candidates against existing
   licensed outlets (`competitors_osm.py` / `competitors_overture.py` + distances). If entry is closed, the real
   options are buying an existing licence or relocating one - and the "location game" becomes a game over licences.
1. **Frame**: format (supermarket vs convenience store), the decision (which of N candidate sites / whether to enter), the owner's existing stores, horizon.
2. **Data** (see `data-acquisition.md`): candidates with rents (ask the user; addresses → coordinates with `geocode.py`), competitors from **two sources** - `competitors_osm.py` and `competitors_overture.py` (global) - merged and checked against Google Maps; official business registries where they exist (DENUE Mexico, CNPJ Brazil…), demand (national small-area census > population grid (Kontur/GHSL) > `demand.py --osm-streets` > `--osm-buildings`; the building proxy self-checks coverage and is unusable in many cities), attractiveness (m² if known; brand tiers otherwise, e.g. hyper/large 3, discounter/express 1, independents 0.7 - label as assumption), prices from the country's open price data if any (`data-acquisition.md` §2 - also tells you which rivals are discounters). Mark own and rival chains' stores in an `owner` column.
   **Study area**: demand and competitors must extend at least one catchment radius beyond the farthest candidate, or edge candidates are mis-measured (`huff.py` warns).
3. **Coverage**: `isochrones.py` around each candidate: population within 5/10/15 min walk or drive.
4. **Huff**: `huff.py --distance network` (straight lines can reorder the ranking: parks, rail lines, avenues), β sweep, `--owner` for cannibalization → ranking + robustness. If #1 and #2 differ by < 5%, it is a **tie**: say so and decide on other grounds.
5. **Economics**: convert captured demand to profit: demand points weight × spend per capita × capture share × margin − rent − fixed costs. Ask the user for margin and rent; otherwise label assumptions.
6. **Rival response**: `location_game.py` with `--a-owner/--b-owner` (chain-level payoffs net of cannibalization) → Nash, Stackelberg, value of signing first, and **naive vs strategic** choice. When they differ, that difference is the headline.
7. **Map**: `map.py` with demand, rivals, candidates colored by score, isochrones of the top site.
8. **Referee + game card**.

## 4. Pitfalls specific to location
- Straight-line distance across rivers, highways, rail lines, parks - use `--distance network`.
- Night population only: offices, universities, hospitals, transit hubs create daytime demand.
- POI data missing stores (small towns, informal and independent retail - kiosks, corner shops, street markets - are under-mapped almost everywhere). Use two sources and verify a sample.
- Units: β depends on whether distance is in km or minutes, and on the country's travel mode (walk-dominant dense cities vs car-dominant suburbs). Never import a β from another context without the sweep.
- Brand heterogeneity: a hard discounter and a premium store are not equally attractive to the same households; segment by income if possible.
- Ignoring delivery/online share for the category.
- Treating the rival as fixed when the rival is actively expanding (look at their recent openings).
- Recommending the best gross site when the net (after cannibalization and rent) is worse.

## 5. How to explain a location result
The **map is the picture**. Annotate: where demand is, where rivals are, each candidate's catchment, and where the rival would answer. Story example:
> *"Site B captures fewer customers than A on paper, but A sits where the rival would open right next to you within a year and split them. B is far enough from the rival's best spots that answering you doesn't pay for them. B wins unless its rent is more than ~$X above A's."*
