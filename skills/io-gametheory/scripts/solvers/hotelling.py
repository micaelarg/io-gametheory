# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "scipy>=1.11", "matplotlib>=3.8"]
# ///
"""Hotelling in all its forms - one numeric engine, verified equilibria.

Consumers are a fine grid with weights (any distribution). Each consumer buys from the
firm with the lowest "delivered price" p_j + C_j(consumer), or nothing if that exceeds v.
  horizontal: C_j(x) = t·d(x, x_j)^k     (k=1 linear, k=2 quadratic, any k>0; line or circle)
  vertical:   C_j(θ) = −θ·s_j            (quality s_j, taste for quality θ; v=0 → outside option)

SUBCOMMANDS
  price      prices given locations/qualities (Bertrand stage). Detects non-existence of a
             pure equilibrium (linear costs, close firms) and then computes the MIXED one.
  location   two-stage game: locations (or qualities) first, then prices (--stage price), or
             the original fixed-price game (--stage fixed: Hotelling/Downs, median voter,
             n firms - Eaton-Lipsey non-existence for n=3). Compares with the social optimum.
  salop      circular city with free entry: closed forms (linear & quadratic costs),
             excess entry, plus numeric check of the symmetric price equilibrium.

EXAMPLES
  uv run hotelling.py price --positions 0.2,0.7 --t 1 --k 2 --plot tent.png
  uv run hotelling.py price --positions 0.45,0.55 --t 1 --k 1            # no pure eq → mixed
  uv run hotelling.py location --n 2 --stage price --k 2 --bounds -0.5,1.5 # → (−1/4, 5/4)
  uv run hotelling.py location --n 3 --stage fixed                         # no equilibrium
  uv run hotelling.py location --n 2 --stage fixed --density beta:2,5      # median
  uv run hotelling.py price --vertical --qualities 1,2 --theta 1,3
  uv run hotelling.py location --vertical --n 2 --theta 1,3 --bounds 1,3 --kappa 0
  uv run hotelling.py salop --t 1 --F 0.01 --k 1

Densities: uniform | beta:a,b | normal:mu,sd | triangular:mode | csv:path[:column]
(on [0,1] for horizontal, on [θlo, θhi] for vertical).
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------- market
class Market:
    def __init__(self, vertical=False, space="line", density="uniform", M=4001, t=1.0, k=2.0,
                 v=np.inf, theta=(1.0, 2.0), mass=1.0):
        self.vertical, self.space, self.t, self.k, self.v = vertical, space, t, k, v
        lo, hi = (theta if vertical else (0.0, 1.0))
        self.lo, self.hi = lo, hi
        # consumers live in M cells; demand is computed with the indifferent consumer located
        # INSIDE each cell (linear interpolation at cell edges) → demand is continuous in prices
        self.z = lo + (hi - lo) * (np.arange(M) + 0.5) / M
        self.ze = lo + (hi - lo) * np.arange(M + 1) / M
        self.w = self._density(density) * mass
        self.density_name = density

    def _density(self, spec):
        u = (self.z - self.lo) / (self.hi - self.lo)
        if spec == "uniform":
            f = np.ones_like(u)
        elif spec.startswith("beta:"):
            from scipy.stats import beta
            a, b = map(float, spec[5:].split(","))
            f = beta.pdf(u, a, b)
        elif spec.startswith("normal:"):
            mu, sd = map(float, spec[7:].split(","))
            f = np.exp(-0.5 * ((self.z - mu) / sd) ** 2)
        elif spec.startswith("triangular:"):
            m = float(spec[11:])
            f = np.where(u <= m, u / max(m, 1e-12), (1 - u) / max(1 - m, 1e-12))
        elif spec.startswith("csv:"):
            import pandas as pd
            parts = spec[4:].split(":")
            df = pd.read_csv(parts[0])
            col = parts[1] if len(parts) > 1 else df.columns[0]
            h, edges = np.histogram(df[col].astype(float), bins=60, range=(self.lo, self.hi))
            from scipy.ndimage import gaussian_filter1d
            h = gaussian_filter1d(h.astype(float), 1.0) + 1e-9
            f = np.interp(self.z, (edges[:-1] + edges[1:]) / 2, h)
        else:
            sys.exit(f"unknown density {spec}")
        f = np.clip(f, 0, None)
        return f / f.sum()

    def column(self, param, z=None):
        z = self.z if z is None else z
        if self.vertical:
            return -z * param
        d = np.abs(z - param)
        if self.space == "circle":
            d = np.minimum(d, 1 - d)
        return self.t * d ** self.k

    def C(self, params):
        """(cost at cell midpoints, cost at cell edges)"""
        return (np.column_stack([self.column(p) for p in params]),
                np.column_stack([self.column(p, self.ze) for p in params]))


# --------------------------------------------------------------------------- price stage
def demand_curve(mk, C, p, i, P):
    """Firm i's demand at each candidate price in P, others at p. Continuous in P."""
    Cm, Ce = C
    others = np.delete(np.arange(len(p)), i)
    if len(others):
        m_e = (p[others][None, :] + Ce[:, others]).min(axis=1)
        Dm = p[others][None, :] + Cm[:, others]
        m_m = Dm.min(axis=1)
        nt = np.isclose(Dm, m_m[:, None], rtol=0, atol=1e-12).sum(axis=1)
    else:
        m_e, m_m, nt = (np.full(len(mk.ze), np.inf), np.full(len(mk.z), np.inf), np.zeros(len(mk.z)))
    cap_e = np.minimum(m_e, mk.v)
    with np.errstate(invalid="ignore", divide="ignore"):
        adv = cap_e[None, :] - (P[:, None] + Ce[:, i][None, :])
        fl, fr = adv[:, :-1], adv[:, 1:]
        frac = np.where((fl >= 0) & (fr >= 0), 1.0, 0.0)
        mixed = (fl > 0) & (fr < 0)
        frac = np.where(mixed, fl / (fl - fr), frac)
        mixed2 = (fl < 0) & (fr > 0)
        frac = np.where(mixed2, fr / (fr - fl), frac)
        zero = (np.abs(fl) < 1e-12) & (np.abs(fr) < 1e-12)
        own_m = P[:, None] + Cm[:, i][None, :]
        tied = np.isclose(own_m, m_m[None, :], rtol=0, atol=1e-12)
        frac = np.where(zero, np.where(tied, 1.0 / (1 + nt[None, :]), 1.0) * (own_m <= mk.v + 1e-12), frac)
    return np.nan_to_num(frac) @ mk.w, cap_e


