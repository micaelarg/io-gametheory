# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "scipy>=1.11", "pandas>=2.1", "matplotlib>=3.8"]
# ///
"""Auction theory engine: equilibrium bidding, revenue, reserve prices, design, and empirics.

SUBCOMMANDS
  bne       Symmetric independent private values (IPV), risk-neutral, any value distribution:
            equilibrium bid functions for first-price/Dutch, second-price/English, all-pay;
            expected revenue (closed form via virtual values) + Monte Carlo check of revenue
            equivalence; bidder surplus; probability of no sale; efficiency loss of the reserve.
  reserve   Optimal reserve (Myerson): φ(r) = seller's own value; revenue-vs-reserve curve;
            regularity check; Bulow-Klemperer (one more bidder vs optimal reserve).
  numeric   ASYMMETRIC bidders (each with its own distribution), first-price or all-pay, with
            reserve: equilibrium bid functions by iterated best response on a value grid, ε-check,
            revenue and efficiency vs second-price (where values are bid truthfully).
  gpv       Recover bidders' private values from OBSERVED first-price bids (Guerre-Perrigne-
            Vuong 2000): v = b + G(b)/((n−1)g(b)). Markups, monotonicity test (violations hint at
            collusion or non-IPV), markups by number of bidders.
  common    Common value: signals s = V + noise. Winner's curse of naive bidding vs equilibrium
            (second-price, Milgrom-Weber b(s) = E[V | s, max other signal = s]); shading grows with n.

FLAGS BY SUBCOMMAND
  bne:     --dist --n [--reserve --v0 --procurement --plot]
  reserve: --dist --n [--v0 --procurement]
  numeric: --bidder (repeat) | --dist --n ; --format fpa|allpay [--reserve --procurement --plot]
  gpv:     --bids --auction-col --bid-col [--estimate-col --bidder-col --n-col --procurement --out --plot]
  common:  --dist --noise --n-list

PROCUREMENT (reverse auctions): add --procurement to bne/reserve/numeric/gpv. Distributions are
then COSTS, the lowest bid wins, --reserve is the maximum acceptable price, and --v0 is the
buyer's cost of not contracting (in-house/next-best). Output speaks in costs and prices.

DISTRIBUTIONS: uniform:a,b | normal:mu,sd[,lo,hi] | lognormal:mu,sigma (of log) |
  beta:a,b,lo,hi | power:alpha,hi (F=(v/hi)^alpha) | empirical:file.csv[:column]

EXAMPLES
  uv run auctions.py bne --dist uniform:0,1 --n 3 --reserve 0.25 --plot bids.png
  uv run auctions.py reserve --dist lognormal:10,0.6 --n 4 --v0 15000
  uv run auctions.py numeric --bidder uniform:0,1 --bidder uniform:0,2 --format fpa --plot asym.png
  uv run auctions.py bne --procurement --dist uniform:80,120 --n 5 --reserve 115
  uv run auctions.py gpv --bids bids.csv --auction-col tender --bid-col amount --procurement
  uv run auctions.py common --dist uniform:0,100 --noise 10 --n-list 2,4,8
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

K = 4001  # grid for distributions


# ----------------------------------------------------------------------------- distributions
class Dist:
    """Tabulated distribution on [lo, hi] - every family handled the same way."""

    def __init__(self, spec: str):
        self.spec = spec
        kind, _, arg = spec.partition(":")
        p = [float(x) for x in arg.split(",")] if arg and kind != "empirical" else []
        from scipy import stats
        if kind == "uniform":
            lo, hi = p
            x = np.linspace(lo, hi, K); f = np.ones(K)
        elif kind == "normal":
            mu, sd = p[:2]
            lo = p[2] if len(p) > 2 else max(mu - 4 * sd, 0.0 if mu - 4 * sd < 0 < mu else mu - 4 * sd)
            hi = p[3] if len(p) > 3 else mu + 4 * sd
            x = np.linspace(lo, hi, K); f = stats.norm.pdf(x, mu, sd)
        elif kind == "lognormal":
            mu, s = p
            hi = float(np.exp(mu + 3.5 * s))
            x = np.linspace(0, hi, K); f = stats.lognorm.pdf(x, s, scale=np.exp(mu))
        elif kind == "beta":
            a, b, lo, hi = p
            x = np.linspace(lo, hi, K); f = stats.beta.pdf((x - lo) / (hi - lo), a, b)
        elif kind == "power":
            al, hi = p
            x = np.linspace(0, hi, K); f = al * (x / hi) ** (al - 1)
        elif kind == "empirical":
            import pandas as pd
            path, _, col = arg.partition(":")
            df = pd.read_csv(path)
            data = df[col or df.columns[0]].dropna().astype(float).values
            kde = stats.gaussian_kde(data)
            lo, hi = max(data.min() - 0.1 * np.ptp(data), 0 if data.min() >= 0 else -np.inf), data.max() + 0.1 * np.ptp(data)
            x = np.linspace(lo, hi, K); f = kde(x)
        else:
            sys.exit(f"unknown distribution {spec}")
        f = np.nan_to_num(np.clip(f, 0, None))
        self.x = x
        cdf = np.concatenate([[0], np.cumsum((f[1:] + f[:-1]) / 2 * np.diff(x))])
        self.f = f / cdf[-1]
        self.Fx = cdf / cdf[-1]
        self.lo, self.hi = float(x[0]), float(x[-1])

    @classmethod
    def flipped(cls, d: "Dist", H: float):
        """Value = H − cost (procurement)."""
        o = cls.__new__(cls)
        o.spec = f"{H:g} − ({d.spec})"
        o.x = (H - d.x)[::-1]
        o.f = d.f[::-1]
        o.Fx = (1 - d.Fx)[::-1]
        o.lo, o.hi = float(o.x[0]), float(o.x[-1])
        return o

    @classmethod
    def scaled(cls, d: "Dist", k: float):
        """Distribution of k·X."""
        o = cls.__new__(cls)
        o.spec = f"{k:g}·({d.spec})"
        o.x = d.x * k
        o.f = d.f / k
        o.Fx = d.Fx.copy()
        o.lo, o.hi = float(o.x[0]), float(o.x[-1])
        return o

    def F(self, v):
        return np.interp(v, self.x, self.Fx, left=0.0, right=1.0)

    def pdf(self, v):
        return np.interp(v, self.x, self.f, left=0.0, right=0.0)

    def ppf(self, q):
        Fu, idx = np.unique(self.Fx, return_index=True)
        return np.interp(q, Fu, self.x[idx])

    def sample(self, size, rng):
        return self.ppf(rng.random(size))

    def mean(self):
        return float(np.trapezoid(self.x * self.f, self.x))


def cumint(y, x):
    return np.concatenate([[0], np.cumsum((y[1:] + y[:-1]) / 2 * np.diff(x))])


# ----------------------------------------------------------------------------- symmetric theory
def symmetric(d: Dist, n: int, r: float, v0: float):
    x = d.x
    F, f = d.Fx, d.f
    G = F ** (n - 1)
    r = max(r, d.lo)
    m = x >= r
    IG = np.zeros_like(x)
    IG[m] = cumint(G[m], x[m])
    with np.errstate(invalid="ignore", divide="ignore"):
        b_fpa = np.where(m, x - IG / np.where(G > 0, G, np.nan), np.nan)
    b_fpa = np.where(m & (G == 0), r, b_fpa)
    b_allpay = np.where(m, x * G - IG, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        phi = x - (1 - F) / np.where(f > 0, f, np.nan)
    integrand = np.where(m, np.nan_to_num(phi) * f * G, 0.0)
    rev_sales = n * np.trapezoid(integrand, x)
    rev = rev_sales + v0 * d.F(r) ** n
    p_sale = 1 - d.F(r) ** n
    # expected max value and efficiency
    Fmax = F ** n
    fmax = np.gradient(Fmax, x)
    e_max = np.trapezoid(x * fmax, x)
    welfare = np.trapezoid(np.where(x >= r, x, v0) * fmax, x)
    welfare_first_best = np.trapezoid(np.maximum(x, v0) * fmax, x)
    bidder_surplus = welfare - rev
    return dict(b_fpa=b_fpa, b_allpay=b_allpay, phi=phi, rev=rev, rev_sales=rev_sales, p_sale=p_sale, e_max=e_max,
                welfare=welfare, welfare_fb=welfare_first_best, bidder_surplus=bidder_surplus, r=r)


def monte_carlo(d: Dist, n: int, r: float, v0: float, res, S=200_000, seed=1):
    rng = np.random.default_rng(seed)
    V = d.sample((S, n), rng)
    srt = np.sort(V, axis=1)
    hi1, hi2 = srt[:, -1], srt[:, -2] if n > 1 else np.full(S, -np.inf)
    sale = hi1 >= r
    spa = np.where(sale, np.maximum(hi2, r), v0)
    bf = np.interp(hi1, d.x, np.nan_to_num(res["b_fpa"], nan=r))
    fpa = np.where(sale, bf, v0)
    ba = np.where(V >= r, np.interp(V, d.x, np.nan_to_num(res["b_allpay"])), 0.0)
    allpay = ba.sum(axis=1) + np.where(sale, 0, v0)
    se = lambda z: z.std() / np.sqrt(S)  # noqa: E731
    return {"First-price / Dutch": (fpa.mean(), se(fpa)), "Second-price / English": (spa.mean(), se(spa)),
            "All-pay": (allpay.mean(), se(allpay))}


def optimal_reserve(d: Dist, v0: float):
    x = d.x
    with np.errstate(invalid="ignore", divide="ignore"):
        phi = x - (1 - d.Fx) / np.where(d.f > 1e-12, d.f, np.nan)
    ok = np.isfinite(phi)
    dphi = np.diff(phi[ok])
    regular = np.mean(dphi >= -1e-9 * np.nanmax(np.abs(phi[ok]))) > 0.995
    idx = np.where(ok & (phi >= v0))[0]
    r = float(x[idx[0]]) if len(idx) else d.hi
    return r, regular


# ----------------------------------------------------------------------------- output helpers
class Units:
    def __init__(self, proc: bool, H: float = 0.0):
        self.proc, self.H = proc, H

    def val(self, v):
        return self.H - v if self.proc else v

    def bid(self, b):
        return self.H - b if self.proc else b

    def money(self, res):
        """Expected seller revenue, or (procurement) expected spend on the contract."""
        return self.H * res["p_sale"] - res["rev_sales"] if self.proc else res["rev"]

    @property
    def V(self):
        return "cost" if self.proc else "value"

    @property
    def B(self):
        return "price asked" if self.proc else "bid"


def build_dist(spec, proc, H=None):
    d = Dist(spec)
    if proc:
        H = d.hi if H is None else H
        return Dist.flipped(d, H), Units(True, H)
    return d, Units(False)


def fmt(x):
    if not np.isfinite(x):
        return "-"
    if abs(x) < 1e-9:
        return "0"
    return f"{x:,.0f}" if abs(x) >= 1000 else f"{x:.4g}"


# ----------------------------------------------------------------------------- bne / reserve
def cmd_bne(a):
    d, u = build_dist(a.dist, a.procurement)
    r = u.val(a.reserve) if a.reserve is not None else d.lo
    v0 = u.val(a.v0) if a.v0 is not None else (d.lo if not a.procurement else d.lo)
    res = symmetric(d, a.n, r, v0)
    mc = monte_carlo(d, a.n, res["r"], v0, res)
    L = [f"# {'Procurement' if u.proc else 'Auction'} - symmetric IPV, n={a.n}, {u.V}s ~ {a.dist}", ""]
    L.append(f"- Reserve: {fmt(u.val(res['r']))}{' (maximum acceptable price)' if u.proc else ''}; "
             f"{'buyer cost if no contract' if u.proc else 'seller value if unsold'}: {fmt(u.val(v0))}")
    L += ["", f"## Equilibrium strategies", ""]
    L.append(f"- **Second-price / English**: {u.B} = your {u.V} (truthful - weakly dominant, no need to guess others).")
    L.append(f"- **First-price / Dutch**: shade toward the expected {'second-lowest cost' if u.proc else 'second-highest value'} "
             f"given you win: b(v) = v − ∫F^(n−1)/F^(n−1)(v).")
    L.append(f"- **All-pay**: bid ∫ u dF^(n−1) (pay always - contests, lobbying, R&D races).")
    L += ["", f"| {u.V} | first-price {u.B} | shading | all-pay {u.B} |", "|---|---|---|---|"]
    for q in (0.1, 0.25, 0.5, 0.75, 0.9, 0.99):
        v = d.ppf(q)
        if v < res["r"]:
            L.append(f"| {fmt(u.val(v))} (q{int(q*100)}) | does not {'bid' if not u.proc else 'qualify'} (below reserve) | | |")
            continue
        b = float(np.interp(v, d.x, np.nan_to_num(res["b_fpa"], nan=res["r"])))
        ba = float(np.interp(v, d.x, np.nan_to_num(res["b_allpay"])))
        sh = ((u.bid(b) - u.val(v)) / abs(u.val(v)) if u.proc else (v - b) / abs(v)) if u.val(v) != 0 else np.nan
        L.append(f"| {fmt(u.val(v))} (q{int(q*100)}) | {fmt(u.bid(b))} | {100*sh:.0f}% {'markup over cost' if u.proc else 'below value'} | {fmt(u.bid(ba)) if not u.proc else '-'} |")
    L += ["", "## Revenue (revenue equivalence)", ""]
    if u.proc:
        L.append(f"- Closed form (virtual values): expected spend on the contract **{fmt(u.money(res))}**")
    else:
        L.append(f"- Closed form (virtual values): expected **cash revenue {fmt(res['rev_sales'])}**; seller's total payoff "
                 f"counting the value of keeping an unsold item ({fmt(v0)}): {fmt(res['rev'])}")
        if a.premium or a.commission:
            ham = res["rev_sales"] / (1 + a.premium)
            L.append(f"- With buyer's premium {100*a.premium:.0f}% and seller's commission {100*a.commission:.0f}%: bidders pay in "
                     f"total {fmt(res['rev_sales'])}, expected hammer {fmt(ham)}, seller nets {fmt(ham*(1-a.commission))}, "
                     f"house earns {fmt(res['rev_sales'] - ham*(1-a.commission))}. (Bidders bid on all-in price: the premium "
                     "lowers hammer prices one-for-one.)")
    for k, (m_, s_) in mc.items():
        if u.proc and k == "All-pay":
            continue
        val = u.H * (1 - d.F(res['r']) ** a.n) - (m_ - (v0 * d.F(res['r']) ** a.n)) if u.proc else m_
        L.append(f"- Monte Carlo, {k}: {fmt(val)} ± {fmt(1.96*s_)}")
    L.append(f"- Probability of {'no contract' if u.proc else 'no sale'}: {100*(1-res['p_sale']):.1f}%")
    L.append(f"- Bidder surplus (expected, all bidders): {fmt(res['bidder_surplus'])}; "
             f"efficiency lost to the reserve: {fmt(res['welfare_fb'] - res['welfare'])}")
    L.append("\nRevenue equivalence holds under: independent private values, risk neutrality, symmetric bidders, "
             "the highest value wins, lowest type gets 0. Break any of these and formats differ - see references/auctions.md.")
    if a.plot:
        plot_bids(d, u, [("first-price", res["b_fpa"]), ("all-pay", res["b_allpay"]) if not u.proc else None,
                         ("second-price (truthful)", np.where(d.x >= res['r'], d.x, np.nan))], a.plot,
                  f"Equilibrium bids, n={a.n}")
        L.append(f"\nPlot saved: {a.plot}")
    print("\n".join(L))


def cmd_reserve(a):
    d, u = build_dist(a.dist, a.procurement)
    v0 = u.val(a.v0) if a.v0 is not None else d.lo
    r_star, regular = optimal_reserve(d, v0)
    L = [f"# Optimal {'maximum price' if u.proc else 'reserve'} - {u.V}s ~ {a.dist}, n={a.n}", ""]
    L.append(f"- {'Buyer cost if no contract' if u.proc else 'Seller own value'} = {fmt(u.val(v0))}")
    L.append(f"- Myerson rule: {'max price P with P + F(P)/f(P) = buyer cost' if u.proc else 'reserve r with r − (1−F(r))/f(r) = own value'} "
             f"→ **{fmt(u.val(r_star))}** (independent of n!)")
    if not regular:
        L.append("- ⚠ Virtual value is not monotone (irregular distribution): optimal mechanism needs **ironing**; "
                 "the simple reserve is an approximation.")
    rows = [(r, symmetric(d, a.n, r, v0)) for r in sorted(set(np.linspace(d.lo, d.hi, 41)[::4]) | {r_star})]
    base = symmetric(d, a.n, d.lo, v0)
    best = symmetric(d, a.n, r_star, v0)
    more = symmetric(d, a.n + 1, d.lo, v0)
    m = u.money
    if u.proc:
        L += ["", "| max price | expected spend | P(contract) |", "|---|---|---|"]
        for r, res in rows:
            L.append(f"| {fmt(u.val(r))}{' ★' if r == r_star else ''} | {fmt(m(res))} | {100*res['p_sale']:.0f}% |")
    else:
        L += ["", "| reserve | expected cash revenue | seller payoff incl. kept item | P(sale) |", "|---|---|---|---|"]
        for r, res in rows:
            L.append(f"| {fmt(r)}{' ★ optimal' if r == r_star else ''} | {fmt(res['rev_sales'])} | {fmt(res['rev'])} | {100*res['p_sale']:.0f}% |")
        L.append("\nThe optimal reserve maximizes the seller's payoff INCLUDING the value of keeping the item; cash revenue "
                 "alone can fall with the reserve (the item sometimes stays unsold).")
    L += ["", "## What is a reserve worth vs one more bidder", ""]
    L.append(f"- No reserve, n={a.n}: {fmt(m(base))}")
    L.append(f"- Optimal reserve, n={a.n}: {fmt(m(best))} (gain {fmt(abs(m(best) - m(base)))}; "
             f"P({'contract' if u.proc else 'sale'}) falls to {100*best['p_sale']:.0f}%)")
    L.append(f"- No reserve, n={a.n+1}: {fmt(m(more))}")
    better = (m(more) < m(best)) if u.proc else (m(more) > m(best))
    L.append(f"- **Bulow-Klemperer**: one more bidder {'beats' if better else 'does not beat'} the optimal reserve here. "
             "Recruiting bidders is usually worth more than fine-tuning the reserve.")
    print("\n".join(L))


# ----------------------------------------------------------------------------- numeric asymmetric
def cmd_numeric(a):
    specs = a.bidder or [a.dist] * a.n
    kap = np.zeros(len(specs))
    if a.credit:
        if not a.procurement:
            sys.exit("--credit applies to procurement (bidding credits / preferences for some bidders).")
        for part in a.credit.split(","):
            i_, k_ = part.split(":")
            kap[int(i_) - 1] = float(k_)
    if a.procurement:
        # A credit κ means bidder i's price b is EVALUATED as b(1−κ) but PAID in full. Equivalent to a bidder with
        # cost c(1−κ) competing in evaluated prices; payments are converted back below.
        raw = [Dist.scaled(Dist(s), 1 - kap[i]) if kap[i] else Dist(s) for i, s in enumerate(specs)]
        H = max(r.hi for r in raw)
        ds = [Dist.flipped(r, H) for r in raw]
        u = Units(True, H)
    else:
        ds = [Dist(s) for s in specs]
        u = Units(False)
    n = len(ds)
    r = u.val(a.reserve) if a.reserve is not None else min(dd.lo for dd in ds)
    Kv = 101
    V = [np.linspace(max(dd.lo, r), dd.hi, Kv) for dd in ds]
    b = [r + (v - r) * (n - 1) / n for v in V]  # start: symmetric-uniform guess

    def win_prob(i, B):
        """Exact: Π_j P(b_j(V_j) < B) = Π_j F_j(b_j^{-1}(B)), bid functions monotone."""
        W = np.ones_like(B)
        for j in range(n):
            if j == i:
                continue
            bj = np.maximum.accumulate(b[j]) + 1e-12 * np.arange(len(b[j]))
            Fr = ds[j].F(V[j][0])
            inv = np.interp(B, bj, V[j])
            P = np.where(B < bj[0], Fr, np.where(B > bj[-1], 1.0, ds[j].F(inv)))
            W *= P
        return W

    def payoff(i, v, B):
        W = win_prob(i, B)
        return (v - B) * W if a.format == "fpa" else v * W - B

    def best_responses(i):
        out = b[i].copy()
        for k, v in enumerate(V[i]):
            B = np.linspace(r if a.format == "fpa" else 0, v, 241)
            pay = payoff(i, v, B)
            j = int(np.argmax(pay))
            lo_, hi_ = B[max(j - 1, 0)], B[min(j + 1, len(B) - 1)]
            Bf = np.linspace(lo_, hi_, 41)
            pf = payoff(i, v, Bf)
            out[k] = Bf[int(np.argmax(pf))] if pf.max() >= pay[j] else B[j]
        return np.maximum.accumulate(out)

    method = "iterated best response with averaging"
    hist = []
    if a.format == "fpa":
        sh = fpa_shooting(ds, r)
        if sh is not None:
            bbar, bgrid, phis = sh
            # values below φ_i(b_low) cannot win: they bid their value (any losing bid)
            b = [np.where(V[i] < phis[i][0], np.minimum(V[i], bgrid[0]),
                          np.interp(V[i], phis[i], bgrid)) for i in range(n)]
            b = [np.minimum(np.maximum(bi, r), bbar) for bi in b]
            method = ("ODE shooting on inverse bid functions (Marshall et al. 1994; Lebrun 1999), "
                      + (f"lowest price anyone asks = {fmt(u.bid(bbar))}" if u.proc else f"common max bid b̄ = {bbar:.5g}"))
    for it in range(0 if method.startswith("ODE") else 400):
        brs = [best_responses(i) for i in range(n)]
        gap = max(float(np.max(np.abs(brs[i] - b[i]))) for i in range(n))
        lam = max(0.6 / (1 + it / 8), 0.03)            # decreasing steps (fictitious-play style averaging)
        b = [(1 - lam) * b[i] + lam * brs[i] for i in range(n)]
        hist.append(gap)
        if gap < 2e-4 * (max(dd.hi for dd in ds) - r + 1e-12):
            break
    # ε-check
    eps = 0.0
    for i in range(n):
        for k, v in enumerate(V[i][::6]):
            B = np.linspace(r if a.format == "fpa" else 0, v, 2001)
            pay = payoff(i, v, B)
            cur = payoff(i, v, np.array([np.interp(v, V[i], b[i])]))[0]
            eps = max(eps, pay.max() - cur)
    scale = max(dd.hi for dd in ds) - r
    # Monte Carlo revenue & efficiency
    rng = np.random.default_rng(3)
    M = 100_000
    X = np.column_stack([dd.sample(M, rng) for dd in ds])
    Bm = np.column_stack([np.where(X[:, i] >= r, np.interp(X[:, i], V[i], b[i]), -np.inf) for i in range(n)])
    w = Bm.argmax(axis=1)
    sale = np.isfinite(Bm.max(axis=1))
    if u.proc:
        true_cost = (u.H - X) / (1 - kap)[None, :]                 # undo the credit scaling
        eff = np.mean((w == true_cost.argmin(axis=1))[sale]) if sale.any() else np.nan
        paid = (u.H - Bm.max(axis=1)) / (1 - kap[w])               # evaluated price → price actually paid
        spend_fp = np.where(sale, paid, 0).mean()
        cw = true_cost[np.arange(M), w]
        eff_loss = np.where(sale, cw - true_cost.min(axis=1), 0).mean()
        tc = np.sort(true_cost, axis=1)
        maxp = u.val(r) if a.reserve is not None else np.inf
        spend_sp = np.where(tc[:, 0] <= maxp, np.minimum(tc[:, 1], maxp), 0).mean()
        rev = spa = None
    else:
        eff = np.mean((w == X.argmax(axis=1))[sale]) if sale.any() else np.nan
        eff_loss = np.where(sale, X.max(axis=1) - X[np.arange(M), w], 0).mean()
        if a.format == "fpa":
            rev = np.where(sale, Bm.max(axis=1), 0).mean()
        else:
            rev = np.where(np.isfinite(Bm), Bm, 0).sum(axis=1).mean()
        srt = np.sort(np.where(X >= r, X, -np.inf), axis=1)
        spa = np.where(np.isfinite(srt[:, -1]), np.maximum(np.where(np.isfinite(srt[:, -2]), srt[:, -2], r), r), 0).mean()
    p_sale = sale.mean()

    lab = "procurement " if u.proc else ""
    L = [f"# Asymmetric {lab}{'first-price' if a.format == 'fpa' else 'all-pay'} auction - {n} bidders", ""]
    for i, s_ in enumerate(specs):
        L.append(f"- Bidder {i+1}: {u.V} ~ {s_}" + (f" - **bidding credit {100*kap[i]:.0f}%**" if kap[i] else ""))
    L.append(f"- {'Maximum price' if u.proc else 'Reserve'}: {fmt(u.val(r)) if a.reserve is not None else 'none'}. Method: {method}{f' ({len(hist)} rounds)' if hist else ''}; "
             f"ε-check: max gain from any deviation = {eps:.2e} ({100*eps/scale:.2f}% of the value range) "
             + ("✅" if eps / scale < 5e-3 else "⚠ not converged - treat bids as approximate"))
    L += ["", f"| {u.V} | " + " | ".join(f"bidder {i+1} {u.B}" for i in range(n)) + " |", "|---|" + "---|" * n]
    if u.proc:
        cmin = min(u.H - dd.hi for dd in ds) / max(1 - kap.max(), 1e-9) if kap.any() else min(u.H - dd.hi for dd in ds)
        costs = np.linspace(min(Dist(s_).lo for s_ in specs), max(Dist(s_).hi for s_ in specs), 9)
        rows_out = []
        for c_ in costs:
            cells = []
            for i in range(n):
                v = u.H - c_ * (1 - kap[i])             # value-space type of bidder i with true cost c_
                if v < V[i][0] - 1e-9 or v > V[i][-1] + 1e-9:
                    cells.append(None)
                else:
                    cells.append((u.H - float(np.interp(v, V[i], b[i]))) / (1 - kap[i]))
            rows_out.append((c_, cells))
            L.append(f"| {fmt(c_)} | " + " | ".join("-" if x is None else fmt(x) for x in cells) + " |")
    else:
        vals = np.linspace(min(dd.lo for dd in ds), max(dd.hi for dd in ds), 9)
        rows_out = []
        for v in vals:
            cells = [None if (v < V[i][0] - 1e-9 or v > V[i][-1] + 1e-9) else float(np.interp(v, V[i], b[i])) for i in range(n)]
            rows_out.append((v, cells))
            L.append(f"| {fmt(v)} | " + " | ".join("-" if x is None else fmt(x) for x in cells) + " |")
    common = np.linspace(max(r, max(dd.lo for dd in ds)), min(dd.hi for dd in ds), 7)
    if a.out:
        import pandas as pd
        pd.DataFrame([[t] + c for t, c in rows_out], columns=[u.V] + [f"bidder{i+1}_{u.B.replace(' ', '_')}" for i in range(n)]).to_csv(a.out, index=False)
    L += ["", "## Outcomes", ""]
    if u.proc:
        L.append(f"- Expected price actually paid: first-price {fmt(spend_fp)} vs second-price without credits {fmt(spend_sp)}")
    else:
        L.append(f"- Expected revenue: {'first-price' if a.format == 'fpa' else 'all-pay'} {fmt(rev)} vs second-price {fmt(spa)}")
    L.append(f"- Efficiency: the {'lowest-cost' if u.proc else 'highest-value'} bidder wins {100*eff:.1f}% of the time "
             f"(second-price: 100%); expected efficiency loss {fmt(eff_loss)} per contract "
             f"({'extra production cost' if u.proc else 'value not realized'}).")
    if a.out:
        L.append(f"- Bid table → `{a.out}`")
    if n == 2 and a.format == "fpa":
        mid = common[len(common) // 2]
        b1, b2 = (float(np.interp(mid, V[i], b[i])) for i in range(2))
        weak = 0 if ds[0].mean() < ds[1].mean() else 1
        L.append(f"- At the same {u.V} {fmt(u.val(mid))}, the **{'weak' if (b1 > b2) == (weak == 0) else 'strong'} bidder "
                 "bids more aggressively** (Maskin-Riley 2000): the weak shade less because they face a tougher rival; "
                 "the strong shade more because they can afford to.")
    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6.4, 4.6))
        for i in range(n):
            xs_ = (u.H - V[i]) / (1 - kap[i]) if u.proc else V[i]
            ys_ = (u.H - b[i]) / (1 - kap[i]) if u.proc else b[i]
            ax.plot(xs_, ys_, lw=2, label=f"bidder {i+1} ({specs[i]})")
        lohi = np.array([min(u.val(dd.lo) for dd in ds), max(u.val(dd.lo) for dd in ds), min(u.val(dd.hi) for dd in ds), max(u.val(dd.hi) for dd in ds)])
        ax.plot([lohi.min(), lohi.max()], [lohi.min(), lohi.max()], ls=":", color="grey", label=f"{u.B} = {u.V}")
        ax.set_xlabel(u.V); ax.set_ylabel(u.B); ax.grid(alpha=0.3); ax.legend(fontsize=8)
        ax.set_title("Equilibrium bid functions (asymmetric)")
        fig.tight_layout(); fig.savefig(a.plot, dpi=150)
        L.append(f"\nPlot saved: {a.plot}")
    print("\n".join(L))


def fpa_shooting(ds, r):
    """Asymmetric first-price equilibrium via backward shooting (Marshall et al. 1994; Lebrun 1999 boundaries).
    Inverse bids φ_i(b) solve, with S = Σ_j 1/(φ_j − b)/(n−1):  φ_i' = F_i(φ_i)/f_i(φ_i) · (S − 1/(φ_i − b)),
    top: φ_i(b̄) = top of support i.  Integrating down, b̄ is too HIGH if some φ_j reaches the bid line
    (φ_j = b) first, too LOW if a bidder whose support starts above the bottom reaches its floor first.
    At the right b̄ both happen together at the lowest winning bid b_low (= r when all supports start at r)."""
    from scipy.integrate import solve_ivp
    n = len(ds)
    tops = np.array([d.hi for d in ds], float)
    floors = np.array([max(d.lo, r) for d in ds], float)
    scale = tops.max() - r

    def rhs(b, phi):
        gap = np.maximum(phi - b, 1e-12)
        S = np.sum(1 / gap) / (n - 1)
        out = np.empty(n)
        for i, d in enumerate(ds):
            F, f = d.F(phi[i]), d.pdf(phi[i])
            out[i] = (F / max(f, 1e-12)) * (S - 1 / gap[i])
        return out

    def shoot(bbar):
        ev_gap = lambda b, phi: np.min(phi - b) - 1e-7 * scale  # noqa: E731
        ev_gap.terminal, ev_gap.direction = True, -1
        evs = [ev_gap]
        high_floor = [i for i in range(n) if floors[i] > r + 1e-9 * scale]
        for i in high_floor:
            e = (lambda i: (lambda b, phi: phi[i] - floors[i]))(i)
            e.terminal, e.direction = True, -1
            evs.append(e)
        sol = solve_ivp(rhs, (bbar, r + 1e-9 * scale), tops.copy(), events=evs, dense_output=True,
                        rtol=1e-8, atol=1e-10 * scale, max_step=(bbar - r) / 200)
        if sol.status == 1:
            hit_gap = len(sol.t_events[0]) > 0
            b_end = sol.t_events[0][0] if hit_gap else min(te[0] for te in sol.t_events[1:] if len(te))
            return ("high" if hit_gap else "low"), sol, b_end
        return "low", sol, r

    lo, hi = r, float(tops.min())
    best = None
    for _ in range(70):
        mid = 0.5 * (lo + hi)
        kind, sol, b_end = shoot(mid)
        if kind == "high":
            hi = mid
        else:
            lo = mid
            best = (mid, sol, b_end)
    if best is None:
        return None
    bbar, sol, b_low = best
    bgrid = np.linspace(b_low + 1e-9 * scale, bbar, 400)
    phis = [np.clip(sol.sol(bgrid)[i], floors[i], tops[i]) for i in range(n)]
    # consistency at the bottom: each φ_i(b_low) is either its floor or ≈ b_low
    for i in range(n):
        if not (abs(phis[i][0] - floors[i]) < 0.02 * scale or abs(phis[i][0] - b_low) < 0.02 * scale):
            return None
    return bbar, bgrid, phis


# ----------------------------------------------------------------------------- GPV
def cmd_gpv(a):
    import pandas as pd
    from scipy.stats import gaussian_kde
    df = pd.read_csv(a.bids)
    keep = [a.auction_col, a.bid_col] + ([a.n_col] if a.n_col else []) + ([a.bidder_col] if a.bidder_col in df.columns else [])
    if a.estimate_col:
        keep.append(a.estimate_col)
    df = df[keep].dropna(subset=[a.auction_col, a.bid_col])
    if a.estimate_col:
        df[a.bid_col] = df[a.bid_col] / df[a.estimate_col]   # normalize heterogeneous objects by their estimate
    df["n"] = df[a.n_col] if a.n_col else df.groupby(a.auction_col)[a.bid_col].transform("size")
    n_in = len(df)
    df = df[df.n >= 2]
    L = [f"# GPV: private {'costs' if a.procurement else 'values'} recovered from first-price bids", ""]
    if a.estimate_col:
        L.append(f"- Bids normalized by `{a.estimate_col}` (bid / estimate): values and costs below are in those units.")
    L.append(f"- {len(df):,} bids in {df[a.auction_col].nunique():,} auctions; bidders per auction: "
             + ", ".join(f"n={k}: {v}" for k, v in df.groupby('n')[a.auction_col].nunique().sort_index().items()))
    out = []
    for n, g in df.groupby("n"):
        bids = g[a.bid_col].astype(float).values
        if len(bids) < 30:
            continue
        kde = gaussian_kde(bids)
        xs = np.linspace(bids.min(), bids.max(), 2000)
        gx = kde(xs)
        Gx = np.cumsum(gx); Gx /= Gx[-1]
        gb, Gb = np.interp(bids, xs, gx), np.interp(bids, xs, Gx)
        if a.procurement:
            v = bids - (1 - Gb) / ((n - 1) * gb)
        else:
            v = bids + Gb / ((n - 1) * gb)
        lo, hi = np.quantile(bids, [0.025, 0.975])
        keep = (bids >= lo) & (bids <= hi)
        o = pd.DataFrame({"auction": g[a.auction_col].values[keep], "n": n, "bid": bids[keep], "value": v[keep]})
        if a.bidder_col in g.columns:
            o["bidder"] = g[a.bidder_col].values[keep]
        out.append(o)
    if not out:
        sys.exit("Need ≥30 bids for at least one value of n.")
    R = pd.concat(out)
    L.append(f"- Bids used: {len(R):,} of {n_in:,} (dropped: auctions with 1 bid, n-groups with < 30 bids, and the 2.5% tails "
             "of each group where kernel estimates are unreliable).")
    R["markup"] = (R.bid - R.value).abs() / R.value.abs()
    L += ["", f"| n | bids | median bid | median {'cost' if a.procurement else 'value'} | median markup |", "|---|---|---|---|---|"]
    for n, g in R.groupby("n"):
        L.append(f"| {n} | {len(g)} | {fmt(g.bid.median())} | {fmt(g.value.median())} | {100*g.markup.median():.1f}% |")
    srt = R.sort_values(["n", "bid"])
    viol = srt.groupby("n").value.apply(lambda s: np.mean(np.diff(s.values) < -1e-9 * np.abs(s.values).mean()))
    L += ["", "## Diagnostics", ""]
    L.append("- Monotonicity of the recovered value in the bid (theory requires increasing): violations "
             + ", ".join(f"n={k}: {100*v:.1f}%" for k, v in viol.items()))
    if (viol > 0.05).any():
        L.append("  - ⚠ Substantial violations: IPV + competitive bidding is rejected for those n. Suspects: **collusion** "
                 "(phantom/cover bids), common values, auction heterogeneity not controlled for (normalize bids by "
                 "the auction's estimate/budget first), or entry selection.")
    if R.n.nunique() > 1:
        mk = R.groupby("n").markup.median()
        trend = "fall" if mk.iloc[-1] < mk.iloc[0] else "do NOT fall"
        L.append(f"- Markups {trend} with the number of bidders ({', '.join(f'n={k}: {100*v:.1f}%' for k, v in mk.items())}). "
                 "Competitive theory predicts they fall; flat or rising markups are a collusion red flag. A falling pattern "
                 "in the POOLED data does not clear a subset: a cartel operating in some tenders can hide inside it - "
                 "run `collusion.py bids` and compare suspect vs other tenders.")
    L.append("- Assumptions: symmetric IPV, risk neutrality, same auction type, homogeneous objects. Normalize bids "
             "(e.g. bid / engineer's estimate) before running on heterogeneous tenders.")
    if a.out:
        R.to_csv(a.out, index=False)
        L.append(f"\nPseudo-values → `{a.out}`")
    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6.4, 4.2))
        for n, g in R.groupby("n"):
            ax.scatter(g.bid, g.value, s=6, alpha=0.6, label=f"n={n}")
        lim = [R[["bid", "value"]].min().min(), R[["bid", "value"]].max().max()]
        ax.plot(lim, lim, ls=":", color="grey"); ax.set_xlabel("bid"); ax.set_ylabel("recovered cost" if a.procurement else "recovered value")
        ax.legend(fontsize=7, ncol=2); ax.grid(alpha=0.3); fig.tight_layout(); fig.savefig(a.plot, dpi=150)
        L.append(f"Plot saved: {a.plot}")
    print("\n".join(L))


# ----------------------------------------------------------------------------- common value
def cmd_common(a):
    d = Dist(a.dist)
    rng = np.random.default_rng(7)
    ns = [int(x) for x in str(a.n_list).split(",")]
    S = 200_000
    L = [f"# Common value - V ~ {a.dist}, signal = V + U[−{a.noise:g}, {a.noise:g}]", ""]
    L.append("| n | naive bid E[V|s]: winner's avg profit | equilibrium (2nd-price): winner's avg profit | avg shading below E[V|s] |")
    L.append("|---|---|---|---|")
    for n in ns:
        Vv = d.sample(S, rng)
        sig = Vv[:, None] + rng.uniform(-a.noise, a.noise, (S, n))
        # E[V | s] by binning
        bins = np.linspace(sig.min(), sig.max(), 200)
        idx = np.clip(np.digitize(sig[:, 0], bins) - 1, 0, len(bins) - 2)
        ev = np.bincount(idx, weights=Vv, minlength=len(bins) - 1) / np.maximum(np.bincount(idx, minlength=len(bins) - 1), 1)
        naive = lambda s: np.interp(s, (bins[:-1] + bins[1:]) / 2, ev)  # noqa: E731
        # equilibrium SPA: b(s) = E[V | s1 = s, Y1 = s]; estimate with pairs where |Y1 - s1| small
        Y1 = np.sort(sig[:, 1:], axis=1)[:, -1] if n > 1 else sig[:, 0]
        close = np.abs(Y1 - sig[:, 0]) < a.noise / 25
        s1, vv = sig[close, 0], Vv[close]
        idx2 = np.clip(np.digitize(s1, bins) - 1, 0, len(bins) - 2)
        cnt = np.bincount(idx2, minlength=len(bins) - 1)
        e2 = np.bincount(idx2, weights=vv, minlength=len(bins) - 1) / np.maximum(cnt, 1)
        mids = (bins[:-1] + bins[1:]) / 2
        good = cnt > 20
        eqb = lambda s: np.interp(s, mids[good], e2[good])  # noqa: E731
        srt = np.sort(sig, axis=1)
        # second-price: winner pays the second-highest bid
        pay_naive = naive(srt[:, -2])
        pay_eq = eqb(srt[:, -2])
        prof_naive = (Vv - pay_naive).mean()
        prof_eq = (Vv - pay_eq).mean()
        shade = (naive(sig[:, 0]) - eqb(sig[:, 0])).mean()
        L.append(f"| {n} | {prof_naive:.3g} | {prof_eq:.3g} | {shade:.3g} |")
    L += ["", "- **Winner's curse**: winning means your signal was the most optimistic - naive bidders overpay on average.",
          "- In common-value auctions **more bidders → bid more cautiously** (winning becomes worse news), the opposite of private values.",
          "- English (open) auctions reveal information as others drop out → less winner's curse, higher revenue than "
          "sealed bids (linkage principle, Milgrom-Weber 1982)."]
    print("\n".join(L))


def plot_bids(d, u, series, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    for s in series:
        if s is None:
            continue
        lab, y = s
        ax.plot(u.val(d.x), u.bid(y), lw=2, label=lab)
    ax.set_xlabel(u.V); ax.set_ylabel(u.B); ax.set_title(title); ax.grid(alpha=0.3); ax.legend(fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=150)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["bne", "reserve", "numeric", "gpv", "common"])
    ap.add_argument("--dist", default="uniform:0,1")
    ap.add_argument("--bidder", action="append", help="numeric: one distribution per bidder (repeatable)")
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--n-list", default="2,4,8", help="common: list of n")
    ap.add_argument("--reserve", type=float)
    ap.add_argument("--v0", type=float, help="seller's own value (or buyer's cost if no contract, procurement)")
    ap.add_argument("--format", choices=["fpa", "allpay"], default="fpa")
    ap.add_argument("--procurement", action="store_true")
    ap.add_argument("--credit", help="numeric --procurement: bidding credits, e.g. '2:0.05,3:0.05' (bidder:fraction)")
    ap.add_argument("--premium", type=float, default=0.0, help="bne/reserve: buyer's premium as a fraction of hammer (e.g. 0.25)")
    ap.add_argument("--commission", type=float, default=0.0, help="bne/reserve: seller's commission as a fraction of hammer")
    ap.add_argument("--noise", type=float, default=0.1)
    ap.add_argument("--bids"); ap.add_argument("--auction-col", default="auction"); ap.add_argument("--bid-col", default="bid")
    ap.add_argument("--n-col"); ap.add_argument("--out")
    ap.add_argument("--estimate-col", help="gpv: normalize bids by this column (engineer's estimate, budget, auction-house estimate)")
    ap.add_argument("--bidder-col", default="bidder", help="gpv: kept in the output if present")
    ap.add_argument("--plot")
    a = ap.parse_args()
    {"bne": cmd_bne, "reserve": cmd_reserve, "numeric": cmd_numeric, "gpv": cmd_gpv, "common": cmd_common}[a.cmd](a)


if __name__ == "__main__":
    main()
