# /// script
# requires-python = ">=3.10"
# dependencies = ["nashpy>=0.0.41", "numpy>=1.26"]
# ///
"""Solve a finite two-player normal-form game.

Input JSON (payoffs as [row_payoff, col_payoff] per cell):
{
  "title": "Entry game",
  "players": ["Incumbent", "Entrant"],
  "row_actions": ["Fight", "Accommodate"],
  "col_actions": ["Enter", "Stay out"],
  "payoffs": [[[-1, -1], [5, 0]],
              [[ 2,  1], [5, 0]]]
}
Alternatively give "A" and "B" matrices.

Reports: matrix with best responses marked, iterated strict dominance,
pure and mixed equilibria, expected payoffs, deviation losses (why each
pure equilibrium is stable), Pareto check.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings

import numpy as np

TOL = 1e-9


def load_game(path: str) -> dict:
    with open(path) as f:
        g = json.load(f)
    if "payoffs" in g:
        P = np.array(g["payoffs"], dtype=float)
        A, B = P[..., 0], P[..., 1]
    else:
        A, B = np.array(g["A"], dtype=float), np.array(g["B"], dtype=float)
    m, n = A.shape
    g.setdefault("players", ["Row", "Col"])
    g.setdefault("row_actions", [f"r{i+1}" for i in range(m)])
    g.setdefault("col_actions", [f"c{j+1}" for j in range(n)])
    g.setdefault("title", "Game")
    g["A"], g["B"] = A, B
    return g


def best_response_masks(A, B):
    row_br = np.isclose(A, A.max(axis=0, keepdims=True), atol=1e-9)
    col_br = np.isclose(B, B.max(axis=1, keepdims=True), atol=1e-9)
    return row_br, col_br


def pure_equilibria(A, B):
    r, c = best_response_masks(A, B)
    return [tuple(x) for x in np.argwhere(r & c)]


def iterated_strict_dominance(A, B):
    rows, cols = list(range(A.shape[0])), list(range(A.shape[1]))
    steps = []
    changed = True
    while changed:
        changed = False
        for i in list(rows):
            for k in rows:
                if k != i and all(A[k, j] > A[i, j] + TOL for j in cols):
                    rows.remove(i)
                    steps.append(("row", i, k))
                    changed = True
                    break
        for j in list(cols):
            for k in cols:
                if k != j and all(B[i, k] > B[i, j] + TOL for i in rows):
                    cols.remove(j)
                    steps.append(("col", j, k))
                    changed = True
                    break
    return rows, cols, steps


def mixed_equilibria(A, B):
    import nashpy as nash

    game = nash.Game(A, B)
    eqs = []
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        if min(A.shape) <= 6 and max(A.shape) <= 10:
            it = game.support_enumeration(tol=1e-12)
            method = "support enumeration (exact for nondegenerate games)"
        else:
            it = game.lemke_howson_enumeration()
            method = "Lemke-Howson from every initial label (may miss equilibria)"
        for s1, s2 in it:
            if np.any(np.isnan(s1)) or np.any(np.isnan(s2)):
                continue
            s1, s2 = np.clip(s1, 0, 1), np.clip(s2, 0, 1)
            s1, s2 = s1 / s1.sum(), s2 / s2.sum()
            if not any(np.allclose(s1, e[0], atol=1e-6) and np.allclose(s2, e[1], atol=1e-6) for e in eqs):
                eqs.append((s1, s2))
        degenerate = any("degenerate" in str(x.message).lower() for x in w)
    return eqs, method, degenerate


def fmt(x):
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    return f"{x:.4g}" if abs(x - round(x)) > 1e-9 else str(int(round(x)))


def render_matrix(g):
    A, B = g["A"], g["B"]
    r, c = best_response_masks(A, B)
    p1, p2 = g["players"]
    lines = [f"Rows: **{p1}**, columns: **{p2}**. Cell = ({p1}, {p2}). `*` = best response of that player.", ""]
    lines.append("| | " + " | ".join(g["col_actions"]) + " |")
    lines.append("|---" * (len(g["col_actions"]) + 1) + "|")
    for i, ra in enumerate(g["row_actions"]):
        cells = []
        for j in range(A.shape[1]):
            a = fmt(A[i, j]) + ("*" if r[i, j] else "")
            b = fmt(B[i, j]) + ("*" if c[i, j] else "")
            cell = f"{a}, {b}"
            if r[i, j] and c[i, j]:
                cell = f"**{cell}**"
            cells.append(cell)
        lines.append(f"| {ra} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def support_str(s, labels):
    return ", ".join(f"{labels[k]} {s[k]:.3f}" for k in range(len(s)) if s[k] > 1e-9)


def analyze(g) -> dict:
    A, B = g["A"], g["B"]
    rows, cols, steps = iterated_strict_dominance(A, B)
    pure = pure_equilibria(A, B)
    # Iterated strict dominance preserves the equilibrium set: solve the reduced game, map back.
    Ar, Br = A[np.ix_(rows, cols)], B[np.ix_(rows, cols)]
    mixed_r, method, degenerate = mixed_equilibria(Ar, Br)
    mixed = []
    for s1r, s2r in mixed_r:
        s1, s2 = np.zeros(A.shape[0]), np.zeros(A.shape[1])
        s1[rows], s2[cols] = s1r, s2r
        mixed.append((s1, s2))
    if (len(rows), len(cols)) != A.shape:
        method += f" on the {len(rows)}×{len(cols)} game left after iterated strict dominance"
    out = {"pure": [], "mixed": [], "dominance_steps": steps, "method": method,
           "degenerate": degenerate, "surviving": (rows, cols)}
    for i, j in pure:
        others_r = [k for k in range(A.shape[0]) if k != i]
        others_c = [k for k in range(A.shape[1]) if k != j]
        dev_r = None if not others_r else max(others_r, key=lambda k: A[k, j])
        dev_c = None if not others_c else max(others_c, key=lambda k: B[i, k])
        pareto_better = [(k, l) for k in range(A.shape[0]) for l in range(A.shape[1])
                         if A[k, l] >= A[i, j] - TOL and B[k, l] >= B[i, j] - TOL
                         and (A[k, l] > A[i, j] + TOL or B[k, l] > B[i, j] + TOL)]
        out["pure"].append({
            "cell": (int(i), int(j)), "payoffs": (A[i, j], B[i, j]),
            "row_best_deviation": None if dev_r is None else (int(dev_r), A[i, j] - A[dev_r, j]),
            "col_best_deviation": None if dev_c is None else (int(dev_c), B[i, j] - B[i, dev_c]),
            "pareto_dominated_by": pareto_better,
        })
    for s1, s2 in mixed:
        if np.count_nonzero(s1 > 1e-9) == 1 and np.count_nonzero(s2 > 1e-9) == 1:
            continue
        out["mixed"].append({"row": s1, "col": s2,
                             "payoffs": (float(s1 @ A @ s2), float(s1 @ B @ s2))})
    return out


def report(g, res) -> str:
    A = g["A"]
    p1, p2 = g["players"]
    R, C = g["row_actions"], g["col_actions"]
    L = [f"# {g['title']}", "", "## Payoff matrix", "", render_matrix(g), ""]

    L += ["## Iterated elimination of strictly dominated strategies", ""]
    if not res["dominance_steps"]:
        L.append("No strictly dominated strategies.")
    for who, a, by in res["dominance_steps"]:
        if who == "row":
            L.append(f"- {p1}: **{R[a]}** is strictly dominated by {R[by]} → eliminated.")
        else:
            L.append(f"- {p2}: **{C[a]}** is strictly dominated by {C[by]} → eliminated.")
    rows, cols = res["surviving"]
    if res["dominance_steps"]:
        L.append(f"- Surviving: {p1} {{{', '.join(R[i] for i in rows)}}}, {p2} {{{', '.join(C[j] for j in cols)}}}.")
        if len(rows) == 1 and len(cols) == 1:
            L.append("- **Solved by dominance alone** - the strongest kind of prediction.")
    L.append("")

    L += ["## Pure-strategy equilibria", ""]
    if not res["pure"]:
        L.append("**None.** Every cell has someone who wants to move - look at the mixed equilibrium.")
        L.append("")
    for e in res["pure"]:
        i, j = e["cell"]
        L.append(f"### ({R[i]}, {C[j]}) → payoffs ({fmt(e['payoffs'][0])}, {fmt(e['payoffs'][1])})")
        if e["row_best_deviation"]:
            k, loss = e["row_best_deviation"]
            strict = "strictly" if loss > TOL else "weakly (indifferent!)"
            L.append(f"- {p1} would not switch to {R[k]}: loses {fmt(loss)} ({strict} stable).")
        if e["col_best_deviation"]:
            k, loss = e["col_best_deviation"]
            strict = "strictly" if loss > TOL else "weakly (indifferent!)"
            L.append(f"- {p2} would not switch to {C[k]}: loses {fmt(loss)} ({strict} stable).")
        if e["pareto_dominated_by"]:
            pd_ = e["pareto_dominated_by"]
            cells = "; ".join(f"({R[k]}, {C[l]})" for k, l in pd_[:3]) + (f" and {len(pd_) - 3} more cells" if len(pd_) > 3 else "")
            L.append(f"- ⚠ Pareto-dominated by {cells}: both could do better, but neither can get there alone "
                     "(prisoner's-dilemma / coordination-failure structure).")
        L.append("")

    L += ["## Mixed-strategy equilibria", ""]
    if not res["mixed"]:
        L.append("None (beyond the pure ones).")
    for e in res["mixed"]:
        L.append(f"- {p1}: {support_str(e['row'], R)} | {p2}: {support_str(e['col'], C)} "
                 f"→ expected payoffs ({fmt(e['payoffs'][0])}, {fmt(e['payoffs'][1])})")
    if res["mixed"]:
        L.append("")
        L.append("Reminder for the explanation: each player mixes so that the **other** is indifferent - "
                 "so a player's probabilities are pinned down by the opponent's payoffs, not their own.")
    L.append("")
    total = len(res["pure"]) + len(res["mixed"])
    L += ["## Diagnostics", "", f"- Method: {res['method']}.", f"- Equilibria found: {total}."]
    if res["degenerate"]:
        L.append("- ⚠ Degenerate game (ties in payoffs): there may be a continuum of equilibria; "
                 "the list above shows extreme points only.")
    elif total % 2 == 0 and total > 0:
        L.append("- ⚠ Even number of equilibria in an apparently nondegenerate game: check for ties / a missing equilibrium.")
    if len(res["pure"]) > 1:
        L.append("- Several pure equilibria → selection problem. Discuss payoff dominance, risk dominance, "
                 "focal points, who can commit / move first.")
        if A.shape == (2, 2) and len(res["pure"]) == 2:
            B = g["B"]
            prods = []
            for e in res["pure"]:
                i, j = e["cell"]
                prods.append((A[i, j] - A[1 - i, j]) * (B[i, j] - B[i, 1 - j]))
            (i0, j0), (i1, j1) = res["pure"][0]["cell"], res["pure"][1]["cell"]
            if abs(prods[0] - prods[1]) > TOL:
                k = 0 if prods[0] > prods[1] else 1
                i, j = res["pure"][k]["cell"]
                L.append(f"- Risk dominance (Harsanyi-Selten, product of deviation losses {fmt(prods[0])} vs {fmt(prods[1])}): "
                         f"**({R[i]}, {C[j]})** is risk-dominant - the safer bet when unsure what the other will do.")
    return "\n".join(L)


def to_json(g, res):
    def conv(o):
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        raise TypeError(type(o))
    payload = {"title": g["title"], "players": g["players"], "row_actions": g["row_actions"],
               "col_actions": g["col_actions"], **{k: v for k, v in res.items()}}
    return json.dumps(payload, default=conv, indent=2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game", help="game JSON file ('-' for stdin)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args()
    if a.game == "-":
        import tempfile
        data = sys.stdin.read()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(data)
            a.game = f.name
    g = load_game(a.game)
    res = analyze(g)
    print(to_json(g, res) if a.json else report(g, res))


if __name__ == "__main__":
    main()