def shares(mk, C, p):
    return np.array([demand_curve(mk, C, p, i, np.array([p[i]]))[0][0] for i in range(len(p))])


def best_price(mk, C, p, i, c_i):
    from scipy.optimize import minimize_scalar
    _, cap_e = demand_curve(mk, C, p, i, np.array([c_i]))
    hi = np.max(cap_e - C[1][:, i])
    if not np.isfinite(hi):
        hi = c_i + 10 * (np.ptp(C[1]) + 1)
    if hi <= c_i:
        return c_i, 0.0
    P = np.linspace(c_i, hi, 121)
    pr = (P - c_i) * demand_curve(mk, C, p, i, P)[0]
    j = int(np.argmax(pr))
    a_, b_ = P[max(j - 1, 0)], P[min(j + 1, len(P) - 1)]
    f = lambda q: -(q - c_i) * demand_curve(mk, C, p, i, np.array([q]))[0][0]  # noqa: E731
    r = minimize_scalar(f, bounds=(a_, b_), method="bounded", options={"xatol": 1e-11})
    if -r.fun >= pr[j]:
        return float(r.x), float(-r.fun)
    return float(P[j]), float(pr[j])


def quad_duopoly_exact(mk, params, c):
    """Exact price equilibrium: line, quadratic cost, covered market, 2 firms, ANY density (via its CDF).
    Indifferent consumer x* = (p2 − p1)/(2tΔ) + (x1 + x2)/2 is linear in prices; FOCs solved by Newton."""
    from scipy.optimize import fsolve
    x1, x2 = params
    if abs(x2 - x1) < 1e-12:
        return None
    cdf_x = mk.ze
    cdf = np.concatenate([[0.0], np.cumsum(mk.w)]) / mk.w.sum()
    F = lambda x: np.interp(x, cdf_x, cdf, left=0.0, right=1.0)  # noqa: E731
    f = lambda x: np.interp(x, mk.z, mk.w / (cdf_x[1] - cdf_x[0]), left=0.0, right=0.0)  # noqa: E731
    d = 2 * mk.t * (x2 - x1)
    m = (x1 + x2) / 2
    mass = mk.w.sum()

    def foc(p):
        xs = (p[1] - p[0]) / d + m
        D1 = F(xs) if d > 0 else 1 - F(xs)
        dD1 = (-f(xs) / d) if d > 0 else (f(xs) / d)
        D2 = 1 - D1
        dD2 = dD1  # dD2/dp2 = −dD1/dp2 = dD1/dp1
        return [mass * (D1 + (p[0] - c[0]) * dD1), mass * (D2 + (p[1] - c[1]) * dD2)]

    p0 = c + abs(d) / 2 + 1e-6
    sol, info, ier, _ = fsolve(foc, p0, full_output=True, xtol=1e-13)
    if ier != 1 or np.any(sol < c - 1e-12):
        return None

    # exact verification: scan every own price with the exact demand
    def prof(i, q, other):
        pp = [q, other] if i == 0 else [other, q]
        xs = (pp[1] - pp[0]) / d + m
        D1 = F(xs) if d > 0 else 1 - F(xs)
        return (q - c[i]) * mass * (D1 if i == 0 else 1 - D1)
    for i in range(2):
        other = sol[1 - i]
        Q = np.linspace(c[i], c[i] + 3 * (abs(d) + abs(other - c[i])) + 1e-9, 4001)
        cur = prof(i, sol[i], other)
        if np.max(prof(i, Q, other)) > cur + 1e-7 * (1 + abs(cur)):
            return None
    return sol


