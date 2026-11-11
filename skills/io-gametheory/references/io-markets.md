# Industrial organization: market power, mergers, collusion

Scripts: `scripts/solvers/merger.py` (`hhi`, `upp`, `demand`, `simulate`, `cournot`) and `scripts/solvers/collusion.py` (`sustain`, `prices`, `bids`). For price/quantity competition games use `continuous_br.py`; for differentiation `hotelling.py`; for tenders `auctions.py`.

## 1. Frame the question
| Question | Tools |
|---|---|
| How concentrated is this market? Will authorities look at this merger? | Market definition → `merger.py hhi` |
| Will this merger raise prices? How much efficiency offsets it? | `merger.py upp` (diversion), `simulate` (logit), `cournot` (homogeneous) |
| What are demand elasticities / diversion? | `merger.py demand` (logit with instruments); surveys; natural experiments |
| Can these firms collude? Is the market prone to it? | `collusion.py sustain` + structural checklist (§4) |
| Do prices / bids look collusive? | `collusion.py prices`, `collusion.py bids`, `auctions.py gpv` |
| Should we enter? How will the incumbent respond? | `extensive_form.py` (entry deterrence), Bresnahan-Reiss (`location.md`), limit pricing |
| Pricing strategy vs a rival | `continuous_br.py` (Bertrand/Cournot/differentiated), strategic complements vs substitutes |
| Platform / two-sided markets | §6 |
| Vertical relations (supplier-retailer, foreclosure) | §5, `bargaining.py` |

## 2. Market definition and concentration
- **SSNIP / hypothetical monopolist test**: smallest set of products/areas where a monopolist would profitably raise price 5-10%. Critical loss = X/(X+M) for an X% increase and margin M; compare with actual loss (from diversion/elasticities). High margins → small critical loss → **narrower** markets than intuition suggests.
- **Cellophane fallacy**: at already-monopolistic prices everything looks substitutable; don't define markets from current elasticities of a dominant firm.
- **HHI** = Σ shares² (shares in %); ΔHHI from a merger of i and j = 2·s_i·s_j. Bands: US 2023 guidelines presume harm if post HHI > 1800 and Δ > 100 (or merged share > 30% with Δ > 100); EU safe harbours: post < 1000, 1000-2000 with Δ < 250, > 2000 with Δ < 150. Most authorities worldwide use similar bands.
- Concentration is a screen. **Closeness of competition** (diversion between the merging products) drives unilateral effects.

## 3. Mergers
- **Unilateral effects (differentiated products)**: after merging, sales lost by raising product 1's price are partly recaptured by product 2 → upward pricing pressure. GUPPI₁ = D₁₂ · m₂ · p₂/p₁. GUPPI < 5% → usually safe.
- **Merger simulation**: calibrate a demand system (logit, nested logit, BLP; AIDS for groceries) to prices, shares and one margin; back out costs from Bertrand FOCs; re-solve with joint ownership. Logit understates effects when the merging products are closer substitutes than their shares suggest (IIA).
- **Efficiencies**: the cost reduction that offsets the price effect is the compensating marginal-cost reduction (Werden 1996). Must be merger-specific, verifiable, passed through; fixed-cost savings don't lower prices.
- **Homogeneous Cournot**: mergers without synergies raise prices and are often unprofitable (Salant-Switzer-Reynolds); making price fall requires the merged firm to be far more efficient (Farrell-Shapiro 1990).
- **Coordinated effects**: fewer, more symmetric firms with transparent prices → collusion easier (§4). A merger that removes a maverick is dangerous even with small ΔHHI.
- **Vertical mergers**: elimination of double marginalization (good) vs raising rivals' costs / foreclosure (bad). vGUPPI. Use `bargaining.py` for input-price negotiations (Nash-in-Nash).
- **Killer acquisitions / nascent competition**: buying a future rival (pharma, tech) - evaluate the counterfactual of the target's independent growth.
- Retrospectives exist for many industries (airlines, hospitals, beer, petroleum, supermarkets): cite them when calibrating plausibility.

