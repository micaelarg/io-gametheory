# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "scipy>=1.11", "matplotlib>=3.8"]
# ///
"""Evolutionary game theory and population genetics.

SUBCOMMANDS
  ess        Symmetric game (payoff matrix of the row strategy): all symmetric Nash equilibria and which are
             EVOLUTIONARILY STABLE (Maynard Smith; Haigh's condition for mixed ones).
               --matrix "0,3;1,2" --labels Hawk,Dove     or   --hawk-dove V,C   --pd T,R,P,S   --rps win,lose
  dynamics   Replicator dynamics (or --dynamics br|logit, --mutation μ): rest points with Jacobian stability,
             basins of attraction (2-3 strategies), simulated trajectories, phase-line / simplex plot.
  moran      Finite population N, selection intensity w: fixation probability of one mutant of each strategy
             (frequency-dependent Moran process, Nowak et al. 2004) vs neutral 1/N; the one-third rule;
             risk-dominance in finite populations.
  genetics   One locus, two alleles: selection with dominance (--fitness wAA,wAa,waa), mutation, drift
             (Wright-Fisher, --N); deterministic equilibrium and stability (heterozygote advantage,
             underdominance), Kimura fixation probability, simulated fixation times.
             --hamilton r,B,C  checks Hamilton's rule rB > C (kin selection).
  spatial    Spatial game on an L×L lattice (Nowak-May 1992): each cell plays its neighbours and imitates the
             best; shows cooperation surviving in clusters where the well-mixed population would defect.

Payoffs: entry (i,j) = payoff to strategy i against strategy j. Fitness = baseline + payoff.
"""
from __future__ import annotations

import argparse
import itertools

import numpy as np
from scipy.integrate import solve_ivp


def fmt(x, d=4):
    if x is None or not np.isfinite(x):
        return "-"
    return f"{x:.{d}g}"


def parse_game(a):
    if a.hawk_dove:
        V, C = map(float, a.hawk_dove.split(","))
        return np.array([[(V - C) / 2, V], [0, V / 2]]), ["Hawk", "Dove"], f"Hawk-Dove V={V:g}, C={C:g}"
    if a.pd:
        T, R, P, S = map(float, a.pd.split(","))
        return np.array([[R, S], [T, P]]), ["Cooperate", "Defect"], f"Prisoner's dilemma T={T:g} R={R:g} P={P:g} S={S:g}"
    if a.rps:
        w, l = map(float, a.rps.split(","))
        return np.array([[0, -l, w], [w, 0, -l], [-l, w, 0]]), ["Rock", "Paper", "Scissors"], f"Rock-paper-scissors win={w:g} lose={l:g}"
    A = np.array([[float(x) for x in r.split(",")] for r in a.matrix.split(";")])
    labels = a.labels.split(",") if a.labels else [f"s{i+1}" for i in range(len(A))]
    return A, labels, " vs ".join(labels)


# ----------------------------------------------------------------------------- ESS
def symmetric_equilibria(A, tol=1e-9):
    n = len(A)
    eqs = []
    for k in range(1, n + 1):
        for S in itertools.combinations(range(n), k):
            S = list(S)
            # indifference on support: (A x)_i = v for i in S, sum x = 1
            M = np.zeros((k + 1, k + 1))
            M[:k, :k] = A[np.ix_(S, S)]
            M[:k, k] = -1
            M[k, :k] = 1
            rhs = np.zeros(k + 1); rhs[k] = 1
            try:
                sol = np.linalg.lstsq(M, rhs, rcond=None)[0]
            except np.linalg.LinAlgError:
                continue
            if np.linalg.norm(M @ sol - rhs) > 1e-8:
                continue
            x = np.zeros(n); x[S] = sol[:k]
            if (x < -tol).any() or (x[S] <= tol).any():
                continue
            v = sol[k]
            if (A @ x > v + 1e-8).any():
                continue
            if not any(np.allclose(x, e, atol=1e-7) for e in eqs):
                eqs.append(x)
    return eqs


