# Auctions and procurement

Script: `scripts/solvers/auctions.py` (`bne`, `reserve`, `numeric`, `gpv`, `common`; add `--procurement` for reverse auctions). All results are checked against closed forms or Monte Carlo inside the script.

## 1. First questions (frame before computing)
1. **Selling or buying?** Selling an asset (art, spectrum, a company, land) vs buying (public procurement, supplier tenders, freight). Buying = reverse auction: lowest price wins → `--procurement`.
2. **Private or common value?** Private: each bidder's value is their own (art for a collector, a construction firm's own cost). Common: the object is worth the same to all but nobody knows how much (oil tract, a company's future cash flows, a debt portfolio). Mixed is common in practice. Common values → winner's curse → `common`.
3. **Who bids?** Number of bidders, symmetric or not (incumbent vs entrants, local vs foreign firms, large vs small) → `numeric` for asymmetric.
4. **Format** - sealed first-price (most procurement), Dutch (flowers, fish, some treasury), English (art houses, cars, real estate), Vickrey/second-price (rare in pure form; eBay proxy bidding ≈ second-price), all-pay (contests, lobbying, R&D races, crowdsourcing), multi-unit (treasury, electricity, emissions, spectrum).
5. **Reserve / maximum price**, entry fees, information disclosure (estimates, condition reports).
6. **Repeated?** Same bidders meeting often → collusion risk (bid rotation, cover bids). See §7.

## 2. Core results (with the command that reproduces each)
| Result | Statement | Command |
|---|---|---|
| Bidding in second-price / English | Bid your value (dominant). English ≈ second-price with private values | `bne` |
| Bidding in first-price / Dutch | Shade: b(v) = v − ∫_r^v F^{n−1}/F^{n−1}(v). Uniform: b = (n−1)/n · v | `bne --plot` |
| **Revenue equivalence** | Symmetric IPV, risk-neutral, highest type wins, same reserve → same expected revenue for all formats | `bne` (closed form + MC of 3 formats) |
| **Optimal reserve** (Myerson 1981) | r − (1−F(r))/f(r) = seller's value; **independent of n**; above the seller's value | `reserve` |
| **Bulow-Klemperer** (1996) | One more bidder without reserve beats the optimal reserve with n bidders | `reserve` |
| Asymmetric bidders | Formats are no longer equivalent; first-price can be inefficient; **weak bidders bid more aggressively** (Maskin-Riley 2000); first-price often raises more revenue | `numeric --bidder … --bidder …` |
| All-pay / contests | Bid ∫ u dF^{n−1}; with complete information and asymmetric values, mixed strategies (weak player has an atom at 0) | `bne`, `mixed_continuous.py` |
| Winner's curse | Common values: naive bidding loses money; shade more with more bidders; English > sealed in revenue (linkage principle) | `common` |
| Risk aversion | First-price > second-price in revenue (risk-averse bidders shade less) | reason; first-price bids rise |
| Budget constraints | Favor first-price / all-pay over second-price for revenue | reason |
| Entry | Endogenous entry with costs: reserves deter entry; fees and reserves interact (Levin-Smith 1994) | reason + `reserve` sensitivity |

## 3. Design checklist (seller / procuring agency)
- **Get more bidders** before tuning anything else (Bulow-Klemperer). Lower entry costs, publicize, split lots so small firms can bid, avoid tailored specifications.
- **Reserve**: set by Myerson if the seller can commit not to re-auction; publish it if that encourages entry; secret reserves are common in art (low estimate ≈ reserve).
- **Asymmetry**: with a strong incumbent, first-price or bidding credits for entrants raise revenue and competition.
- **Common values**: release information (condition reports, data rooms, engineer's estimates) - reduces winner's curse and raises revenue.
- **Collusion-proofing**: sealed bids over open ones when collusion is a risk; don't publish all bids immediately when the same firms meet often; vary reserves; random lot sizes; screening (§7).
- **Multi-unit**: uniform-price invites demand reduction; pay-as-bid changes bidding but not necessarily revenue; ascending clock / combinatorial for complements (spectrum).
- **Procurement specifics**: abnormally low tenders (winner's curse, renegotiation), scoring auctions (price + quality weights), framework agreements, the maximum price as a reserve.

## 4. Empirics: from observed bids to values (`gpv`)
- First-price bids → private values: v = b + G(b)/((n−1)g(b)) (procurement: c = b − (1−G(b))/((n−1)g(b))).
- Before running: **normalize** bids by an object-level benchmark (engineer's estimate, budget, auction-house estimate) or regress out covariates (homogenized bids), and run separately by n.
- Outputs: recovered values, markups, **markups vs n** (should fall), **monotonicity** (should hold). Failures → collusion, common values, risk aversion, or uncontrolled heterogeneity.
- English/open auctions (art houses): the price ≈ second-highest valuation (+ increment) → bounds on values (Haile-Tamer 2003): price ≤ 2nd-highest value ≤ ... use the hammer price as a lower bound on the winner's value.
- Art: estimates are signals the house controls; low estimate ≈ reserve (often secret); buyer's premium raises the true price by 20-27%: always compare like with like (hammer vs premium-inclusive).

## 5. Data sources (worldwide)
Public procurement is published in the **Open Contracting Data Standard (OCDS)** in 50+ countries - one parser serves many: data.open-contracting.org lists publishers.
| Region | Procurement | Other auctions |
|---|---|---|
| EU | TED (Tenders Electronic Daily, all EU above thresholds), national portals (Spain PLACSP, France DECP/BOAMP, Italy ANAC, Portugal BASE, Germany e-Vergabe) | ECB/national treasury auction results; EEX emissions auctions |
| UK | Find a Tender, Contracts Finder (OCDS) | DMO gilt auctions; Ofcom spectrum |
| US | SAM.gov, USAspending, state portals | TreasuryDirect (all bids aggregated), FCC spectrum (bid-level data), BLM oil & gas leases, USDA timber |
| Latin America | Argentina COMPR.AR/CONTRAT.AR, Brazil PNCP/ComprasNet, Chile Mercado Público (excellent API), Colombia SECOP II, Mexico ComprasMX, Peru SEACE, Paraguay DNCP (OCDS) | central bank FX/treasury auctions; electricity (CAMMESA AR, CCEE BR) |
| Asia/Oceania | India GeM/CPPP, Indonesia LPSE, Philippines PhilGEPS, Australia AusTender | spectrum regulators |
| Global | World Bank and IDB contract awards, UNGM | Art: Christie's, Sotheby's, Phillips results pages; regional houses |
Bid-level data (all bids, not just winners) is what enables `gpv` and collusion tests - check that the source has it (Chile, Brazil, Colombia, EU TED partially, many US agencies do).

## 6. Explaining auctions (game card hints)
- Story: *"Each bidder knows what it's worth to them, not what the others think."*
- Picture: bid functions (`bne --plot`, `numeric --plot`): bids below the 45° line = shading.
- Stability: *"If you bid more you'd win more often, but each win would be worth less; at the equilibrium bid, the extra wins exactly pay for the lower margin."*
- Counterintuitive favorites: second-price makes honesty optimal; more bidders in common-value auctions make each bid *more* cautious; a weak bidder bids more aggressively than a strong one with the same value; a reserve that sometimes leaves the item unsold raises expected revenue; one more bidder is worth more than the cleverest reserve.

## 7. Collusion in auctions (screens; full module pending)
- Bid rotation: winners take turns; low win-rate variance among a stable group.
- Cover bids: losing bids far above the winner, clustered; losers never win when the "designated" winner bids.
- Phantom competition: bids identical or in fixed ratios; same typos/formatting; bids submitted from the same IP or minutes apart.
- Structural: markups flat in n (`gpv`), winning bid near the maximum price, fewer bidders after a cartel forms, subcontracting to losers.
- Econometric: Porter-Zona (1993) - test whether ranks of bids depend on costs for non-winners; Bajari-Ye (2003) - conditional independence and exchangeability.
Flag legal context: bid rigging is criminal in most jurisdictions; present screens as red flags, not proof.