def price_equilibrium(mk, params, c, iters=200, p0=None):
    if (not mk.vertical and mk.space == "line" and abs(mk.k - 2) < 1e-12 and not np.isfinite(mk.v)
            and len(params) == 2):
        ex = quad_duopoly_exact(mk, np.asarray(params, float), np.asarray(c, float))
        if ex is not None:
            return ex, True, 0, mk.C(params)
    C = mk.C(params)
    n = len(params)
    p = np.array(p0 if p0 is not None else c + np.ptp(C[0]) / 2 + 1e-3, float)
    # Firms at the same spot (same quality) are perfect substitutes: Bertrand inside the group,
    # price = second-lowest cost of the group. Solve it analytically instead of undercutting cent by cent.
    free = np.ones(n, bool)
    cell = (mk.hi - mk.lo) / len(mk.z)
    key = np.round(np.asarray(params, float) / (0.5 * cell)) * (0.5 * cell)
    for v in np.unique(key):
        g = np.where(key == v)[0]
        if len(g) > 1:
            p[g] = np.sort(c[g])[1]
            free[g] = False
    hist = []
    for it in range(iters):
        old = p.copy()
        for i in np.where(free)[0]:
            p[i], _ = best_price(mk, C, p, i, c[i])
        hist.append(p.copy())
        if np.max(np.abs(p - old)) < 1e-9 * (1 + np.abs(p).max()):
            return p, True, it + 1, C
        if it > 30 and any(np.allclose(p, h, atol=1e-7) for h in hist[:-3]):
            return p, False, it + 1, C
    return p, False, iters, C


def verify_prices(mk, C, p, c, rtol=1e-5):
    out = []
    s = shares(mk, C, p)
    for i in range(len(p)):
        cur = (p[i] - c[i]) * s[i]
        _, bv = best_price(mk, C, p, i, c[i])
        gain = bv - cur
        out.append((gain, gain <= rtol * max(abs(cur), 1e-6) + 1e-10))
    return out


def mixed_prices(mk, params, c, N=61):
    sys.path.insert(0, HERE)
    from _milp import epsilon, milp_nash
    C = mk.C(params)
    hi = max(c) + np.ptp(C[0]) + 1e-6
    if np.isfinite(mk.v):
        hi = min(hi, mk.v - C[0].min())
    G = [np.linspace(c[i], hi, N) for i in range(2)]
    A = np.zeros((N, N)); B = np.zeros((N, N))
    for a in range(N):
        for b in range(N):
            s = shares(mk, C, np.array([G[0][a], G[1][b]]))
            A[a, b] = (G[0][a] - c[0]) * s[0]
            B[a, b] = (G[1][b] - c[1]) * s[1]
    x, y = milp_nash(A, B)
    eps, v1, v2 = epsilon(A, B, x, y)
    return G, x, y, v1, v2, eps


# --------------------------------------------------------------------------- reporting helpers
def welfare(mk, C, p, c):
    C = C[0]
    D = p[None, :] + C
    j = D.argmin(axis=1)
    buy = D.min(axis=1) <= mk.v + 1e-12
    trans = (C[np.arange(len(j)), j] * buy) @ mk.w
    return trans