def is_ess(A, x, tol=1e-9):
    """Haigh (1975): x Nash; B = pure best replies to x; A negative definite on {z: Σz=0, z_i=0 ∉ B} (z≠0)."""
    u = A @ x
    v = x @ u
    B = np.where(np.abs(u - v) < 1e-8)[0]
    if len(B) == 1:
        return True, "strict Nash equilibrium (unique best reply) → ESS"
    k = len(B)
    # basis of {z in R^B: Σz=0}
    Z = np.zeros((k, k - 1))
    for j in range(k - 1):
        Z[0, j] = 1; Z[j + 1, j] = -1
    Ab = A[np.ix_(B, B)]
    Q = Z.T @ ((Ab + Ab.T) / 2) @ Z
    ev = np.linalg.eigvalsh(Q)
    supp = np.where(x > tol)[0]
    if set(B) != set(supp):
        # alternative best replies outside support: Haigh condition still applies on B
        pass
    if (ev < -1e-10).all():
        if (x > tol).sum() == 1:
            return True, ("ESS by the second condition: alternative best replies tie against it but do worse "
                          "against themselves than it does against them")
        return True, f"mixed ESS: payoffs negative definite among best replies (eigenvalues {np.round(ev, 4).tolist()})"
    if (ev <= 1e-10).all():
        return False, "neutrally stable (not strictly ESS): invaders do no better, no worse - drift possible"
    return False, f"NOT ESS: some mutant mixture does better against itself (eigenvalues {np.round(ev, 4).tolist()})"


def cmd_ess(a):
    A, lab, name = parse_game(a)
    L = [f"# Evolutionary stability - {name}", "", "Payoff to row strategy against column strategy:", "",
         "| | " + " | ".join(lab) + " |", "|---|" + "---|" * len(lab)]
    for i, r in enumerate(A):
        L.append(f"| **{lab[i]}** | " + " | ".join(fmt(v) for v in r) + " |")
    L += ["", "## Symmetric Nash equilibria and ESS", ""]
    for x in symmetric_equilibria(A):
        ok, why = is_ess(A, x)
        mix = ", ".join(f"{lab[i]} {x[i]:.3f}" for i in range(len(x)) if x[i] > 1e-9)
        L.append(f"- **{mix}** (payoff {x @ A @ x:.4g}): {'✅ ESS' if ok else '❌'} - {why}")
    L += ["", "ESS: a population playing it cannot be invaded by a small group of mutants playing anything else. "
          "Every ESS is a Nash equilibrium and an asymptotically stable rest point of the replicator dynamics; "
          "not every stable outcome is an ESS (e.g. Rock-Paper-Scissors cycles)."]
    print("\n".join(L))


# ----------------------------------------------------------------------------- dynamics
def field(A, kind, mu, beta):
    n = len(A)

    def f(t, x):
        x = np.clip(x, 0, None); x = x / x.sum()
        u = A @ x
        if kind == "replicator":
            dx = x * (u - x @ u)
        elif kind == "br":
            br = np.zeros(n); br[np.argmax(u)] = 1
            dx = br - x
        else:  # logit
            e = np.exp(beta * (u - u.max())); dx = e / e.sum() - x
        if mu > 0:
            dx = (1 - mu) * dx + mu * (1 / n - x)
        return dx
    return f


