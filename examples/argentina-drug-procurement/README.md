# Case study: bidding for Argentina's medicines

**Read it as a web page:** https://micaelarg.github.io/io-gametheory/

A walkthrough of an analysis run with the `io-gametheory` skill on Argentina's federal purchases of drugs and medical supplies, following the skill's seven steps. Numbers below come from 1,300 scraped tenders (133 of them by the Ministry of Health, 2016–2026): every competitive tender won by suppliers registered under COMPR.AR's medical/pharmaceutical category, which mixes drugs with medical supplies and devices.

## 1. Frame

> *"Corré la skill sobre las licitaciones de laboratorios en Argentina."* ("Run the skill on drug-laboratory tenders in Argentina.")

- **Who decides:** the Ministry of Health and other federal buyers; laboratories and distributors that bid.
- **Question:** are drug prices set by competition, and if not, by what?
- **Compared to what:** the same items with more bidders; the same drugs bought under a credible alternative (importing, pooled purchasing).
- **Rules of the game:** federal procurement rules (Decrees 1023/2001 and 1030/2016): sealed bids, the most advantageous compliant offer wins (usually the lowest price), and direct contracting is allowed on legal grounds such as exclusivity or urgency.

## 2. Data

| Source | Winners | Every bid | Used for |
|---|---|---|---|
| Ministry of Health court-order purchase tables | yes | yes | 425 comparable items, 1,900 bids (Oct 2024 – Oct 2026) |
| COMPR.AR purchase orders | yes | no | 5,415 orders 2017–2026: who won, tender vs direct award |
| COMPR.AR open data (datos.gob.ar) | yes | no | calls and awards; no losing bids |
| COMPR.AR comparison tables (scraped, `code/scraper.py`) | yes | yes | every bid per item, unit price, made-in-Argentina flag |

The open data has no losing bids, so a scraper was written for the comparison table each tender shows publicly (two seconds between requests, raw pages cached). Only aggregated tables are published here (`data/`).

## 3. The games

- **Tenders → a procurement auction.** Bidders know their own cost, submit a sealed price, the lowest wins. Prediction: bidders shade above cost, and the shading shrinks with more bidders.
- **Direct awards → bargaining with a monopolist.** The Ministry and a patent holder split the gap between the treatment's value to the State and its cost. Prediction: the price is capped by the State's best credible alternative.

## 4. Solve with code

**How many bids each item received** (37,963 items):

| bids received | items | share |
|---|---|---|
| 0 | 7,949 | 21% |
| 1 | 9,463 | 25% |
| 2 | 7,531 | 20% |
| 3 | 5,134 | 14% |
| 4 | 3,035 | 8% |
| 5 | 1,766 | 5% |
| 6+ | 3,085 | 8% |

46% of all items, and 59% of the Ministry of Health's, got one bid or none.

