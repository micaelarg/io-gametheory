<p align="center"><img src=".claude-plugin/icon.png" width="96" alt=""></p>

# io-gametheory

**An applied industrial-organization and game-theory analyst, packaged as an agent skill.**

Ask it where to open a store, how much to bid in a tender, what to ask for in a salary negotiation, whether a merger will raise prices, whether bids look rigged, or which strategy survives in a population. It frames the question, gets the data, writes the game down, solves it with verified code, attacks its own conclusion, and explains the result so a non-economist can follow it.

A language model already knows the theory. What it lacks is discipline. This skill supplies the discipline: a fixed seven-step method, 20 solvers that check their own answers, and a mandatory "game card" at the end.

## What it covers

| Module | Questions it answers | Tools |
|---|---|---|
| **Core solvers** | Any game: discrete or continuous strategies, simultaneous or sequential, pure or mixed equilibria | Nash (support enumeration, MILP), backward induction with non-credible threats, continuous best responses with symbolic comparative statics and grid cross-checks, mixed equilibria of discontinuous games |
| **Location** | Where to open, how much a site captures, cannibalization, what the rival will do about it | Competitors from OpenStreetMap and Overture Maps (worldwide), demand from census or population grids, walking/driving isochrones on the real street network, Huff gravity model, two-chain location game with lease exclusivity, interactive maps |
| **Hotelling** | Cluster or spread out? Product positioning, political platforms, quality tiers, how many stores fit | One verified engine for every variant: linear/quadratic costs, line or circle, any consumer distribution, fixed prices (median voter, Eaton-Lipsey) or price competition (maximum differentiation), vertical differentiation, Salop free entry, sequential entry |
| **Auctions & procurement** | Bidding strategy, reserve prices, format design, recovering costs from observed bids | Equilibrium bids for any value distribution, revenue equivalence check, Myerson reserve and Bulow-Klemperer, asymmetric first-price auctions (exact ODE solver), bidding credits, GPV estimation, winner's curse |
| **Bargaining** | Salary, supplier, M&A, rent, settlements, coalitions | Nash and Kalai-Smorodinsky, Rubinstein with outside options, deadlines and breakdown risk, optimal final offer under uncertainty, Myerson-Satterthwaite, multi-issue logrolling, Shapley value and core |
| **Markets, mergers & collusion** | Market power, merger effects, whether a cartel is sustainable, whether prices or bids look coordinated | HHI with US/EU/UK thresholds, GUPPI/UPP, logit demand with instruments, Bertrand-logit merger simulation, Cournot merger paradox, critical discount factors in real time, price screens, bid-rigging screens (rotation groups, cover bids, overcharge) |
| **Evolutionary games** | Which behaviors, conventions or alleles persist | ESS (including mixed), replicator/best-response/logit dynamics with phase plots, Moran fixation and the one-third rule, population genetics with drift and Kimura fixation, Hamilton's rule, spatial games |

Every solver was tested against closed-form results from the literature (Cournot, Stackelberg, Rubinstein, Myerson, Griesmer/Plum asymmetric auctions, d'Aspremont-Gabszewicz-Thisse, Salop, Hillman-Riley all-pay, Chatterjee-Samuelson, Kimura) and the skill was evaluated on 23 realistic prompts.

## The method

1. **Frame**: who decides, what they want, compared to what.
2. **Data first**: what would discipline the answer, and where to get it. Open data first, then APIs, then scraping; sources are listed by country.
3. **Write the game**: players, actions, timing, information, payoffs, with numbers.
4. **Solve with code**: never by eye; continuous solutions are cross-checked on a grid, and multiple or missing equilibria are checked rather than assumed away.
5. **What flips the answer**: thresholds a decision-maker can act on.
6. **Referee**: the three strongest objections, answered.
7. **Explain**: the game card, with the story in two lines, the five pieces, the right picture, why nobody wants to move, what is counterintuitive, and three reading levels.

## Install

### As a plugin (recommended)

In Claude Code:

```
/plugin marketplace add micaelarg/io-gametheory
/plugin install io-gametheory@io-gametheory
```

### As a plain skill

```
git clone https://github.com/micaelarg/io-gametheory
cp -R io-gametheory/skills/io-gametheory ~/.claude/skills/
```

The skill follows the open `SKILL.md` format, so agents that read skills from a folder can use it too.

### Requirements

- Python 3.10+ and [uv](https://docs.astral.sh/uv/). Every script declares its own dependencies inline and runs with `uv run`; nothing is installed globally.
- Internet access for the location module (OpenStreetMap, Overture Maps) and for some data sources.

## Use

Just ask. The skill activates on questions about competition, location, auctions, tenders, negotiation, mergers, collusion or evolutionary dynamics, in any language. A few examples:

- *"Two cement plants compete in quantities, demand P = 100 − Q, costs 10 and 20. What happens if the second cuts its cost to 15?"*
- *"I have four candidate storefronts in this neighborhood and a rival chain is also looking. Which one do I sign?"*
- *"I'm auctioning a painting; four serious buyers, values around 50k. What reserve should I set?"*
- *"Here is a CSV of five years of road tenders with every bid. Find anything suspicious."*
- *"I have an offer for 90k and think they'd go up to 110k. What should I ask for?"*
- *"Why might an industry stick with an inferior standard?"*

The scripts also work on their own. Each one prints a markdown report and has `--help`:

```
uv run skills/io-gametheory/scripts/solvers/finite_nash.py examples/stag_hunt.json
uv run skills/io-gametheory/scripts/solvers/continuous_br.py examples/cournot.json --leader "Firm 1" --plot br.png
uv run skills/io-gametheory/scripts/solvers/hotelling.py location --n 2 --stage price --k 2
uv run skills/io-gametheory/scripts/solvers/auctions.py numeric --bidder uniform:0,1 --bidder uniform:0,2 --plot bids.png
uv run skills/io-gametheory/scripts/solvers/bargaining.py issues --spec examples/union_negotiation.json
uv run skills/io-gametheory/scripts/solvers/merger.py hhi --shares examples/market_shares.csv --merge A,B
uv run skills/io-gametheory/scripts/solvers/evolutionary.py dynamics --rps 1,2 --plot rps.png
```

## Repository layout

```
.claude-plugin/        plugin and marketplace manifests, icon
skills/io-gametheory/
  SKILL.md             the method, routing table and quality bar
  references/          one guide per module (location, hotelling, auctions, bargaining,
                       io-markets, evolutionary, solution methods, data sources by country,
                       referee checklist, how to explain a game)
  scripts/solvers/     game solvers and economic tools
  scripts/location/    maps, competitors, demand, isochrones, Huff, location game
  evals/evals.json     23 evaluation prompts with pass criteria
examples/              ready-to-run game files
```

## Limits

- Statistical screens for collusion are red flags for further investigation, never proof.
- The location module depends on public OpenStreetMap servers, which can be slow; street networks are cached locally.
- Results are only as good as the assumptions. The skill labels every assumption and says which number would most change the conclusion.

## License

MIT
