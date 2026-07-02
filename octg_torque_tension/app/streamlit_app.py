"""Torque-Tension Analytical Model.

Manual-entry tool: the user supplies their own connection geometry, pipe body
geometry, material grade, and torque-turn data. Results are only as good as
the inputs — this is an analytical model, not a certified engineering tool.

Run locally:
    streamlit run octg_torque_tension/app/streamlit_app.py

Streamlit Community Cloud:
    Push repo root. Set main file to octg_torque_tension/app/streamlit_app.py.
    All dependencies in requirements.txt.

Architecture:
    All physics in octg_torque_tension/core/. Zero calculations in this file
    beyond simple UI bookkeeping (default/example comparison, display labels).
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from octg_torque_tension.core.connections import Connection
from octg_torque_tension.core.envelope import compute_envelope, check_operating_point, OperatingPoint, EnvelopeResult
from octg_torque_tension.core.geometry import (
    bccs_area,
    pipe_id_from_wall,
    polar_moment_annulus,
    wall_from_nominal_weight,
)
from octg_torque_tension.core.materials import P110, N80, L80, Q125, SteelGrade

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Torque-Tension Analytical Model",
    page_icon="🔩",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────

_GRADES: dict[str, SteelGrade] = {"P110": P110, "N80": N80, "L80": L80, "Q125": Q125}
_CONN_COLOR = "#1f77b4"

# Example presets — used only for the optional "cargar ejemplo" button and to
# detect whether the user is still on out-of-the-box (uncalibrated) values.
# Sourced from MODEL_NOTES estimates (BTC6.30, BSP6.05).
_EXAMPLES = {
    "Buttress / Shouldered": dict(
        cod=6.300, bcr=5.385, st_pin=5.500, l_b=9.375, l_fl=0.200, lf_area=60.0,
        pipe_od=5.500, pipe_wall=0.361,
        delta_mu=0.030, delta_ot=0.150,
        tq_max=30_600.0, design_factor=1.4, grade="P110",
    ),
    "Wedge": dict(
        cod=6.050, bcr=5.399, st_pin=5.500, l_b=9.375, l_fl=0.200, lf_area=60.0,
        pipe_od=5.500, pipe_wall=0.361,
        delta_mu=0.030, delta_ot=0.150,
        tq_max=39_800.0, design_factor=1.4, grade="P110",
    ),
}

_KEYS = [
    "geo_cod", "geo_bcr", "geo_st_pin", "geo_l_b", "geo_l_fl", "geo_lf_area",
    "pipe_od", "pipe_wall", "dt_delta_mu", "dt_delta_ot",
    "tq_max", "design_factor", "mat_grade",
]


def _init_defaults(conn_type: str) -> None:
    ex = _EXAMPLES[conn_type]
    st.session_state["geo_cod"] = ex["cod"]
    st.session_state["geo_bcr"] = ex["bcr"]
    st.session_state["geo_st_pin"] = ex["st_pin"]
    st.session_state["geo_l_b"] = ex["l_b"]
    st.session_state["geo_l_fl"] = ex["l_fl"]
    st.session_state["geo_lf_area"] = ex["lf_area"]
    st.session_state["pipe_od"] = ex["pipe_od"]
    st.session_state["pipe_wall"] = ex["pipe_wall"]
    st.session_state["dt_delta_mu"] = ex["delta_mu"]
    st.session_state["dt_delta_ot"] = ex["delta_ot"]
    st.session_state["tq_max"] = ex["tq_max"]
    st.session_state["design_factor"] = ex["design_factor"]
    st.session_state["mat_grade"] = ex["grade"]
    st.session_state["j_mode"] = "Calculado de COD/BCR"
    st.session_state["pipe_spec_mode"] = "Wall thickness"


def sticky_number_input(label: str, key: str, fallback: float, **kwargs):
    """number_input that survives being conditionally un-rendered.

    Streamlit deletes a widget's session_state entry when the widget isn't
    instantiated on a run (e.g. screw-jack fields while Wedge is selected).
    Without this, switching Wedge -> Buttress would silently reset those
    fields to their min_value instead of the user's last entry. We cache the
    last value under a plain (non-widget) key and re-seed before remount.
    """
    cache_key = f"_last_{key}"
    if key not in st.session_state:
        st.session_state[key] = st.session_state.get(cache_key, fallback)
    val = st.sidebar.number_input(label, key=key, **kwargs)
    st.session_state[cache_key] = val
    return val


# ── Sidebar ───────────────────────────────────────────────────────────────────

st.sidebar.title("🔩 Torque-Tension Analytical Model")
st.sidebar.divider()

# 1) Tipo de conexión — controla el screw-jack
st.sidebar.subheader("1. Tipo de conexión")
conn_type = st.sidebar.radio(
    "Tipo",
    ["Buttress / Shouldered", "Wedge"],
    key="conn_type",
    help="Buttress/Shouldered → screw-jack activo (F_TQ, Eq. 6). "
         "Wedge → sin screw-jack (F_TQ = 0, curva plana).",
)
has_screwjack = conn_type == "Buttress / Shouldered"

if not any(k in st.session_state for k in _KEYS):
    _init_defaults(conn_type)

if st.sidebar.button("↺ Cargar valores de ejemplo", help="Prellena con datos estimados de la tabla del paper (BTC6.30 / BSP6.05). Opcional — el modo principal es carga manual."):
    _init_defaults(conn_type)
    st.rerun()

st.sidebar.divider()

# 2) Geometría del pipe body — determina el OD/ID del caño
st.sidebar.subheader("2. Pipe body")
pipe_od = st.sidebar.number_input(
    "OD caño [in]", min_value=0.1, max_value=30.0, step=0.01, format="%.3f",
    key="pipe_od",
)
pipe_spec_mode = st.sidebar.radio(
    "Especificar por", ["Wall thickness", "Peso nominal [lb/ft]", "ID directo"],
    key="pipe_spec_mode", horizontal=True,
)
pipe_id_val = None
pipe_id_error = None
if pipe_spec_mode == "Wall thickness":
    pipe_wall = sticky_number_input(
        "Wall thickness [in]", "pipe_wall", _EXAMPLES[conn_type]["pipe_wall"],
        min_value=0.01, max_value=2.0, step=0.001, format="%.3f",
    )
    try:
        pipe_id_val = pipe_id_from_wall(pipe_od, pipe_wall)
    except ValueError as e:
        pipe_id_error = str(e)
elif pipe_spec_mode == "Peso nominal [lb/ft]":
    pipe_weight = st.sidebar.number_input(
        "Peso nominal [lb/ft]", min_value=1.0, max_value=200.0, step=0.5,
        format="%.1f", key="pipe_weight", value=20.0,
    )
    try:
        pipe_wall = wall_from_nominal_weight(pipe_od, pipe_weight)
        pipe_id_val = pipe_id_from_wall(pipe_od, pipe_wall)
    except ValueError as e:
        pipe_id_error = str(e)
else:  # ID directo — exact manufacturer value, no wall/weight approximation
    pipe_id_val = sticky_number_input(
        "ID caño [in]", "pipe_id_direct", _EXAMPLES[conn_type]["pipe_od"] - 2 * _EXAMPLES[conn_type]["pipe_wall"],
        min_value=0.01, max_value=29.9, step=0.001, format="%.3f",
        help="Dato exacto del fabricante — evita la aproximación plain-end de peso/wall.",
    )
    if pipe_id_val >= pipe_od:
        pipe_id_error = f"OD ({pipe_od} in) must exceed ID ({pipe_id_val} in)"
    pipe_wall = (pipe_od - pipe_id_val) / 2.0

if pipe_id_error:
    st.sidebar.error(f"Geometría de pipe body inválida: {pipe_id_error}")
    st.error(f"Geometría de pipe body inválida: {pipe_id_error}")
    st.stop()

if pipe_spec_mode == "ID directo":
    st.sidebar.caption(f"ID caño (dato directo) = **{pipe_id_val:.3f} in** — wall implícito = {pipe_wall:.3f} in")
else:
    st.sidebar.caption(f"ID caño (calculado) = **{pipe_id_val:.3f} in** — wall = {pipe_wall:.3f} in")

st.sidebar.divider()

# 3) Geometría de la conexión (BCCS / pin)
st.sidebar.subheader("3. Geometría de la conexión")
cod = st.sidebar.number_input(
    "COD — Coupling OD [in]", min_value=0.1, max_value=30.0,
    step=0.01, format="%.3f", key="geo_cod",
    help="Eq. 2 — debe superar el ID del caño (validado al calcular).",
)
bcr = st.sidebar.number_input(
    "BCR — Box Critical Root Diameter [in]", min_value=0.1,
    max_value=30.0, step=0.005, format="%.3f", key="geo_bcr",
    help="Eq. 2 — debe estar entre ID y COD (validado al calcular).",
)
st_pin = st.sidebar.number_input(
    "ST_pin — Pin Face OD [in]", min_value=0.1, max_value=30.0,
    step=0.005, format="%.3f", key="geo_st_pin",
    help="Eq. 3 — debe superar el ID del caño (validado al calcular).",
)

try:
    j_btc_geom = polar_moment_annulus(cod, bcr)
except ValueError as e:
    st.sidebar.error(f"COD/BCR inválidos: {e}")
    st.error(f"Geometría inválida — COD/BCR: {e}")
    st.stop()

j_mode = st.sidebar.radio(
    "J_BTC — Polar Moment", ["Calculado de COD/BCR", "Manual (valor del fabricante)"],
    key="j_mode", horizontal=True,
    help="Default = π/32×(COD⁴−BCR⁴). Esa fórmula anular no descuenta el material "
         "removido por la rosca — sobreescribí con el J real si lo tenés (CDS).",
)
if j_mode.startswith("Calculado"):
    j_btc = j_btc_geom
    st.sidebar.caption(f"J_BTC = π/32×(COD⁴−BCR⁴) = **{j_btc:.2f} in⁴**")
else:
    j_btc = sticky_number_input(
        "J_BTC — Polar Moment [in⁴]", "geo_j_btc_manual", j_btc_geom,
        min_value=0.01, max_value=10_000.0, step=0.1, format="%.2f",
    )
    st.sidebar.caption(f"Valor geométrico de referencia = {j_btc_geom:.2f} in⁴")

if has_screwjack:
    st.sidebar.markdown("**Screw-jack (Buttress)**")
    l_b = sticky_number_input(
        "L_B — Coupling Length [in]", "geo_l_b", _EXAMPLES[conn_type]["l_b"],
        min_value=0.1, max_value=60.0, step=0.05, format="%.3f",
    )
    l_fl = sticky_number_input(
        "LFL — Thread Lead [in/rev]", "geo_l_fl", _EXAMPLES[conn_type]["l_fl"],
        min_value=0.01, max_value=2.0, step=0.005, format="%.3f",
    )
    lf_area_val = sticky_number_input(
        "LF_area — Load-Flank Area [in²]", "geo_lf_area", _EXAMPLES[conn_type]["lf_area"],
        min_value=0.1, max_value=500.0, step=1.0, format="%.1f",
    )
else:
    l_b = l_fl = lf_area_val = None

st.sidebar.divider()

# 4) Material
st.sidebar.subheader("4. Material")
grade_choice = st.sidebar.selectbox(
    "Grado de acero", list(_GRADES.keys()) + ["Custom"], key="mat_grade",
)
if grade_choice == "Custom":
    c_smys = st.sidebar.number_input(
        "fSMYS [psi]", min_value=1000.0, max_value=300_000.0, value=110_000.0,
        step=1000.0, format="%.0f",
    )
    c_e = st.sidebar.number_input(
        "E — Young's modulus [psi]", min_value=1_000_000.0, max_value=60_000_000.0,
        value=30_000_000.0, step=100_000.0, format="%.0f",
    )
    try:
        grade = SteelGrade(name="Custom", smys=c_smys, E=c_e)
    except ValueError as e:
        st.sidebar.error(str(e))
        st.stop()
else:
    grade = _GRADES[grade_choice]

st.sidebar.divider()

# 5) Design factor
st.sidebar.subheader("5. Design factor")
design_factor = st.sidebar.number_input(
    "Design Factor", min_value=1.0, max_value=3.0, step=0.05, format="%.2f",
    key="design_factor",
    help="Paper cita DF=1.4 para BTC6.30 (Liu 2021). No confirmado para otras conexiones.",
)

st.sidebar.divider()

# 6) Delta turns — solo aplica a Buttress (screw-jack)
delta_mu_val = delta_ot_val = None
dt_mode = None
if has_screwjack:
    st.sidebar.subheader("6. Delta turns (screw-jack)")
    dt_mode = st.sidebar.radio(
        "Modo",
        ["Modo A — Tengo datos torque-turn", "Modo B — Estimar desde torque"],
        key="dt_mode",
        help="Δ_MU y Δ_OT no son derivables del modelo (Eq. 1 los toma como dato experimental).",
    )
    if dt_mode.startswith("Modo A"):
        delta_mu_val = sticky_number_input(
            "ΔMU — Make-up Delta Turns [rev]", "dt_delta_mu", _EXAMPLES[conn_type]["delta_mu"],
            min_value=0.0, max_value=5.0, step=0.005, format="%.3f",
        )
        delta_ot_val = sticky_number_input(
            "ΔOT — Operational Delta Turns @ Tq rated [rev]", "dt_delta_ot", _EXAMPLES[conn_type]["delta_ot"],
            min_value=0.0, max_value=5.0, step=0.005, format="%.3f",
        )
    else:
        # BANNER DESACTIVADO - reponer acá
        # st.sidebar.warning(
        #     "⚠️ Delta turns estimados por suposición lineal no validada — modo aproximado.",
        #     icon="⚠️",
        # )
        delta_mu_val = st.session_state.get("_last_dt_delta_mu", _EXAMPLES[conn_type]["delta_mu"])
        delta_ot_val = st.session_state.get("_last_dt_delta_ot", _EXAMPLES[conn_type]["delta_ot"])
        st.sidebar.caption(
            f"Usa ΔMU = {delta_mu_val:.3f} rev y ΔOT_rated = {delta_ot_val:.3f} rev "
            "(constantes asumidas, no medidas) escaladas linealmente con el torque "
            "aplicado (Torque aplicado / Torque operativo máx.)."
        )
else:
    st.sidebar.subheader("6. Delta turns")
    st.sidebar.caption("No aplica — conexión Wedge, F_TQ = 0 por construcción.")

st.sidebar.divider()

# 7) Condiciones operativas
st.sidebar.subheader("7. Condiciones operativas")
tq_max = st.sidebar.number_input(
    "Torque operativo máximo [ft·lbf]", min_value=100.0, max_value=200_000.0,
    step=100.0, format="%.0f", key="tq_max",
    help="Límite CDS de la conexión — define el eje X del envelope.",
)
tq_applied = st.sidebar.slider("Torque aplicado [ft·lbf]", 0, int(tq_max), int(tq_max * 0.8), 100)
hook_load = st.sidebar.slider("Hook Load [kips]", 0, 1500, 400, 10)

# ── Build Connection ─────────────────────────────────────────────────────────

try:
    conn = Connection(
        name="Custom",
        cod=cod,
        operating_torque_ft_lbf=float(tq_max),
        tension_capacity_kips=1.0,  # not used by compute_envelope/check_operating_point
        clearance_in=0.0,
        has_screwjack=has_screwjack,
        grade=grade,
        id_=pipe_id_val,
        bcr=bcr,
        st_pin=st_pin,
        l_b=l_b,
        l_fl=l_fl,
        lf_area_in2=lf_area_val,
        delta_mu=delta_mu_val,
        delta_ot=delta_ot_val,
    )
except ValueError as e:
    st.error(f"Geometría inválida: {e}")
    st.stop()

sj_overrides: dict = {}
if has_screwjack:
    sj_overrides = dict(lf_area_in2=lf_area_val, delta_mu=delta_mu_val, delta_ot=delta_ot_val)

# ── Compute ───────────────────────────────────────────────────────────────────

try:
    result = compute_envelope(conn, design_factor=design_factor, n_points=300,
                               pipe_od=pipe_od, j_bccs=j_btc, **sj_overrides)
except ValueError as e:
    st.error(f"Envelope error: {e}")
    st.stop()

try:
    op = check_operating_point(conn, float(tq_applied), float(hook_load),
                                design_factor=design_factor, pipe_od=pipe_od,
                                j_bccs=j_btc, **sj_overrides)
except ValueError as e:
    st.error(f"Operating point error: {e}")
    st.stop()


def _bccs_governs(op: OperatingPoint) -> bool:
    return op.bccs_applied_tension_kips < op.pipe_applied_tension_kips


bccs_gov = _bccs_governs(op)

# ── Calibration state — "using defaults/example" or "Modo B estimation" ───────

_ex = _EXAMPLES[conn_type]
_cmp_pairs = [
    (cod, _ex["cod"]), (bcr, _ex["bcr"]), (st_pin, _ex["st_pin"]),
    (pipe_od, _ex["pipe_od"]), (pipe_wall, _ex["pipe_wall"]),
]
if has_screwjack:
    _cmp_pairs += [(l_b, _ex["l_b"]), (l_fl, _ex["l_fl"]), (lf_area_val, _ex["lf_area"])]
using_example_values = all(abs(a - b) < 1e-9 for a, b in _cmp_pairs)
estimating_delta_turns = has_screwjack and dt_mode is not None and dt_mode.startswith("Modo B")
uncalibrated = using_example_values or estimating_delta_turns

# ── Title ─────────────────────────────────────────────────────────────────────

st.title("Torque-Tension Analytical Model")

# BANNER DESACTIVADO - reponer acá
# Always-on general disclaimer (calm tone)
# st.info(
#     "Modelo analítico — **no es una herramienta certificada**. "
#     "Verificar contra datos CDS del fabricante y criterios de la operadora antes de "
#     "cualquier decisión de campo.",
#     icon="ℹ️",
# )

# BANNER DESACTIVADO - reponer acá
# Conditional prominent warning — only when using example/default values or Modo B
# Lógica conservada (reasons se sigue calculando) — solo se suprime el render.
if uncalibrated:
    reasons = []
    if using_example_values:
        reasons.append("la geometría todavía corresponde a los **valores de ejemplo** (no se cargaron datos propios)")
    if estimating_delta_turns:
        reasons.append("los **delta turns están estimados** por suposición lineal (Modo B), no medidos")
    # st.warning(
    #     "**⚠️ RESULTADO PRELIMINAR** — " + "; y ".join(reasons) + ". "
    #     "No usar para decisiones de campo hasta reemplazar por datos reales.",
    #     icon="⚠️",
    # )

# ── KPI row ───────────────────────────────────────────────────────────────────

util_pct = op.utilization * 100

if uncalibrated:
    if op.safe:
        kpi_status, kpi_verdict = "⚠️ PRELIMINAR-SEGURO", "PRELIMINARY"
    else:
        kpi_status, kpi_verdict = "⚠️ PRELIMINAR-EXCEDIDO", "PRELIMINARY"
    governing_label = "BCCS" if bccs_gov else "Pipe body"
    governing_label += " — ejemplo/estimado"
else:
    if op.utilization <= 0.8:
        kpi_status, kpi_verdict = "✅ SEGURO", "RELIABLE"
    elif op.utilization <= 1.0:
        kpi_status, kpi_verdict = "⚠️ PRECAUCIÓN", "RELIABLE"
    else:
        kpi_status, kpi_verdict = "🚨 EXCEDIDO", "RELIABLE"
    governing_label = "BCCS (conexión)" if bccs_gov else "Pipe body"

# KPI DESACTIVADO - reponer acá
# c1, c2, c3, c4 = st.columns(4)
# c1.metric("Estado", kpi_status)
# c2.metric("Utilización", f"{util_pct:.1f}%", delta=f"{util_pct-100:.1f}% vs límite")
# c3.metric("Allowable [kips]", f"{op.allowable_kips:.1f}", help="Envelope / DF")
# c4.metric("Componente limitante", governing_label)

st.divider()

# ── Plot + table ──────────────────────────────────────────────────────────────

col_plot, col_table = st.columns([3, 1])

with col_plot:
    st.subheader("Torque–Tension Envelope")
    tq_x = result.torques_ft_lbf / 1_000  # kft·lbf

    fig, ax = plt.subplots(figsize=(9, 5.5))

    diff = result.bccs_curve_kips - result.pipe_curve_kips
    bccs_zone = diff < 0
    if bccs_zone.any() and uncalibrated:
        ax.fill_between(
            tq_x, result.bccs_curve_kips, result.pipe_curve_kips,
            where=bccs_zone, alpha=0.07, color="red", hatch="////",
            label="Zona BCCS-limitada (preliminar)",
        )

    # CURVA OCULTA - reponer acá
    # ax.plot(tq_x, result.pipe_curve_kips, color="black", lw=2.0, ls="-",
    #         label=f"Pipe body ({result.pipe_body_kips:.0f} kips)")

    bccs_label = "BCCS" + (" — ⚠️ ejemplo/estimado" if uncalibrated else "")
    # CURVA OCULTA - reponer acá
    # ax.plot(tq_x, result.bccs_curve_kips, color=_CONN_COLOR, lw=1.5, ls="--", alpha=0.85,
    #         label=bccs_label)

    ax.plot(tq_x, result.envelope_kips, color=_CONN_COLOR, lw=2.5, ls="-",
            label="Envelope")
    ax.fill_between(tq_x, result.envelope_kips, alpha=0.08, color=_CONN_COLOR)

    if result.has_screwjack and result.f_tq_kips is not None:
        pass
        # CURVA OCULTA - reponer acá
        # ax.plot(tq_x, result.f_tq_kips, color=_CONN_COLOR, lw=0.9, ls="-.",
        #         alpha=0.5, label="F_TQ screw-jack [kips]")

    if kpi_verdict == "RELIABLE":
        pt_c = "#2ca02c" if op.utilization <= 0.8 else ("#ff7f0e" if op.utilization <= 1.0 else "#d62728")
    else:
        pt_c = "#ff7f0e" if op.safe else "#d62728"

    ax.scatter([tq_applied / 1000], [hook_load], c=pt_c, s=140, zorder=6,
               edgecolors="black", lw=0.8, marker="*",
               label=f"Punto op. ({tq_applied/1000:.1f} kft·lbf, {hook_load} kips)")
    ax.annotate(
        f"  {hook_load} kips\n  Util: {util_pct:.1f}%\n  [{kpi_verdict}]",
        xy=(tq_applied / 1000, hook_load), fontsize=7.5, color=pt_c, fontweight="bold",
        va="bottom",
    )

    if uncalibrated and bccs_zone.any():
        mid_x = tq_x[bccs_zone].mean()
        mid_y = (result.bccs_curve_kips[bccs_zone].mean() + result.pipe_curve_kips[bccs_zone].mean()) / 2
        ax.text(mid_x, mid_y, "EJEMPLO / ESTIMADO", ha="center", va="center",
                fontsize=7, color="red", alpha=0.4, rotation=10, fontweight="bold")

    ax.set_xlabel("Applied Torque [kft·lbf]", fontsize=11)
    ax.set_ylabel("Applied Tension [kips]", fontsize=11)
    ax.set_title("Torque–Tension Envelope", fontsize=11, fontweight="bold")
    ax.set_xlim(0, tq_max / 1000)
    y_top = max(800.0, result.pipe_body_kips * 1.2, result.bccs_curve_kips.max() * 1.1, hook_load * 1.15)
    ax.set_ylim(0, y_top)
    ax.legend(fontsize=7.5, loc="lower left", framealpha=0.9)
    ax.grid(True, alpha=0.25)

    # BANNER DESACTIVADO - reponer acá
    # if uncalibrated:
    #     ax.text(
    #         0.99, 0.99, "⚠️ RESULTADO PRELIMINAR\nGeometría de ejemplo o\ndelta turns estimados",
    #         transform=ax.transAxes, fontsize=7, ha="right", va="top",
    #         color="red", alpha=0.5,
    #         bbox=dict(boxstyle="round", fc="white", ec="red", alpha=0.5),
    #     )

    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

# ── Results table ─────────────────────────────────────────────────────────────

with col_table:
    st.subheader("Valores Calculados")

    a_bccs = bccs_area(conn.cod, bcr)
    j_bccs = j_btc
    a_pipe = math.pi / 4 * (pipe_od**2 - pipe_id_val**2)
    sigma_axial = (op.f_tq_kips + op.hook_load_kips) * 1_000 / a_bccs if a_bccs > 0 else 0
    tau_outer = (float(tq_applied) * 12 * (conn.cod / 2) / j_bccs) if j_bccs > 0 else 0
    vm_stress = math.sqrt(sigma_axial**2 + 3 * tau_outer**2)

    rows = [
        ("A_BCCS [in²]", f"{a_bccs:.3f}"),
        ("J_BCCS [in⁴]", f"{j_bccs:.2f}"),
        ("A_pipe [in²]", f"{a_pipe:.3f}"),
        ("", ""),
        ("F_TQ Eq.6 [kips]", f"{op.f_tq_kips:.1f}"),
        ("P_BTC Eq.8 BCCS [kips]", f"{op.p_btc_kips:.1f}"),
        ("P_total Eq.9 [kips]", f"{op.p_total_kips:.1f}"),
        ("F_hook [kips]", f"{hook_load:.1f}"),
        ("", ""),
        ("BCCS curve [kips]", f"{op.bccs_applied_tension_kips:.1f}"),
        ("Pipe curve [kips]", f"{op.pipe_applied_tension_kips:.1f}"),
        ("Envelope [kips]", f"{op.envelope_kips:.1f}"),
        ("Allowable [kips]", f"{op.allowable_kips:.1f}"),
        ("Utilización", f"{util_pct:.1f}%"),
        ("", ""),
        ("σ_axial [psi]", f"{sigma_axial:,.0f}"),
        ("τ_outer [psi]", f"{tau_outer:,.0f}"),
        ("σ_VM [psi]", f"{vm_stress:,.0f}"),
        ("SMYS [psi]", f"{grade.smys:,.0f}"),
    ]

    for label, value in rows:
        if not label:
            st.write("")
            continue
        ca, cb = st.columns([1.7, 1])
        ca.caption(label)
        cb.markdown(f"**{value}**")

# ── Expanders ─────────────────────────────────────────────────────────────────

st.divider()

with st.expander("📐 Resumen de Geometría e Inputs"):
    c1, c2, c3 = st.columns(3)
    c1.metric("COD", f"{cod:.3f} in")
    c1.metric("BCR", f"{bcr:.3f} in")
    c1.metric("ST_pin", f"{st_pin:.3f} in")
    c2.metric("OD caño", f"{pipe_od:.3f} in")
    c2.metric("ID caño (calc.)", f"{pipe_id_val:.3f} in")
    c2.metric("Wall (calc.)", f"{pipe_wall:.3f} in")
    c3.metric("Torque operativo máx.", f"{tq_max:,.0f} ft·lbf")
    c3.metric("Screw-jack", "Sí (Buttress)" if has_screwjack else "No (Wedge)")
    if has_screwjack:
        st.caption(
            f"L_B = {l_b:.3f} in | LFL = {l_fl:.3f} in/rev | LF_area = {lf_area_val:.1f} in² | "
            f"ΔMU = {delta_mu_val:.3f} rev | ΔOT_rated = {delta_ot_val:.3f} rev "
            f"({'medido' if dt_mode and dt_mode.startswith('Modo A') else 'estimado'})"
        )

with st.expander("📖 Notas del Modelo y Limitaciones"):
    st.markdown("""
    **Modelo analítico — ecuaciones de interacción torque-tensión**

    | Ecuación | Descripción |
    |----------|-------------|
    | Eq. 1 | L_OT = (ΔMU + ΔOT) × LFL |
    | Eq. 2 | A_BCCS = π/4 × (COD² − BCR²) |
    | Eq. 3 | FA_pin = π/4 × (STpin² − ID²) |
    | Eq. 4 | εR = A_BCCS / (A_BCCS + FA_pin + LFArea) |
    | Eq. 5 | δ = LOT × εR |
    | Eq. 6 | F_TQ = δ × E × A_BCCS / L_B |
    | Eq. 7 | Q_T = 0.096167 × (J/D) × √(Ym²−(P/A)²) [ft·lbf] |
    | Eq. 8 | P_BTC = A × (fSMYS − √(fSMYS²−(Tq·D/(0.096167·J))²)) |
    | Eq. 9 | P_total = F_TQ + P_BTC |

    **Interpretación del eje Y:**
    - Curva Pipe: A_pipe·fSMYS − P_BTC_pipe(Tq)
    - Curva BCCS: A_BCCS·fSMYS − P_total(Tq)
    - Envelope: min(BCCS, Pipe)

    **Limitaciones:**
    - Δ_MU y Δ_OT son datos experimentales (Eq. 1) — no derivables del modelo. En Modo B,
      Δ_OT se estima asumiendo escala lineal con el torque aplicado (Δ_OT ∝ Tq); esta
      suposición NO está validada en el paper.
    - Modelo elástico (Beer, 2015); inválido más allá del límite de fluencia.
    - El wall/ID del caño derivado del peso nominal usa la aproximación API 5CT
      W ≈ 10.69·t·(OD−t) (plain-end); puede diferir levemente del peso de catálogo.
    - Herramienta de exploración analítica — no reemplaza el CDS del fabricante ni
      validación experimental (torque-turn, Fig. 11 del paper).
    """)

st.caption(
    "Imperial: in, lbf, psi, ft·lbf | Modelo analítico — no certificado para uso en campo"
)