def rest_points(A, kind, mu, beta):
    f = field(A, kind, mu, beta)
    n = len(A)
    from scipy.optimize import fsolve
    pts = []
    starts = list(np.eye(n)) + [np.ones(n) / n]
    rng = np.random.default_rng(0)
    starts += list(rng.dirichlet(np.ones(n), 60))
    for s in starts:
        def g(y):
            x = np.append(y, 1 - y.sum())
            return f(0, x)[:-1]
        y, info, ier, _ = fsolve(g, s[:-1], full_output=True)
        x = np.append(y, 1 - y.sum())
        if ier == 1 and (x > -1e-9).all() and np.linalg.norm(f(0, x)) < 1e-9:
            x = np.clip(x, 0, None); x /= x.sum()
            if not any(np.allclose(x, p, atol=1e-6) for p in pts):
                pts.append(x)
    if kind == "replicator" and mu == 0:
        for x in symmetric_equilibria(A):
            if not any(np.allclose(x, p, atol=1e-6) for p in pts):
                pts.append(x)
        for i in range(n):
            e = np.eye(n)[i]
            if not any(np.allclose(e, p, atol=1e-6) for p in pts):
                pts.append(e)
    return pts


def classify(A, x, kind, mu, beta):
    f = field(A, kind, mu, beta)
    n = len(A)
    h = 1e-6
    J = np.zeros((n - 1, n - 1))
    for j in range(n - 1):
        d = np.zeros(n); d[j] = h; d[-1] = -h
        J[:, j] = (f(0, x + d)[:-1] - f(0, x - d)[:-1]) / (2 * h)
    ev = np.linalg.eigvals(J)
    # restrict to feasible directions on the boundary: approximate via simulation from nearby interior points
    rng = np.random.default_rng(1)
    back = 0
    for _ in range(12):
        y = np.clip(x + 0.01 * rng.normal(size=n), 1e-4, None); y /= y.sum()
        sol = solve_ivp(f, (0, 200), y, rtol=1e-8)
        z = sol.y[:, -1]; z = np.clip(z, 0, None); z /= z.sum()
        back += np.linalg.norm(z - x) < 0.02
    re = ev.real
    if back >= 10:
        kind_s = "stable (attracts nearby populations)"
    elif back == 0:
        kind_s = "unstable"
    else:
        kind_s = "saddle / stable only from some directions"
    if np.all(np.abs(re) < 1e-7) and np.any(np.abs(ev.imag) > 1e-7):
        kind_s += " - center: populations cycle around it"
    return ev, kind_s


def cmd_dynamics(a):
    A, lab, name = parse_game(a)
    n = len(A)
    f = field(A, a.dynamics, a.mutation, a.beta)
    L = [f"# {a.dynamics.capitalize()} dynamics - {name}" + (f", mutation μ={a.mutation:g}" if a.mutation else ""), ""]
    L += ["| rest point | eigenvalues (Jacobian) | stability |", "|---|---|---|"]
    pts = rest_points(A, a.dynamics, a.mutation, a.beta)
    kinds = []
    for x in sorted(pts, key=lambda p: tuple(-p)):
        ev, k = classify(A, x, a.dynamics, a.mutation, a.beta)
        kinds.append((x, k))
        L.append(f"| {', '.join(f'{lab[i]} {x[i]:.3f}' for i in range(n))} | {', '.join(f'{e.real:.3g}' + (f'{e.imag:+.3g}i' if abs(e.imag) > 1e-9 else '') for e in ev)} | {k} |")
    # basins by sampling
    rng = np.random.default_rng(2)
    ends = []
    for x0 in rng.dirichlet(np.ones(n), 300):
        sol = solve_ivp(f, (0, a.T), x0, rtol=1e-7)
        z = sol.y[:, -1]; z = np.clip(z, 0, None); z /= z.sum()
        ends.append(np.round(z, 2))
    ends = np.array(ends)
    uniq, cnt = np.unique(ends, axis=0, return_counts=True)
    L += ["", f"## Where populations end up (300 random starting mixes, t = {a.T:g})", ""]
    saddle_ends = 0
    for u_, c in sorted(zip(uniq, cnt), key=lambda t: -t[1])[:8]:
        near = [k for x, k in kinds if np.allclose(x, u_, atol=0.03)]
        tag = ""
        if near and not near[0].startswith("stable"):
            tag = " (snapshot near a non-attracting rest point - the population is passing by)"
            saddle_ends += c
        L.append(f"- {', '.join(f'{lab[i]} {u_[i]:.2f}' for i in range(n))}: {100*c/300:.0f}% of starts{tag}")
    if saddle_ends > 0.8 * 300:
        L.append("- ⚠ No attractor: trajectories approach a **heteroclinic cycle** along the boundary - each strategy "
                 "booms and collapses in turn, spending ever longer near each pure strategy (check the plot).")
    elif len(uniq) > 8:
        L.append("- Endpoints are spread out → no single attractor: likely **cycles** (check the plot).")
    if a.plot:
        plot_dynamics(A, lab, f, pts, a)
        L.append(f"\nPlot saved: {a.plot}")
    print("\n".join(L))


