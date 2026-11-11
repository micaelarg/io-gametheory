# /// script
# requires-python = ">=3.10"
# dependencies = ["sympy>=1.12", "numpy>=1.26", "scipy>=1.11", "matplotlib>=3.8"]
# ///
"""Continuous-strategy games (prices, quantities, locations, efforts, bids) with n players.

Input JSON:
{
  "title": "Differentiated Bertrand",
  "players": {
    "Firm 1": {"var": "p1", "payoff": "(p1 - c1) * (a - b*p1 + d*p2)", "bounds": [0, 200]},
    "Firm 2": {"var": "p2", "payoff": "(p2 - c2) * (a - b*p2 + d*p1)", "bounds": [0, 200]}
  },
  "params": {"a": 100, "b": 2, "d": 1, "c1": 10, "c2": 20},
  "comparative_statics": ["c1", "a"]          (optional; default = all params)
}
Payoffs are sympy expressions (use Max, Min, Piecewise, exp, log, sqrt...).
Bounds are REQUIRED (finite) - they define the strategy space.

Pipeline:
 1. Symbolic FOCs and best responses (sympy), joint solution with symbolic params.
 2. Numeric fallback: damped best-response iteration (global grid search + refinement).
 3. VERIFICATION: for each player, search the whole strategy space for a profitable
    unilateral deviation. An equilibrium is reported only if none exists.
 4. Strategic complements/substitutes (slope of best responses at equilibrium).
 5. Comparative statics dx*/dθ (symbolic if possible, else finite differences).
 6. Optional: --grid N discrete cross-check (2 players), --plot file.png best responses,
    --leader NAME Stackelberg solution with NAME moving first.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
from contextlib import contextmanager

import numpy as np
import sympy as sp
from scipy.optimize import minimize_scalar

GRID = 801


@contextmanager
def time_limit(seconds):
    def handler(signum, frame):
        raise TimeoutError
    old = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


class Game:
    def __init__(self, spec):
        self.title = spec.get("title", "Continuous game")
        self.names = list(spec["players"].keys())
        P = spec["players"]
        self.vars = [sp.Symbol(P[n]["var"], real=True) for n in self.names]
        self.bounds = []
        for n in self.names:
            b = P[n].get("bounds")
            if not b or b[0] is None or b[1] is None:
                sys.exit(f"Player {n}: finite 'bounds' [lo, hi] are required.")
            self.bounds.append((float(b[0]), float(b[1])))
        self.params = {sp.Symbol(k, real=True): float(v) for k, v in spec.get("params", {}).items()}
        local = {str(s): s for s in list(self.vars) + list(self.params)}
        self.u = [sp.sympify(P[n]["payoff"], locals=local) for n in self.names]
        free = set().union(*[e.free_symbols for e in self.u]) - set(self.vars)
        missing = {str(s) for s in free} - {str(s) for s in self.params}
        if missing:
            sys.exit(f"Parameters without values: {sorted(missing)}")
        # rebind to the exact symbols used
        self.params = {s: self.params[next(p for p in self.params if str(p) == str(s))] for s in free}
        self.cs = spec.get("comparative_statics") or [str(s) for s in self.params]
        self.n = len(self.names)
        self.set_numeric(self.params)

    def set_numeric(self, pvals):
        self.pvals = pvals
        self.f = [sp.lambdify(self.vars, e.subs(pvals), "numpy") for e in self.u]

    def payoff(self, i, x):
        return float(self.f[i](*x))

    def best_response(self, i, x):
        lo, hi = self.bounds[i]
        grid = np.linspace(lo, hi, GRID)
        xs = [np.full_like(grid, v) if k != i else grid for k, v in enumerate(x)]
        vals = np.asarray(self.f[i](*xs), dtype=float) * np.ones_like(grid)
        vals = np.where(np.isfinite(vals), vals, -np.inf)
        k = int(np.argmax(vals))
        a, b = grid[max(k - 1, 0)], grid[min(k + 1, GRID - 1)]
        best_x, best_v = grid[k], vals[k]
        if b > a:
            def neg(z):
                y = list(x); y[i] = z
                v = self.payoff(i, y)
                return -v if np.isfinite(v) else np.inf
            r = minimize_scalar(neg, bounds=(a, b), method="bounded", options={"xatol": 1e-10})
            if r.success and -r.fun > best_v:
                best_x, best_v = r.x, -r.fun
        return float(best_x), float(best_v)

    def verify(self, x, rtol=1e-6):
        out = []
        for i in range(self.n):
            ui = self.payoff(i, x)
            bx, bv = self.best_response(i, x)
            gain = bv - ui
            ok = gain <= rtol * max(1.0, abs(ui))
            out.append({"player": self.names[i], "payoff": ui, "best_deviation": bx, "gain": gain, "ok": ok})
        return out

    def numeric_equilibrium(self, x0=None, iters=2000, damp=0.5):
        x = list(x0) if x0 else [(lo + hi) / 2 for lo, hi in self.bounds]
        for it in range(iters):
            new = list(x)
            for i in range(self.n):
                bx, _ = self.best_response(i, new)
                new[i] = (1 - damp) * new[i] + damp * bx
            if max(abs(a - b) for a, b in zip(new, x)) < 1e-10:
                return new, it + 1, True
            x = new
        return x, iters, False


def symbolic(g: Game):
    res = {"focs": [], "br": [], "eq": None, "note": ""}
    for i in range(g.n):
        foc = sp.diff(g.u[i], g.vars[i])
        res["focs"].append(sp.simplify(foc))
        try:
            with time_limit(10):
                sol = sp.solve(foc, g.vars[i], dict=False)
            res["br"].append(sol)
        except Exception:
            res["br"].append(None)
    try:
        with time_limit(25):
            sols = sp.solve(res["focs"], g.vars, dict=True)
        cands = []
        for s in sols:
            if len(s) != g.n:
                continue
            num = [complex(sp.N(s[v].subs(g.pvals))) for v in g.vars]
            if any(abs(z.imag) > 1e-9 for z in num):
                continue
            num = [z.real for z in num]
            if not all(lo - 1e-9 <= z <= hi + 1e-9 for z, (lo, hi) in zip(num, g.bounds)):
                continue
            soc = [float(sp.diff(g.u[i], g.vars[i], 2).subs(g.pvals).subs(dict(zip(g.vars, num))))
                   for i in range(g.n)]
            cands.append((s, num, soc))
        res["candidates"] = cands
        if not sols:
            res["note"] = "sympy found no closed-form solution of the FOC system."
    except TimeoutError:
        res["candidates"] = []
        res["note"] = "symbolic solve timed out (payoffs too complex) - using numeric methods."
    except Exception as e:  # noqa
        res["candidates"] = []
        res["note"] = f"symbolic solve failed ({type(e).__name__}) - using numeric methods."
    return res


def br_slopes(g: Game, x):
    """dBR_i/dx_j = -(d2u_i/dx_i dx_j) / (d2u_i/dx_i^2) at x."""
    sub = {**g.pvals, **dict(zip(g.vars, x))}
    out = []
    for i in range(g.n):
        own = sp.diff(g.u[i], g.vars[i], 2).subs(sub)
        for j in range(g.n):
            if i == j:
                continue
            cross = sp.diff(g.u[i], g.vars[i], g.vars[j]).subs(sub)
            try:
                slope = float(-cross / own)
            except Exception:
                slope = float("nan")
            out.append((g.names[i], g.names[j], slope))
    return out


def comparative_statics(g: Game, sym_sol, x_eq):
    rows = []
    for name in g.cs:
        th = next((p for p in g.pvals if str(p) == name), None)
        if th is None:
            continue
        derivs = []
        for k, v in enumerate(g.vars):
            if sym_sol is not None:
                d = sp.simplify(sp.diff(sym_sol[v], th))
                derivs.append((float(sp.N(d.subs(g.pvals))), str(d)))
            else:
                h = 1e-4 * max(1.0, abs(g.pvals[th]))
                vals = []
                for sgn in (1, -1):
                    pv = dict(g.pvals); pv[th] += sgn * h
                    g.set_numeric(pv)
                    xx, _, _ = g.numeric_equilibrium(x0=x_eq)
                    vals.append(xx[k])
                g.set_numeric(dict(g.pvals))
                derivs.append(((vals[0] - vals[1]) / (2 * h), "numeric"))
        rows.append((name, derivs))
    return rows


def grid_check(g: Game, _unused, N):
    (l1, h1), (l2, h2) = g.bounds
    G1, G2 = np.linspace(l1, h1, N), np.linspace(l2, h2, N)
    X1, X2 = np.meshgrid(G1, G2, indexing="ij")
    A = np.asarray(g.f[0](X1, X2), float) * np.ones_like(X1)
    B = np.asarray(g.f[1](X1, X2), float) * np.ones_like(X1)
    rb = np.isclose(A, A.max(axis=0, keepdims=True), rtol=1e-12, atol=1e-12)
    cb = np.isclose(B, B.max(axis=1, keepdims=True), rtol=1e-12, atol=1e-12)
    eqs = [(G1[i], G2[j]) for i, j in np.argwhere(rb & cb)]
    step = ((h1 - l1) / (N - 1), (h2 - l2) / (N - 1))
    return eqs, step


def stackelberg(g: Game, leader: str):
    L = g.names.index(leader)
    F = 1 - L
    lo, hi = g.bounds[L]

    def leader_value(xl):
        x = [0.0, 0.0]; x[L] = xl
        x[F], _ = g.best_response(F, x)
        return g.payoff(L, x), x

    grid = np.linspace(lo, hi, 401)
    vals = [leader_value(z)[0] for z in grid]
    k = int(np.argmax(vals))
    a, b = grid[max(k - 1, 0)], grid[min(k + 1, len(grid) - 1)]
    r = minimize_scalar(lambda z: -leader_value(z)[0], bounds=(a, b), method="bounded")
    xl = r.x if -r.fun >= vals[k] else grid[k]
    v, x = leader_value(xl)
    return x, [g.payoff(i, x) for i in range(2)]


def plot(g: Game, x_eq, path, stack=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    (l1, h1), (l2, h2) = g.bounds
    t2 = np.linspace(l2, h2, 120)
    t1 = np.linspace(l1, h1, 120)
    br1 = [g.best_response(0, [x_eq[0], z])[0] for z in t2]
    br2 = [g.best_response(1, [z, x_eq[1]])[0] for z in t1]
    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    ax.plot(br1, t2, lw=2.2, label=f"{g.names[0]}'s best response to {g.vars[1]}")
    ax.plot(t1, br2, lw=2.2, label=f"{g.names[1]}'s best response to {g.vars[0]}")
    ax.scatter([x_eq[0]], [x_eq[1]], s=90, zorder=5, color="black", label="Nash equilibrium")
    ax.annotate(f"  ({x_eq[0]:.3g}, {x_eq[1]:.3g})", (x_eq[0], x_eq[1]), fontsize=10)
    if stack is not None:
        ax.scatter([stack[0]], [stack[1]], s=80, marker="D", zorder=5, color="tab:red", label="Stackelberg")
    ax.set_xlabel(f"{g.vars[0]} ({g.names[0]})")
    ax.set_ylabel(f"{g.vars[1]} ({g.names[1]})")
    ax.set_title(g.title)
    ax.grid(alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game")
    ap.add_argument("--grid", type=int, default=201,
                    help="discrete cross-check with N points per player (2 players; default 201, 0 = off)")
    ap.add_argument("--plot", help="PNG path for best-response plot (2 players)")
    ap.add_argument("--leader", help="also solve Stackelberg with this player moving first (2 players)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    with open(a.game) as f:
        spec = json.load(f)
    g = Game(spec)
    i_of = lambda c: g.names.index(c["player"])  # noqa: E731
    sym = symbolic(g)

    L = [f"# {g.title}", "", "## The game", ""]
    for i, n in enumerate(g.names):
        L.append(f"- **{n}** chooses {g.vars[i]} ∈ [{g.bounds[i][0]:g}, {g.bounds[i][1]:g}], payoff `{g.u[i]}`")
    L.append("- Parameters: " + ", ".join(f"{k}={v:g}" for k, v in sorted(g.pvals.items(), key=lambda kv: str(kv[0]))))
    L += ["", "## First-order conditions and best responses", ""]
    for i, n in enumerate(g.names):
        L.append(f"- {n}: ∂u/∂{g.vars[i]} = `{sym['focs'][i]}` = 0")
        if sym["br"][i]:
            for s in sym["br"][i]:
                L.append(f"  - BR: {g.vars[i]} = `{sp.simplify(s)}`")
    L.append("")

    # candidate equilibria
    eqs = []
    sym_sol = None
    for s, num, soc in sym.get("candidates", []):
        eqs.append(("symbolic FOC solution", num, soc, s))
    if sym["note"]:
        L.append(f"_Note: {sym['note']}_\n")
    xn, its, conv = g.numeric_equilibrium()
    if conv and not any(np.allclose(xn, e[1], atol=1e-5) for e in eqs):
        eqs.append((f"numeric best-response iteration ({its} its)", xn, None, None))
    geqs, gstep = ([], None)
    if a.grid and g.n == 2:
        geqs, gstep = grid_check(g, None, a.grid)
        # grid equilibria far from known candidates become candidates themselves
        tol = [2.01 * st for st in gstep]
        added = 0
        for e in geqs:
            if added >= 6:
                break
            if not any(abs(e[0] - c[1][0]) <= tol[0] and abs(e[1] - c[1][1]) <= tol[1] for c in eqs):
                eqs.append(("discrete grid equilibrium", [float(e[0]), float(e[1])], None, None))
                added += 1

    L += ["## Equilibria", ""]
    verified = []
    for src, x, soc, s in eqs:
        chk = g.verify(x)
        ok = all(c["ok"] for c in chk)
        head = "✅ VERIFIED equilibrium" if ok else "❌ NOT an equilibrium (profitable deviation exists)"
        L.append(f"### {head} - from {src}")
        L.append("- " + ", ".join(f"{g.vars[i]} = {x[i]:.6g}" for i in range(g.n)))
        L.append("- Payoffs: " + ", ".join(f"{c['player']} {c['payoff']:.6g}" for c in chk))
        if soc is not None:
            L.append("- Second-order: " + ", ".join(f"{g.names[i]} {soc[i]:.3g}{' ✓' if soc[i] < 0 else ' ⚠ not concave'}"
                                                   for i in range(g.n)))
        for c in chk:
            if c["ok"]:
                L.append(f"- {c['player']}: best unilateral deviation found in the whole range gains {c['gain']:.2e} → none pays.")
            else:
                L.append(f"- {c['player']}: deviating to {c['best_deviation']:.10g} gains {c['gain']:.6g}"
                         + (" (an ε-undercut/overshoot: payoff jumps → discontinuity)" if abs(c['best_deviation'] - x[i_of(c)]) < 1e-3 else "") + ".")
        L.append("")
        if ok:
            verified.append((x, s))
            if s is not None and sym_sol is None:
                sym_sol = s
    if not verified:
        L.append("**No verified pure-strategy equilibrium.** Likely causes: discontinuous payoffs (undercutting, ties, "
                 "capacity), non-concave payoffs, or cycling best responses. Run `--grid` and then `mixed_continuous.py`.\n")
        if not conv:
            L.append(f"_Best-response iteration did not converge after {its} iterations (cycling is a hint of no pure equilibrium)._ \n")
    if len(verified) > 1:
        L.append("⚠ **Multiple equilibria** - discuss selection.\n")

    if sym_sol is not None:
        L += ["## Closed form", ""]
        for v in g.vars:
            L.append(f"- {v}* = `{sp.simplify(sym_sol[v])}`")
        L.append("")

    if geqs is not None and a.grid and g.n == 2:
        step = gstep
        L += [f"## Discrete cross-check ({a.grid}×{a.grid} grid, step {step[0]:.3g} × {step[1]:.3g})", ""]
        if not geqs:
            L.append("❌ No pure equilibrium on the grid either → expect a **mixed** equilibrium: run `mixed_continuous.py`.")
        else:
            near_any = []
            far = []
            for e in geqs:
                if any(abs(e[0] - x[0]) <= 2.01 * step[0] and abs(e[1] - x[1]) <= 2.01 * step[1] for x, _ in verified):
                    near_any.append(e)
                else:
                    far.append(e)
            L.append(f"- Grid equilibria: {len(geqs)}; within 2 grid steps of a verified continuous equilibrium: {len(near_any)}.")
            if len(geqs) <= 10:
                L.append("- Grid points: " + ", ".join(f"({e[0]:.4g}, {e[1]:.4g})" for e in geqs)
                         + (" - neighbours of the continuous solution can be discretization artifacts, or genuine "
                            "discrete equilibria (e.g. price = cost + 1 cent): judge which." if len(geqs) > 1 else ""))
            if verified and near_any:
                L.append("- ✅ The discrete game reproduces the continuous solution.")
            if far:
                pts = ", ".join(f"({e[0]:.4g}, {e[1]:.4g})" for e in far[:8])
                L.append(f"- ⚠ Equilibria that exist **only in the discrete game**: {pts}{' ...' if len(far) > 8 else ''}. "
                         "Typical with discrete prices (Bertrand: cost and cost + 1 cent). Say which version is relevant.")
        L.append("")

    smooth = not any(e.has(sp.Piecewise, sp.Max, sp.Min, sp.Abs, sp.Heaviside, sp.sign) for e in g.u)
    if verified and not smooth:
        L.append("_Payoffs are non-smooth (Piecewise/Max/Min/Abs): best-response slopes and derivative-based "
                 "comparative statics are not reported. Re-run with changed parameters instead._\n")
    if verified and smooth:
        x_eq = verified[0][0]
        L += ["## Strategic interaction (slope of best responses at equilibrium)", ""]
        for i_name, j_name, sl in br_slopes(g, x_eq):
            kind = "**complements** (if the rival raises, I raise)" if sl > 1e-12 else (
                "**substitutes** (if the rival raises, I lower)" if sl < -1e-12 else "independent")
            L.append(f"- {i_name} w.r.t. {j_name}: slope {sl:.3g} → strategic {kind}")
        L.append("")
        L += ["## Comparative statics (how the equilibrium moves)", ""]
        for name, derivs in comparative_statics(g, sym_sol, x_eq):
            parts = []
            for k, (d, expr) in enumerate(derivs):
                parts.append(f"∂{g.vars[k]}*/∂{name} = {d:.4g}" + (f" (`{expr}`)" if expr != "numeric" else ""))
            L.append(f"- {name}: " + "; ".join(parts))
        L.append("")

    if verified:
        x_eq = verified[0][0]
        stack = None
        if a.leader and g.n == 2:
            sx, sv = stackelberg(g, a.leader)
            stack = sx
            nash_v = [g.payoff(i, x_eq) for i in range(2)]
            L += [f"## Stackelberg - {a.leader} moves first", ""]
            L.append("- " + ", ".join(f"{g.vars[i]} = {sx[i]:.6g}" for i in range(2)))
            for i in range(2):
                L.append(f"- {g.names[i]}: {sv[i]:.6g} (vs {nash_v[i]:.6g} simultaneous; Δ {sv[i]-nash_v[i]:+.4g})")
            L.append("- The leader's Δ is the **value of commitment / moving first**.")
            L.append("")

        if a.plot and g.n == 2:
            plot(g, x_eq, a.plot, stack)
            L.append(f"Plot saved: {a.plot}")

    if a.json:
        print(json.dumps({"title": g.title, "equilibria": [x for x, _ in verified],
                          "payoffs": [[g.payoff(i, x) for i in range(g.n)] for x, _ in verified]}, indent=2))
    else:
        print("\n".join(L))


if __name__ == "__main__":
    main()
