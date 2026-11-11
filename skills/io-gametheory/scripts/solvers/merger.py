# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "scipy>=1.11", "pandas>=2.1"]
# ///
"""Market power and mergers: concentration, upward pricing pressure, demand, merger simulation.

SUBCOMMANDS
  hhi       Shares CSV (firm, share|sales [, owner_after]) or --merge A,B → HHI pre/post, ΔHHI, CR4,
            and the screening thresholds of several jurisdictions (US 2023, EU, UK, others similar).
  upp       Diversion-ratio screens for a two-product merger: GUPPI, UPP, first-order price effects,
            compensating marginal-cost reductions (Werden 1996).
              --p1 --p2 --m1 --m2 (Lerner margins) --d12 --d21 (diversion ratios) [--e1 --e2 efficiencies]
  demand    (--data --market-col --share-col --price-col [--x a,b --iv z1,z2 --outside-col])
            Logit demand from market-share data (Berry 1994 inversion): ln(s_j) − ln(s_0) = x'β − α p + ξ,
            OLS and 2SLS with your instruments; elasticities and implied Bertrand margins; warns when
            price looks endogenous (α wrong sign, inelastic demand).
  simulate  Bertrand-logit merger simulation (multi-product firms): calibrate α from one known margin,
            back out marginal costs, re-solve with the merged ownership. Price changes, shares, profits,
            consumer surplus (logsum), compensating cost reductions, efficiency scenarios.
              --products products.csv (product, firm, price, share[, margin]) --merge A,B
              [--outside-share s0 | --diversion D --div-from P1 --div-to P2] [--market-size M] [--efficiency 0.05]
  cournot   Homogeneous Cournot with linear demand and asymmetric costs: merger effects, the merger
            paradox (Salant-Switzer-Reynolds 1983) and the cost saving that makes prices not rise.
              --a 100 --b 1 --costs 10,10,10,10 --merge 1,2 [--merged-cost 8]

All monetary inputs in any currency; shares in % or fractions (auto-detected).
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd


def fmt(x, d=4):
    if x is None or not np.isfinite(x):
        return "-"
    if abs(x) < 1e-12:
        return "0"
    return f"{x:,.0f}" if abs(x) >= 1000 else f"{x:.{d}g}"


# ----------------------------------------------------------------------------- HHI
THRESHOLDS = [
    ("US (DOJ/FTC Merger Guidelines 2023)",
     lambda pre, post, d, smax: ("presumed to substantially lessen competition" if (post > 1800 and d > 100) or (smax > 30 and d > 100)
                                 else "no structural presumption")),
    ("EU (Horizontal Merger Guidelines 2004)",
     lambda pre, post, d, smax: ("safe harbour (unlikely concerns)" if post < 1000 or (post <= 2000 and d < 250) or (post > 2000 and d < 150)
                                 else "outside safe harbours - further analysis")),
    ("UK (CMA)", lambda pre, post, d, smax: ("concentrated" if post > 2000 else "moderately concentrated" if post > 1000 else "unconcentrated")
     + (", ΔHHI > 250 → likely to be examined" if d > 250 else "")),
]


def cmd_hhi(a):
    df = pd.read_csv(a.shares)
    df.columns = [c.lower() for c in df.columns]
    col = "share" if "share" in df.columns else "sales"
    s = df[col].astype(float)
    s = 100 * s / s.sum() if col == "sales" or s.sum() <= 1.0001 else s
    df["s"] = s
    if "owner_after" in df.columns:
        df["post_owner"] = df.owner_after.fillna(df.firm)
    else:
        merge = [m.strip() for m in (a.merge or "").split(",") if m.strip()]
        df["post_owner"] = df.firm.where(~df.firm.isin(merge), "+".join(merge))
    pre = (df.s ** 2).sum()
    post_sh = df.groupby("post_owner").s.sum()
    post = (post_sh ** 2).sum()
    d = post - pre
    cr4 = df.s.nlargest(4).sum()
    merging = bool(a.merge) or "owner_after" in df.columns
    L = ["# Concentration", "", f"- Firms: {len(df)}; CR4 = {cr4:.1f}%; effective number of equal-sized firms 1/HHI = {10000/pre:.1f}",
         (f"- HHI pre = **{pre:,.0f}**, post = **{post:,.0f}**, ΔHHI = **{d:,.0f}**" if merging else
          f"- HHI = **{pre:,.0f}** ({'highly concentrated' if pre > 1800 else 'moderately concentrated' if pre > 1000 else 'unconcentrated'}; no merger specified)"),
         f"- Largest post-merger share: {post_sh.max():.1f}% ({post_sh.idxmax()})", "", "| jurisdiction | reading |", "|---|---|"]
    for name, f in THRESHOLDS:
        L.append(f"| {name} | {f(pre, post, d, post_sh.max())} |")
    L += ["", "Thresholds are screens, not verdicts: market definition drives everything (SSNIP test, "
          "diversion), and unilateral effects depend on closeness of competition (run `upp`/`simulate`). "
          "Other authorities (Brazil CADE, Mexico, Chile FNE, India CCI, Australia ACCC…) use similar HHI bands - "
          "check the local guidelines."]
    print("\n".join(L))


# ----------------------------------------------------------------------------- UPP
def cmd_upp(a):
    p1, p2, m1, m2, d12, d21 = a.p1, a.p2, a.m1, a.m2, a.d12, a.d21
    c1, c2 = p1 * (1 - m1), p2 * (1 - m2)
    g1 = d12 * m2 * p2 / p1
    g2 = d21 * m1 * p1 / p2
    upp1 = d12 * (p2 - c2) - a.e1 * c1
    upp2 = d21 * (p1 - c1) - a.e2 * c2
    # Werden (1996) compensating marginal-cost reductions (Bertrand, two single-product firms)
    den = (1 - d12 * d21)
    cmcr1 = (m1 * d12 * d21 + m2 * d12 * p2 / p1) / ((1 - m1) * den)
    cmcr2 = (m2 * d21 * d12 + m1 * d21 * p1 / p2) / ((1 - m2) * den)
    L = ["# Upward pricing pressure (merger of product 1 and product 2)", ""]
    L.append(f"- Prices {fmt(p1)}, {fmt(p2)}; margins {100*m1:.0f}%, {100*m2:.0f}%; diversion 1→2 {100*d12:.0f}%, 2→1 {100*d21:.0f}%")
    L += ["", "| | product 1 | product 2 |", "|---|---|---|",
          f"| GUPPI (value of diverted sales / own price) | {100*g1:.1f}% | {100*g2:.1f}% |",
          f"| UPP (net of claimed efficiencies {100*a.e1:.0f}%, {100*a.e2:.0f}%) | {fmt(upp1)} | {fmt(upp2)} |",
          f"| First-order price rise, pass-through ½ (linear demand) | {100*0.5*upp1/p1:.1f}% | {100*0.5*upp2/p2:.1f}% |",
          f"| First-order price rise, pass-through 1 (logit-like) | {100*upp1/p1:.1f}% | {100*upp2/p2:.1f}% |",
          f"| Cost cut needed to keep prices unchanged (Werden CMCR) | {100*cmcr1:.1f}% | {100*cmcr2:.1f}% |"]
    L += ["", "- Rule of thumb used by authorities: GUPPI below ~5% rarely raises unilateral-effects concerns.",
          "- Diversion ratios: from switching surveys, win/loss data, customer churn, or estimated demand (`demand`).",
          "- UPP ignores rivals' responses and feedback; use `simulate` for the equilibrium effect."]
    print("\n".join(L))


# ----------------------------------------------------------------------------- logit demand
def tsls(y, X, Z):
    """2SLS: X endogenous+exog, Z instruments+exog (same exog included)."""
    Pz = Z @ np.linalg.pinv(Z.T @ Z) @ Z.T
    Xh = Pz @ X
    b = np.linalg.pinv(Xh.T @ X) @ Xh.T @ y
    u = y - X @ b
    s2 = u @ u / (len(y) - X.shape[1])
    V = s2 * np.linalg.pinv(Xh.T @ Xh)
    return b, np.sqrt(np.diag(V))


def cmd_demand(a):
    df = pd.read_csv(a.data)
    x = [c for c in (a.x or "").split(",") if c]
    z = [c for c in (a.iv or "").split(",") if c]
    df["s0"] = 1 - df.groupby(a.market_col)[a.share_col].transform("sum") if a.outside_col is None else df[a.outside_col]
    if (df.s0 <= 0).any():
        sys.exit("Inside shares sum to ≥ 1 in some market: shares must be of the TOTAL potential market (define market size).")
    y = np.log(df[a.share_col]) - np.log(df.s0)
    X = np.column_stack([np.ones(len(df)), df[a.price_col]] + [df[c] for c in x])
    names = ["const", "price"] + x
    b, se = np.linalg.lstsq(X, y, rcond=None)[0], None
    u = y - X @ b
    se = np.sqrt(np.diag(u @ u / (len(y) - X.shape[1]) * np.linalg.pinv(X.T @ X)))
    L = [f"# Logit demand - {len(df)} product-market observations, {df[a.market_col].nunique()} markets", ""]
    rows = [("OLS", b, se)]
    if z:
        Z = np.column_stack([np.ones(len(df))] + [df[c] for c in z] + [df[c] for c in x])
        b2, se2 = tsls(y.values, X, Z)
        rows.append(("2SLS", b2, se2))
        # first stage F
        Zf = np.column_stack([np.ones(len(df))] + [df[c] for c in x])
        r_res = df[a.price_col] - Zf @ np.linalg.lstsq(Zf, df[a.price_col], rcond=None)[0]
        u_res = df[a.price_col] - Z @ np.linalg.lstsq(Z, df[a.price_col], rcond=None)[0]
        q = len(z)
        F = ((r_res @ r_res - u_res @ u_res) / q) / (u_res @ u_res / (len(df) - Z.shape[1]))
    L += ["| coefficient | " + " | ".join(r[0] for r in rows) + " |", "|---|" + "---|" * len(rows)]
    for k, nm in enumerate(names):
        L.append(f"| {nm} | " + " | ".join(f"{r[1][k]:.4g} ({r[2][k]:.3g})" for r in rows) + " |")
    alpha = -rows[-1][1][1]
    p, s = df[a.price_col].values, df[a.share_col].values
    el = -alpha * p * (1 - s)
    marg = 1 / (alpha * (1 - s))
    L += ["", f"- Using **{rows[-1][0]}**: α = {alpha:.4g}. Own-price elasticity median {np.median(el):.2f} "
          f"(range {el.min():.2f} to {el.max():.2f}).",
          f"- Implied single-product Bertrand margin (p−c)/p: median {100*np.median(marg/p):.0f}%. Compare with known margins - "
          "that comparison is the best validation you have."]
    if z:
        L.append(f"- First-stage F on excluded instruments: {F:.1f} " + ("✅" if F > 10 else "⚠ weak instruments (F < 10)"))
        a_ols, a_iv = -rows[0][1][1], -rows[1][1][1]
        if F < 10:
            L.append("- ⚠ Instruments are weak (F < 10): 2SLS is unreliable and biased toward OLS - do not conclude "
                     "anything about endogeneity from this comparison; find stronger instruments.")
        elif a_iv > 0 and abs(a_ols - a_iv) / a_iv > 0.25:
            L.append(f"- OLS α ({a_ols:.3g}) vs 2SLS α ({a_iv:.3g}): **price is endogenous** - OLS is biased toward zero "
                     "because high-quality products (unobserved) are priced higher. Never use the OLS elasticities.")
    if alpha <= 0 or np.median(np.abs(el)) < 1:
        L.append("- ⚠ Price coefficient has the wrong sign or demand is inelastic: price is correlated with unobserved quality "
                 "(endogeneity). Use instruments: cost shifters, Hausman (same product's price in other markets), "
                 "BLP (sums of rivals' characteristics), or the number of rivals.")
    L.append("- Logit imposes IIA (diversion proportional to share). For closer substitution patterns use nested logit "
             "(nests by segment) or random coefficients (BLP; e.g. PyBLP).")
    print("\n".join(L))


# ----------------------------------------------------------------------------- logit merger simulation
def logit_shares(delta, alpha, p):
    e = np.exp(delta - alpha * p)
    return e / (1 + e.sum())


def solve_prices(delta, alpha, c, owner, p0):
    firms = np.unique(owner)
    p = p0.copy()
    for _ in range(5000):
        s = logit_shares(delta, alpha, p)
        mu = np.empty_like(p)
        for f in firms:
            m = owner == f
            mu[m] = 1 / (alpha * (1 - s[m].sum()))
        new = c + mu
        if np.max(np.abs(new - p)) < 1e-12 * (1 + p.max()):
            return new
        p = 0.5 * p + 0.5 * new
    return p


def cmd_simulate(a):
    df = pd.read_csv(a.products)
    df.columns = [c.lower() for c in df.columns]
    p = df.price.values.astype(float)
    s = df.share.values.astype(float)
    if s.sum() > 1.0001:
        s = s / 100
    if a.diversion is not None:
        # logit diversion D_ij = s_j / (1 − s_i): choose the scale of inside shares to match the observed diversion
        names = df["product"].astype(str).tolist()
        i, j = names.index(a.div_from), names.index(a.div_to)
        rel = s / s.sum()
        k = a.diversion / (rel[j] + a.diversion * rel[i])
        if k * rel.sum() >= 1:
            sys.exit("Observed diversion is too high for logit with these shares (would leave no outside good): "
                     "the products are closer substitutes than logit allows → use nested logit or `upp` with survey diversion.")
        s = rel * k
        print(f"_Calibrated outside-good share from observed diversion {a.div_from}→{a.div_to} = {a.diversion:g}: "
              f"s0 = {1 - s.sum():.3f}_\n")
    elif a.outside_share is not None:
        s = s / s.sum() * (1 - a.outside_share)
    if s.sum() >= 1:
        sys.exit("Shares must leave room for the outside good: give --outside-share (e.g. 0.3).")
    s0 = 1 - s.sum()
    owner = df.firm.astype(str).values
    merge = [m.strip() for m in a.merge.split(",")]
    new_owner = np.where(np.isin(owner, merge), "+".join(merge), owner)
    # calibrate alpha from the first product with a known margin
    if "margin" not in df.columns or df.margin.isna().all():
        if a.alpha is None:
            sys.exit("Need a margin for at least one product (column 'margin', Lerner (p−c)/p) or --alpha.")
        alpha = a.alpha
    else:
        k = int(df.margin.first_valid_index())
        Sf = s[owner == owner[k]].sum()
        alpha = 1 / (df.margin[k] * p[k] * (1 - Sf))
    mu_pre = np.empty_like(p)
    for f in np.unique(owner):
        m = owner == f
        mu_pre[m] = 1 / (alpha * (1 - s[m].sum()))
    c = p - mu_pre
    if (c <= 0).any():
        print("⚠ Some implied marginal costs are ≤ 0: the calibrated α implies margins above 100% - check the margin input.")
    delta = np.log(s) - np.log(s0) + alpha * p
    eff = np.where(np.isin(owner, merge), 1 - a.efficiency, 1.0)
    p_post = solve_prices(delta, alpha, c * eff, new_owner, p)
    s_post = logit_shares(delta, alpha, p_post)
    M = a.market_size
    cs = lambda pp: M / alpha * np.log(1 + np.exp(delta - alpha * pp).sum())  # noqa: E731
    dcs = cs(p_post) - cs(p)
    prof = lambda pp, ss, cc: (pp - cc) * ss * M  # noqa: E731
    # compensating marginal cost reduction (prices unchanged after merger)
    mu_post_at_pre = np.empty_like(p)
    for f in np.unique(new_owner):
        m = new_owner == f
        mu_post_at_pre[m] = 1 / (alpha * (1 - s[m].sum()))
    cmcr = (mu_post_at_pre - mu_pre) / c
    L = [f"# Merger simulation (Bertrand, logit demand): {' + '.join(merge)}", ""]
    L.append(f"- α = {alpha:.4g} (calibrated from {'a known margin' if a.alpha is None else 'input'}); outside good share {100*s0:.1f}%; "
             f"market size {fmt(M)}; efficiency on merging products {100*a.efficiency:.0f}%")
    L += ["", "| product | firm | price pre | price post | Δ% | share pre | share post | margin pre | CMCR |", "|---|---|---|---|---|---|---|---|---|"]
    for j in range(len(p)):
        L.append(f"| {df['product'][j]} | {owner[j]} | {fmt(p[j])} | {fmt(p_post[j])} | {100*(p_post[j]/p[j]-1):+.1f}% | "
                 f"{100*s[j]:.1f}% | {100*s_post[j]:.1f}% | {100*mu_pre[j]/p[j]:.0f}% | "
                 f"{100*cmcr[j]:.1f}% |" if np.isin(owner[j], merge) else
                 f"| {df['product'][j]} | {owner[j]} | {fmt(p[j])} | {fmt(p_post[j])} | {100*(p_post[j]/p[j]-1):+.1f}% | "
                 f"{100*s[j]:.1f}% | {100*s_post[j]:.1f}% | {100*mu_pre[j]/p[j]:.0f}% | |")
    pr_pre, pr_post = prof(p, s, c), prof(p_post, s_post, c * eff)
    # verification: no firm gains by moving any of its prices (±0.5%…±10%) at the post-merger equilibrium
    worst = 0.0
    for f in np.unique(new_owner):
        m = new_owner == f
        base_pf = ((p_post - c * eff) * s_post)[m].sum()
        for jj in np.where(m)[0]:
            for d in (-0.1, -0.03, -0.005, 0.005, 0.03, 0.1):
                pp = p_post.copy(); pp[jj] *= 1 + d
                ss = logit_shares(delta, alpha, pp)
                worst = max(worst, ((pp - c * eff) * ss)[m].sum() - base_pf)
    mg = np.isin(owner, merge)
    L += ["", "## Effects", "",
          f"- Share-weighted price change: merging products {100*np.average(p_post[mg]/p[mg]-1, weights=s[mg]):+.2f}%, "
          f"rivals {100*np.average(p_post[~mg]/p[~mg]-1, weights=s[~mg]) if (~mg).any() else 0:+.2f}% (rivals raise too: strategic complements)",
          f"- Consumer surplus change: **{fmt(dcs)}**",
          f"- Merging firms' profit change: {fmt(pr_post[mg].sum() - pr_pre[mg].sum())}; rivals: {fmt(pr_post[~mg].sum() - pr_pre[~mg].sum())}",
          f"- Cost reduction needed for zero price effect (CMCR): {', '.join(f'{100*x:.1f}%' for x in cmcr[mg])}. "
          "Claimed efficiencies below this → prices rise.",
          f"- Verification: best unilateral price deviation found gains {worst:.2e} (per unit of market size) → "
          + ("✅ equilibrium" if worst <= 1e-9 * max(1, abs(pr_post.sum())) else "⚠ check"),
          "- Logit assumes diversion proportional to share (IIA). If the merging products are closer substitutes than "
          "shares suggest, this UNDER-states the price effect; use nested logit/BLP or survey diversion (`upp`)."]
    print("\n".join(L))


# ----------------------------------------------------------------------------- cournot
def cournot_eq(a_, b, c):
    c = np.asarray(c, float)
    active = np.ones(len(c), bool)
    while True:
        n = active.sum()
        q = np.zeros(len(c))
        q[active] = (a_ - (n + 1) * c[active] + c[active].sum()) / (b * (n + 1))
        if (q[active] >= -1e-12).all():
            break
        active &= q > 0
    q = np.maximum(q, 0)
    P = a_ - b * q.sum()
    return q, P, (P - c) * q


def cmd_cournot(a):
    c = np.array([float(x) for x in a.costs.split(",")])
    m = [int(x) - 1 for x in a.merge.split(",")]
    q0, P0, pi0 = cournot_eq(a.a, a.b, c)
    keep = [i for i in range(len(c)) if i not in m]
    mc = a.merged_cost if a.merged_cost is not None else c[m].min()
    c1 = np.concatenate([[mc], c[keep]])
    q1, P1, pi1 = cournot_eq(a.a, a.b, c1)
    cs = lambda Q: 0.5 * a.b * Q ** 2  # noqa: E731
    # cost making price unchanged: total output unchanged → merged firm's cost
    # Q depends on sum of costs: Q = (n a - Σc)/(b(n+1)) → need Σc_post = Σc_pre·... solve
    n0, n1 = len(c), len(c1)
    Q0 = q0.sum()
    sum_needed = n1 * a.a - Q0 * a.b * (n1 + 1)
    c_needed = sum_needed - c[keep].sum()
    L = [f"# Cournot merger: firms {', '.join(str(i+1) for i in m)} (linear demand P = {a.a:g} − {a.b:g}Q)", ""]
    L += ["| | pre | post |", "|---|---|---|",
          f"| price | {fmt(P0)} | {fmt(P1)} |",
          f"| total output | {fmt(Q0)} | {fmt(q1.sum())} |",
          f"| merging firms' joint profit | {fmt(pi0[m].sum())} | {fmt(pi1[0])} |",
          f"| outsiders' profit | {fmt(pi0[keep].sum())} | {fmt(pi1[1:].sum())} |",
          f"| consumer surplus | {fmt(cs(Q0))} | {fmt(cs(q1.sum()))} |"]
    gain = pi1[0] - pi0[m].sum()
    verdict = ("break-even (exactly the Salant-Switzer-Reynolds threshold)" if abs(gain) < 1e-9 * (1 + abs(pi0[m].sum()))
               else "profitable" if gain > 0 else "NOT profitable")
    L += ["", f"- Merger is **{verdict}** for the merging firms (Δ profit {fmt(gain)}).",
          (f"- Merged firm's marginal cost needed to keep the price unchanged: **{fmt(c_needed)}** "
           f"(vs {fmt(c[m].min())} best pre-merger cost: a {100*(1 - c_needed/c[m].min()):.1f}% cut)." if c_needed > 0 else
           f"- **No feasible cost saving keeps the price unchanged** (it would need marginal cost {fmt(c_needed)} < 0): "
           "in Cournot, a merger without synergies large enough to make the merged firm more efficient than the best "
           "pre-merger firm by a wide margin always raises price (Farrell-Shapiro 1990)."),
          "- **Merger paradox** (Salant-Switzer-Reynolds 1983): in symmetric linear Cournot, merging is unprofitable unless "
          "~80% of the firms merge - outsiders expand and capture the gains. Real mergers that happen therefore signal "
          "efficiencies, product differentiation, capacity constraints, or coordinated effects."]
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["hhi", "upp", "demand", "simulate", "cournot"])
    ap.add_argument("--shares"); ap.add_argument("--merge")
    for k in ("p1", "p2", "m1", "m2", "d12", "d21"):
        ap.add_argument(f"--{k}", type=float)
    ap.add_argument("--e1", type=float, default=0.0); ap.add_argument("--e2", type=float, default=0.0)
    ap.add_argument("--data"); ap.add_argument("--market-col", default="market"); ap.add_argument("--share-col", default="share")
    ap.add_argument("--price-col", default="price"); ap.add_argument("--outside-col"); ap.add_argument("--x"); ap.add_argument("--iv")
    ap.add_argument("--products"); ap.add_argument("--outside-share", type=float); ap.add_argument("--market-size", type=float, default=1.0)
    ap.add_argument("--efficiency", type=float, default=0.0); ap.add_argument("--alpha", type=float)
    ap.add_argument("--diversion", type=float, help="simulate: observed diversion ratio from --div-from to --div-to (calibrates the outside good)")
    ap.add_argument("--div-from"); ap.add_argument("--div-to")
    ap.add_argument("--a", type=float, default=100); ap.add_argument("--b", type=float, default=1)
    ap.add_argument("--costs"); ap.add_argument("--merged-cost", type=float)
    a = ap.parse_args()
    {"hhi": cmd_hhi, "upp": cmd_upp, "demand": cmd_demand, "simulate": cmd_simulate, "cournot": cmd_cournot}[a.cmd](a)


if __name__ == "__main__":
    main()