def plot_dynamics(A, lab, f, pts, a):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(A)
    if n == 2:
        xs = np.linspace(0, 1, 401)
        dx = np.array([f(0, np.array([x, 1 - x]))[0] for x in xs])
        fig, ax = plt.subplots(figsize=(6.5, 3.4))
        ax.axhline(0, color="black", lw=0.8)
        ax.plot(xs, dx, lw=2)
        for p in pts:
            ax.scatter([p[0]], [0], s=70, zorder=5, color="black")
        for x in np.linspace(0.05, 0.95, 10):
            d = f(0, np.array([x, 1 - x]))[0]
            if abs(d) > 1e-9:
                ax.annotate("", xy=(x + 0.04 * np.sign(d), 0), xytext=(x, 0), arrowprops=dict(arrowstyle="->", color="tab:red"))
        ax.set_xlabel(f"share of {lab[0]}"); ax.set_ylabel(f"d(share)/dt")
        ax.set_title("Phase line (arrows = direction; dots = rest points)", fontsize=10)
        ax.grid(alpha=0.3)
    else:
        def to2d(x):
            return np.array([x[1] + x[2] / 2, x[2] * np.sqrt(3) / 2])
        fig, ax = plt.subplots(figsize=(6.2, 5.6))
        tri = np.array([to2d(e) for e in np.eye(3)] + [to2d(np.eye(3)[0])])
        ax.plot(tri[:, 0], tri[:, 1], color="black", lw=1)
        for i, e in enumerate(np.eye(3)):
            p = to2d(e); ax.annotate(lab[i], p, textcoords="offset points", xytext=(0, -14 if i < 2 else 6), ha="center")
        rng = np.random.default_rng(5)
        for x0 in rng.dirichlet(np.ones(3), 28):
            sol = solve_ivp(f, (0, min(a.T, 60)), x0, rtol=1e-7, max_step=0.1)
            P = np.array([to2d(sol.y[:, k] / sol.y[:, k].sum()) for k in range(sol.y.shape[1])])
            ax.plot(P[:, 0], P[:, 1], lw=0.8, alpha=0.7)
            ax.annotate("", xy=P[min(8, len(P) - 1)], xytext=P[0], arrowprops=dict(arrowstyle="->", lw=0.8))
        for p in pts:
            q = to2d(p); ax.scatter([q[0]], [q[1]], s=60, color="black", zorder=5)
        ax.set_aspect("equal"); ax.axis("off")
        ax.set_title("Strategy-mix trajectories (dots = rest points)", fontsize=10)
    fig.tight_layout(); fig.savefig(a.plot, dpi=150)


# ----------------------------------------------------------------------------- Moran
def fixation(A, i, j, N, w):
    """Probability that one i-mutant takes over a population of j (frequency-dependent Moran)."""
    a_, b_, c_, d_ = A[i, i], A[i, j], A[j, i], A[j, j]
    s = 0.0
    prod = 1.0
    for k in range(1, N):  # k mutants
        fi = 1 - w + w * (a_ * (k - 1) + b_ * (N - k)) / (N - 1)
        fj = 1 - w + w * (c_ * k + d_ * (N - k - 1)) / (N - 1)
        prod *= fj / fi
        s += prod
    return 1 / (1 + s)


