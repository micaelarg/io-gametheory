# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "scipy>=1.11", "pandas>=2.1", "matplotlib>=3.8"]
# ///
"""Collusion: can it be sustained, and do the data look like it?

SUBCOMMANDS
  sustain   Repeated-game sustainability (grim trigger): critical discount factor δ* for Bertrand,
            Cournot (linear demand) or your own payoffs (--pi-c --pi-d --pi-n); detection lags
            (deviation unseen for L periods), and the translation into REAL TIME: the longest interval
            between price changes / tender rounds that still sustains collusion given an annual
            discount rate. Shows why price transparency and frequent interaction help cartels.
  prices    Price screens on a panel (date, firm, price [, cost]): variance screen (low CV),
            margin level and structural breaks, parallel moves and price leadership, Edgeworth-cycle
            signature, asymmetric cost pass-through ("rockets and feathers").
  bids      Bid-rigging screens on tenders (tender, bidder, bid [, winner, estimate]):
            per-tender CV / kurtosis / relative distance / % difference (Imhof et al.), cover-bid
            pattern, bid rotation within stable groups, co-bidding pairs that never compete,
            identical and round bids, last-digit (Benford) test, bids vs estimate.

FLAGS BY SUBCOMMAND
  sustain: --model bertrand|cournot|custom --n [--pi-c --pi-d --pi-n] --rate --survival [--lag]
  prices:  --data --date-col --firm-col --price-col [--cost-col] --window --lag --tol
  bids:    --data --tender-col --bidder-col --bid-col [--estimate-col --process-col --min-procs] --cv-thr --min-meet --jaccard [--out]
           When tenders are split into items (lots), pass the item as --tender-col and the procedure as --process-col:
           co-bidding across items of ONE procedure is a single interaction and is not read as rotation.

Screens are RED FLAGS for further investigation, never proof. Collusion is illegal in nearly every
jurisdiction; report findings as statistical anomalies with their innocent explanations.
"""
from __future__ import annotations

import argparse
import itertools
import sys

import numpy as np
import pandas as pd
from scipy import stats


def fmt(x, d=3):
    if x is None or not np.isfinite(x):
        return "-"
    return f"{x:,.0f}" if abs(x) >= 1000 else f"{x:.{d}g}"


# ----------------------------------------------------------------------------- sustainability
def delta_star(piC, piD, piN, lag=1):
    """Smallest δ with piC/(1-δ) ≥ piD·(1-δ^lag)/(1-δ) + δ^lag·piN/(1-δ)."""
    if piD <= piC:
        return 0.0
    if lag == 1:
        return (piD - piC) / (piD - piN)
    from scipy.optimize import brentq
    f = lambda d: piC - piD * (1 - d ** lag) - d ** lag * piN  # noqa: E731
    if f(0.999999) < 0:
        return 1.0
    return brentq(f, 1e-9, 0.999999)


