# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "scipy>=1.11", "pandas>=2.1", "matplotlib>=3.8"]
# ///
"""Bargaining and negotiation engine.

SUBCOMMANDS
  nash        Axiomatic solutions on any frontier: (asymmetric) Nash, Kalai-Smorodinsky, egalitarian,
              utilitarian. Sensitivity: what +1 of outside option (BATNA) or bargaining power buys you.
                --frontier "100 - u1" --u1-range 0,100 --d 20,10 [--alpha 0.5]
                --pie 100 --rho1 1 --rho2 0.5 --d 0,0          (money split with risk aversion u=x^rho)
  rubinstein  Alternating offers (infinite or --rounds T), discounting (--delta1/--delta2 or --r1/--r2
              --period), risk of breakdown (--breakdown p with inside options --d), OUTSIDE OPTIONS
              (--outside1/--outside2, outside-option principle), who proposes first, limit as offers
              become frequent (→ asymmetric Nash with power r2/(r1+r2)).
  offer       One-sided uncertainty: the other side's reservation price ~ distribution. Optimal
              take-it-or-leave-it offer, acceptance probability, expected gain, probability the ZOPA exists.
                --role seller --reservation 100 --other "normal:130,20"
  double      Two-sided private information (Chatterjee-Samuelson k=1/2 double auction, uniform values on a
              common support): equilibrium asks/bids, which deals fail, efficiency vs first best
              (Myerson-Satterthwaite: no mechanism is fully efficient).
  issues      Multi-issue negotiation from a JSON scoring table (format below): Pareto-efficient packages, Nash package,
              versus "split every issue down the middle" - the gains from logrolling.
  shapley     Coalitional bargaining: Shapley value, core (non-empty?), least core / nucleolus-style
              allocation, from a JSON characteristic function.

issues JSON:
  {"parties": ["Union", "Firm"],
   "issues": [{"name": "wage", "options": ["3%", "5%", "7%"],
               "scores": {"Union": [0, 30, 45], "Firm": [40, 20, 0]}}, ...],
   "batna": {"Union": 30, "Firm": 25}}
  Scores are each party's utility for each option (additive across issues, same scale within a party).

offer extras: --truncate-below X (the other side's reservation is known to be ≥ X, e.g. they already offered X);
  --if-rejected V (what you get if the offer is rejected, e.g. an existing offer that stays on the table;
  default = your reservation price).

Distributions (offer): uniform:a,b | normal:mu,sd | lognormal:mu,sigma | beta:a,b,lo,hi | empirical:file.csv[:col]
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def fmt(x):
    if x is None or not np.isfinite(x):
        return "-"
    if abs(x) < 1e-9:
        return "0"
    return f"{x:,.0f}" if abs(x) >= 1000 else f"{x:.4g}"


# ----------------------------------------------------------------------------- nash family
def frontier_from_args(a):
    if a.pie is not None:
        P = a.pie
        x = np.linspace(0, P, 20001)
        u1 = (x / P) ** a.rho1 * P
        u2 = ((P - x) / P) ** a.rho2 * P
        lab = f"split of {fmt(P)}; u1 = x^{a.rho1:g}, u2 = (pie−x)^{a.rho2:g} (scaled)"
        return u1, u2, x, lab
    lo, hi = (float(v) for v in a.u1_range.split(","))
    u1 = np.linspace(lo, hi, 20001)
    u2 = eval(a.frontier, {"np": np, "u1": u1, "sqrt": np.sqrt, "log": np.log, "exp": np.exp})  # local tool input
    u2 = np.asarray(u2, float) * np.ones_like(u1)
    return u1, u2, None, f"u2 = {a.frontier}, u1 ∈ [{lo:g}, {hi:g}]"


def nash_solutions(u1, u2, d, alpha):
    ok = (u1 >= d[0]) & (u2 >= d[1])
    if not ok.any():
        return None
    idx = np.where(ok)[0]
    g1, g2 = u1[idx] - d[0], u2[idx] - d[1]
    with np.errstate(divide="ignore"):
        nash = idx[np.argmax(alpha * np.log(np.maximum(g1, 1e-300)) + (1 - alpha) * np.log(np.maximum(g2, 1e-300)))]
    ideal = (g1.max(), g2.max())
    ks = idx[np.argmin(np.abs(g1 / ideal[0] - g2 / ideal[1]))]
    ega = idx[np.argmin(np.abs(g1 - g2))]
    tot = u1[idx] + u2[idx]
    uti = idx[np.argmax(tot)] if np.ptp(tot) > 1e-9 * (1 + np.abs(tot).max()) else None
    out = {"Nash" + (f" (α={alpha:g})" if alpha != 0.5 else ""): nash, "Kalai-Smorodinsky": ks,
           "Egalitarian (equal gains)": ega}
    if uti is not None:
        out["Utilitarian (max total)"] = uti
    return out


def cmd_nash(a):
    u1, u2, x, lab = frontier_from_args(a)
    d = [float(v) for v in a.d.split(",")]
    sols = nash_solutions(u1, u2, d, a.alpha)
    L = [f"# Bargaining solutions - {lab}", "", f"- Disagreement point (BATNAs): d = ({fmt(d[0])}, {fmt(d[1])})"]
    if sols is None:
        L.append("- ❌ **No ZOPA**: no point on the frontier gives both parties at least their BATNA. Walk away "
                 "(or change the frontier: new issues, side payments).")
        print("\n".join(L)); return
    L += ["", "| solution | u1 | u2 | gain 1 | gain 2 |" + (" split x |" if x is not None else ""),
          "|---|---|---|---|---|" + ("---|" if x is not None else "")]
    for k, i in sols.items():
        L.append(f"| {k} | {fmt(u1[i])} | {fmt(u2[i])} | {fmt(u1[i]-d[0])} | {fmt(u2[i]-d[1])} |"
                 + (f" {fmt(x[i])} |" if x is not None else ""))
    nk = next(iter(sols))
    i0 = sols[nk]
    # sensitivity
    step = 0.01 * (u1.max() - u1.min() + 1e-12)
    s1 = nash_solutions(u1, u2, [d[0] + step, d[1]], a.alpha)
    s2 = nash_solutions(u1, u2, d, min(a.alpha + 0.05, 0.999))
    L += ["", "## What moves the Nash outcome", ""]
    if s1:
        dU = u1[next(iter(s1.values()))] - u1[i0]
        L.append(f"- Raising player 1's BATNA by {fmt(step)} raises its payoff by {fmt(dU)} "
                 f"({dU/step:.2f} per unit). **Improving your outside option is the most reliable lever.**")
    if s2:
        dU = u1[next(iter(s2.values()))] - u1[i0]
        L.append(f"- Bargaining power α {a.alpha:g} → {min(a.alpha + 0.05, 0.999):g} (patience, deadlines, commitment): "
                 f"player 1 gains {fmt(dU)}.")
    if "Utilitarian (max total)" not in sols:
        L.append("- Total utility is the same everywhere on this frontier (pure transfer): the utilitarian criterion "
                 "doesn't pick a point.")
    if a.pie is not None and a.rho1 != a.rho2:
        L.append("- Risk aversion is costly in bargaining: the more risk-averse side concedes more "
                 "(it fears breakdown more).")
    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.plot(u1, u2, lw=2, color="black", label="frontier")
        ax.scatter([d[0]], [d[1]], marker="x", s=80, color="red", label="disagreement (BATNAs)")
        ax.axvline(d[0], color="red", lw=0.6, ls=":"); ax.axhline(d[1], color="red", lw=0.6, ls=":")
        for k, i in sols.items():
            ax.scatter([u1[i]], [u2[i]], s=60, label=k, zorder=5)
        ax.set_xlabel("player 1 utility"); ax.set_ylabel("player 2 utility"); ax.grid(alpha=0.3); ax.legend(fontsize=8)
        ax.set_title("Bargaining set and solutions")
        fig.tight_layout(); fig.savefig(a.plot, dpi=150)
        L.append(f"\nPlot saved: {a.plot}")
    print("\n".join(L))


# ----------------------------------------------------------------------------- rubinstein
def cmd_rubinstein(a):
    P = a.pie
    if a.r1 is not None:
        d1, d2 = np.exp(-a.r1 * a.period), np.exp(-a.r2 * a.period)
    else:
        d1, d2 = a.delta1, a.delta2
    p = a.breakdown
    b = [float(v) for v in a.d.split(",")]
    o = [a.outside1 or 0.0, a.outside2 or 0.0]
    first = a.first
    L = [f"# Alternating-offers bargaining over {fmt(P)}", ""]
    L.append(f"- Discount factors per round δ1={d1:.4g}, δ2={d2:.4g}; breakdown risk per rejection p={p:g} "
             f"(inside options {fmt(b[0])}, {fmt(b[1])}); outside options {fmt(o[0])}, {fmt(o[1])}; player {first} proposes first.")

    if a.rounds:
        # backward induction, finite horizon; proposer in round t alternates starting with `first`
        T = a.rounds
        cont = [b[0], b[1]]  # after the last rejection: disagreement
        hist = []
        for t in range(T, 0, -1):
            prop = first if (t % 2 == 1) else (3 - first)
            j = 2 - prop  # index of responder (0 or 1)
            i = prop - 1
            delta = [d1, d2]
            accept_value = max(o[j], delta[j] * cont[j])
            give = accept_value
            take = P - give
            cont = [0, 0]
            cont[i], cont[j] = take, give
            hist.append((t, prop, take, give))
        hist = hist[::-1]
        L += ["", f"## Finite horizon: {T} rounds (backward induction)", "", "| round | proposer | proposer keeps | offers |", "|---|---|---|---|"]
        for t, prop, tk, gv in hist:
            L.append(f"| {t} | {prop} | {fmt(tk)} | {fmt(gv)} |")
        L.append(f"\n- Agreement in round 1: player {first} keeps {fmt(hist[0][2])}, player {3-first} gets {fmt(hist[0][3])}.")
        L.append("- With few rounds the **last proposer** has the power (ultimatum at the deadline); with many rounds the "
                 "result approaches the infinite-horizon split below. Deadlines are bargaining power.")

    # infinite horizon stationary SPE with breakdown + outside options (fixed point)
    A, B = P / 2, P / 2  # A = share of player 1 when 1 proposes; B = share of 2 when 2 proposes
    for _ in range(10000):
        resp2 = max(o[1], d2 * ((1 - p) * B + p * b[1]))
        resp1 = max(o[0], d1 * ((1 - p) * A + p * b[0]))
        A_new, B_new = P - resp2, P - resp1
        if abs(A_new - A) + abs(B_new - B) < 1e-13:
            break
        A, B = A_new, B_new
    feasible = A >= max(o[0], 0) - 1e-12 and B >= max(o[1], 0) - 1e-12
    L += ["", "## Infinite horizon (unique subgame-perfect equilibrium)", ""]
    if not feasible:
        L.append("- ❌ Outside options sum to more than the pie: no deal - at least one side walks away.")
    else:
        if first == 1:
            L.append(f"- Player 1 proposes: keeps **{fmt(A)}**, offers player 2 **{fmt(P - A)}** - accepted immediately.")
        else:
            L.append(f"- Player 2 proposes: keeps **{fmt(B)}**, offers player 1 **{fmt(P - B)}** - accepted immediately.")
        base = (1 - d2) / (1 - d1 * d2) * P if p == 0 else None
        if base is not None and o == [0, 0]:
            L.append(f"- Closed form (Rubinstein 1982): proposer 1 share = (1−δ2)/(1−δ1δ2) = {fmt(base)} ✓")
        fm = (A - (P - B)) if first == 1 else (B - (P - A))
        L.append(f"- **First-mover advantage**: {fmt(fm)} ({100*fm/P:.1f}% of the pie) - shrinks as offers become frequent.")
        for j, nm in ((1, "player 2"), (0, "player 1")):
            inside = (d2 if j == 1 else d1) * ((1 - p) * (B if j == 1 else A) + p * b[j])
            if o[j] > inside + 1e-12:
                L.append(f"- **Outside-option principle**: {nm}'s outside option ({fmt(o[j])}) binds - it gets exactly "
                         "that, no more. An outside option helps only if it beats what you'd get by bargaining.")
            elif o[j] > 0:
                L.append(f"- {nm}'s outside option ({fmt(o[j])}) does **not** bind: it is an empty threat and changes nothing.")
    if a.r1 is not None:
        al = a.r2 / (a.r1 + a.r2)
        L.append(f"- Limit as rounds get short (Binmore-Rubinstein-Wolinsky 1986): asymmetric Nash with player 1's power "
                 f"α = r2/(r1+r2) = {al:.3f} → player 1 gets {fmt(al * P)} (the **more patient** side gets more).")
    if p > 0 and d1 == 1 and d2 == 1:
        L.append(f"- Pure breakdown risk with inside options (no impatience) → the split approaches the Nash solution "
                 f"with disagreement point = inside options: player 1 ≈ {fmt(b[0] + (P - b[0] - b[1]) / 2)}.")
    print("\n".join(L))


# ----------------------------------------------------------------------------- offer under uncertainty
def cmd_offer(a):
    from auctions import Dist
    d = Dist(a.other)
    if a.truncate_below is not None:
        m = d.x >= a.truncate_below
        d.f = np.where(m, d.f, 0.0)
        cdf = np.concatenate([[0], np.cumsum((d.f[1:] + d.f[:-1]) / 2 * np.diff(d.x))])
        d.f = d.f / cdf[-1]; d.Fx = cdf / cdf[-1]
    x = d.x
    s = a.reservation
    fb = a.if_rejected if a.if_rejected is not None else s     # what a rejection leaves you with
    if a.role == "seller":
        acc = 1 - d.Fx
        pay = acc * (x - s) + (1 - acc) * (fb - s)
        zopa = 1 - d.F(s)
    else:
        acc = d.Fx
        pay = acc * (s - x) + (1 - acc) * (s - fb)
        zopa = d.F(s)
    k = int(np.argmax(pay))
    p_star = x[k]
    L = [f"# Optimal take-it-or-leave-it offer - you are the {a.role}", ""]
    L.append(f"- Your reservation price: {fmt(s)}. The other side's reservation ~ {a.other}"
             + (f", known to be ≥ {fmt(a.truncate_below)}" if a.truncate_below is not None else "") + f" (mean {fmt(d.mean())}).")
    if a.if_rejected is not None:
        L.append(f"- If your offer is rejected you keep {fmt(fb)} (e.g. an existing offer stays on the table) - gains below are vs your reservation.")
    L.append(f"- Probability a deal is possible at all (ZOPA exists): **{100*zopa:.0f}%**")
    L.append(f"- Optimal offer: **{fmt(p_star)}** → accepted with probability {100*acc[k]:.0f}%, expected gain {fmt(pay[k])}")
    L += ["", f"| offer | P(accept) | expected gain |", "|---|---|---|"]
    for q in np.linspace(0.05, 0.95, 7):
        v = d.ppf(q)
        i = int(np.searchsorted(x, v))
        i = min(i, len(x) - 1)
        L.append(f"| {fmt(x[i])} | {100*acc[i]:.0f}% | {fmt(pay[i])} |")
    flat = x[pay >= pay[k] - 0.02 * abs(pay[k])]
    L.append(f"- Near-optimal range (within 2% of the best expected gain): {fmt(flat.min())} – {fmt(flat.max())}")
    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6.4, 4))
        ax.plot(x, pay, lw=2, label="expected gain"); ax2 = ax.twinx(); ax2.plot(x, acc, ls="--", color="tab:orange", label="P(accept)")
        ax.axvline(p_star, color="black", lw=0.8); ax.set_xlabel("offer"); ax.set_ylabel("expected gain"); ax2.set_ylabel("P(accept)")
        ax.set_title(f"Optimal offer {fmt(p_star)}"); ax.grid(alpha=0.3); fig.tight_layout(); fig.savefig(a.plot, dpi=150)
        L.append(f"- Plot saved: {a.plot}")
    L += ["", "- The optimal offer trades off a better price against a higher chance of no deal: it **deliberately "
          "risks breakdown**. That inefficiency is unavoidable with private information (Myerson-Satterthwaite).",
          "- If you cannot commit to walking away, the other side waits for a better offer (Coase): the commitment "
          "to 'final offer' is what makes this work - deadlines, public statements, delegation to an agent with limits.",
          "- As an opening offer in back-and-forth haggling, anchor beyond this point and concede toward it."]
    print("\n".join(L))


# ----------------------------------------------------------------------------- double auction
def cmd_double(a):
    lo, hi = (float(v) for v in a.support.split(","))
    w = hi - lo
    ask = lambda vs: lo + w * (2 / 3 * (vs - lo) / w + 1 / 4)  # noqa: E731
    bid = lambda vb: lo + w * (2 / 3 * (vb - lo) / w + 1 / 12)  # noqa: E731
    fb = w / 6
    cs = w * 9 / 64
    rng = np.random.default_rng(0)
    vs, vb = rng.uniform(lo, hi, 400_000), rng.uniform(lo, hi, 400_000)
    trade = bid(vb) >= ask(vs)
    real = np.mean((vb - vs) * trade)
    lost = np.mean((vb > vs) & ~trade)
    L = ["# Bargaining with private information on both sides (Chatterjee-Samuelson, k = 1/2)", ""]
    L.append(f"- Seller's cost and buyer's value independent uniform on [{fmt(lo)}, {fmt(hi)}]; price = average of ask and bid if bid ≥ ask.")
    L.append(f"- Seller asks: {fmt(2/3)}·cost + {fmt(lo/3 + w/4)}; buyer bids: {fmt(2/3)}·value + {fmt(lo/3 + w/12)}")
    L.append(f"- Trade happens only if value − cost ≥ **{fmt(w/4)}** (a quarter of the range)")
    L.append(f"- Expected gains from trade: first best {fmt(fb)}, this equilibrium {fmt(cs)} (MC {fmt(real)}) → "
             f"**{100*cs/fb:.0f}% efficiency**; {100*lost:.0f}% of all encounters are profitable deals that fail.")
    L.append("- Myerson-Satterthwaite (1983): no bargaining procedure can be efficient, budget-balanced and voluntary "
             "when both sides have private information; for uniform values this linear equilibrium is the best possible.")
    L.append("- Practical lesson: mediators, information disclosure, and outside valuation (appraisals) create value by "
             "shrinking private information - they can recover part of the lost deals.")
    print("\n".join(L))


# ----------------------------------------------------------------------------- multi-issue
def cmd_issues(a):
    spec = json.load(open(a.spec))
    P1, P2 = spec["parties"]
    issues = spec["issues"]
    batna = spec.get("batna", {P1: -np.inf, P2: -np.inf})
    sizes = [len(i["options"]) for i in issues]
    total = int(np.prod(sizes))
    if total > 3_000_000:
        sys.exit(f"{total:,} packages - too many; group options.")
    S1 = np.zeros(total); S2 = np.zeros(total)
    combos = list(itertools.product(*[range(s) for s in sizes]))
    for k, c in enumerate(combos):
        S1[k] = sum(iss["scores"][P1][j] for iss, j in zip(issues, c))
        S2[k] = sum(iss["scores"][P2][j] for iss, j in zip(issues, c))
    ok = (S1 >= batna[P1]) & (S2 >= batna[P2])
    order = np.lexsort((-S2, -S1))
    pareto, best2 = [], -np.inf
    for k in order:
        if S2[k] > best2:
            pareto.append(k); best2 = S2[k]
    pareto_ok = [k for k in pareto if ok[k]]
    desc = lambda k: "; ".join(f"{iss['name']}: {iss['options'][j]}" for iss, j in zip(issues, combos[k]))  # noqa: E731
    mid = tuple((s - 1) // 2 for s in sizes)   # middle option (lower middle for an even count)
    km = combos.index(mid)
    L = [f"# Multi-issue negotiation: {P1} vs {P2}", ""]
    L.append(f"- {len(issues)} issues, {total:,} packages; BATNAs {P1} {fmt(batna[P1])}, {P2} {fmt(batna[P2])}.")
    L.append(f"- Packages acceptable to both: {ok.sum():,}; Pareto-efficient among them: {len(pareto_ok)}")
    if not pareto_ok:
        L.append("- ❌ No package beats both BATNAs. Add issues (side payments, timing, guarantees) to create value.")
        print("\n".join(L)); return
    g = lambda k: (S1[k] - batna[P1]) * (S2[k] - batna[P2]) if np.isfinite(batna[P1]) else S1[k] * S2[k]  # noqa: E731
    kn = max(pareto_ok, key=g)
    L += ["", f"## Nash package (max product of gains over BATNAs)", "", f"- {desc(kn)}",
          f"- Scores: {P1} {fmt(S1[kn])}, {P2} {fmt(S2[kn])}"]
    L += ["", "## versus splitting every issue down the middle", "", f"- {desc(km)}",
          f"- Scores: {P1} {fmt(S1[km])}, {P2} {fmt(S2[km])}"]
    dom = [k for k in pareto_ok if S1[k] >= S1[km] and S2[k] >= S2[km] and (S1[k] > S1[km] or S2[k] > S2[km])]
    if dom:
        kb = max(dom, key=lambda k: S1[k] + S2[k])
        L.append(f"- ⚠ The compromise is **inefficient**: e.g. «{desc(kb)}» gives {P1} {fmt(S1[kb])} and {P2} {fmt(S2[kb])} - "
                 "both better off.")
    L += ["", "## Logrolling - what the efficient package trades (vs splitting each issue)", ""]
    for iss, jn, jm in zip(issues, combos[kn], combos[km]):
        s1, s2 = iss["scores"][P1], iss["scores"][P2]
        d1, d2 = s1[jn] - s1[jm], s2[jn] - s2[jm]
        if jn == jm:
            L.append(f"- **{iss['name']}**: keep the middle option «{iss['options'][jn]}».")
            continue
        tot_ = np.array(s1, float) + np.array(s2, float)
        tr = np.ptp(tot_) < 1e-9 * (1 + np.abs(tot_).max())
        L.append(f"- **{iss['name']}**: «{iss['options'][jm]}» → «{iss['options'][jn]}»: {P1} {d1:+g}, {P2} {d2:+g}"
                 + (" (pure transfer: this issue only moves value, use it to balance the deal)" if tr else
                    f" - concession by {P1 if d1 < 0 else P2}, worth less to them than it is to the other side" if d1 * d2 < 0 else ""))
    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.scatter(S1, S2, s=8, color="0.7", label="all packages")
        ax.plot([S1[k] for k in pareto_ok], [S2[k] for k in pareto_ok], "o-", color="tab:blue", label="efficient & acceptable")
        ax.scatter([S1[kn]], [S2[kn]], s=90, color="tab:red", zorder=5, label="Nash package")
        ax.scatter([S1[km]], [S2[km]], s=90, marker="x", color="black", zorder=5, label="split every issue")
        ax.set_xlabel(P1); ax.set_ylabel(P2); ax.grid(alpha=0.3); ax.legend(fontsize=8)
        fig.tight_layout(); fig.savefig(a.plot, dpi=150)
        L.append(f"\nPlot saved: {a.plot}")
    L += ["", "## Efficient frontier (acceptable packages)", "", f"| {P1} | {P2} | package |", "|---|---|---|"]
    for k in pareto_ok[:12]:
        L.append(f"| {fmt(S1[k])} | {fmt(S2[k])} | {desc(k)} |")
    print("\n".join(L))


# ----------------------------------------------------------------------------- shapley / core
def cmd_shapley(a):
    from scipy.optimize import linprog
    spec = json.load(open(a.spec))
    N = spec["players"]
    n = len(N)
    if n > 14:
        sys.exit("Too many players for exact Shapley (n ≤ 14).")
    raw = {frozenset(x.strip() for x in k.split(",")): float(v) for k, v in spec["v"].items()}
    default = spec.get("default", "zero")

    def v(S):
        S = frozenset(S)
        if not S:
            return 0.0
        if S in raw:
            return raw[S]
        if default == "additive":
            return sum(raw.get(frozenset([i]), 0.0) for i in S)
        return 0.0
    from math import factorial
    sh = np.zeros(n)
    for i, p in enumerate(N):
        others = [q for q in N if q != p]
        for r in range(n):
            for S in itertools.combinations(others, r):
                w = factorial(r) * factorial(n - r - 1) / factorial(n)
                sh[i] += w * (v(set(S) | {p}) - v(S))
    vN = v(N)
    # least core: min e s.t. x(S) >= v(S) - e for all proper S, x(N) = v(N)
    coal = [S for r in range(1, n) for S in itertools.combinations(N, r)]
    A_ub, b_ub = [], []
    for S in coal:
        row = [-1.0 if p in S else 0.0 for p in N] + [-1.0]
        A_ub.append(row); b_ub.append(-v(S))
    res = linprog(c=[0] * n + [1], A_ub=A_ub, b_ub=b_ub, A_eq=[[1.0] * n + [0]], b_eq=[vN],
                  bounds=[(None, None)] * (n + 1), method="highs")
    e = res.x[-1]; lc = res.x[:n]
    shapley_in_core = all(sum(sh[N.index(p)] for p in S) >= v(S) - 1e-9 for S in coal)
    L = [f"# Coalitional bargaining - {n} players, v(N) = {fmt(vN)}", ""]
    L += ["| player | Shapley value | share | least-core allocation |", "|---|---|---|---|"]
    for i, p in enumerate(N):
        L.append(f"| {p} | {fmt(sh[i])} | {100*sh[i]/vN if vN else 0:.1f}% | {fmt(lc[i])} |")
    L += [""]
    if e <= 1e-9:
        L.append(f"- ✅ **Core is non-empty** (least-core ε = {fmt(e)}): there are splits no coalition can block.")
        L.append(f"- Shapley value {'is' if shapley_in_core else 'is NOT'} in the core"
                 + ("" if shapley_in_core else " - some coalition would walk away from the 'fair' split; use the least-core allocation") + ".")
    else:
        L.append(f"- ❌ **Core is empty** (ε = {fmt(e)}): every split leaves some coalition better off on its own → "
                 "unstable; expect breakups, side deals, or the need for an outside enforcer/subsidy of ≥ ε per coalition.")
    L.append("- Shapley = average marginal contribution over all joining orders: pay each player what it adds.")
    piv = max(range(n), key=lambda i: sh[i])
    if np.ptp(sh) < 1e-9:
        L.append("- All players are symmetric: equal power.")
    else:
        L.append(f"- Most powerful player: **{N[piv]}** ({100*sh[piv]/vN if vN else 0:.0f}% of the value).")
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["nash", "rubinstein", "offer", "double", "issues", "shapley"])
    ap.add_argument("--frontier", default="100 - u1"); ap.add_argument("--u1-range", default="0,100")
    ap.add_argument("--pie", type=float); ap.add_argument("--rho1", type=float, default=1.0); ap.add_argument("--rho2", type=float, default=1.0)
    ap.add_argument("--d", default="0,0", help="disagreement / inside options d1,d2")
    ap.add_argument("--alpha", type=float, default=0.5, help="bargaining power of player 1")
    ap.add_argument("--delta1", type=float, default=0.9); ap.add_argument("--delta2", type=float, default=0.9)
    ap.add_argument("--r1", type=float); ap.add_argument("--r2", type=float); ap.add_argument("--period", type=float, default=1.0)
    ap.add_argument("--breakdown", type=float, default=0.0)
    ap.add_argument("--outside1", type=float); ap.add_argument("--outside2", type=float)
    ap.add_argument("--first", type=int, default=1, choices=[1, 2]); ap.add_argument("--rounds", type=int)
    ap.add_argument("--role", choices=["seller", "buyer"], default="seller"); ap.add_argument("--reservation", type=float, default=0)
    ap.add_argument("--other", default="uniform:0,1"); ap.add_argument("--support", default="0,1")
    ap.add_argument("--truncate-below", type=float); ap.add_argument("--if-rejected", type=float)
    ap.add_argument("--spec"); ap.add_argument("--plot", help="nash, offer, issues: save a PNG")
    a = ap.parse_args()
    if a.cmd == "rubinstein" and a.pie is None:
        a.pie = 1.0
    {"nash": cmd_nash, "rubinstein": cmd_rubinstein, "offer": cmd_offer, "double": cmd_double,
     "issues": cmd_issues, "shapley": cmd_shapley}[a.cmd](a)


if __name__ == "__main__":
    main()
