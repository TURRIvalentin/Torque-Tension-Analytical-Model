# OCTG Torque–Tension Interaction Model

**Analytical implementation of SPE-232499-MS — "OCTG Torque vs Tension: A Growing Concern for Well Integrity"**
Ott, Del Castillo, Broussard — Fermata Connections (2026)

---

## ⚠️ Safety Notice

> The BCCS coupling curve uses **placeholder parameters** (BCR, STpin, LB, LFArea, ΔMU, ΔOT)
> that are **not given numerically in the paper**. Results in BCCS-governed zones are
> **PRELIMINARY** and must **NOT** be used for field decisions until calibrated against
> manufacturer CDS data and Fig. 11 torque-turn experimental data.
>
> The **pipe body curve is reliable** (anchored to API 5CT / Table 1 geometry — 641 kips).

---

## Quick Start

### Run locally

```bash
pip install -r requirements.txt
streamlit run octg_torque_tension/app/streamlit_app.py
```

### Run tests

```bash
pytest octg_torque_tension/tests/ -v
```

---

## Deploy on Streamlit Community Cloud

1. Push this repository root to GitHub (public or private repo).
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Set **Main file path** to:
   ```
   octg_torque_tension/app/streamlit_app.py
   ```
4. Streamlit Cloud will install `requirements.txt` automatically.
5. Click **Deploy**.

---

## Model Overview

The app implements the two-curve torque–tension envelope from MODEL_NOTES §6 (HIPÓTESIS DERIVADA):

| Curve | Formula | Status |
|-------|---------|--------|
| Pipe body | A\_pipe·fSMYS − P\_BTC\_pipe(Tq) | ✓ Reliable — API 5CT geometry |
| BCCS (coupling) | A\_BCCS·fSMYS − F\_TQ(Tq) − P\_BTC\_BCCS(Tq) | ⚠️ NOT CALIBRATED — placeholder params |
| Envelope | min(BCCS, Pipe) | Reliable only in pipe-limited zone |

### Equations (SPE-232499-MS)

| Eq. | Description | Notes |
|-----|-------------|-------|
| 1–3 | L\_OT, A\_BCCS, FA\_pin | Paper geometry |
| 4–6 | εR, δ, F\_TQ (screw-jack) | Confirmed from PDF images |
| 7 | Q\_T — torsional capacity [ft·lbf] | 0.096167 = 2/(12√3), API RP 7G |
| 8 | P\_BTC — consumed tensile capacity | fSMYS **minus** sqrt form |
| 9 | P\_total = F\_TQ + P\_BTC | Not F\_TQ + F\_hook |

### Connections (Table 1, SPE-232499-MS)

All for 5.5-in 20# P110 casing:

| Connection | COD [in] | Tq\_op [ft·lbf] | Clearance [in] | Type |
|------------|----------|-----------------|----------------|------|
| BTC6.30 | 6.300 | 30,600 | 0.225 | Shouldered (screw-jack) |
| BTC6.05 | 6.050 | 30,600 | 0.350 | Shouldered (screw-jack) |
| BSP6.05 | 6.050 | 39,800 | 0.350 | Wedge (no screw-jack) |
| BSL5.90 | 5.900 | 38,750 | 0.425 | Wedge (no screw-jack) |

---

## Project Structure

```
octg_torque_tension/
  core/
    connections.py   — Connection dataclass + pre-built catalog (Table 1)
    materials.py     — SteelGrade (P110, N80, L80, Q125)
    geometry.py      — bccs_area, fa_pin, polar_moment_annulus
    screwjack.py     — Eq. 1–6: l_ot, epsilon_r, delta_displacement, f_tq
    interaction.py   — Eq. 7–9: q_t, p_btc, p_total
    envelope.py      — Two-curve model: compute_envelope, check_operating_point
  app/
    streamlit_app.py — Streamlit UI (reads from core/ only)
  examples/
    plot_envelopes.py — Matplotlib script reproducing Fig. 12–13
  tests/             — 100 pytest tests (100% green)
MODEL_NOTES.md       — Full derivation, assumptions, placeholder inventory
requirements.txt
```

---

## Calibration Status

Two calibration symptoms must be corrected simultaneously when real CDS + Fig. 11 data arrive:

1. **BTC6.05 crossover** — placeholder params produce crossover at ~8.9 kft·lbf; paper shows ~20 kft·lbf
2. **BTC6.30 convergence** — placeholder BCCS sits ~230 kips above pipe; paper shows convergence

Both symptoms share the same parameter set (BCR, ΔMU, ΔOT) — fixing one without the other indicates a modeling error. See MODEL_NOTES.md §6 for the full calibration criteria.

---

*Units: Imperial throughout — inches, psi, lbf, ft·lbf, kips.*
