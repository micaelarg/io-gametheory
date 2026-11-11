# /// script
# requires-python = ">=3.10"
# dependencies = ["sympy>=1.12", "numpy>=1.26", "scipy>=1.11", "matplotlib>=3.8"]
# ///
"""Mixed equilibria of continuous two-player games with no pure equilibrium.

Typical cases: all-pay auctions / contests, wars of attrition, price dispersion
(Varian sales model), Bertrand-Edgeworth (capacity-constrained pricing),
Hotelling with linear transport costs.

Same input JSON as continuous_br.py (2 players, finite bounds).
Method: discretize each strategy space into N points, solve the matrix game
(linear programming if zero-sum, otherwise Lemke-Howson from several starting
labels), verify ε (max gain from deviating to any grid point), report the
support, atoms, mean, quantiles, and plot the CDFs. Refine N to check that the
distribution converges (it should, if the continuous equilibrium is atomless).
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings

import os

import numpy as np
import sympy as sp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load(path):
    with open(path) as f:
        spec = json.load(f)
    names = list(spec["players"].keys())
    if len(names) != 2:
        sys.exit("mixed_continuous.py handles 2 players.")
    P = spec["players"]
    vars_ = [sp.Symbol(P[n]["var"], real=True) for n in names]
    params = {sp.Symbol(k, real=True): float(v) for k, v in spec.get("params", {}).items()}
    local = {str(s): s for s in list(vars_) + list(params)}
    us = [sp.sympify(P[n]["payoff"], locals=local).subs(params) for n in names]
    f = [sp.lambdify(vars_, u, "numpy") for u in us]
    bounds = [tuple(map(float, P[n]["bounds"])) for n in names]
    return spec.get("title", "Game"), names, vars_, f, bounds


def matrices(f, bounds, N):
    G1, G2 = np.linspace(*bounds[0], N), np.linspace(*bounds[1], N)
    X1, X2 = np.meshgrid(G1, G2, indexing="ij")
    A = np.asarray(f[0](X1, X2), float) * np.ones_like(X1)
    B = np.asarray(f[1](X1, X2), float) * np.ones_like(X1)
    return G1, G2, A, B


from _milp import epsilon, milp_nash, solve, zero_sum_lp  # noqa: E402,F401


def describe(grid, p, name, var):
    cdf = np.cumsum(p)
    supp = grid[p > 1e-6]
    q = lambda t: grid[np.searchsorted(cdf, t)]  # noqa: E731
    atoms = [(grid[k], p[k]) for k in range(len(p)) if p[k] > 0.08]
    lines = [f"- **{name}** ({var}): support ≈ [{supp.min():.4g}, {supp.max():.4g}], mean {grid @ p:.4g}, "
             f"quartiles {q(0.25):.4g} / {q(0.5):.4g} / {q(0.75):.4g}"]
    if atoms:
        lines.append("  - mass points (>8% on one grid point): " + ", ".join(f"{a:.4g} ({w:.0%})" for a, w in atoms)
                     + " - check whether they persist as N grows (true atom) or spread out (discretization).")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game")
    ap.add_argument("--n", type=int, default=81, help="grid points per player (default 81)")
    ap.add_argument("--plot", help="PNG path for the CDF plot")
    a = ap.parse_args()
    title, names, vars_, f, bounds = load(a.game)

    out = [f"# {title} - mixed equilibrium", ""]
    results = []
    for N in (max(11, a.n // 2) | 1, a.n):
        G1, G2, A, B = matrices(f, bounds, N)
        rb = np.isclose(A, A.max(axis=0, keepdims=True))
        cb = np.isclose(B, B.max(axis=1, keepdims=True))
        pure = np.argwhere(rb & cb)
        x, y, method = solve(A, B)
        eps, v1, v2 = epsilon(A, B, x, y)
        results.append((N, G1, G2, x, y, eps, v1, v2, len(pure), method))

    N, G1, G2, x, y, eps, v1, v2, npure, method = results[-1]
    out.append(f"- Grid: {N} points per player. Method: {method}.")
    out.append(f"- Pure equilibria on the grid: {npure}"
               + (" - a pure equilibrium exists; use continuous_br.py instead." if npure else " (as expected)."))
    out.append(f"- ε-check: the best deviation to any grid point gains {eps:.2e} (≈0 means exact equilibrium of the discretized game).")
    out.append(f"- Expected payoffs: {names[0]} {v1:.4g}, {names[1]} {v2:.4g}")
    out.append("")
    out += describe(G1, x, names[0], vars_[0])
    out += describe(G2, y, names[1], vars_[1])
    Nc, G1c, G2c, xc, yc, *_ , v1c, v2c, _, _ = results[0]
    out.append("")
    out.append(f"**Convergence** (N={Nc} → N={N}): mean {names[0]} {G1c @ xc:.4g} → {G1 @ x:.4g}, "
               f"{names[1]} {G2c @ yc:.4g} → {G2 @ y:.4g}; payoffs {v1c:.4g} → {v1:.4g}, {v2c:.4g} → {v2:.4g}. "
               "Stable numbers = trustworthy approximation of the continuous equilibrium.")
    out.append("")
    out.append("Explanation hint: in a mixed equilibrium every price/bid in the support yields the **same** expected "
               "payoff - that indifference is what pins down the distribution. Say it with the numbers above.")

    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6.4, 4.4))
        ax.step(G1, np.cumsum(x), where="post", lw=2, label=f"{names[0]} ({vars_[0]})")
        ax.step(G2, np.cumsum(y), where="post", lw=2, ls="--", label=f"{names[1]} ({vars_[1]})")
        ax.set_xlabel("strategy")
        ax.set_ylabel("cumulative probability")
        ax.set_title(f"{title}: equilibrium CDFs")
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(a.plot, dpi=150)
        out.append(f"\nPlot saved: {a.plot}")
    print("\n".join(out))


if __name__ == "__main__":
    main()
