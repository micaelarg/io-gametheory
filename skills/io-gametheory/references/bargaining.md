# Bargaining and negotiation

Script: `scripts/solvers/bargaining.py` (`nash`, `rubinstein`, `offer`, `double`, `issues`, `shapley`). Works for any negotiation: salaries and union contracts, supplier/retailer terms, M&A price, rent, debt restructuring, international treaties, divorce settlements, licensing, coalition governments, cost sharing.

## 1. Frame: the five pieces of a negotiation
- **Players** - who actually decides (and who is an *agent* with their own incentives: lawyers, managers, negotiators with mandates).
- **The pie** - what is created by agreeing vs not agreeing. Name the **value created** (synergies, gains from trade) separately from how it is **split**.
- **BATNAs / disagreement point** - what each gets with no deal: next-best buyer, strike pay, litigation outcome, the status quo. Distinguish **inside options** (what you get *while* disagreeing: rent during a dispute) from **outside options** (what you get if you *quit* for good).
- **Timing and costs of delay** - discount rates, deadlines, perishability, risk of breakdown (the other side walks, regulation changes, a competitor steps in).
- **The protocol** - who makes offers, how many rounds or sessions, **who has the last word before the deadline**, and what happens at the deadline (trial, strike, walk-away, status quo). Look it up (mediation law, procedure, contract) or ask; never invent it. When it is unknown, run `rubinstein --rounds-sweep` and show how the split changes with the number of rounds and with who speaks last.
- **Information** - does each side know the other's reservation price? Private info → delay, failed deals, signaling.

## 2. Which model when
| Situation | Model | Command |
|---|---|---|
| Split a surplus, symmetric info, want a benchmark | Nash bargaining (power α, BATNAs) | `nash --pie … --d …` or `--frontier` |
| Who has more patience / who moves first matters | Rubinstein alternating offers | `rubinstein --delta1 --delta2` or `--r1 --r2 --period` |
| A credible walk-away option exists | Outside-option principle | `rubinstein --outside2 …` |
| Hard deadline | Finite-horizon alternating offers | `rubinstein --rounds T` |
| Unknown number of rounds / who speaks last | Sweep the protocol | `rubinstein --rounds-sweep 1,2,3,5,10,inf` |
| Risk the talks collapse (not impatience) | Breakdown probability, inside options | `rubinstein --breakdown p --d …` |
| You don't know their reservation price | Optimal (final) offer under uncertainty | `offer --role --reservation --other dist` |
| Neither knows the other's | Chatterjee-Samuelson / Myerson-Satterthwaite | `double --support` |
| Several issues on the table | Integrative bargaining, logrolling, Pareto frontier | `issues --spec file.json` |
| More than two parties, coalitions | Shapley value, core | `shapley --spec file.json` |
| Ongoing relationship / hold-up | Repeated game; specific investments; contracts | reason; `extensive_form.py` |

## 3. Results to know (and use in the explanation)
- **Nash solution**: maximize (u1−d1)^α (u2−d2)^(1−α). With linear utilities each gets its BATNA plus a share α / 1−α of the surplus. **Raising your BATNA by 1 raises your payoff by about α to 1** - the most reliable lever. Risk aversion loses bargaining power.
- **Rubinstein (1982)**: proposer keeps (1−δ2)/(1−δ1δ2). Immediate agreement (in theory, delay is a mistake when information is complete). First-mover advantage vanishes as offers get frequent; the split converges to Nash with α = r2/(r1+r2) → **the more patient side gets more**.
- **Outside-option principle** (Binmore-Shaked-Sutton 1989): an outside option only matters if it exceeds what you would get by bargaining; then you get exactly the outside option. "I have another offer" works only if that offer is better than your bargaining share.
- **Breakdown risk**: pure risk of collapse with inside options → Nash with disagreement point = inside options (not outside options).
- **Deadlines**: with a known last round, whoever makes the last offer has ultimatum power. Real deadlines produce last-minute agreements ("deadline effect").
- **Commitment** (Schelling 1956): binding yourself (public statements, delegation to an agent with limited authority, "my board won't approve more") can win - if credible and observable. Over-commitment by both sides → breakdown.
- **Private information**: efficient deals fail. Myerson-Satterthwaite: no procedure is efficient, voluntary and budget-balanced. With uniform values, ~16% of the gains are lost even in the best equilibrium (`double`). Delay and strikes are screening/signaling devices (the patient/strong type waits).
- **Coase conjecture**: a seller who cannot commit not to cut prices later competes against its future self → prices fall toward cost. Durable goods, land, repeated offers to the same buyer.
- **Hold-up**: if one side makes a relationship-specific investment before bargaining, the other side captures part of its return → underinvestment. Fix with contracts, vertical integration, or ownership (Grossman-Hart-Moore).
- **Multi-issue**: splitting each issue in half is usually **Pareto-inefficient**. Trade issues by relative importance (logrolling). Adding issues (timing, guarantees, contingent payments, earn-outs) can create a ZOPA where none existed.
- **Contingent contracts** settle disagreements about the future: bet on it instead of arguing (earn-outs in M&A, indexed prices).
- **Coalitions**: Shapley = average marginal contribution; **scarce sides capture the surplus** (glove game: one left glove and two right gloves → the left owner gets everything in the core). Empty core → unstable coalitions, expect defections.
- **Two-level games** (Putnam 1988): a negotiator with a tough domestic constituency (ratification) has more bargaining power abroad.

## 4. Practical translation (BATNA / ZOPA language)
- **Reservation price** = walk-away value (from BATNA). **ZOPA** = overlap of reservation prices. **Anchor** = first offer.
- Opening offer: with uncertainty about the other side, `offer` gives the price that maximizes expected gain; open a bit beyond it if there will be counteroffers, concede toward it.
- Probe the other side's BATNA; improve yours before negotiating (get a second quote - it is worth α per unit).
- Watch for agents: the person across the table may have a mandate (limit) and career incentives.

## 5. Data and calibration (worldwide)
- Wage bargaining: collective agreements registries (ministries of labour; EU Eurofound database; ILO), strike data (ILO, national statistics).
- M&A: deal terms in SEC EDGAR (merger proxies, 8-K), Companies House (UK), CNMV (ES), CVM (BR); premiums paid as bargaining outcome.
- Bilateral industry bargaining: retailer-supplier margins (competition authority reports), hospital-insurer prices (US price transparency files), carriage fees (TV), rent negotiations (listing vs contract prices).
- Litigation/settlement: court records of settlements (where public).
- International: treaty texts and negotiation records (WTO, UN treaty collection).
Use them to calibrate BATNAs (next-best prices), patience (cost of delay), and outcomes (observed splits).

## 6. Explaining a negotiation (game card hints)
- Story: who wants what, what happens with no deal, who can wait longer.
- Picture: the frontier with BATNA point and solutions (`nash --plot`); or the round-by-round table (`rubinstein --rounds`).
- Stability: *"Neither side will reject: the responder gets exactly what waiting would give them, so rejecting gains nothing, and the proposer can't ask for more without being rejected."*
- Counterintuitive: a better outside option that is still worse than your bargaining share changes nothing; being more patient beats being smarter; tying your own hands can make you stronger; splitting every issue 50/50 leaves money on the table; a deadline helps whoever speaks last.