def cmd_moran(a):
    A, lab, name = parse_game(a)
    n = len(A)
    L = [f"# Finite population (Moran process) - {name}, N={a.N}, selection intensity w={a.w:g}", "",
         f"Neutral benchmark: a single mutant fixes with probability 1/N = {1/a.N:.4f}.", "",
         "| mutant → resident | fixation probability | vs neutral |", "|---|---|---|"]
    for i, j in itertools.permutations(range(n), 2):
        r = fixation(A, i, j, a.N, a.w)
        L.append(f"| one {lab[i]} in a population of {lab[j]} | {r:.4g} | {'favoured by selection' if r > 1/a.N else 'opposed by selection'} ({r*a.N:.2f}× neutral) |")
    if n == 2:
        a_, b_, c_, d_ = A[0, 0], A[0, 1], A[1, 0], A[1, 1]
        den = a_ - b_ - c_ + d_
        if abs(den) > 1e-12 and a_ > c_ and d_ > b_:
            xs = (d_ - b_) / den
            if abs(xs - 0.5) < 1e-9:
                rd = "Neither convention is risk-dominant (x* = 1/2 exactly): the long-run selection depends on N and w."
            else:
                rd = (f"{lab[0] if xs < 0.5 else lab[1]} is risk-dominant (x* {'<' if xs < 0.5 else '>'} 1/2): it is the one "
                      "selected in the long run in the limit of rare mutations and large populations (Kandori-Mailath-Rob, "
                      "Young). For THIS N and w use the finite-population share below.")
            L += ["", f"- Coordination game: unstable interior point at {lab[0]} share x* = {xs:.3f}.",
                  f"- **One-third rule** (weak selection, large N): {lab[0]} mutants are favoured iff x* < 1/3 → "
                  f"{'yes' if xs < 1/3 else 'no'}.", f"- {rd}"]
        r1, r2 = fixation(A, 0, 1, a.N, a.w), fixation(A, 1, 0, a.N, a.w)
        L.append(f"- Long-run share of time near all-{lab[0]} with rare mutations at N={a.N}, w={a.w:g}: {r1/(r1+r2):.2f}")
    L += ["", "In small populations drift can fix strategies that are not ESS and remove ones that are; "
          "as N·w grows, selection dominates and finite-population results converge to the replicator/ESS ones."]
    print("\n".join(L))


