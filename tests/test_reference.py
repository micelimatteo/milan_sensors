import pandas as pd

from sensor_reliability.analysis.reference import (
    assign_nearest,
    error_percentiles,
    haversine_km,
)


def test_haversine_zero_and_degree():
    assert haversine_km(45.0, 9.0, 45.0, 9.0) == 0.0
    # one degree of latitude is ~111 km
    assert abs(haversine_km(45.0, 9.0, 46.0, 9.0) - 111.2) < 1.0


def test_haversine_known_pair():
    # Milano v.Marche to v.Senato, ~2.9 km
    d = haversine_km(45.49632, 9.19093, 45.47050, 9.19746)
    assert 2.5 < d < 3.3


def test_error_percentiles():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    p = error_percentiles(s)
    assert p["p50"] == 5.5
    assert p["p90"] > p["p50"]


def test_assign_nearest_picks_closest_station():
    citizen = pd.DataFrame(
        {"location_id": [1, 2], "lat": [45.496, 45.478], "lon": [9.191, 9.232]}
    )
    stations = pd.DataFrame(
        {"idsensore": [20529, 10283],
         "lat": [45.49632, 45.478347], "lng": [9.19093, 9.231667]}
    )
    out = assign_nearest(citizen, stations).set_index("location_id")
    assert out.loc[1, "idsensore"] == 20529  # location 1 nearest to Marche
    assert out.loc[2, "idsensore"] == 10283  # location 2 nearest to Pascal
    assert out.loc[1, "dist_km"] < 1.0
