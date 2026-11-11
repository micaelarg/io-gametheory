# Solution methods: classify, then solve

## 1. Classify on four axes

| Axis | Discrete | Continuous |
|---|---|---|
| **Strategies** | enter / stay out, accept / reject, a finite list of sites | price, quantity, bid, effort, location on a line or plane |
| **Time** | one-shot, stages, repeated, alternating offers | differential games, wars of attrition, races, ODE dynamics |
| **Types (information)** | a few types (high / low cost) | a distribution F(v) of valuations or costs |
| **Population** | finite (Moran process, drift, small markets) | infinite / large (replicator, ESS, mean field) |

Plus: **simultaneous vs sequential**, **complete vs incomplete information**, **one-shot vs repeated**, **zero-sum vs not**.

Write the classification in one line before solving, e.g. *"2 players, continuous strategies (prices), simultaneous, complete information, one-shot"*.

## 2. Solver decision tree

```
Strategies finite?
├─ yes ─ Simultaneous? ─ yes → finite_nash.py (pure + mixed; check dominance first)
│                      └ no  → extensive_form.py (backward induction → SPE)
│        Incomplete info, few types → expand Harsanyi: nature moves first (chance node),
│                                     solve Bayesian Nash / PBE; check beliefs off-path
└─ no (continuous)
   ├─ smooth, concave payoffs → continuous_br.py (FOCs, symbolic if possible)
   │                            + --grid check  + verify no profitable deviation
   ├─ discontinuous payoffs (ties, capacity, all-pay, undercutting)
   │                          → expect NO pure equilibrium → mixed_continuous.py
   ├─ sequential (Stackelberg, leader-follower) → solve follower BR symbolically,
   │                            substitute into leader payoff, maximize
   └─ continuous types (auctions, screening) → equilibrium bidding functions /
                                revelation principle; simulate to verify
Time continuous → ODE (replicator, dynamics) or optimal control (Pontryagin / HJB)
Repeated → folk theorem conditions: δ ≥ (π_deviate − π_collude)/(π_deviate − π_punish)
```

## 3. Discrete methods

- **Iterated elimination of strictly dominated strategies** first - it shrinks the game and often is the whole answer. Weak dominance elimination is order-dependent: do not rely on it.
- **Pure Nash**: mutual best responses (mark them in the matrix).
- **Mixed Nash**: support enumeration (exact, small games), Lemke-Howson (one equilibrium, large games). Mixed equilibrium logic for explanation: *each player mixes to make the other indifferent* - so a player's mixing probabilities depend on the **other's** payoffs (counterintuitive and worth saying).
- **Generic games have an odd number of equilibria.** If you found 2, look for the third (usually mixed).
- **Equilibrium selection** when multiple: payoff dominance, risk dominance (stag hunt), focal points, history, who can commit, evolutionary stability. Say which and why; never silently pick one.
- **Sequential**: SPE by backward induction. Flag **non-credible threats** (actions a player announces but would not carry out at that node). Flag the value of **commitment** (what a player gains by moving first or burning options).

## 4. Continuous methods

- **FOCs**: ∂uᵢ/∂xᵢ = 0 for each i → best response xᵢ = BRᵢ(x₋ᵢ). Equilibrium = intersection. Check SOC ∂²uᵢ/∂xᵢ² < 0.
- **Strategic complements vs substitutes**: sign of ∂BRᵢ/∂xⱼ. Prices are usually complements (rival raises → I raise), quantities substitutes. This determines whether to be aggressive or soft before competition (top dog / puppy dog / fat cat / lean and hungry). Always report the sign: it is the key to the intuition.
- **Corners**: if the interior solution violates bounds (negative quantity, price below cost), the equilibrium is at the bound for that player - re-solve with that player fixed.
- **Existence of pure equilibria fails** when payoffs are discontinuous: Bertrand with capacity constraints (Edgeworth cycles), all-pay auctions, Varian sales model, Hotelling with linear transport costs and close firms. Then the equilibrium is a **continuous mixed distribution**. The grid check will show no pure equilibrium on the grid - that is the signal.
- **Discretization matters**: Bertrand with prices in cents has an equilibrium at cost + 1 cent (and at cost); continuous Bertrand has only p = c. Say when the discrete and continuous answers differ and which is relevant (real prices are discrete).
- **Verification**: after solving, check numerically that no player gains more than ε by any unilateral deviation on a fine grid. `continuous_br.py` does this automatically. Report the result.

## 5. Dynamics and evolution

- **Replicator**: ẋᵢ = xᵢ (fᵢ(x) − f̄(x)). Every Nash equilibrium is a rest point (not conversely); every Lyapunov-stable rest point is a Nash equilibrium; every ESS is asymptotically stable. Draw the phase line / simplex.
- **ESS**: strategy s is ESS if u(s,s) > u(t,s), or u(s,s) = u(t,s) and u(s,t) > u(t,t), for all t ≠ s.
- **Finite populations**: fixation probabilities (Moran). Drift matters when N·selection is small.
- **Learning**: fictitious play, best-response dynamics - useful to argue which equilibrium a market reaches.

## 6. Repeated games and collusion

- Grim trigger sustains collusion iff δ ≥ (πᴰ − πᶜ)/(πᴰ − πᴺ), with πᶜ collusive, πᴰ best deviation, πᴺ Nash punishment. Compute the critical δ and translate δ into "how often firms interact / how fast deviations are detected".
- More firms, lumpy demand, secret price cuts, growing demand of entrants → collusion harder. Multi-market contact, transparency (published prices!) → easier.

## 7. Reporting a solution

Always state: classification · solver used · all equilibria found (or why unique) · payoffs at equilibrium · stability/verification check · the sign of strategic interaction · what selects among equilibria if several.
