import numpy as np

from sensor_reliability.analysis.humidity import koehler_correction


def test_kappa_zero_is_identity():
    assert koehler_correction(10.0, 90.0, kappa=0.0) == 10.0


def test_correction_deflates_and_stays_positive():
    corrected = koehler_correction(10.0, 80.0, kappa=0.5)
    assert 0.0 < corrected < 10.0


def test_more_humid_means_more_deflation():
    assert koehler_correction(10.0, 50.0) > koehler_correction(10.0, 80.0)


def test_rh_cap_bounds_the_divergence():
    # At RH -> 100% the growth term diverges; the cap keeps it finite and equal to the cap value.
    capped = koehler_correction(10.0, 100.0, rh_cap=99.0)
    assert np.isfinite(capped)
    assert capped == koehler_correction(10.0, 99.0, rh_cap=99.0)


def test_vectorised():
    out = koehler_correction(np.array([10.0, 10.0]), np.array([50.0, 80.0]))
    assert out.shape == (2,)
    assert out[0] > out[1]