# ----------------------------------------------------------------------------- genetics
def cmd_genetics(a):
    L = []
    if a.hamilton:
        r, B, C = map(float, a.hamilton.split(","))
        ok = r * B > C
        L += ["# Hamilton's rule (kin selection)", "", f"- relatedness r = {r:g}, benefit to recipient B = {B:g}, cost to actor C = {C:g}",
              f"- rB = {r*B:.4g} {'>' if ok else '≤'} C = {C:g} → altruism **{'spreads' if ok else 'does not spread'}**.",
              f"- Break-even benefit: B > C/r = {C/r if r else float('inf'):.4g}. (r: parent-child or full siblings 0.5, "
              "half siblings or grandparent 0.25, first cousins 0.125.)", ""]
        if not a.fitness:
            print("\n".join(L)); return
    wAA, wAa, waa = map(float, a.fitness.split(","))
    mu = a.mutation
    N = a.N

    def step(p):
        q = 1 - p
        wbar = p * p * wAA + 2 * p * q * wAa + q * q * waa
        pn = (p * p * wAA + p * q * wAa) / wbar
        return pn * (1 - mu) + (1 - pn) * mu
    L += [f"# One locus, two alleles: fitness AA={wAA:g}, Aa={wAa:g}, aa={waa:g}" + (f", mutation μ={mu:g}" if mu else ""), ""]
    h_num = wAa - waa; den = 2 * wAa - wAA - waa
    if wAa > max(wAA, waa):
        ps = h_num / den
        L.append(f"- **Heterozygote advantage (overdominance)**: stable polymorphism at p(A) = {ps:.4f} "
                 "(e.g. sickle-cell allele where malaria is common). Both alleles are maintained.")
    elif wAa < min(wAA, waa):
        ps = h_num / den
        L.append(f"- **Underdominance**: unstable point p(A) = {ps:.4f}; the allele above it fixes, below it is lost "
                 "(founder effects / bistability, like a coordination game).")
    else:
        fav = "A" if wAA >= waa else "a"
        L.append(f"- Directional selection: allele **{fav}** goes to fixation (deterministically).")
    if a.p0 is None:
        a.p0 = 1 / (2 * N) if N else 0.01
    p = a.p0
    traj = [p]
    for _ in range(a.generations):
        p = step(p); traj.append(p)
    L.append(f"- Deterministic: p(A) from {a.p0:g} → {traj[-1]:.4f} after {a.generations} generations "
             f"(half-way at generation {next((g for g, x in enumerate(traj) if abs(x - traj[-1]) < abs(traj[0] - traj[-1]) / 2), '-')}).")
    directional = not (wAa > max(wAA, waa) or wAa < min(wAA, waa))
    s = (wAa - waa) / waa if waa else 0   # Kimura: heterozygote advantage under additive (genic) selection
    additive = abs((wAA - wAa) - (wAa - waa)) < 0.05 * max(abs(wAA - waa), 1e-12)
    if N:
        Ne = N
        if directional and abs(s) > 1e-12:
            p1 = 1 / (2 * Ne)
            u = (1 - np.exp(-4 * Ne * s * p1)) / (1 - np.exp(-4 * Ne * s))
            L.append(f"- **Kimura** fixation probability of a single new A allele (s = heterozygote advantage {s:.3g}, N = {Ne}"
                     + ("" if additive else "; ⚠ fitnesses not additive - approximation") + "): "
                     f"{u:.4g} vs neutral {p1:.4g} ({u/p1:.1f}×). Selection beats drift when |4Ns| ≫ 1 (here {4*Ne*s:.1f}).")
        rng = np.random.default_rng(0)
        fixed, lost, times = 0, 0, []
        for _ in range(a.reps):
            x = a.p0
            for g in range(1, 100 * N):
                x = rng.binomial(2 * N, step(x)) / (2 * N)
                if x in (0.0, 1.0):
                    times.append(g)
                    if x == 1.0:
                        fixed += 1
                    else:
                        lost += 1
                    break
        if not directional and wAa > max(wAA, waa):
            # establishment = reaching half the equilibrium frequency
            est = 0
            rng2 = np.random.default_rng(1)
            for _ in range(a.reps):
                x = a.p0
                for g in range(20 * N):
                    x = rng2.binomial(2 * N, step(x)) / (2 * N)
                    if x == 0 or x >= ps / 2:
                        est += x >= ps / 2
                        break
            L.append(f"- **Establishment probability** (reaches half the equilibrium frequency {ps/2:.3f} before being lost; "
                     f"{a.reps} runs from p0 = {a.p0:.4g}): {100*est/a.reps:.1f}% - once established, balancing selection keeps it.")
        L.append(f"- Wright-Fisher simulation ({a.reps} runs, N = {N}, p0 = {a.p0:g}): A fixed {100*fixed/a.reps:.0f}%, lost "
                 f"{100*lost/a.reps:.0f}%, still polymorphic after {100*N} generations {100*(a.reps-fixed-lost)/a.reps:.0f}%"
                 + (" (balancing selection keeps both alleles)" if not directional and wAa > max(wAA, waa)
                    and (a.reps - fixed - lost) > a.reps / 2 else "")
                 + "; median time to absorption "
                 f"{int(np.median(times)) if times else '-'} generations.")
    L += ["", "Link to games: genotype fitness = payoff; frequency-dependent fitness turns this into an evolutionary game (`dynamics`, `moran`)."]
    print("\n".join(L))


