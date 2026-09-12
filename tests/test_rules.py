from sensor_reliability.quality.rules import (
    in_plausible_range,
    is_outdoor,
    is_saturated_humidity,
)


def test_in_plausible_range_pm():
    assert in_plausible_range("P2", 12.3)
    assert not in_plausible_range("P2", -1.0)
    assert not in_plausible_range("P2", 5000.0)


def test_in_plausible_range_humidity_bounds():
    assert in_plausible_range("humidity", 100.0)  # 100% RH is physically valid
    assert not in_plausible_range("humidity", 100.1)
    assert not in_plausible_range("humidity", None)


def test_unknown_value_type_passes():
    assert in_plausible_range("noise_LAeq", 42.0)


def test_saturated_humidity():
    assert is_saturated_humidity(100.0)
    assert is_saturated_humidity(99.0)
    assert not is_saturated_humidity(98.9)
    assert not is_saturated_humidity(None)


def test_is_outdoor():
    assert is_outdoor(0)
    assert not is_outdoor(1)
    assert not is_outdoor(None)
