import pandas as pd
import pytest

pytest.importorskip("rdflib")

from sensor_reliability.semantic.graph import (  # noqa: E402
    Q_MEAN_PM25_PER_NETWORK,
    build_graph,
)

# Two citizen days (mean 4) and their nearest reference on the same days (mean 12).
PAIRS = pd.DataFrame(
    [
        {"location_id": 1, "date": "2026-09-01", "cit_pm25": 3.0, "lat": 45.49, "lon": 9.19,
         "idsensore": 100, "dist_km": 0.5, "ref_pm25": 11.0,
         "station_name": "Ref A", "station_lat": 45.496, "station_lon": 9.191},
        {"location_id": 1, "date": "2026-09-02", "cit_pm25": 5.0, "lat": 45.49, "lon": 9.19,
         "idsensore": 100, "dist_km": 0.5, "ref_pm25": 13.0,
         "station_name": "Ref A", "station_lat": 45.496, "station_lon": 9.191},
    ]
)


def test_graph_has_expected_sensors_and_measurements():
    g = build_graph(PAIRS)
    from rdflib import RDF, Namespace

    saref = Namespace("https://saref.etsi.org/core/")
    sensors = set(g.subjects(RDF.type, saref.Sensor))
    measurements = set(g.subjects(RDF.type, saref.Measurement))
    assert len(sensors) == 2  # one citizen, one reference
    assert len(measurements) == 4  # 2 citizen days + 2 reference days


def test_mean_query_separates_networks():
    g = build_graph(PAIRS)
    means = {str(network): float(mean) for network, mean, _ in g.query(Q_MEAN_PM25_PER_NETWORK)}
    assert means["citizen"] == 4.0  # (3 + 5) / 2
    assert means["reference"] == 12.0  # (11 + 13) / 2
    assert means["citizen"] < means["reference"]