def cmd_sustain(a):
    L = ["# Can collusion be sustained? (infinitely repeated game, grim-trigger punishment)", ""]
    if a.model == "bertrand":
        n = a.n
        piC, piD, piN = 1 / n, 1.0, 0.0
        desc = f"homogeneous Bertrand, {n} symmetric firms (profits as fractions of monopoly profit)"
    elif a.model == "cournot":
        n = a.n
        piM = 0.25
        piC = piM / n
        piN = 1 / (n + 1) ** 2
        qc = 0.5 / n
        qd = (1 - (n - 1) * qc) / 2
        piD = qd * (1 - (n - 1) * qc - qd)
        desc = f"Cournot, linear demand, {n} symmetric firms"
    else:
        piC, piD, piN = a.pi_c, a.pi_d, a.pi_n
        desc = "custom payoffs"
    L.append(f"- Model: {desc}. Per-period profit: collude {fmt(piC)}, best deviation {fmt(piD)}, punishment (Nash) {fmt(piN)}")
    ds = delta_star(piC, piD, piN)
    L.append(f"- **Critical discount factor δ\\* = {ds:.3f}** "
             + (f"(closed form {(1 - 1/a.n):.3f} = 1 − 1/n)" if a.model == "bertrand" else
                f"(closed form (n+1)²/(n²+6n+1) = {(a.n+1)**2/(a.n**2+6*a.n+1):.3f})" if a.model == "cournot" else ""))
    L += ["", "## In real time", "", f"Annual discount rate {100*a.rate:.0f}%, probability the market/cartel survives each year "
          f"{100*a.survival:.0f}%. δ per period = survival^Δ · e^(−rΔ).", "",
          "| detection lag (periods) | δ* | longest period between interactions that sustains collusion |", "|---|---|---|"]
    for lag in sorted({1, 2, 4, 12, a.lag}):
        d = delta_star(piC, piD, piN, lag)
        if d >= 1:
            L.append(f"| {lag} | ≥1 | never sustainable |")
            continue
        # δ(Δ) = exp(-(r - ln(survival))Δ) ≥ d  → Δ ≤ -ln d / (r - ln surv)
        k = a.rate - np.log(a.survival)
        dt = -np.log(d) / k if d > 0 else np.inf
        L.append(f"| {lag} | {d:.3f} | {dt*365:.0f} days ({dt*12:.1f} months) |")
    L += ["", "## Reading it",
          "- More firms → δ* rises → harder to collude (Bertrand: 1−1/n).",
          "- Frequent interaction (daily prices, weekly tenders) makes δ per period ≈ 1: almost any cartel is sustainable "
          "*if* deviations are seen quickly. **Price transparency (published prices, price-comparison sites, "
          "mandatory price publication) shortens detection lags and can facilitate collusion.**",
          "- Lumpy, infrequent contracts (large tenders once a year) and secret discounts make deviation tempting → harder.",
          "- Multi-market contact, symmetric firms, stable demand, barriers to entry, homogeneous products → easier.",
          "- Asymmetric capacities/costs → the efficient firm's deviation gain is larger → harder."]
    print("\n".join(L))


# ----------------------------------------------------------------------------- price screens
def binseg_break(y):
    """Single best mean-shift break (least squares); returns index, F-like stat."""
    y = np.asarray(y, float)
    n = len(y)
    if n < 20:
        return None, 0.0
    best, bi = np.inf, None
    tot = ((y - y.mean()) ** 2).sum()
    for k in range(int(0.1 * n), int(0.9 * n)):
        a_, b_ = y[:k], y[k:]
        sse = ((a_ - a_.mean()) ** 2).sum() + ((b_ - b_.mean()) ** 2).sum()
        if sse < best:
            best, bi = sse, k
    F = (tot - best) / (best / (n - 2)) if best > 0 else np.inf
    return bi, F


