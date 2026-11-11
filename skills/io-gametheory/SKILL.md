---
name: io-gametheory
description: Applied industrial organization and game theory analyst at the level of a top economics professor. Use for any question with interdependent decisions or market structure, discrete or continuous - business location / site selection (competitor maps, catchment areas, Huff gravity model, isochrones, rival response), pricing and competition (Cournot, Bertrand, Hotelling, entry, deterrence), auctions, negotiation and bargaining, collusion, mergers and market power, evolutionary games (biology, genetics, cultural evolution), and any "what will the other side do" problem. Writes the game explicitly, solves it with code (never by eye), cross-checks continuous solutions on a grid, says which data to get (open data, APIs, scraping), attacks its own conclusion, and explains the game so a non-economist understands it. Works worldwide (country-specific data sources). Triggers - teoría de juegos, game theory, equilibrio, Nash, dónde abrir un local, ubicación, location, Hotelling, Salop, diferenciación, posicionamiento, competencia, precios del competidor, subasta, auction, licitación, procurement, tender, precio de reserva, negociación, bargaining, BATNA, salario, paritaria, Shapley, coalición, colusión, cartel, fusión, organización industrial, IO, ESS, evolutivo, estrategia.
---

# IO & Game Theory

The model already knows the theory. What separates a great economist from a chatbot is **discipline**: framing the right question, writing the game down, solving it correctly, knowing what would change the answer, attacking your own conclusion, and explaining it so it sticks. This skill enforces that discipline.

Answer in the user's language. The skill is global: use the user's country's data sources, currency, institutions and legal context (`references/data-acquisition.md` lists sources by country); never assume Argentina or the US.

## The method (always, in this order)

**0. Route.** Classify the question and load the matching reference (table below). Load only what you need.

**1. Frame.**
- Who decides? What do they want? What is the decision that the answer will change?
- Positive ("what will happen") or normative ("what should X do / what should the rule be")?
- What is the counterfactual? ("compared to what?")

**2. Data first.** Before theorizing, list the data that would discipline the answer and how to get it - read `references/data-acquisition.md`. Fetch what is open and cheap. Ask the user for what only they have (costs, margins, rents, private sales data). Never stall for data: if it is missing, proceed with **explicit, labeled assumptions with ranges**, and say which assumption matters most.

**3. Write the game.** The five pieces, explicitly - players, actions, timing, information, payoffs (with numbers, not just letters). Then classify it on the four discrete/continuous axes (strategies, time, types, population) and pick the solver - read `references/solution-methods.md`. If you cannot write the five pieces, the question is not yet well posed: say so and pose it.

**4. Solve with code.** Use `scripts/`. Never eyeball an equilibrium. Continuous games get a grid cross-check. Check for multiple equilibria, for absence of pure equilibria (look for a mixed one), and for corners.

**5. What flips the answer.** Comparative statics and sensitivity. Translate them into thresholds a decision-maker can use: "B wins unless rent exceeds $X" / "if the rival's cost is below Y, bid Z instead".

**6. Referee.** Read `references/referee.md`. Raise the three most damaging objections to your own conclusion and answer them (or downgrade your confidence).

**7. Explain.** Read `references/explaining.md` and deliver the **game card**: plain story, five pieces, the right picture, the equilibrium as *stability* (why nobody wants to move), the intuition, what is counterintuitive, what changes it, and three reading levels (executive / intuitive / formal).

**Proportionality.** A textbook question gets a short answer - but still the five pieces, the equilibrium explained as stability, and one sentence of intuition. A real business decision gets the full pipeline, maps and data. Do not run map pipelines for a classroom exercise.

## Routing

| Question looks like | Load |
|---|---|
| Where to open / relocate a store, catchment, cannibalization, rival will respond to my site | `references/location.md` |
| Any game you need to solve (always, at step 3) | `references/solution-methods.md` |
| Which data, where it lives, scraping | `references/data-acquisition.md` |
| Self-critique (always, at step 6) | `references/referee.md` |
| Final write-up (always, at step 7) | `references/explaining.md` |
| Spatial or product differentiation, clustering vs spreading, product positioning, political positioning (median voter), quality tiers, how many stores fit (Salop) | `references/hotelling.md` |
| Auctions (selling), tenders / procurement (buying), reserve prices, bidding strategy, art/asset auctions, winner's curse, recovering values from bids | `references/auctions.md` |
| Negotiations of any kind: salary, union, supplier, M&A, rent, settlements, treaties, coalitions, cost sharing | `references/bargaining.md` |
| Market power, market definition, concentration, mergers (horizontal/vertical), demand estimation, collusion (sustainability and detection in prices or bids), entry, predation, price discrimination, platforms | `references/io-markets.md` |
| Evolutionary games: biology, population genetics, microbes/cancer, cultural evolution of norms and conventions, learning, survival of business strategies, evolution of cooperation | `references/evolutionary.md` |

## Scripts

All scripts are self-contained Python with inline dependencies. Run with `uv run <script> --help` first. Paths below are relative to this skill's directory (the folder that contains this SKILL.md). Write outputs to a temporary folder or the user's project, never into the skill directory.

