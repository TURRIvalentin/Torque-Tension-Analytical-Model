"""Geometric cross-section calculations for OCTG connections.

All inputs and outputs in inches (in) or square inches (in²) / in⁴.
Sources: SPE-232499-MS Eq. 2, Eq. 3; API 5B (2023).
"""
import math


def bccs_area(cod: float, bcr: float) -> float:
    """Eq. 2 — Box Critical Cross Section annular area (in²).

    A_BCCS = π/4 × (COD² − BCR²)

    SPE-232499-MS p. 11: 'where COD is the coupling outer-diameter and BCR is
    box critical root diameter where the last engaged pin thread meets the box thread.'

    Args:
        cod: Coupling outer diameter [in].
        bcr: Box critical root diameter — last engaged pin thread (in).

    Returns:
        A_BCCS cross-sectional area [in²].
    """
    if cod <= 0 or bcr <= 0:
        raise ValueError(f"Diameters must be positive: COD={cod}, BCR={bcr}")
    if cod <= bcr:
        raise ValueError(f"COD ({cod} in) must exceed BCR ({bcr} in)")
    return math.pi / 4.0 * (cod**2 - bcr**2)


def fa_pin(st_pin: float, id_: float) -> float:
    """Eq. 3 — Pin face contact area (in²).

    FA_pin = π/4 × (STpin² − ID²)

    SPE-232499-MS p. 11: 'where STpin is the outside diameter of the pin-face
    contact and ID is the inside diameter of the same region.'

    Args:
        st_pin: Outside diameter of pin-face contact surface [in].
        id_: Inside diameter of the pin-face region [in].

    Returns:
        FA_pin contact area [in²].
    """
    if st_pin <= 0 or id_ <= 0:
        raise ValueError(f"Diameters must be positive: STpin={st_pin}, ID={id_}")
    if st_pin <= id_:
        raise ValueError(f"STpin ({st_pin} in) must exceed ID ({id_} in)")
    return math.pi / 4.0 * (st_pin**2 - id_**2)


def polar_moment_annulus(od: float, id_: float) -> float:
    """Polar moment of inertia for a hollow annular section (in⁴).

    J = π/32 × (OD⁴ − ID⁴)

    Used for J_BTC in Eq. 7 and Eq. 8 (torsional yield formulation).

    Args:
        od: Outer diameter [in].
        id_: Inner diameter [in].

    Returns:
        Polar moment of inertia J [in⁴].
    """
    if od <= 0 or id_ <= 0:
        raise ValueError(f"Diameters must be positive: OD={od}, ID={id_}")
    if od <= id_:
        raise ValueError(f"OD ({od} in) must exceed ID ({id_} in)")
    return math.pi / 32.0 * (od**4 - id_**4)


def lf_area(
    tpi: float,
    engagement_length: float,
    pitch_diameter: float,
    flank_angle_deg: float = 10.0,
) -> float:
    """Helical load-flank area — active thread surface bearing axial load (in²).

    SPE-232499-MS p. 12: 'The helical load-flank area, LFArea, represents the
    active thread surface bearing load up to the operating limit.'

    # TODO: Refine with exact thread root geometry from API 5B Table B.4.
    # The current approximation uses a rectangular thread height model.
    # Treat as INPUT via Connection.lf_area_in2 if accurate geometry is unavailable.

    Args:
        tpi: Threads per inch [in⁻¹]. For BTC 5.5-in: 5 TPI (API 5B).
        engagement_length: Axial thread engagement length [in].
            Typically ~half of coupling length for BTC.
        pitch_diameter: Mean pitch diameter of engaged threads [in].
            Approx. average of COD and pipe OD.
        flank_angle_deg: Load flank angle from pipe axis [degrees].
            BTC buttress load flank: 10° (API 5B); stab flank: 54.7°.

    Returns:
        LFArea helical load-flank area [in²].
    """
    if tpi <= 0 or engagement_length <= 0 or pitch_diameter <= 0:
        raise ValueError("tpi, engagement_length, and pitch_diameter must be positive")
    thread_height = (1.0 / tpi) * 0.625  # API 5B buttress: height ≈ 0.625 × pitch
    n_threads = engagement_length * tpi
    circumference = math.pi * pitch_diameter
    return n_threads * circumference * thread_height * math.cos(math.radians(flank_angle_deg))