def cmd_prices(a):
    df = pd.read_csv(a.data, parse_dates=[a.date_col])
    df = df.rename(columns={a.date_col: "date", a.firm_col: "firm", a.price_col: "price"})
    has_cost = a.cost_col is not None
    if has_cost:
        df = df.rename(columns={a.cost_col: "cost"})
    df = df.sort_values(["firm", "date"])
    P = df.pivot_table(index="date", columns="firm", values="price")
    L = [f"# Price screens - {P.shape[1]} firms, {P.shape[0]} periods ({P.index.min().date()} → {P.index.max().date()})", ""]

    # 1. variance screen over rolling windows
    W = a.window
    if has_cost:
        # screen the MARGIN, not the raw price: cost shocks move prices without saying anything about conduct
        Cm = df.pivot_table(index="date", columns="firm", values="cost")
        Mg = P - Cm
        cv = (Mg.rolling(W).std() / Mg.rolling(W).mean().abs()).mean(axis=1).dropna()
        L.append("_Variance screen run on margins (price − cost)._\n")
    else:
        cv = (P.rolling(W).std() / P.rolling(W).mean()).mean(axis=1).dropna()
        L.append("_No cost data: variance screen on raw prices - common cost shocks can create false breaks._\n")
    L += ["## 1. Variance screen (Abrantes-Metz et al. 2006)", ""]
    if len(cv) > 10:
        q10 = cv.quantile(0.10)
        low = cv[cv <= q10]
        L.append(f"- Average within-firm CV over {W}-period windows: median {cv.median():.4f}, 10th pct {q10:.4f}")
        k, F = binseg_break(cv.values)
        if k is not None and F > 20:
            before, after = cv.iloc[:k].mean(), cv.iloc[k:].mean()
            L.append(f"- Structural break in price variability around **{cv.index[k].date()}**: CV {before:.4f} → {after:.4f} "
                     f"({'⚠ variance FELL - consistent with coordination starting' if after < before else 'variance rose - consistent with a cartel ending / price war'}). "
                     f"Rolling windows delay the date by up to {W} periods: date the event with the margin break or raw prices.")
        else:
            L.append("- No clear break in price variability.")
    # 2. margins
    if has_cost:
        C = df.pivot_table(index="date", columns="firm", values="cost")
        M = (P - C).mean(axis=1).dropna()
        k, F = binseg_break(M.values)
        L += ["", "## 2. Margins", "", f"- Mean margin {fmt(M.mean())} (price − cost)."]
        if k is not None and F > 20:
            L.append(f"- Break in margins around **{M.index[k].date()}**: {fmt(M.iloc[:k].mean())} → {fmt(M.iloc[k:].mean())}"
                     + (" ⚠ margins jumped and stayed - check for entry/exit, regulation, cost shocks; otherwise a red flag." if M.iloc[k:].mean() > M.iloc[:k].mean() else ""))
    # 3. parallelism and leadership
    dP = P.diff()
    L += ["", "## 3. Parallel moves and price leadership", ""]
    if P.shape[1] >= 2:
        corr = dP.corr()
        iu = np.triu_indices_from(corr, 1)
        L.append(f"- Mean pairwise correlation of price changes: {np.nanmean(corr.values[iu]):.2f}")
        ups = (dP > a.tol)
        lead = {}
        for t in range(1, len(P)):
            movers = ups.columns[ups.iloc[t]].tolist()
            if len(movers) == 1:
                followers = ups.iloc[t + 1:t + 1 + a.lag].any().drop(movers[0]).mean() if t + 1 < len(P) else 0
                if followers > 0.5:
                    lead[movers[0]] = lead.get(movers[0], 0) + 1
        if lead:
            tot = sum(lead.values())
            top = max(lead, key=lead.get)
            L.append(f"- Price increases initiated by one firm and followed by most others within {a.lag} periods: {tot}; "
                     f"leader **{top}** in {100*lead[top]/tot:.0f}% of them"
                     + (" ⚠ stable price leadership (a known focal-point coordination device, e.g. fuel retail)." if lead[top] / tot > 0.6 and tot >= 5 else "."))
        else:
            L.append("- No clear leader-follower increases.")
    # 4. Edgeworth cycles
    L += ["", "## 4. Cycle signature", ""]
    inc = dP[dP > a.tol].stack()
    dec = dP[dP < -a.tol].stack()
    if len(inc) and len(dec):
        ratio = len(dec) / len(inc)
        size = inc.mean() / -dec.mean()
        L.append(f"- Decreases per increase: {ratio:.1f}; average increase is {size:.1f}× the average decrease.")
        if ratio > 2 and size > 2:
            L.append("- Pattern = **Edgeworth cycles** (many small cuts, rare big jumps). In theory (Maskin-Tirole) these are a "
                     "*competitive* equilibrium, but a coordinated restoration day / leader is a coordination sign.")
    # 5. rockets and feathers
    if has_cost:
        g = df.sort_values("date").groupby("firm")
        rows = []
        for f_, d in g:
            d = d.set_index("date")
            dp, dc = d.price.diff(), d.cost.diff()
            Xs = []
            for l in range(a.lag + 1):
                Xs.append(dc.clip(lower=0).shift(l).rename(f"up{l}"))
                Xs.append(dc.clip(upper=0).shift(l).rename(f"dn{l}"))
            X = pd.concat(Xs, axis=1)
            Z = pd.concat([dp.rename("dp"), X], axis=1).dropna()
            if len(Z) > 30:
                b = np.linalg.lstsq(np.column_stack([np.ones(len(Z)), Z.drop(columns="dp").values]), Z.dp.values, rcond=None)[0][1:]
                rows.append((b[0::2].sum(), b[1::2].sum()))
        if rows:
            up, dn = np.mean([r[0] for r in rows]), np.mean([r[1] for r in rows])
            L += ["", "## 5. Cost pass-through", "",
                  f"- Cumulative pass-through within {a.lag} periods: cost increases {up:.2f}, cost decreases {dn:.2f}"]
            if up > dn + 0.15:
                L.append("- ⚠ **Rockets and feathers**: prices rise with costs faster than they fall. Explanations: consumer search "
                         "costs, inventories - or tacit coordination using cost decreases as a focal point to keep margins.")
    L += ["", "_Innocent explanations to rule out for every flag: common cost shocks, regulation, seasonality, "
          "entry/exit, data artefacts (price caps, reporting rules)._"]
    print("\n".join(L))


