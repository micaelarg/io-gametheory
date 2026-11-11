# Evolutionary game theory and population genetics

Script: `scripts/solvers/evolutionary.py` (`ess`, `dynamics`, `moran`, `genetics`, `spatial`). Strategies are not chosen by rational players: they are **inherited or imitated**, and what does well spreads. Same math for genes, behaviors, norms, technologies, firms' routines, and learning agents.

## 1. Where it applies
| Domain | "Strategy" | "Payoff / fitness" | Typical question |
|---|---|---|---|
| Biology / ecology | behavioral phenotype (fight or display, cooperate, signal) | reproductive success | Which behaviors persist? Polymorphisms? |
| Genetics | allele / genotype | viability × fertility | Will this allele fix? How fast? Why does a harmful allele persist? |
| Microbiology / cancer | cell types (producers vs cheaters, resistant vs sensitive) | growth rate | Will resistance take over? Can therapy exploit the dynamics (adaptive therapy)? |
| Cultural evolution | norms, conventions, languages, technologies | how often copied | Which convention wins? Why do inefficient norms persist? |
| Economics / management | routines, pricing rules, business models | profit (survival of firms) | Which strategies survive competition? Can cooperation survive? |
| Learning in games | actions of boundedly rational agents | experienced payoff | Which equilibrium will play converge to? |
| Online / platforms | content strategies, bots | engagement | Do clickbait-like strategies take over? |

## 2. Core concepts and the command for each
- **ESS** (Maynard Smith-Price 1973): a strategy that, once common, cannot be invaded by rare mutants: u(x,x) > u(y,x), or = and u(x,y) > u(y,y). Every ESS is Nash; not every Nash is ESS. Mixed ESS = stable **polymorphism** (e.g. Hawk-Dove: share of Hawks = V/C). → `ess`
- **Replicator dynamics**: ẋᵢ = xᵢ(fᵢ − f̄): strategies above average grow. ESS ⇒ asymptotically stable; stable ⇒ Nash; interior cycles possible (RPS). → `dynamics --plot` (phase line for 2 strategies, simplex for 3).
- **Other dynamics**: best-response (fast, myopic optimizers), logit (noisy choice, `--beta`), replicator-mutator (`--mutation`) - mutation moves rest points inward and can turn cycles into stable mixes or limit cycles.
- **Rock-Paper-Scissors**: if winning gains more than losing costs → stable interior (ESS); equal → neutral cycles; losing costs more → heteroclinic cycle (booms and busts of each type). Real cases: side-blotched lizards' mating strategies, E. coli colicin producers/resistant/sensitive strains.
- **Coordination / stag hunt**: two ESS; the basin of attraction decides; the **risk-dominant** convention is selected in the long run with mutations (Kandori-Mailath-Rob 1993, Young 1993) - not the efficient one.
- **Finite populations** (Moran): fixation probability ρ vs neutral 1/N; **one-third rule** (Nowak et al. 2004): with weak selection, A invades B if the unstable mix x* < 1/3. Drift can fix non-ESS strategies in small groups. → `moran`
- **Population genetics**: selection with dominance (directional, **heterozygote advantage** maintaining polymorphism - sickle cell / malaria, **underdominance** bistability); mutation-selection balance; drift; **Kimura**: a new allele with advantage s fixes with probability ≈ 2s if 4Ns ≫ 1, ≈ 1/(2N) if |4Ns| ≪ 1. → `genetics --fitness wAA,wAa,waa --N`
- **Kin selection**: Hamilton's rule rB > C. → `genetics --hamilton r,B,C`
- **Five rules for cooperation** (Nowak 2006): kin selection (r > C/B), direct reciprocity (w > C/B, repeated games), indirect reciprocity / reputation (q > C/B), network/spatial reciprocity (B/C > k), group selection. → `spatial` shows network reciprocity: cooperators survive in clusters.
- **Evolution of norms and institutions**: punishment, conformity bias, payoff-biased vs conformist imitation; persistent inefficient conventions (QWERTY, driving side, corruption equilibria).

## 3. Method specifics
1. Define the strategy set and the payoff matrix (payoff to row strategy against column). Be explicit about what "fitness" means and its units.
2. Identify **frequency dependence**: if fitness doesn't depend on others' strategies, it's not a game - use `genetics` (directional selection).
3. `ess` for the static answer; `dynamics` for basins, cycles and speed; `moran` when the population is small (< ~1,000 or weak selection); `spatial` when interactions are local.
4. Parameter sweep: where does the ESS change (e.g. V/C in Hawk-Dove; b/c thresholds for cooperation)?
5. Referee: are interactions really random (well-mixed)? Is reproduction asexual or sexual (genetics adds dominance and recombination)? Mutation rates? Population size and drift? Timescale separation (ecology vs evolution)?

## 4. Data
- Genetics: allele frequencies (gnomAD, 1000 Genomes, UK Biobank summary stats), ancient DNA time series (selection estimates), experimental evolution datasets (Lenski LTEE).
- Ecology / behavior: field frequencies of morphs over time (fit replicator dynamics), microbial competition assays (payoff matrices from co-culture growth rates).
- Cancer: tumor cell-type frequencies under therapy (adaptive-therapy trials).
- Cultural: name frequencies (national registries), language use, technology adoption curves, Google Ngram; experimental game data (public goods, ultimatum across societies - Henrich et al.).
- Economics: firm survival and entry/exit (business demography statistics), strategy imitation (pricing rules adoption).
Estimate payoffs from growth rates: for two types, d logit(x)/dt = f_A − f_B; regress it on x to recover the payoff matrix.

## 5. Explaining (game card hints)
- Story: *"Nobody chooses here: whatever does better leaves more copies (children, imitators). The question is what mix survives."*
- Picture: phase line (2 strategies) or simplex with trajectories (3) - `dynamics --plot`; lattice snapshot for spatial games.
- Stability: *"If Hawks became more common, they'd meet each other more and get injured, so Doves would do better and grow back: the 50/50 mix restores itself."*
- Counterintuitive: the efficient convention can lose to the safer one; cheaters can win everywhere yet cooperation survives in clusters; a harmful allele can persist because carriers have an advantage; small populations can lose the best strategy by pure chance; Rock-Paper-Scissors never settles.