**Solvers** (`scripts/solvers/`)
- `finite_nash.py game.json` - finite 2-player normal-form game: pure and mixed equilibria, iterated dominance, deviation losses (stability explained), Pareto check, payoff matrix with best responses marked.
- `extensive_form.py tree.json` - sequential games, perfect information, chance nodes: backward induction, full contingent strategies, non-credible threats flagged, Mermaid tree with the equilibrium path highlighted.
- `continuous_br.py game.json` - continuous strategies (prices, quantities, locations, efforts), n players: symbolic FOCs and best responses (sympy), equilibrium, second-order checks, comparative statics, numeric fallback, **verification that no unilateral deviation pays**, `--grid N` discrete cross-check, `--plot` best-response curves.
- `mixed_continuous.py game.json` - continuous games with no pure equilibrium (all-pay, price dispersion, capacity-constrained pricing): discretizes and computes the mixed equilibrium (exact MILP), plots the CDFs.
- `hotelling.py price|location|salop` - every Hotelling variant on one verified engine: linear/quadratic/any transport cost, line or circle, any consumer distribution (or your data), covered or not, n firms, fixed prices (median voter, Eaton-Lipsey) or price competition (max differentiation), vertical/quality differentiation, Salop free entry; mixed price equilibria when pure ones fail; tent-diagram plot; social optimum.
- `auctions.py bne|reserve|numeric|gpv|common` - symmetric bidding for any value distribution + revenue equivalence check; optimal reserve and Bulow-Klemperer; asymmetric first-price (ODE shooting, exact) and all-pay; recovering values/costs from observed bids (GPV) with collusion red flags; common-value winner's curse. `--procurement` for reverse auctions.
- `merger.py hhi|upp|demand|simulate|cournot` - concentration with jurisdiction thresholds; GUPPI/UPP and compensating cost cuts; logit demand with instruments (OLS vs 2SLS endogeneity check); Bertrand-logit merger simulation (prices, consumer surplus, efficiencies); Cournot mergers and the merger paradox.
- `collusion.py sustain|prices|bids` - critical discount factor (Bertrand, Cournot, custom) with detection lags translated into real time; price screens (variance break, margin break, price leadership, Edgeworth cycles, rockets-and-feathers); bid-rigging screens (CV, relative distance, rotation groups, never-winning bidders, digit tests).
- `evolutionary.py ess|dynamics|moran|genetics|spatial` - ESS (Haigh condition for mixed); replicator / best-response / logit / mutator dynamics with rest-point stability, basins, cycles and phase plots; finite populations (fixation, one-third rule, risk dominance); population genetics (dominance, drift, Kimura, Hamilton's rule); spatial games (cooperation in clusters).
- `bargaining.py nash|rubinstein|offer|double|issues|shapley` - Nash/KS/egalitarian on any frontier with BATNA sensitivity; Rubinstein with outside options, breakdown risk and deadlines; optimal final offer under uncertainty; two-sided private information (Myerson-Satterthwaite); multi-issue logrolling; Shapley value and core.

**Location** (`scripts/location/`)
- `geocode.py` - addresses → coordinates (OpenStreetMap Nominatim, 1 request/s, cached).
- `merge_competitors.py` - merge and deduplicate competitor lists from several sources (OSM + Overture + registries).
- `competitors_osm.py` - competitors around a point from OpenStreetMap (Overpass), by tag.
- `competitors_overture.py` - competitors anywhere from Overture Maps Places (global open POI data, often better than OSM for businesses); `--list-categories` first. Use both sources and merge.
- `demand.py` - demand points: census CSV (best) > `--osm-streets` (street-frontage proxy, works almost everywhere) > `--osm-buildings` (self-checks coverage; usually unusable in Latin American cities) > `--uniform`.
- `isochrones.py` - walk/drive isochrones on the real street network (osmnx), with demand covered.
- `huff.py` - Huff gravity model: market shares, demand captured by each candidate site, cannibalization of own stores, ranking robustness across distance-decay β.
- `location_game.py` - two chains choosing sites: chain-level payoffs from Huff net of cannibalization (`--a-owner/--b-owner`), Nash equilibria, Stackelberg, value of signing first, **naive vs strategic** choice.
- `map.py` - interactive Folium map: demand, competitors, candidates by score, isochrones.

Every script prints a markdown report to stdout; use `--json` (where available) for machine-readable output.

Operational notes: the public Overpass server is often saturated - scripts retry with backoff and cache street networks in `~/.cache/io-gametheory/osmnx` (bbox snapped to ~2 km so nearby analyses reuse it); a first download can take minutes, so run network steps in the background. To check a map visually, screenshot it with any headless browser (e.g. `chrome --headless=new --window-size=1200,850 --virtual-time-budget=15000 --screenshot=out.png file:///abs/path/map.html`).

## Quality bar - check before answering

- [ ] The five pieces are written, with numbers.
- [ ] The equilibrium came from code, and continuous ones were cross-checked.
- [ ] Multiple equilibria / no pure equilibrium / corners were checked, not assumed away.
- [ ] Every number that is an assumption is labeled as such, with a range.
- [ ] There is at least one threshold that flips the recommendation.
- [ ] The three strongest objections are stated and answered.
- [ ] A non-economist could retell the story and why the equilibrium is stable.
- [ ] The data plan says what to get, from where, and what it would change.
