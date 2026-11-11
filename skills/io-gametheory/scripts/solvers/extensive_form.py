# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Solve a sequential (extensive-form) game of perfect information by backward induction.

Tree JSON - three node kinds:
  decision : {"player": "Entrant", "actions": {"Enter": <node>, "Stay out": <node>}}
  chance   : {"chance": {"Boom": {"p": 0.6, "node": <node>}, "Bust": {"p": 0.4, "node": <node>}}}
  terminal : {"payoffs": {"Entrant": 2, "Incumbent": 1}}
Optional top level: {"title": "...", "players": [...], "tree": <node>}  (or the root node itself).

Reports the subgame-perfect equilibrium (full contingent plan: what each player
does at EVERY node, including off-path), the equilibrium path and payoffs,
non-credible threats, ties (multiple SPE), and a Mermaid diagram with the
equilibrium choices drawn as thick arrows.

For imperfect information (information sets), write the normal form and use
finite_nash.py, or add a chance node for nature and reason about beliefs (PBE).
"""
from __future__ import annotations

import argparse
import json

TOL = 1e-9


class Solver:
    def __init__(self, root, players):
        self.root = root
        self.players = players
        self.choices = {}   # node id -> chosen action
        self.info = {}      # node id -> details
        self.ties = []
        self._ids = {}
        self.counter = 0
        self.path_labels = {}

    def nid(self, node):
        k = id(node)
        if k not in self._ids:
            self._ids[k] = f"n{self.counter}"
            self.counter += 1
        return self._ids[k]

    def solve(self, node, history=()):
        nid = self.nid(node)
        self.path_labels[nid] = " → ".join(history) if history else "(root)"
        if "payoffs" in node:
            return {p: float(node["payoffs"].get(p, 0.0)) for p in self.players}
        if "chance" in node:
            total = sum(b["p"] for b in node["chance"].values())
            if abs(total - 1) > 1e-6:
                raise ValueError(f"chance probabilities at {self.path_labels[nid]} sum to {total}")
            val = {p: 0.0 for p in self.players}
            for lab, b in node["chance"].items():
                v = self.solve(b["node"], history + (f"[{lab}]",))
                for p in self.players:
                    val[p] += b["p"] * v[p]
            return val
        mover = node["player"]
        vals = {a: self.solve(child, history + (f"{mover}:{a}",)) for a, child in node["actions"].items()}
        best = max(v[mover] for v in vals.values())
        best_actions = [a for a, v in vals.items() if abs(v[mover] - best) <= TOL]
        if len(best_actions) > 1:
            self.ties.append((self.path_labels[nid], mover, best_actions))
        choice = best_actions[0]
        self.choices[nid] = choice
        self.info[nid] = {"mover": mover, "vals": vals, "choice": choice}
        return vals[choice]

    def equilibrium_path(self):
        path, node = [], self.root
        while "payoffs" not in node:
            nid = self.nid(node)
            if "chance" in node:
                path.append(("chance", "nature", ", ".join(f"{k} p={b['p']}" for k, b in node["chance"].items())))
                break  # expected values beyond this point
            a = self.choices[nid]
            path.append((nid, node["player"], a))
            node = node["actions"][a]
        return path, node


def fmt(x):
    return f"{x:.4g}" if abs(x - round(x)) > 1e-9 else str(int(round(x)))


def fmt_pay(v, players):
    return "(" + ", ".join(f"{p} {fmt(v[p])}" for p in players) + ")"


def mermaid(root, solver):
    lines = ["```mermaid", "graph TD"]

    def walk(node):
        nid = solver.nid(node)
        if "payoffs" in node:
            lab = "<br/>".join(f"{p}: {fmt(float(node['payoffs'].get(p, 0)))}" for p in solver.players)
            lines.append(f'  {nid}(["{lab}"])')
            return
        if "chance" in node:
            lines.append(f'  {nid}{{{{"Nature"}}}}')
            for lab, b in node["chance"].items():
                c = b["node"]
                walk(c)
                lines.append(f'  {nid} -. "{lab} ({b["p"]})" .-> {solver.nid(c)}')
            return
        lines.append(f'  {nid}["{node["player"]}"]')
        for a, c in node["actions"].items():
            walk(c)
            arrow = "==>" if solver.choices.get(nid) == a else "-->"
            lines.append(f'  {nid} {arrow}|"{a}"| {solver.nid(c)}')

    walk(root)
    lines.append("```")
    lines.append("Thick arrows (==>) = equilibrium choice at every node, on and off the path.")
    return "\n".join(lines)


def collect_players(node, acc):
    if "payoffs" in node:
        for p in node["payoffs"]:
            if p not in acc:
                acc.append(p)
    elif "chance" in node:
        for b in node["chance"].values():
            collect_players(b["node"], acc)
    else:
        if node["player"] not in acc:
            acc.append(node["player"])
        for c in node["actions"].values():
            collect_players(c, acc)
    return acc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tree")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    with open(a.tree) as f:
        g = json.load(f)
    root = g.get("tree", g)
    title = g.get("title", "Sequential game")
    players = g.get("players") or collect_players(root, [])
    s = Solver(root, players)
    value = s.solve(root)
    path, end = s.equilibrium_path()
    on_path = {nid for nid, _, _ in path}

    if a.json:
        print(json.dumps({"title": title, "value": value,
                          "strategy": {s.path_labels[k]: v for k, v in s.choices.items()},
                          "path": [(p, x) for _, p, x in path], "ties": s.ties}, indent=2))
        return

    L = [f"# {title}", "", "## Subgame-perfect equilibrium", ""]
    L.append("**Equilibrium path:** " + " → ".join(f"{p} plays *{x}*" for _, p, x in path))
    L.append(f"**Payoffs:** {fmt_pay(value, players)}")
    L.append("")
    L.append("### Full strategy (what each player does at every node, including nodes never reached)")
    L.append("")
    order = sorted(s.info, key=lambda k: int(k[1:]))
    for nid in order:
        inf = s.info[nid]
        tag = "" if nid in on_path else " *(off path)*"
        L.append(f"- After {s.path_labels[nid]}: **{inf['mover']}** plays **{inf['choice']}**{tag}")
    L.append("")
    L.append("### Why each choice (and which threats are not credible)")
    L.append("")
    any_threat = False
    for nid in order:
        inf = s.info[nid]
        mover, vals, ch = inf["mover"], inf["vals"], inf["choice"]
        for alt, v in vals.items():
            if alt == ch:
                continue
            loss = vals[ch][mover] - v[mover]
            hurt = [p for p in players if p != mover and v[p] < vals[ch][p] - TOL]
            line = f"- After {s.path_labels[nid]}: {mover} prefers *{ch}* over *{alt}* (gains {fmt(loss)})."
            # threats are about RESPONSES: a move by a player answering someone else's earlier move
            if hurt and loss > TOL and s.path_labels[nid] != "(root)":
                any_threat = True
                line += (f" ⇒ A threat by {mover} to play *{alt}* would hurt {', '.join(hurt)} but "
                         f"is **not credible**: when the moment comes, {mover} loses {fmt(loss)} by carrying it out.")
            L.append(line)
    if not any_threat:
        L.append("- No non-credible threats in this tree.")
    L.append("")
    if s.ties:
        L.append("### ⚠ Ties → multiple SPE")
        for where, mover, acts in s.ties:
            L.append(f"- After {where}: {mover} is indifferent among {acts}. The SPE above picks the first; "
                     "each choice gives a different SPE. Discuss which is plausible.")
        L.append("")
    L.append("## Tree")
    L.append("")
    L.append(mermaid(root, s))
    print("\n".join(L))


if __name__ == "__main__":
    main()