def analytic_price_note(mk, params, c):
    if mk.vertical or mk.space != "line" or mk.density_name != "uniform" or len(params) != 2 or np.isfinite(mk.v):
        if mk.vertical and len(params) == 2 and mk.density_name == "uniform" and not np.isfinite(mk.v) and abs(c[0] - c[1]) < 1e-12:
            sL, sH = sorted(params)
            ds = sH - sL
            tl, th = mk.lo, mk.hi
            if th >= 2 * tl:
                return (f"Closed form (covered vertical, uniform θ∈[{tl:g},{th:g}]): p_H = c + (2θ̄−θ̲)Δs/3 = {c[0] + (2*th - tl)*ds/3:.4g}, "
                        f"p_L = c + (θ̄−2θ̲)Δs/3 = {c[0] + (th - 2*tl)*ds/3:.4g}")
        return None
    if abs(mk.k - 2) < 1e-12 and abs(c[0] - c[1]) < 1e-12:
        x1, x2 = sorted(params)
        a, b = x1, 1 - x2
        p1 = c[0] + mk.t * (1 - a - b) * (1 + (a - b) / 3)
        p2 = c[0] + mk.t * (1 - a - b) * (1 + (b - a) / 3)
        return f"Closed form (quadratic, d'Aspremont-Gabszewicz-Thisse): p = ({p1:.4g}, {p2:.4g})"
    if abs(mk.k - 1) < 1e-12 and abs(c[0] - c[1]) < 1e-12:
        x1, x2 = sorted(params)
        a, b = x1, 1 - x2
        cond = (1 + (a - b) / 3) ** 2 >= 4 * (a + 2 * b) / 3 and (1 + (b - a) / 3) ** 2 >= 4 * (b + 2 * a) / 3
        p1 = c[0] + mk.t * (1 + (a - b) / 3)
        p2 = c[0] + mk.t * (1 + (b - a) / 3)
        return (f"Closed form (linear, Hotelling 1929): p = ({p1:.4g}, {p2:.4g}) - valid only if firms are far enough apart; "
                f"d'Aspremont et al. condition {'holds ✓' if cond else 'FAILS ✗ → no pure price equilibrium'}")
    return None


def tent_plot(mk, params, p, c, path, title, names):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    C = mk.C(params)[0]
    D = p[None, :] + C
    j = D.argmin(axis=1)
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    ax2 = ax.twinx()
    ax2.fill_between(mk.z, mk.w / mk.w.max(), color="0.85", step="mid", zorder=0)
    ax2.set_ylim(0, 4)
    ax2.set_yticks([])
    cols = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    for i in range(len(params)):
        lab = names[i] if names else f"Firm {i+1}"
        ax.plot(mk.z, D[:, i], lw=1, ls=":", color=cols[i % len(cols)])
        msk = j == i
        ax.plot(np.where(msk, mk.z, np.nan), np.where(msk, D[:, i], np.nan), lw=2.6, color=cols[i % len(cols)],
                label=f"{lab}: {'s' if mk.vertical else 'x'}={params[i]:.3g}, p={p[i]:.3g}")
        if not mk.vertical:
            ax.axvline(params[i], color=cols[i % len(cols)], alpha=0.3)
    if np.isfinite(mk.v):
        ax.axhline(mk.v, color="black", ls="--", lw=1, label=f"reservation value v={mk.v:g}")
    ax.set_zorder(ax2.get_zorder() + 1)
    ax.patch.set_visible(False)
    ax.set_xlabel("taste for quality θ" if mk.vertical else "consumer location")
    ax.set_ylabel("price − utility" if mk.vertical else "delivered price  p + transport cost")
    ax.set_title(title + "\n(solid = who serves each consumer; grey = consumer density)", fontsize=10)
    ax.legend(fontsize=8, loc="best")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


