# Hotelling in all its forms (spatial and product differentiation)

"Location" is any attribute consumers differ on: physical place, product taste (sweetness, style), political position (Downs), time of departure (airlines), quality (vertical), brand image. Script: `scripts/solvers/hotelling.py` - one engine for all variants below, equilibria verified. For real maps use `location.md`; Hotelling is the theory that tells you *why* the map result looks the way it does.

## 1. The map of variants

| Variant | Key result | Command |
|---|---|---|
| **Original, fixed prices, 2 firms** (Hotelling 1929) | Both at the **median** consumer: minimum differentiation ("principle of minimum differentiation") | `location --n 2 --stage fixed [--density …]` |
| **Political** (Downs 1957) | Two parties converge to the median voter | same as above; density = voter distribution |
| **Fixed prices, 3 firms** (Eaton-Lipsey 1975) | **No pure equilibrium**: the middle firm is squeezed and jumps out | `location --n 3 --stage fixed` (proved on grid) |
| **Fixed prices, 4-5 firms** | Pairs at quartiles (n=4); pairs + one in middle (n=5) | `--n 4/5` (best-response search) |
| **Location → price, linear transport cost** | Price equilibrium **fails to exist** when firms are close (d'Aspremont-Gabszewicz-Thisse 1979) | `price --k 1 --positions 0.45,0.55` → mixed prices |
| **Location → price, quadratic transport cost** | **Maximum differentiation** (ends of the market; at −¼, 5/4 if allowed outside) | `location --n 2 --stage price --k 2 [--bounds -0.5,1.5]` |
| **Price stage only** (given locations) | p₁ = c + t(1−a−b)(1+(a−b)/3) (quadratic) | `price --positions … --k 2` |
| **Non-uniform consumers** | Fixed price → median. Price competition → less than maximal differentiation when consumers are concentrated (Tabuchi-Thisse 1995) | `--density beta:3,3 / normal:… / csv:file:col` |
| **Uncovered market** (reservation value v) | Local monopolies when t large or v low; firms don't compete at all if catchments don't touch | `--v 1.2` |
| **Asymmetric costs** | Low-cost firm charges less, serves more, may move toward the center | `--costs 0,0.2` |
| **Circular city** (Salop 1979) | p = c + t/n; free entry n* = √(tL/F); **excess entry** (2× optimum with linear cost) | `salop --t --F --k`, `price --space circle` |
| **Vertical differentiation** (Gabszewicz-Thisse 1979, Shaked-Sutton 1982) | Firms pick **maximally different qualities** to soften price competition; high-quality firm earns more | `price --vertical --qualities 1,2 --theta 1,3`, `location --vertical` |
| **Vertical with quality cost** | Quality gap narrows as quality gets costly | `location --vertical --kappa 0.5` |
| **Natural oligopoly** (Shaked-Sutton) | With vertical differentiation, only a finite number of firms survive even as the market grows | discuss; simulate `--n 3 --vertical` |
| **Two dimensions** (Irmen-Thisse 1998, "Max-min") | Maximal differentiation in the dominant characteristic, **minimal** in the others | reason with the 1-D results; use `location.md` scripts for real 2-D space |
| **Sequential entry** (Prescott-Visscher 1977) | Early entrants choose spots anticipating later entrants; leaders keep the best spots and can deter entry | run `location` stage-by-stage; or `location_game.py` with real sites |
| **Elastic demand / outside goods** | Behaves like an uncovered market; proximity raises total demand, not only share | `--v` |
| **Mixed strategies in prices** (Osborne-Pitchik 1987) | When no pure price equilibrium: firms randomize, observed as price dispersion / sales | `price --k 1` with close firms |

## 2. The one lesson to remember

**Proximity has two effects that pull in opposite directions:**
1. *Market-grabbing* (pull to the center): moving toward the rival steals its customers.
2. *Competition-softening* (push apart): being close makes the products substitutes, so prices fall.

Which one wins depends on whether prices are free to react:
- Prices fixed or regulated (pharmacies with regulated prices, taxis, parties on an ideological line, fixed-fare airlines picking departure times) → **cluster**.
- Prices react quickly (groceries, fuel, commodities) → **spread out**.
- Quality (vertical) → **spread out** in quality: a budget brand and a premium brand both earn more than two mid-range brands.

This is the theory behind the real-world location result: if a client's best Huff site is right next to a rival that competes on price, warn that the price response may eat the market share gained.

## 3. Welfare
- Fixed prices → **too little** differentiation (both at center; socially, quartiles minimize travel).
- Quadratic price competition → **too much** differentiation (ends vs quartiles).
- Free entry in Salop → **too many** stores (business stealing).
- `hotelling.py location` always prints the social optimum next to the equilibrium.

## 4. Reading the solver output
- `price`: verified equilibrium table (prices, margins, shares, profits) + closed form when one exists; if no pure equilibrium, the mixed one from MILP on a price grid.
- `location`: equilibrium locations/qualities, verification gain (≈0), a note if stage-2 equilibria fail somewhere, and the social optimum.
- `--plot` draws the **tent diagram** (delivered price p + transport cost across consumers, lower envelope = who serves whom, grey = consumer density). It is THE picture for explaining Hotelling.
- Fixed-price games with n ≤ 3 are solved by **exhaustive search on a grid**: when it says "no equilibrium", that is a proof on the grid, not a convergence failure.

## 5. Mapping real problems to Hotelling
| Real problem | "Location" | Transport cost t means |
|---|---|---|
| Store placement on a street | physical position | walking/driving cost |
| Product design (taste, size, flavor) | product attribute | disutility of a non-ideal product |
| Political platforms | policy position | ideological distance |
| Flight / bus schedules | departure time | cost of leaving at a non-preferred time |
| Media / news slant | editorial position | readers' dislike of disagreeing content |
| Quality tiers (budget vs premium) | quality (vertical) | taste for quality θ |
| Retail format (discount vs service) | service level | value of time/service |

Calibrate t from data when possible: t ≈ how much more a consumer pays to avoid one unit of "distance" (e.g. price premium of the nearest store vs one 1 km away; fare premium for preferred departure time).