# ----------------------------------------------------------------------------- bid screens
def last_digit_note(last):
    cnt = np.bincount(last, minlength=10)
    p_all = stats.chisquare(cnt).pvalue
    other = np.delete(cnt, [0, 5])
    p_other = stats.chisquare(other).pvalue if other.sum() >= 80 else np.nan
    if p_all >= 0.01:
        return f"- Last-digit test: uniform (p = {p_all:.2f})."
    if np.isfinite(p_other) and p_other >= 0.01:
        return (f"- Last digits over-use 0/5 ({100*(cnt[0]+cnt[5])/cnt.sum():.0f}% vs 20% expected) but are uniform otherwise "
                f"(p = {p_other:.2f}): **round pricing convention, not evidence of fabrication**.")
    return (f"- ⚠ Last digits non-uniform even excluding 0/5 (p = {p_other:.3f}): numbers may be engineered "
            "(e.g. cover bids computed as winner × fixed factor) - or they are COMPUTED amounts (quantity × unit price, taxes): run the test on the numbers bidders actually choose (unit prices).")



def cmd_bids(a):
    df = pd.read_csv(a.data)
    df = df.rename(columns={a.tender_col: "tender", a.bidder_col: "bidder", a.bid_col: "bid"})
    df = df.dropna(subset=["bid"])
    if a.estimate_col:
        df["rel"] = df.bid / df[a.estimate_col]
    else:
        df["rel"] = df.bid / df.groupby("tender").bid.transform("median")
    df["rank"] = df.groupby("tender").bid.rank(method="first")
    df["n"] = df.groupby("tender").bid.transform("size")
    T = []
    for t, g in df.groupby("tender"):
        b = np.sort(g.bid.values)
        if len(b) < 3:
            continue
        losers = b[1:]
        sd_l = losers.std(ddof=1) if len(losers) > 1 else np.nan
        T.append({"tender": t, "n": len(b), "winner_bid": b[0],
                  "cv": b.std(ddof=1) / b.mean(), "kurtosis": stats.kurtosis(b) if len(b) >= 4 else np.nan,
                  "skewness": stats.skew(b), "diffp": (b[1] - b[0]) / b[0],
                  "rd": (b[1] - b[0]) / sd_l if sd_l and sd_l > 0 else np.nan,
                  "spread": (b[-1] - b[0]) / b[0]})
    T = pd.DataFrame(T)
    L = [f"# Bid-rigging screens - {df.tender.nunique()} tenders, {df.bidder.nunique()} bidders, {len(df)} bids", ""]
    if T.empty:
        sys.exit("Need tenders with ≥ 3 bids.")
    # per-tender flags (Imhof, Karagök & Rutz 2018 style; thresholds are rules of thumb - calibrate on clean data)
    T["flag_cv"] = T.cv < a.cv_thr
    T["flag_rd"] = T.rd > 1.0
    T["score"] = T.flag_cv.astype(int) + T.flag_rd.astype(int) + (T["kurtosis"] > 1).fillna(False).astype(int) + (T["skewness"] < -0.5).astype(int)
    L += ["## 1. Distribution screens per tender", "",
          f"- Median CV {T.cv.median():.3f}; tenders with CV < {a.cv_thr}: {T.flag_cv.mean()*100:.0f}%",
          f"- Relative distance RD = (2nd − 1st)/sd(losing bids): median {T.rd.median():.2f}; RD > 1 in {T.flag_rd.mean()*100:.0f}% "
          "(cover bids cluster together, far above the winner)",
          f"- Gap between 1st and 2nd bid: median {100*T.diffp.median():.1f}%",
          "- ⚠ Per-tender CV/RD flags are noisy (with 3-4 bids RD > 1 is common by chance): calibrate thresholds on a "
          "period/market known to be clean, and trust patterns that repeat across tenders and bidders over single flags.", ""]
    top = T.sort_values(["score", "rd"], ascending=False).head(10)
    L += ["| tender | n | CV | RD | gap 1-2 | kurtosis | score |", "|---|---|---|---|---|---|---|"]
    for _, r in top.iterrows():
        L.append(f"| {r.tender} | {r.n} | {r.cv:.3f} | {fmt(r.rd)} | {100*r.diffp:.1f}% | {fmt(r["kurtosis"])} | {r.score} |")
    # 2. rotation and co-bidding
    L += ["", "## 2. Who meets whom, and who wins", ""]
    winners = df[df["rank"] == 1].set_index("tender").bidder
    parts = df.groupby("tender").bidder.apply(set)
    pairs = {}
    for t, S in parts.items():
        for p_, q_ in itertools.combinations(sorted(S), 2):
            pairs.setdefault((p_, q_), []).append(t)
    # groups of bidders that (almost) always bid together: Jaccard similarity of their tender sets
    tsets = df.groupby("bidder").tender.apply(set)
    adj = {}
    for (p_, q_), ts in pairs.items():
        if len(ts) < a.min_meet:
            continue
        jac = len(ts) / len(tsets[p_] | tsets[q_])
        if jac >= a.jaccard:
            adj.setdefault(p_, set()).add(q_); adj.setdefault(q_, set()).add(p_)
    seen, groups = set(), []
    for v in adj:
        if v in seen:
            continue
        comp, stack = set(), [v]
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x); stack.extend(adj.get(x, ()))
        seen |= comp
        groups.append(sorted(comp))
    flagged = []
    for G in groups:
        ts = [t for t, S in parts.items() if len(S & set(G)) >= 2]
        if len(ts) < a.min_meet:
            continue
        w = winners.reindex(ts)
        inside = w.isin(G)
        counts = w[inside].value_counts().reindex(G, fill_value=0)
        pshare = counts / max(counts.sum(), 1)
        ent = -(pshare[pshare > 0] * np.log(pshare[pshare > 0])).sum() / np.log(len(G)) if len(G) > 1 else 0
        flagged.append((G, len(ts), inside.mean(), ent, counts.to_dict(), list(ts)))
    L.append(f"- Groups of bidders that bid together (Jaccard ≥ {a.jaccard}, ≥ {a.min_meet} joint tenders): {len(flagged)}")
    for G, nt, wr, ent, cnt, ts in sorted(flagged, key=lambda x: -x[2]):
        if a.process_col:
            nproc = df[df.tender.isin(ts)][a.process_col].nunique()
            if nproc < a.min_procs:
                L.append(f"  - {', '.join(map(str, G))}: {nt} joint items but only **{nproc} tender(s)** - items of the same tender are "
                         "one interaction, not repeated play (firms often split items by specialty). Not a rotation signal.")
                continue
        rot = wr > 0.8 and ent > 0.8
        if wr > 0.8:
            ordered = [winners.get(t) for t in sorted(ts)]
            seq = " → ".join(str(x) for x in ordered[:12]) + (" …" if len(ordered) > 12 else "")
            extra = f"\n    - win sequence (by tender id): {seq}"
            if a.estimate_col:
                wrel = df[(df.tender.isin(ts)) & (df["rank"] == 1)].rel.median()
                orel = df[(~df.tender.isin(ts)) & (df["rank"] == 1)].rel.median()
                wsum = df[(df.tender.isin(ts)) & (df["rank"] == 1)][a.estimate_col].sum()
                extra += (f"\n    - winning bid / estimate: {wrel:.3f} in the group's tenders vs {orel:.3f} elsewhere → "
                          f"implied overcharge ≈ {100*(wrel/orel-1):.1f}% ≈ {fmt(wsum*(wrel-orel))} on these tenders "
                          "(assumes other tenders are a valid competitive benchmark)")
            outs = df[df.tender.isin(ts) & ~df.bidder.isin(G)]
            if len(outs):
                extra += (f"\n    - outside firms bid in {outs.tender.nunique()} of these tenders and never won"
                          + (f"; their bids / estimate median {outs.rel.median():.3f}" if a.estimate_col else "")
                          + " - possible cover bids (or genuinely uncompetitive firms)")
        else:
            extra = ""
        L.append(f"  - {', '.join(map(str, G))}: {nt} joint tenders, group wins {100*wr:.0f}%, "
                 f"evenness of wins (entropy, 1 = equal) {abs(ent):.2f}: {cnt}" + (" ⚠ **bid-rotation pattern**" if rot else
                    " → one member always wins: check whether the others are cover bidders or sell a different (dearer) product" if wr > 0.8 and ent < 0.3 else "") + extra)
    # 3. bidder level
    bl = df.groupby("bidder").agg(bids=("bid", "size"), wins=("rank", lambda s: (s == 1).sum()), rel=("rel", "median"))
    never = bl[(bl.bids >= a.min_meet) & (bl.wins == 0)]
    L += ["", "## 3. Bidder-level", "",
          f"- Bidders that bid ≥ {a.min_meet} times and never win: {len(never)} "
          + (f"({', '.join(map(str, never.sort_values('bids', ascending=False).index[:8]))}) - possible cover bidders or subcontractors of winners"
             if len(never) else "")]
    # 4. identical / round / digits
    ident = df.duplicated(["tender", "bid"], keep=False).groupby(df.tender).any().mean()
    last = (df.bid.round().astype(int).abs() % 10)
    chi = stats.chisquare(np.bincount(last, minlength=10)) if len(last) >= 100 else None
    roundshare = (df.bid.round() % 1000 == 0).mean()
    L += ["", "## 4. Formatting anomalies", "",
          f"- Tenders with identical bids: {100*ident:.1f}%",
          f"- Bids that are multiples of 1,000: {100*roundshare:.1f}%",
          last_digit_note(last) if chi is not None else "- Last-digit test needs ≥ 100 bids."]
    if a.estimate_col:
        L.append(f"- Winning bid / estimate: median {df[df['rank'] == 1].rel.median():.2f}; "
                 f"tenders won above the estimate: {100*(df[df['rank'] == 1].rel > 1).mean():.0f}%")
    if a.out:
        T.to_csv(a.out, index=False)
        L.append(f"\nPer-tender screens → `{a.out}`")
    L += ["", "_Follow-ups: compare screens before/after known events (leniency case, entry of a new bidder, change of "
          "procurement rules); run `auctions.py gpv` to check whether markups fall with n; Porter-Zona test if cost proxies "
          "(distance to site, backlog) exist. Innocent explanations: subcontracting, joint bids, capacity, specialization._"]
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["sustain", "prices", "bids"])
    ap.add_argument("--model", choices=["bertrand", "cournot", "custom"], default="bertrand")
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--pi-c", type=float); ap.add_argument("--pi-d", type=float); ap.add_argument("--pi-n", type=float)
    ap.add_argument("--rate", type=float, default=0.10); ap.add_argument("--survival", type=float, default=0.95)
    ap.add_argument("--data")
    ap.add_argument("--date-col", default="date"); ap.add_argument("--firm-col", default="firm")
    ap.add_argument("--price-col", default="price"); ap.add_argument("--cost-col")
    ap.add_argument("--window", type=int, default=30)
    ap.add_argument("--lag", type=int, default=3, help="prices: max lag for leadership/pass-through; sustain: extra detection lag row")
    ap.add_argument("--tol", type=float, default=1e-9)
    ap.add_argument("--tender-col", default="tender"); ap.add_argument("--bidder-col", default="bidder")
    ap.add_argument("--bid-col", default="bid"); ap.add_argument("--estimate-col")
    ap.add_argument("--cv-thr", type=float, default=0.03); ap.add_argument("--min-meet", type=int, default=5)
    ap.add_argument("--jaccard", type=float, default=0.6, help="co-bidding similarity to group bidders")
    ap.add_argument("--process-col", help="bids: column with the tender/procedure id when each row's tender is an ITEM (lot) of it")
    ap.add_argument("--min-procs", type=int, default=3, help="bids: minimum distinct procedures for a group to count as repeated play")
    ap.add_argument("--out")
    a = ap.parse_args()
    {"sustain": cmd_sustain, "prices": cmd_prices, "bids": cmd_bids}[a.cmd](a)


if __name__ == "__main__":
    main()
