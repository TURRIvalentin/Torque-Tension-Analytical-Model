"""Torque–tension operating envelope — two-curve model (MODEL_NOTES §6).

Each torque value produces two limits (Fig. 12–13 interpretation, HIPOTESIS DERIVADA):

    Applied_Tension_BCCS(Tq) = A_BCCS * fSMYS - P_total(Tq)          [coupling governs]
    Applied_Tension_Pipe(Tq) = A_pipe * fSMYS - P_BTC_pipe(Tq)        [pipe body governs]
    Envelope(Tq)             = min(BCCS, Pipe)                          [actual limit]

where P_total = F_TQ (Eq. 6) + P_BTC (Eq. 8), and P_BTC_pipe uses pipe body geometry.

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
        envelope_kips   : min(bccs_curve, pipe_curve) at each torque point [kips].
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
    design_factor: float
    connection_name: str
    has_screwjack: bool
    screwjack_params_available: bool


@dataclass
class OperatingPoint:
    """Single operating-point check against the two-curve envelope.

    Criterion: F_hook <= envelope(Tq) / DF
    """

    torque_ft_lbf: float
    hook_load_kips: float
    f_tq_kips: float                    # Eq. 6 screw-jack preload; 0 for wedge
    p_btc_kips: float                   # Eq. 8 consumed capacity (BCCS geometry)
    p_total_kips: float                 # Eq. 9 = F_TQ + P_BTC
    bccs_applied_tension_kips: float    # A_BCCS*fSMYS - P_total
    pipe_applied_tension_kips: float    # A_pipe*fSMYS - P_BTC_pipe
    envelope_kips: float                # min(BCCS, Pipe)
    allowable_kips: float               # envelope / DF
    utilization: float                  # F_hook / allowable
    safe: bool                          # F_hook <= allowable


def _resolve(conn_val: Optional[float], override: Optional[float]) -> Optional[float]:
    return override if override is not None else conn_val


def compute_envelope(
    connection: Connection,
    design_factor: float = 1.4,
    n_points: int = 200,
    lf_area_in2: Optional[float] = None,
    delta_mu: Optional[float] = None,
    delta_ot: Optional[float] = None,
) -> EnvelopeResult:
    """Generate torque–tension envelope for one connection (two-curve model).

    Sweeps torque from 0 to connection.operating_torque_ft_lbf and computes the
    BCCS curve, pipe curve, and envelope at each step.

    Args:
        connection:    Connection dataclass with specs. BCR must be set.
        design_factor: Applied at check time (envelope / DF). Paper cites 1.4 for BTC6.30.
        n_points:      Number of torque steps in the sweep.
        lf_area_in2:   Override for connection.lf_area_in2 [in²].
        delta_mu:      Override for connection.delta_mu [rev].
        delta_ot:      Override for connection.delta_ot [rev] — rated at operating torque.
                       ⚠️ Linearly scaled for intermediate Tq (see module docstring).

    Returns:
        EnvelopeResult with arrays in ft·lbf and kips.
    """
    if design_factor <= 0:
        raise ValueError(f"design_factor must be positive, got {design_factor}")
    if n_points < 2:
        raise ValueError(f"n_points must be >= 2, got {n_points}")

    # ---- BCCS geometry ----
    bcr = connection.require("bcr", connection.bcr)
    a_bccs = bccs_area(connection.cod, bcr)
    j_bccs = polar_moment_annulus(connection.cod, bcr)
    smys = connection.grade.smys
    bccs_capacity = a_bccs * smys  # lbf — upper bound at Tq=0, P=0

    # ---- Pipe body geometry (fixed OD=5.5 in for this study) ----
    a_pipe = math.pi / 4.0 * (_PIPE_OD**2 - connection.id_**2)
    j_pipe = math.pi / 32.0 * (_PIPE_OD**4 - connection.id_**4)
    pipe_capacity = a_pipe * smys  # lbf

    # ---- Torque sweep ----
    tq_max = connection.operating_torque_ft_lbf
    torques = np.linspace(0.0, tq_max, n_points)

    # ---- P_BTC for BCCS and pipe body (always computable) ----
    pbtc_bccs_arr = np.array([p_btc(tq, connection.cod, j_bccs, smys, a_bccs) for tq in torques])
    pbtc_pipe_arr = np.array([p_btc(tq, _PIPE_OD, j_pipe, smys, a_pipe) for tq in torques])

    # ---- F_TQ sweep (screw-jack) ----
    screw_available = False
    f_tq_arr: Optional[np.ndarray] = None

    if not connection.has_screwjack:
        # Wedge: F_TQ = 0 by construction regardless of params
        screw_available = True
        f_tq_arr = np.zeros(n_points)

    else:
        lf = _resolve(connection.lf_area_in2, lf_area_in2)
        dmu = _resolve(connection.delta_mu, delta_mu)
        dot_rated = _resolve(connection.delta_ot, delta_ot)
        st = connection.st_pin
        lb = connection.l_b
        lfl = connection.l_fl

        missing = [n for n, v in [
            ("lf_area_in2", lf), ("delta_mu", dmu), ("delta_ot", dot_rated),
            ("st_pin", st), ("l_b", lb), ("l_fl", lfl),
        ] if v is None]

        if not missing:
            fa = fa_pin(st, connection.id_)
            eps = epsilon_r(a_bccs, fa, lf)  # constant over sweep (geometry fixed)
            f_tq_list = []
            for tq in torques:
                # ⚠️ ASSUMPTION: delta_ot scales linearly with torque
                fraction = tq / tq_max if tq_max > 0 else 0.0
                dot_at = dot_rated * fraction
                lot = l_ot(dmu, dot_at, lfl)
                d = delta_displacement(lot, eps)
                f_tq_list.append(f_tq(d, connection.grade.E, a_bccs, lb))
            f_tq_arr = np.array(f_tq_list)
            screw_available = True

    # ---- Two curves ----
    # BCCS curve: A_BCCS*fSMYS - F_TQ - P_BTC_BCCS
    # When F_TQ unavailable (BTC, params missing): use 0.0 — optimistic, flagged by screwjack_params_available
    f_tq_for_bccs = f_tq_arr if f_tq_arr is not None else np.zeros(n_points)
    ptotal_arr = f_tq_for_bccs + pbtc_bccs_arr  # lbf — Eq. 9

    bccs_arr = np.maximum(0.0, bccs_capacity - ptotal_arr)   # lbf, clamped at 0
    pipe_arr = np.maximum(0.0, pipe_capacity - pbtc_pipe_arr)  # lbf, clamped at 0
    env_arr = np.minimum(bccs_arr, pipe_arr)                   # lbf

    return EnvelopeResult(
        torques_ft_lbf=torques,
        bccs_curve_kips=bccs_arr / _KIP,
        pipe_curve_kips=pipe_arr / _KIP,
        envelope_kips=env_arr / _KIP,
        f_tq_kips=f_tq_arr / _KIP if f_tq_arr is not None else None,
        p_btc_bccs_kips=pbtc_bccs_arr / _KIP,
        pipe_body_kips=pipe_capacity / _KIP,
        design_factor=design_factor,
        connection_name=connection.name,
        has_screwjack=connection.has_screwjack,
        screwjack_params_available=screw_available,
    )


def check_operating_point(
    connection: Connection,
    tq_ft_lbf: float,
    f_hook_kips: float,
    design_factor: float = 1.4,
    lf_area_in2: Optional[float] = None,
    delta_mu: Optional[float] = None,
    delta_ot: Optional[float] = None,
) -> OperatingPoint:
    """Evaluate a single (Tq, F_hook) point against the two-curve envelope.

    Criterion: F_hook <= envelope(Tq) / DF
    where envelope(Tq) = min(Applied_Tension_BCCS, Applied_Tension_Pipe).

    Args:
        connection:   Connection to check. BCR must be set.
        tq_ft_lbf:   Applied torque [ft·lbf].
        f_hook_kips: Applied hook load [kips].
        design_factor: Safety factor (default 1.4).
        lf_area_in2, delta_mu, delta_ot: Override values for BTC screw-jack params.

    Returns:
        OperatingPoint with all intermediate quantities and safe/unsafe flag.
    """
    if tq_ft_lbf < 0:
        raise ValueError(f"tq_ft_lbf must be >= 0, got {tq_ft_lbf}")
    if f_hook_kips < 0:
        raise ValueError(f"f_hook_kips must be >= 0, got {f_hook_kips}")

    bcr = connection.require("bcr", connection.bcr)
    a_bccs = bccs_area(connection.cod, bcr)
    j_bccs = polar_moment_annulus(connection.cod, bcr)
    smys = connection.grade.smys

    # Pipe body
    a_pipe = math.pi / 4.0 * (_PIPE_OD**2 - connection.id_**2)
    j_pipe = math.pi / 32.0 * (_PIPE_OD**4 - connection.id_**4)

    # P_BTC for BCCS and pipe (Eq. 8)
    pbtc_bccs_val = p_btc(tq_ft_lbf, connection.cod, j_bccs, smys, a_bccs)
    pbtc_pipe_val = p_btc(tq_ft_lbf, _PIPE_OD, j_pipe, smys, a_pipe)

    # F_TQ (Eq. 6)
    f_tq_val = 0.0
    if connection.has_screwjack:
        lf = _resolve(connection.lf_area_in2, lf_area_in2)
        dmu = _resolve(connection.delta_mu, delta_mu)
        dot_rated = _resolve(connection.delta_ot, delta_ot)
        st = connection.st_pin
        lb = connection.l_b
        lfl = connection.l_fl
        if all(v is not None for v in [lf, dmu, dot_rated, st, lb, lfl]):
            fa = fa_pin(st, connection.id_)
            eps = epsilon_r(a_bccs, fa, lf)
            tq_max = connection.operating_torque_ft_lbf
            fraction = tq_ft_lbf / tq_max if tq_max > 0 else 0.0
            dot_at = dot_rated * fraction
            lot = l_ot(dmu, dot_at, lfl)
            d = delta_displacement(lot, eps)
            f_tq_val = f_tq(d, connection.grade.E, a_bccs, lb)

    # Eq. 9
    ptotal_val = p_total(f_tq_val, pbtc_bccs_val)

    # Two curves and envelope
    bccs_val = max(0.0, a_bccs * smys - ptotal_val)
    pipe_val = max(0.0, a_pipe * smys - pbtc_pipe_val)
    env_val = min(bccs_val, pipe_val)
    allowable = env_val / design_factor
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