# --------------------------------------------------------------------------- subcommands
def cmd_price(a, mk):
    params = np.array([float(x) for x in (a.qualities if a.vertical else a.positions).split(",")])
    n = len(params)
    c = np.array([float(x) for x in a.costs.split(",")]) if a.costs else np.zeros(n)
    if a.kappa:
        c = c + a.kappa * params ** 2 / 2
    p, conv, its, C = price_equilibrium(mk, params, c)
    chk = verify_prices(mk, C, p, c)
    ok = conv and all(x[1] for x in chk)
    what = "qualities" if mk.vertical else "locations"
    L = [f"# Hotelling price stage ({'vertical' if mk.vertical else mk.space + ', k=' + format(mk.k, 'g')})", ""]
    L.append(f"- {what}: {', '.join(f'{x:g}' for x in params)}; unit costs {', '.join(f'{x:.4g}' for x in c)}; "
             f"t={mk.t:g}; v={'∞ (covered market)' if not np.isfinite(mk.v) else format(mk.v, 'g')}; density {mk.density_name}")
    note = analytic_price_note(mk, params, c)
    if ok:
        s = shares(mk, C, p)
        L += ["", "## ✅ Pure price equilibrium (verified: no firm gains by any price change)", ""]
        L.append("| firm | price | margin | share | profit |\n|---|---|---|---|---|")
        for i in range(n):
            L.append(f"| {i+1} | {p[i]:.4g} | {p[i]-c[i]:.4g} | {100*s[i]:.1f}% | {(p[i]-c[i])*s[i]:.4g} |")
        L.append(f"\n- Served: {100*s.sum():.1f}% of consumers. Avg transport/mismatch cost: {welfare(mk, C, p, c):.4g}.")
        if note:
            L.append(f"- {note}")
        L.append("- Demand is computed with the indifferent consumer interpolated inside each cell (continuous in prices); "
                 "closed forms above are the check.")
        if a.plot:
            tent_plot(mk, params, p, c, a.plot, "Price equilibrium", None)
            L.append(f"\nPlot saved: {a.plot}")
    else:
        L += ["", "## ❌ No pure price equilibrium", ""]
        L.append("Best responses cycle (Edgeworth-type): each firm wants to undercut to grab the rival's whole "
                 "hinterland, then raise again. Typical with linear transport costs and firms close together.")
        if note:
            L.append(f"- {note}")
        if n == 2:
            G, x, y, v1, v2, eps = mixed_prices(mk, params, c)
            L += ["", "## Mixed price equilibrium (MILP on a 61×61 price grid)", ""]
            for i, (g, pr) in enumerate(((G[0], x), (G[1], y))):
                sup = g[pr > 1e-6]
                L.append(f"- Firm {i+1}: prices in [{sup.min():.4g}, {sup.max():.4g}], mean {g @ pr:.4g}")
            L.append(f"- Expected profits: {v1:.4g}, {v2:.4g}; ε = {eps:.1e}")
            L.append("- Interpretation: observed price dispersion / sales cycles (Osborne-Pitchik 1987).")
    print("\n".join(L))


_WARM = None


def stage_payoffs(mk, params, c0, a):
    n = len(params)
    c = c0 + (a.kappa * np.asarray(params) ** 2 / 2 if a.kappa else 0)
    C = mk.C(params)
    if a.stage == "fixed":
        p = np.full(n, a.price)
        s = shares(mk, C, p)
        return (p - c) * s if a.price > 0 else s, p, True
    global _WARM
    p0 = _WARM if _WARM is not None and len(_WARM) == n else None
    p, conv, its, _ = price_equilibrium(mk, params, c, iters=150, p0=p0)
    if conv and its == 0:          # exact path, verified analytically
        ok = True
    else:
        chk = verify_prices(mk, C, p, c)
        ok = all(x[1] for x in chk)   # verification, not convergence speed, decides
    if ok:
        _WARM = p.copy()
    return (p - c) * shares(mk, C, p), p, ok


def exhaustive(mk, a, lo, hi, c0, n, G, fixed=()):
    """All pure equilibria on a grid (n ≤ 3): payoff tensor, mutual best responses. Proof of (non)existence on the grid."""
    import itertools
    grid = np.linspace(lo, hi, G)
    P = np.zeros((G,) * n + (n,))
    fixed = np.asarray(fixed, float)
    for prof in itertools.product(range(G), repeat=n):
        P[prof] = stage_payoffs(mk, np.concatenate([grid[list(prof)], fixed]), c0, a)[0][:n]
    mask = np.ones((G,) * n, bool)
    for i in range(n):
        Pi = P[..., i]
        mask &= Pi >= Pi.max(axis=i, keepdims=True) - 1e-9 * (1 + np.abs(Pi).max())
    eqs = sorted({tuple(sorted(grid[list(e)])) for e in np.argwhere(mask)})
    return grid, eqs


