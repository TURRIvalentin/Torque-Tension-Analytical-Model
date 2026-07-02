"""Torque–tension operating envelope — two-curve model (MODEL_NOTES §6).

Each torque value produces two limits (Fig. 12–13 interpretation, HIPOTESIS DERIVADA):

    Applied_Tension_BCCS(Tq) = A_BCCS * fSMYS - P_total(Tq)          [coupling governs]
    Applied_Tension_Pipe(Tq) = A_pipe * fSMYS - P_BTC_pipe(Tq)        [pipe body governs]
    Envelope(Tq)             = min(BCCS, Pipe)                          [actual limit]

where P_total = F_TQ (Eq. 6) + P_BTC (Eq. 8), and P_BTC_pipe uses pipe body geometry.
This is nominal capacity — no design factor or other safety margin is applied anywhere
in this module. allowable(Tq) == envelope(Tq), identically.

_envelope_at_torque() is the ONLY place this formula is evaluated. Both compute_envelope
(the torque sweep used to plot the curve) and check_operating_point (the single-point
check used for utilization/verdict) call it — so the plotted curve and the allowable
used to judge a point can never diverge into two different numbers.

⚠️  ASSUMPTION: for the torque sweep, delta_ot scales linearly with Tq
    (delta_ot(Tq) = delta_ot_rated * Tq / Tq_op). This is NOT stated in the paper;
    it is an engineering assumption consistent with a linear torque-turn slope (Fig. 11).
    Replace with a callable when real Fig. 11 data are available.

Source: SPE-232499-MS pp. 11–13.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from octg_torque_tension.core.connections import Connection
from octg_torque_tension.core.geometry import bccs_area, fa_pin, polar_moment_annulus
from octg_torque_tension.core.interaction import p_btc, p_total
from octg_torque_tension.core.screwjack import (
    delta_displacement,
    epsilon_r,
    f_tq,
    l_ot,
)

_KIP = 1_000.0
_PIPE_OD = 5.5  # in — fixed for this study (all connections: 5.5-in 20# pipe body)


@dataclass
class EnvelopeResult:
    """Output of compute_envelope — ready for plotting.

    Field semantics:
        bccs_curve_kips : Applied_Tension_BCCS = A_BCCS*fSMYS − P_total [kips]
                          If screwjack_params_available=False, P_total = P_BTC only
                          (F_TQ contribution absent — result is optimistic for BTC).
        pipe_curve_kips : Applied_Tension_Pipe = A_pipe*fSMYS − P_BTC_pipe [kips]
                          Always computed; nearly flat (small torsional penalty on pipe body).
        envelope_kips   : min(bccs_curve, pipe_curve) at each torque point [kips] —
                          nominal capacity, no design factor.
        f_tq_kips       : screw-jack preload array [kips]; zeros for wedge,
                          None if BTC screw-jack params are unavailable.
        p_btc_bccs_kips : P_BTC for BCCS cross-section [kips] — torsional consumed capacity.
        pipe_body_kips  : A_pipe * fSMYS / 1000 — the Tq=0 reference (= Table 1 value).
    """

    torques_ft_lbf: np.ndarray
    bccs_curve_kips: np.ndarray
    pipe_curve_kips: np.ndarray
    envelope_kips: np.ndarray
    f_tq_kips: Optional[np.ndarray]   # None if BTC params missing
    p_btc_bccs_kips: np.ndarray
    pipe_body_kips: float
    connection_name: str
    has_screwjack: bool
    screwjack_params_available: bool


@dataclass
class OperatingPoint:
    """Single operating-point check against the two-curve envelope.

    Criterion: F_hook <= envelope(Tq) [nominal capacity, no design factor]
    """

    torque_ft_lbf: float
    hook_load_kips: float
    f_tq_kips: float                    # Eq. 6 screw-jack preload; 0 for wedge
    p_btc_kips: float                   # Eq. 8 consumed capacity (BCCS geometry)
    p_total_kips: float                 # Eq. 9 = F_TQ + P_BTC
    bccs_applied_tension_kips: float    # A_BCCS*fSMYS - P_total
    pipe_applied_tension_kips: float    # A_pipe*fSMYS - P_BTC_pipe
    envelope_kips: float                # min(BCCS, Pipe) — same value as the plotted curve
    allowable_kips: float               # = envelope_kips, identically (no design factor)
    utilization: float                  # F_hook / allowable
    safe: bool                          # F_hook <= allowable


def _resolve(conn_val: Optional[float], override: Optional[float]) -> Optional[float]:
    return override if override is not None else conn_val


def _envelope_at_torque(
    connection: Connection,
    tq_ft_lbf: float,
    tq_max_ft_lbf: float,
    a_bccs: float,
    j_bccs: float,
    a_pipe: float,
    j_pipe: float,
    pipe_od_val: float,
    smys: float,
    lf_area_in2: Optional[float],
    delta_mu: Optional[float],
    delta_ot_rated: Optional[float],
) -> tuple[float, float, float, float, float]:
    """Canonical single-torque evaluation of the two-curve envelope. All values in lbf.

    Returns (f_tq_val, p_btc_bccs_val, p_total_val, bccs_val, pipe_val, envelope_val).

    This is the single source of truth for the envelope formula (Eq. 6, 8, 9 combined).
    Do not reimplement it elsewhere — both the torque sweep (compute_envelope) and the
    single-point check (check_operating_point) call this function so that the plotted
    curve and the allowable used for utilization/verdict are always the same number.
    """
    pbtc_bccs_val = p_btc(tq_ft_lbf, connection.cod, j_bccs, smys, a_bccs)
    pbtc_pipe_val = p_btc(tq_ft_lbf, pipe_od_val, j_pipe, smys, a_pipe)

    f_tq_val = 0.0
    if connection.has_screwjack:
        st, lb, lfl = connection.st_pin, connection.l_b, connection.l_fl
        if all(v is not None for v in [lf_area_in2, delta_mu, delta_ot_rated, st, lb, lfl]):
            fa = fa_pin(st, connection.id_)
            eps = epsilon_r(a_bccs, fa, lf_area_in2)
            # ⚠️ ASSUMPTION: delta_ot scales linearly with torque
            fraction = tq_ft_lbf / tq_max_ft_lbf if tq_max_ft_lbf > 0 else 0.0
            dot_at = delta_ot_rated * fraction
            lot = l_ot(delta_mu, dot_at, lfl)
            d = delta_displacement(lot, eps)
            f_tq_val = f_tq(d, connection.grade.E, a_bccs, lb)

    ptotal_val = p_total(f_tq_val, pbtc_bccs_val)  # Eq. 9
    bccs_val = max(0.0, a_bccs * smys - ptotal_val)
    pipe_val = max(0.0, a_pipe * smys - pbtc_pipe_val)
    envelope_val = min(bccs_val, pipe_val)  # nominal capacity, no design factor
    return f_tq_val, pbtc_bccs_val, ptotal_val, bccs_val, pipe_val, envelope_val


def compute_envelope(
    connection: Connection,
    n_points: int = 200,
    lf_area_in2: Optional[float] = None,
    delta_mu: Optional[float] = None,
    delta_ot: Optional[float] = None,
    pipe_od: Optional[float] = None,
    j_bccs: Optional[float] = None,
) -> EnvelopeResult:
    """Generate torque–tension envelope for one connection (two-curve model).

    Sweeps torque from 0 to connection.operating_torque_ft_lbf, calling
    _envelope_at_torque at each step — the same function used by check_operating_point.

    Args:
        connection:    Connection dataclass with specs. BCR must be set.
        n_points:      Number of torque steps in the sweep.
        lf_area_in2:   Override for connection.lf_area_in2 [in²].
        delta_mu:      Override for connection.delta_mu [rev].
        delta_ot:      Override for connection.delta_ot [rev] — rated at operating torque.
                       ⚠️ Linearly scaled for intermediate Tq (see module docstring).
        pipe_od:       Pipe body outer diameter [in]. Defaults to 5.5 in (this study).
        j_bccs:        Override for the BCCS polar moment of inertia [in⁴]. Defaults
                       to the annular estimate π/32×(COD⁴−BCR⁴), which does not
                       account for material removed by the thread — supply the
                       manufacturer's measured value when available.

    Returns:
        EnvelopeResult with arrays in ft·lbf and kips.
    """
    if n_points < 2:
        raise ValueError(f"n_points must be >= 2, got {n_points}")

    pipe_od_val = pipe_od if pipe_od is not None else _PIPE_OD

    # ---- BCCS geometry ----
    bcr = connection.require("bcr", connection.bcr)
    a_bccs = bccs_area(connection.cod, bcr)
    j_bccs_val = j_bccs if j_bccs is not None else polar_moment_annulus(connection.cod, bcr)
    smys = connection.grade.smys

    # ---- Pipe body geometry ----
    a_pipe = math.pi / 4.0 * (pipe_od_val**2 - connection.id_**2)
    j_pipe = math.pi / 32.0 * (pipe_od_val**4 - connection.id_**4)
    pipe_capacity = a_pipe * smys  # lbf — Tq=0 reference

    # ---- Torque sweep ----
    tq_max = connection.operating_torque_ft_lbf
    torques = np.linspace(0.0, tq_max, n_points)

    lf = _resolve(connection.lf_area_in2, lf_area_in2)
    dmu = _resolve(connection.delta_mu, delta_mu)
    dot_rated = _resolve(connection.delta_ot, delta_ot)

    if not connection.has_screwjack:
        screw_available = True  # Wedge: F_TQ = 0 by construction regardless of params
    else:
        missing = [n for n, v in [
            ("lf_area_in2", lf), ("delta_mu", dmu), ("delta_ot", dot_rated),
            ("st_pin", connection.st_pin), ("l_b", connection.l_b), ("l_fl", connection.l_fl),
        ] if v is None]
        screw_available = not missing

    f_tq_list, pbtc_bccs_list, bccs_list, pipe_list, env_list = [], [], [], [], []
    for tq in torques:
        f_tq_val, pbtc_bccs_val, _ptotal_val, bccs_val, pipe_val, env_val = _envelope_at_torque(
            connection, tq, tq_max, a_bccs, j_bccs_val, a_pipe, j_pipe, pipe_od_val, smys,
            lf, dmu, dot_rated,
        )
        f_tq_list.append(f_tq_val)
        pbtc_bccs_list.append(pbtc_bccs_val)
        bccs_list.append(bccs_val)
        pipe_list.append(pipe_val)
        env_list.append(env_val)

    f_tq_arr = np.array(f_tq_list) if screw_available else None

    return EnvelopeResult(
        torques_ft_lbf=torques,
        bccs_curve_kips=np.array(bccs_list) / _KIP,
        pipe_curve_kips=np.array(pipe_list) / _KIP,
        envelope_kips=np.array(env_list) / _KIP,
        f_tq_kips=f_tq_arr / _KIP if f_tq_arr is not None else None,
        p_btc_bccs_kips=np.array(pbtc_bccs_list) / _KIP,
        pipe_body_kips=pipe_capacity / _KIP,
        connection_name=connection.name,
        has_screwjack=connection.has_screwjack,
        screwjack_params_available=screw_available,
    )


def check_operating_point(
    connection: Connection,
    tq_ft_lbf: float,
    f_hook_kips: float,
    lf_area_in2: Optional[float] = None,
    delta_mu: Optional[float] = None,
    delta_ot: Optional[float] = None,
    pipe_od: Optional[float] = None,
    j_bccs: Optional[float] = None,
) -> OperatingPoint:
    """Evaluate a single (Tq, F_hook) point against the two-curve envelope.

    Criterion: F_hook <= envelope(Tq) [nominal capacity, no design factor]
    where envelope(Tq) = min(Applied_Tension_BCCS, Applied_Tension_Pipe), computed by
    the same _envelope_at_torque() call used by compute_envelope's sweep.

    Args:
        connection:   Connection to check. BCR must be set.
        tq_ft_lbf:   Applied torque [ft·lbf].
        f_hook_kips: Applied hook load [kips].
        lf_area_in2, delta_mu, delta_ot: Override values for BTC screw-jack params.
        pipe_od: Pipe body outer diameter [in]. Defaults to 5.5 in (this study).
        j_bccs: Override for the BCCS polar moment of inertia [in⁴]. Defaults to
               the annular estimate π/32×(COD⁴−BCR⁴) — see compute_envelope.

    Returns:
        OperatingPoint with all intermediate quantities and safe/unsafe flag.
    """
    if tq_ft_lbf < 0:
        raise ValueError(f"tq_ft_lbf must be >= 0, got {tq_ft_lbf}")
    if f_hook_kips < 0:
        raise ValueError(f"f_hook_kips must be >= 0, got {f_hook_kips}")

    pipe_od_val = pipe_od if pipe_od is not None else _PIPE_OD

    bcr = connection.require("bcr", connection.bcr)
    a_bccs = bccs_area(connection.cod, bcr)
    j_bccs_val = j_bccs if j_bccs is not None else polar_moment_annulus(connection.cod, bcr)
    smys = connection.grade.smys

    a_pipe = math.pi / 4.0 * (pipe_od_val**2 - connection.id_**2)
    j_pipe = math.pi / 32.0 * (pipe_od_val**4 - connection.id_**4)

    lf = _resolve(connection.lf_area_in2, lf_area_in2)
    dmu = _resolve(connection.delta_mu, delta_mu)
    dot_rated = _resolve(connection.delta_ot, delta_ot)
    tq_max = connection.operating_torque_ft_lbf

    f_tq_val, pbtc_bccs_val, ptotal_val, bccs_val, pipe_val, env_val = _envelope_at_torque(
        connection, tq_ft_lbf, tq_max, a_bccs, j_bccs_val, a_pipe, j_pipe, pipe_od_val, smys,
        lf, dmu, dot_rated,
    )

    allowable = env_val  # nominal capacity, identical to the plotted envelope — no design factor
    hook_lbf = f_hook_kips * _KIP
    utilization = hook_lbf / allowable if allowable > 0 else float("inf")

    return OperatingPoint(
        torque_ft_lbf=tq_ft_lbf,
        hook_load_kips=f_hook_kips,
        f_tq_kips=f_tq_val / _KIP,
        p_btc_kips=pbtc_bccs_val / _KIP,
        p_total_kips=ptotal_val / _KIP,
        bccs_applied_tension_kips=bccs_val / _KIP,
        pipe_applied_tension_kips=pipe_val / _KIP,
        envelope_kips=env_val / _KIP,
        allowable_kips=allowable / _KIP,
        utilization=utilization,
        safe=utilization <= 1.0,
    )