# ----------------------------------------------------------------------------- spatial
def cmd_spatial(a):
    b = a.b
    Lsz = a.L
    rng = np.random.default_rng(a.seed)
    C = rng.random((Lsz, Lsz)) < a.coop0
    shifts = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]  # Moore + self (Nowak-May)
    hist = [C.mean()]
    for _ in range(a.steps):
        nc = sum(np.roll(np.roll(C, dx, 0), dy, 1) for dx, dy in shifts).astype(float)
        pay = np.where(C, nc * 1.0, nc * b)  # C gets 1 per C neighbour; D gets b per C neighbour
        best = pay.copy(); strat = C.copy()
        for dx, dy in shifts:
            pn = np.roll(np.roll(pay, dx, 0), dy, 1); sn = np.roll(np.roll(C, dx, 0), dy, 1)
            upd = pn > best
            best = np.where(upd, pn, best); strat = np.where(upd, sn, strat)
        C = strat
        hist.append(C.mean())
    out = [f"# Spatial prisoner's dilemma (Nowak-May 1992): {Lsz}×{Lsz} lattice, temptation b={b:g}", "",
           f"- Cooperators: start {100*hist[0]:.0f}% → after {a.steps} rounds {100*hist[-1]:.1f}% "
           f"(mean of last 20 rounds {100*np.mean(hist[-20:]):.1f}%)",
           "- Well-mixed population: cooperation goes extinct for any b > 1.",
           "- On a lattice, cooperators form clusters that protect each other: **population structure lets cooperation survive** "
           "for intermediate b (roughly 1 < b < 2 in this model), with ever-changing patterns."]
    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(9, 4.2))
        ax[0].imshow(C, cmap="Blues", interpolation="nearest", vmin=0, vmax=1); ax[0].set_title("final lattice (dark = cooperators)"); ax[0].axis("off")
        ax[1].plot(np.array(hist) * 100); ax[1].set_xlabel("round"); ax[1].set_ylabel("% cooperators"); ax[1].grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(a.plot, dpi=150)
        out.append(f"\nPlot saved: {a.plot}")
    print("\n".join(out))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["ess", "dynamics", "moran", "genetics", "spatial"])
    ap.add_argument("--matrix", default="0,3;1,2"); ap.add_argument("--labels")
    ap.add_argument("--hawk-dove"); ap.add_argument("--pd"); ap.add_argument("--rps")
    ap.add_argument("--dynamics", choices=["replicator", "br", "logit"], default="replicator")
    ap.add_argument("--mutation", type=float, default=0.0, help="dynamics: mutation rate μ")
    ap.add_argument("--beta", type=float, default=5.0, help="dynamics logit: choice precision")
    ap.add_argument("--T", type=float, default=200.0)
    ap.add_argument("--N", type=int, default=100, help="population size (moran, genetics; default 100)")
    ap.add_argument("--w", type=float, default=0.1, help="moran: selection intensity 0-1 (default 0.1)")
    ap.add_argument("--fitness", help="genetics: wAA,wAa,waa")
    ap.add_argument("--p0", type=float, default=None, help="genetics: initial allele frequency (default 1/(2N): one new mutant)")
    ap.add_argument("--generations", type=int, default=500, help="genetics: deterministic generations")
    ap.add_argument("--reps", type=int, default=500, help="genetics: Wright-Fisher replicates")
    ap.add_argument("--hamilton")
    ap.add_argument("--b", type=float, default=1.85, help="spatial: temptation payoff of defecting against a cooperator (C-C pays 1)")
    ap.add_argument("--L", type=int, default=99, help="spatial: lattice side")
    ap.add_argument("--steps", type=int, default=200, help="spatial: rounds")
    ap.add_argument("--coop0", type=float, default=0.9, help="spatial: initial share of cooperators")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--plot")
    a = ap.parse_args()
    {"ess": cmd_ess, "dynamics": cmd_dynamics, "moran": cmd_moran, "genetics": cmd_genetics, "spatial": cmd_spatial}[a.cmd](a)


if __name__ == "__main__":
    main()