**Markups recovered from bids** (Guerre-Perrigne-Vuong, bids normalized by the item's median):

```
uv run skills/io-gametheory/scripts/solvers/auctions.py gpv --bids panel_bids.csv --auction-col tender --bid-col norm --procurement
```

| bidders | bids | median markup over implied cost |
|---|---|---|
| 2 | 13,286 | 40.8% |
| 3 | 12,978 | 15.8% |
| 4 | 9,716 | 11.0% |
| 5 | 6,891 | 8.7% |
| 6 | 5,546 | 6.2% |
| 7 | 4,097 | 4.6% |
| 8 | 2,660 | 4.3% |

Markups fall steeply from two to four bidders and keep falling to 2–4% in large auctions, as competitive theory predicts.

**Bid-rigging screens:**

```
uv run skills/io-gametheory/scripts/solvers/collusion.py bids --data panel_bids.csv --tender-col tender --process-col process --min-meet 8
```

No rotation across repeated tenders. Six pairs of firms almost always bid together. Four met in one or two tenders only (items of one tender split by specialty). The other two met in six tenders each with a single buyer and won most items where they met. Neither took turns by tender: one pair looks like a market-share shift over time (one firm until 2023, the other from 2024), and in the other both firms win items inside the same tender, split by product. That pair stays on the watch list (step 6).

**Court-ordered purchases:** the median gap between the winning and the second-lowest bid is 16.3% with two bidders and 3.5% with six or more (`data/court_orders_winner_gap.csv`).

**Direct contracting at the Ministry of Health** rose from 36% of drug spending in 2019 to 80% in 2025 (`data/minsalud_direct_contracting_share.csv`). Tendered spending in 2023–2025 is highly concentrated (HHI 3,403, about three equal-sized firms); direct awards go to many patent holders, each a monopolist on its own drug (`data/minsalud_concentration_2023_2025.csv`).

```
uv run skills/io-gametheory/scripts/solvers/merger.py hhi --shares minsalud_tendered_2023_25.csv
uv run skills/io-gametheory/scripts/solvers/collusion.py sustain --model bertrand --n 2 --lag 12
```

## 5. What flips the answer

- **The third bidder.** Markups and the winner's cushion drop sharply between two and four bidders; recruiting bidders beats any reserve-price tweak.
- **A credible outside option.** In direct deals the price cannot exceed the State's real alternative. If importing costs about 15% over the international reference price, prices above roughly 1.15× mean that alternative was not used. An earlier comparison of 16 purchases found 1.13× (pembrolizumab) and 2.1× (nivolumab bought through a distributor).
- **Collusion is sustainable** with about two effective firms and monthly purchases, even with a year's detection lag; the screens found no rotation, and one product split to watch.

## 6. Referee: false alarms removed

| Flag | After checking |
|---|---|
| A "cover bidder" losing every cochlear-implant item, 67–153% dearer | Two brands (MED-EL, Cochlear): competition between brands, and patients need compatible parts |
| Losing bids clustered 1–3% above the winner | Distributors of one single-source drug with a common cost; pricing power is upstream |
| Two pairs "taking turns" (84–92% of shared items, equal shares) | No turns by tender: one pair is a share shift over time; the other splits products inside each tender (brand-specific supplies with loaned equipment), which bids alone cannot tell apart from a market split, so it stays on the watch list. The screen now counts tenders and shows wins within each tender |
| Four more groups that always bid together | Items of one or two tenders, split by specialty |
| 24 bidders with 8+ bids and no wins | 18 bid in one or two tenders only; the other 6 priced above the item median (expensive, no evidence of cover bidding) |
| A bid 58× cheaper | Quoted per capsule vs per box; comparing totals fixed 35 "probable winners" |

Limits: the category mixes drugs and medical supplies; "winner" is the lowest comparable bid, not the formal award; items whose bids differ more than fivefold are dropped; concentration counts firms by tax ID (corporate groups would raise it); screens are red flags, not evidence of wrongdoing.

## 7. The game card

| | |
|---|---|
| **Story** | The State buys medicines two ways. When it tenders, few firms show up, and with two bidders the winner keeps a fat cushion. When it buys directly from a patent holder, it haggles with a monopolist, often against a court deadline. |
| **Why it is stable** | A bidder facing one rival gains nothing by cutting further; a monopolist has no reason to go below what the State's alternative would cost. |
| **Counterintuitive** | No cartel is needed for prices to be high, and an alternative the State never uses still sets the price, if the seller believes it. |
| **What to do** | Recruit the third bidder; make the outside option credible; publish losing bids as open data. |

## Reproduce

- `code/scraper.py`: downloads COMPR.AR comparison tables for a list of tender numbers (`uv run code/scraper.py --lista tenders.txt`).
- `code/analisis.py`: builds the per-item table and the bid panel used by the skill's scripts.
- Sources: argentina.gob.ar/salud/manda-judicial, comprar.gob.ar, datos.gob.ar (COMPR.AR).