## 4. Collusion
**Theory (repeated games)**: collusion is sustainable iff δ ≥ δ* = (π_D − π_C)/(π_D − π_N). Bertrand n firms: δ* = 1 − 1/n. Cournot linear: (n+1)²/(n²+6n+1). Detection lags raise δ*; translate into real time with `sustain`.

**Structural factors that facilitate collusion**: few firms; high barriers to entry; homogeneous products; symmetric costs/capacities; stable, predictable demand; frequent small transactions; **price transparency** (public prices, price-comparison sites, mandated price publication, information exchanges); multi-market contact; cross-ownership; trade associations; excess capacity used as a punishment threat; no maverick; inelastic demand.

**Behavioral screens**:
| Pattern | Screen | Innocent explanations |
|---|---|---|
| Prices move together, low variance | `prices` variance screen + break test | common costs, regulation, menu costs |
| Margins jump and stay high | `prices` margin break | cost measurement, demand shock, entry of a costly product |
| One firm always raises first, others follow | `prices` leadership | barometric leadership by best-informed firm |
| Edgeworth cycles with a coordinated restoration day | `prices` cycle signature + leader | competitive cycles are normal (Maskin-Tirole) |
| Prices rise with costs fast, fall slowly | `prices` pass-through asymmetry | search costs, inventories |
| Bid rotation | `bids` group rotation | capacity constraints, specialization |
| Cover bids (losers clustered far above winner) | `bids` RD, CV | genuine cost differences |
| Markups don't fall with more bidders | `auctions.py gpv` | selection, common values |
| Winning bids near/above the estimate | `bids` (with estimate) | bad estimates |
| Structural breaks around leniency cases / dawn raids | compare before/after | other contemporaneous changes |

**Algorithmic pricing**: pricing algorithms can learn to sustain supra-competitive prices without communication (Calvano et al. 2020); hub-and-spoke via a common pricing software provider is the current legal concern (RealPage-type cases).

**Legal**: price fixing, market sharing and bid rigging are per-se illegal / criminal in most jurisdictions; leniency programs reward the first confessor (a prisoner's dilemma by design - model it with `finite_nash.py`). Present screens as anomalies, not accusations.

## 5. Vertical relations and pricing practices
- Double marginalization; resale price maintenance; exclusive dealing; tying and bundling; loyalty rebates; MFN clauses (price parity in platforms).
- Price discrimination: first/second/third degree; welfare depends on output expansion. Personalized pricing with data.
- Predation: price below an appropriate cost measure (AVC/AAC) plus recoupment; reputation models.
- Limit pricing / entry deterrence: capacity as commitment (Dixit 1980), learning-by-doing, brand proliferation (product space pre-emption - Hotelling!).

## 6. Platforms and two-sided markets
- Prices depend on cross-side network effects: the side that brings more value to the other is subsidized (often free). Price structure ≠ cost structure; below-cost prices on one side are not predation per se.
- Single- vs multi-homing determines competitive bottlenecks (the multi-homing side gets charged).
- Tipping and winner-take-all; data as entry barrier; self-preferencing.

## 7. Data (see `data-acquisition.md`)
Competition-authority decisions (shares, diversion, margins); price panels (SEPA AR, fuel feeds ES/FR/DE/IT/CL/AU); procurement bids (OCDS publishers); company financials (margins: SEC EDGAR, Companies House, national registries); trade data (UN Comtrade) for import competition; scanner data (Nielsen/IRI/Kantar - paid) for demand estimation.

## 8. Explaining (game card hints)
- Mergers: *"Before, when A raised its price, customers who left went partly to B - a loss for A. After the merger, they go to the same owner, so raising the price stops hurting as much."* Picture: diversion arrows; price changes table.
- Collusion: *"Each firm could steal the whole market tomorrow by undercutting - but then the truce ends forever. If they meet often and see each other's prices, the one-day gain isn't worth losing the high margins."* Picture: the δ* line vs actual δ; the price series with the break.
- Counterintuitive: rivals gain from a merger more than the merging firms (Cournot); price transparency can hurt consumers; more firms can mean higher prices in search markets; a merger can be bad even when HHI is low (maverick removal).