def cmd_location(a, mk):
    n = a.n
    lo, hi = (float(x) for x in a.bounds.split(",")) if a.bounds else ((mk.lo, mk.hi) if mk.vertical else (0.0, 1.0))
    FX = np.array([float(v) for v in a.fixed.split(",")]) if a.fixed else np.zeros(0)
    c0 = np.array([float(x) for x in a.costs.split(",")]) if a.costs else np.zeros(n + len(FX))
    _sp = stage_payoffs

    def stage_payoffs_free(mk_, xfree, c_, a_):
        pay_, p_, ok_ = _sp(mk_, np.concatenate([np.asarray(xfree, float), FX]), c_, a_)
        return pay_, p_, ok_
    SP = stage_payoffs_free
    x = np.array([float(v) for v in a.init.split(",")]) if a.init else np.linspace(lo, hi, n + 2)[1:-1] + 1e-3 * np.arange(n)
    grid = np.linspace(lo, hi, a.grid)
    hist, conv, bad = [x.copy()], False, 0
    exh = None
    if a.stage == "fixed" and n <= 3:
        G = a.grid_user or (81 if n == 2 else 41)
        g_, eqs = exhaustive(mk, a, lo, hi, c0, n, G, FX)
        exh = (G, eqs)
        if eqs:
            x = np.array(eqs[len(eqs) // 2], float)
            conv = True
    capped = False
    for it in range(0 if exh else a.iters):
        old = x.copy()
        for i in range(n):
            vals = []
            for g in grid:
                y = x.copy(); y[i] = g
                pay, _, ok = SP(mk, y, c0, a)
                bad += (not ok)
                vals.append(pay[i] if ok else -np.inf)
            j = int(np.argmax(vals))
            # refine
            from scipy.optimize import minimize_scalar

            def negpay(g, i=i):
                y = x.copy(); y[i] = g
                pay, _, ok = SP(mk, y, c0, a)
                return -pay[i] if ok else np.inf
            r = minimize_scalar(negpay, bounds=(grid[max(j - 1, 0)], grid[min(j + 1, len(grid) - 1)]),
                                method="bounded", options={"xatol": 1e-7 * (hi - lo)})
            x[i] = r.x if np.isfinite(r.fun) and -r.fun >= vals[j] else grid[j]
        hist.append(x.copy())
        if np.max(np.abs(x - old)) < 1e-5 * (hi - lo):
            conv = True
            break
        # cycle detection
        if any(np.allclose(x, h, atol=1e-9) for h in hist[:-2]):
            break
    else:
        capped = not exh
    pay, p, ok = SP(mk, x, c0, a)
    # verification: no firm gains by moving anywhere on a fine grid
    gains = []
    for i in range(n):
        best = pay[i]
        for g in np.linspace(lo, hi, 2 * a.grid + 1):
            y = x.copy(); y[i] = g
            py, _, ok2 = SP(mk, y, c0, a)
            if ok2:
                best = max(best, py[i])
        gains.append(best - pay[i])
    verified = conv and all(g <= 2e-3 * max(abs(pv), 1e-6) + 1e-9 for g, pv in zip(gains, pay))
    if exh and exh[1]:
        verified = True  # exact on the grid; fine-grid gains reported below are discretization

    kind = "quality" if mk.vertical else "location"
    kinds = "qualities" if mk.vertical else "locations"
    L = [f"# Hotelling {kind} game - n={n}, stage 2 = {'price competition' if a.stage == 'price' else f'fixed price {a.price:g}'}", ""]
    L.append(f"- Space {'θ∈[%g,%g]' % (mk.lo, mk.hi) if mk.vertical else mk.space}; strategy bounds [{lo:g}, {hi:g}]; "
             f"{'' if mk.vertical else (f't={mk.t:g}, k={mk.k:g}; ' if a.stage == 'price' else f'k={mk.k:g} (only used for the social-optimum transport cost); ')}density {mk.density_name}; "
             f"v={'∞' if not np.isfinite(mk.v) else format(mk.v, 'g')}" + (f"; quality cost κs²/2 with κ={a.kappa:g}" if a.kappa else ""))
    if len(FX):
        L.append(f"- **Sequential entry**: firms already located at {', '.join(f'{v:g}' for v in FX)} (fixed); "
                 f"solving for the {n} new entrant(s).")
    if verified:
        how = (f"exhaustive search over all profiles on a {exh[0]}-point grid; {len(exh[1])} equilibrium profile(s) "
               f"up to relabeling: " + "; ".join("(" + ", ".join(f"{v:.3g}" for v in e) + ")" for e in exh[1][:6])) if exh else \
              f"best-response iteration, verified against every move on a {2*a.grid+1}-point grid"
        L += ["", f"## ✅ Equilibrium {kinds} ({how})", ""]
        C = mk.C(np.concatenate([x, FX]))
        s = shares(mk, C, p)
        L.append(f"| firm | {kind} | price | share | payoff | best deviation gain |\n|---|---|---|---|---|---|")
        for i in np.argsort(x):
            L.append(f"| {i+1}{' (new)' if len(FX) else ''} | {x[i]:.4g} | {p[i]:.4g} | {100*s[i]:.1f}% | {pay[i]:.4g} | {gains[i]:.1e} |")
        for k_, fx in enumerate(FX):
            j = n + k_
            L.append(f"| incumbent {k_+1} (fixed) | {fx:.4g} | {p[j]:.4g} | {100*s[j]:.1f}% | - | - |")
    else:
        L += ["", f"## ❌ No pure {kind} equilibrium found", ""]
        if exh:
            L.append(f"**Proved on the grid**: exhaustive search over all {exh[0]}^{n} profiles finds no profile where "
                     "every firm is best-responding.")
        else:
            why = ("hit the iteration cap - rerun with more --iters" if capped else
                   "cycled" if not conv else "converged but a profitable move remains")
            L.append(f"Best responses {why}. Last profile: {', '.join(f'{v:.3g}' for v in x)}; "
                     f"max deviation gain {max(gains):.3g}.")
        if a.stage == "fixed" and n == 3 and not mk.vertical:
            L.append("This is the classic **Eaton-Lipsey (1975)** result: with 3 firms the one in the middle is squeezed "
                     "and always wants to jump outside → no pure equilibrium. (n=2: both at the median; n=4,5: pairs.)")
    if bad and a.stage == "price":
        if abs(mk.k - 1) < 1e-9:
            L.append(f"\n⚠ {bad} location profiles had **no pure price equilibrium** in stage 2 (excluded) - expected with "
                     "linear transport costs (d'Aspremont-Gabszewicz-Thisse 1979): Hotelling's 'minimum differentiation' "
                     "is not an equilibrium. Use k=2, or price-stage mixed equilibria.")
        else:
            L.append(f"\n_Note: {bad} off-equilibrium profiles (typically corner cases where one firm would take the whole "
                     "market) had no verified stage-2 price equilibrium and were excluded from best-response search._")

    # social optimum (horizontal, covered): minimize transport costs over positions
    if verified and not mk.vertical and not np.isfinite(mk.v):
        ntot = n + len(FX)
        y = np.linspace(lo, hi, ntot + 2)[1:-1]
        for _ in range(30):
            for i in range(ntot):
                cand = []
                for g in np.linspace(lo, hi, 201):
                    z = y.copy(); z[i] = g
                    cand.append(mk.C(z)[0].min(axis=1) @ mk.w)
                y[i] = np.linspace(lo, hi, 201)[int(np.argmin(cand))]
        Cx = mk.C(np.concatenate([x, FX]))
        L += ["", "## Versus the social optimum", ""]
        L.append(f"- Cost-minimizing {kinds}: {', '.join(f'{v:.3g}' for v in sorted(y))} "
                 f"(avg transport cost {mk.C(y)[0].min(axis=1) @ mk.w:.4g})")
        L.append(f"- Equilibrium avg transport cost: {welfare(mk, Cx, p, c0):.4g} → "
                 + ("**too little differentiation**" if np.ptp(np.concatenate([x, FX])) < np.ptp(y) - 1e-3 else
                    "**too much differentiation**" if np.ptp(np.concatenate([x, FX])) > np.ptp(y) + 1e-3 else "efficient"))
    if a.plot and verified:
        tent_plot(mk, np.concatenate([x, FX]), p, c0 + (a.kappa * x ** 2 / 2 if a.kappa else 0), a.plot, f"Equilibrium {kind}s and prices", None)
        L.append(f"\nPlot saved: {a.plot}")
    print("\n".join(L))


def cmd_salop(a):
    t, F, k, L_, c = a.t, a.F, a.k, a.mass, 0.0
    out = [f"# Salop circular city - t={t:g}, F={F:g}, market size L={L_:g}, transport k={k:g}", ""]
    if abs(k - 1) < 1e-12:
        n_free = np.sqrt(t * L_ / F); n_opt = 0.5 * np.sqrt(t * L_ / F)
        price = lambda n: t / n  # noqa: E731
        trans = lambda n: t / (4 * n)  # noqa: E731
    elif abs(k - 2) < 1e-12:
        n_free = (t * L_ / F) ** (1 / 3); n_opt = (t * L_ / (6 * F)) ** (1 / 3)
        price = lambda n: t / n ** 2  # noqa: E731
        trans = lambda n: t / (12 * n ** 2)  # noqa: E731
    else:
        sys.exit("salop closed forms for k=1 or k=2")
    ni = int(np.floor(n_free + 1e-9))
    while ni > 1 and price(ni) * L_ / ni - F < 0:
        ni -= 1
    out.append(f"- Free entry: n* = {n_free:.3g} (integer: **{ni}** firms), price markup p − c = {price(ni):.4g}, "
               f"profit per firm {price(ni)*L_/ni - F:.3g}")
    oi = max(1, int(round(n_opt)))
    out.append(f"- Social optimum: n° = {n_opt:.3g} (≈ {oi}) - minimizes n·F + L·avg transport cost")
    out.append(f"- **Excess entry**: market has {n_free/n_opt:.2f}× the efficient number of stores "
               f"(business stealing: an entrant's profit includes customers taken from others, not new value).")
    out.append(f"- Social cost free entry {ni*F + L_*trans(ni):.4g} vs optimum {oi*F + L_*trans(oi):.4g}")
    # numeric check
    mk = Market(space="circle", t=t, k=k, M=4000, mass=L_)
    pos = (np.arange(ni) + 0.25) / ni
    p, conv, _, C = price_equilibrium(mk, pos, np.zeros(ni))
    out.append(f"- Numeric check (engine, {ni} equally spaced firms): prices {np.round(p, 4).tolist()[:6]}{'…' if ni > 6 else ''} "
               f"vs closed form {price(ni):.4g} {'✓' if np.allclose(p, price(ni), rtol=5e-3) else '✗ (check)'}")
    print("\n".join(out))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["price", "location", "salop"])
    ap.add_argument("--vertical", action="store_true", help="vertical (quality) differentiation")
    ap.add_argument("--space", choices=["line", "circle"], default="line")
    ap.add_argument("--positions", default="0.25,0.75")
    ap.add_argument("--qualities", default="1,2")
    ap.add_argument("--theta", default="1,2", help="vertical: taste range θlo,θhi")
    ap.add_argument("--costs", help="unit costs per firm (comma)")
    ap.add_argument("--kappa", type=float, default=0.0, help="vertical: unit cost of quality κ·s²/2")
    ap.add_argument("--t", type=float, default=1.0)
    ap.add_argument("--k", type=float, default=2.0, help="transport cost exponent (1 linear, 2 quadratic)")
    ap.add_argument("--v", type=float, default=float("inf"), help="reservation value (uncovered market); vertical: use 0 for outside option")
    ap.add_argument("--density", default="uniform")
    ap.add_argument("--M", type=int, default=2001, help="consumer cells (price stage; location stage uses ≤801)")
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--stage", choices=["price", "fixed"], default="price")
    ap.add_argument("--price", type=float, default=0.0, help="fixed price (stage fixed); 0 → firms maximize share")
    ap.add_argument("--bounds")
    ap.add_argument("--init")
    ap.add_argument("--fixed", help="location: positions of firms that already entered (sequential entry), e.g. 0.25,0.75")
    ap.add_argument("--grid", type=int, default=0, help="strategy grid (default 41 fixed-price, 25 price stage)")
    ap.add_argument("--iters", type=int, default=40)
    ap.add_argument("--F", type=float, default=0.01, help="salop: fixed cost of entry")
    ap.add_argument("--mass", type=float, default=1.0, help="market size")
    ap.add_argument("--plot")
    a = ap.parse_args()
    if a.cmd == "salop":
        return cmd_salop(a)
    a.grid_user = a.grid or None
    if not a.grid:
        a.grid = 41 if a.stage == "fixed" else 25
    theta = tuple(float(x) for x in a.theta.split(","))
    mk = Market(vertical=a.vertical, space=a.space, density=a.density, M=a.M if a.cmd == "price" else min(a.M, 801),
                t=a.t, k=a.k, v=a.v, theta=theta, mass=a.mass)
    (cmd_price if a.cmd == "price" else cmd_location)(a, mk)


if __name__ == "__main__":
    main()
