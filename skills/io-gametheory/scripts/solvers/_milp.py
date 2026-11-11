"""Shared exact solvers for bimatrix games (imported by other scripts)."""
from __future__ import annotations

import sys

import numpy as np


def zero_sum_lp(A):
    from scipy.optimize import linprog
    m, n = A.shape
    shift = A.min() - 1
    M = A - shift
    # row player: max v s.t. x^T M >= v ; equivalently min sum(y) with M^T y >= 1
    r = linprog(np.ones(m), A_ub=-M.T, b_ub=-np.ones(n), bounds=[(0, None)] * m, method="highs")
    x = r.x / r.x.sum()
    c = linprog(-np.ones(n), A_ub=M, b_ub=np.ones(m), bounds=[(0, None)] * n, method="highs")
    y = c.x / c.x.sum()
    return x, y


def epsilon(A, B, x, y):
    v1, v2 = x @ A @ y, x @ B @ y
    return max((A @ y).max() - v1, (x @ B).max() - v2), v1, v2


def milp_nash(A, B, time_limit=120):
    """Exact Nash equilibrium of a bimatrix game via MILP (Sandholm, Gilpin & Conitzer 2005), HiGHS."""
    from scipy.optimize import milp, LinearConstraint, Bounds
    from scipy.sparse import lil_matrix
    m, n = A.shape
    U1, U2 = A.max() - A.min() + 1e-9, B.max() - B.min() + 1e-9
    # variable layout: x[m] y[n] u1 u2 s1[m] s2[n]
    nx, ny, iu1, iu2 = 0, m, m + n, m + n + 1
    is1, is2 = m + n + 2, m + n + 2 + m
    nv = m + n + 2 + m + n
    rows = 2 + 3 * m + 3 * n
    M = lil_matrix((rows, nv))
    lo, hi = np.full(rows, -np.inf), np.full(rows, np.inf)
    r = 0
    M[r, nx:nx + m] = 1; lo[r] = hi[r] = 1; r += 1
    M[r, ny:ny + n] = 1; lo[r] = hi[r] = 1; r += 1
    for i in range(m):
        M[r, iu1] = 1; M[r, ny:ny + n] = -A[i]; lo[r] = 0; r += 1              # regret >= 0
        M[r, iu1] = 1; M[r, ny:ny + n] = -A[i]; M[r, is1 + i] = -U1; hi[r] = 0; r += 1  # regret <= U s
        M[r, nx + i] = 1; M[r, is1 + i] = 1; hi[r] = 1; r += 1                   # x_i <= 1 - s_i
    for j in range(n):
        M[r, iu2] = 1; M[r, nx:nx + m] = -B[:, j]; lo[r] = 0; r += 1
        M[r, iu2] = 1; M[r, nx:nx + m] = -B[:, j]; M[r, is2 + j] = -U2; hi[r] = 0; r += 1
        M[r, ny + j] = 1; M[r, is2 + j] = 1; hi[r] = 1; r += 1
    lb = np.zeros(nv); ub = np.ones(nv)
    lb[iu1], ub[iu1] = A.min(), A.max()
    lb[iu2], ub[iu2] = B.min(), B.max()
    integrality = np.zeros(nv); integrality[is1:] = 1
    res = milp(c=np.zeros(nv), constraints=LinearConstraint(M.tocsr(), lo, hi), bounds=Bounds(lb, ub),
               integrality=integrality, options={"time_limit": time_limit, "disp": False})
    if res.x is None:
        sys.exit(f"MILP found no equilibrium within the time limit ({res.message}). Lower --n.")
    x, y = np.clip(res.x[nx:nx + m], 0, None), np.clip(res.x[ny:ny + n], 0, None)
    return x / x.sum(), y / y.sum()


def solve(A, B):
    if np.allclose(A + B, 0, atol=1e-9):
        x, y = zero_sum_lp(A)
        return x, y, "linear programming (zero-sum, exact on the grid)"
    x, y = milp_nash(A, B)
    return x, y, "mixed-integer programming (Sandholm-Gilpin-Conitzer; exact on the grid)"
