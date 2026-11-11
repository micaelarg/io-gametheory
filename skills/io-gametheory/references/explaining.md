# Explaining the game

An analysis nobody understands has no value. Every analysis ends with a **game card**. The test: could a smart non-economist retell the story *and* say why nobody wants to change what they are doing?

## The game card (always, in this order)

### 1. The story, two lines, no jargon
Concrete actors, concrete stakes.
- Good: *"Two supermarkets choose where to open on the same avenue. If they sit next to each other they split the customers; if they spread out, each owns its neighborhood - but the second one chooses knowing where the first is."*
- Bad: *"We model a two-stage location-then-price game with spatial differentiation."*

### 2. The five pieces
- **Players** - who decides.
- **Actions** - what each can choose (say if discrete or continuous).
- **Timing** - who moves first; who sees what before deciding.
- **Information** - what each knows about the other (costs, valuations, intentions).
- **Payoffs** - what each gains, **with numbers**. Letters only in the formal level.

### 3. The right picture

| Game | Picture |
|---|---|
| Discrete, simultaneous | Payoff matrix with best responses marked (`finite_nash.py`) |
| Sequential | Tree with equilibrium path highlighted (`extensive_form.py`, Mermaid) |
| Continuous | Best-response curves crossing at the equilibrium (`continuous_br.py --plot`) |
| No pure equilibrium | CDF of the mixed strategy (`mixed_continuous.py`) |
| Location | The map: demand, rivals, candidates, catchment (`map.py`) |
| Evolutionary | Phase line / simplex with arrows |
| Hotelling / differentiation | Tent diagram: delivered price across consumers, who serves whom (`hotelling.py --plot`) |
| Auction | Bid functions vs the 45° line (`auctions.py bne/numeric --plot`) |
| Bargaining | Frontier with BATNA point and solutions (`bargaining.py nash --plot`); round-by-round offers table |

One picture, the right one. Annotate it: the reader should find the equilibrium in the picture in 3 seconds.

### 4. The equilibrium as **stability**
Never just "the equilibrium is (3,4)". Say why nobody moves:
- *"Nobody wants to move: if A cuts its price to 90, it gains 10% more customers but loses $1.2M in margin; if B moves to the avenue, it gains 300 households but pays $800k more rent."*
Use the deviation losses that `finite_nash.py` and `continuous_br.py` report.

For multiple equilibria: say there are several, which one you expect and why (focal point, who moves first, history, risk).

### 5. The intuition, one memorable sentence
- *"The threat to enter is worth more than entering."*
- *"In this auction you should bid below your value - not to cheat, but because winning is only good news when you bid less than it is worth."*
- *"Spreading out is not generosity; it is how both avoid a price war."*

### 6. What is counterintuitive
Where common sense fails and why. This is what makes an analysis memorable. Typical: more information can hurt; having fewer options can help (commitment); a lower cost can lower your profit (it changes the rival's response); mixed strategies depend on the *other* player's payoffs; adding a store can reduce chain profit (cannibalization); closer to customers is not always better (price competition).

### 7. What changes it
Comparative statics as decisions: thresholds, not derivatives.
- *"Site B wins unless monthly rent there exceeds $X, or the rival opens at C first."*
- *"Collusion is sustainable only if they meet more often than once every N months."*

### 8. Three reading levels
- **Executive** (3 lines): what to do, why, and what would change it.
- **Intuitive**: story + picture + stability + intuition (items 1-6).
- **Formal**: model, equations, assumptions with sources, solver used, verification result, code/commands to reproduce.

## Style rules

- Numbers beat letters. Round sensibly (no false precision: "~40%" not "39.87%").
- Never hide an assumption. Put an **Assumptions to confirm** block at the top, one line each, phrased as a question in the user's language: *"I assumed the mediation has three sessions and the other side speaks last. Is that right? If not, how does it work?"* Give the range you tested and whether the recommendation survives it.
- Name the solver and the check: "solved with support enumeration; grid check on 201 points found the same equilibrium".
- If an assumption drives the result, say it up front, not in a footnote.
- Prefer one long-lived concept (best response, commitment, credibility, outside option, cannibalization) over listing five.
- For large analyses: produce a self-contained HTML page (picture + map + card) the user can share.

## Failing examples (do not do this)

- Equilibrium stated without why it is stable.
- Jargon in the story ("subgame perfect", "Bayesian") - those belong in the formal level.
- Payoffs only as symbols.
- A recommendation with no threshold under which it flips.
- A map with no legend and no interpretation.
