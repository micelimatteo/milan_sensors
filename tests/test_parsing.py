import datetime as dt

from sensor_reliability.sensor_community import flatten

FETCHED_AT = dt.datetime(2026, 9, 12, 9, 0, tzinfo=dt.timezone.utc)

# Mirrors real API quirks: string values, a derived value that is already numeric and has no id,
# and a co-located node (BME280 humidity + SDS011 PM sharing one location).
RECORDS = [
    {
        "id": 30675246373,
        "timestamp": "2026-09-12 09:21:51",
        "location": {"id": 45825, "latitude": "45.434", "longitude": "9.116",
                     "altitude": "115.5", "country": "IT", "indoor": 0, "exact_location": 0},
        "sensor": {"id": 59971, "sensor_type": {"name": "BME280"}},
        "sensordatavalues": [
            {"id": 1, "value_type": "temperature", "value": "24.02"},
            {"id": 2, "value_type": "humidity", "value": "100.00"},
            {"value_type": "pressure_at_sealevel", "value": 102313.83},  # numeric, no id
        ],
    },
    {
        "id": 30675246400,
        "timestamp": "2026-09-12 09:22:01",
        "location": {"id": 45825, "latitude": "45.434", "longitude": "9.116",
                     "altitude": "115.5", "country": "IT", "indoor": 0, "exact_location": 0},
        "sensor": {"id": 59972, "sensor_type": {"name": "SDS011"}},
        "sensordatavalues": [
            {"id": 3, "value_type": "P1", "value": "12.3"},
            {"id": 4, "value_type": "P2", "value": None},  # missing value
        ],
    },
]


def test_flatten_row_count_matches_values():
    rows = flatten(RECORDS, FETCHED_AT)
    assert len(rows) == 5  # 3 + 2 sensordatavalues


def test_flatten_coerces_and_propagates():
    rows = flatten(RECORDS, FETCHED_AT)
    by_type = {r["value_type"]: r for r in rows}

    assert by_type["temperature"]["value"] == 24.02  # string -> float
    assert by_type["pressure_at_sealevel"]["value"] == 102313.83  # numeric passes through
    assert by_type["P2"]["value"] is None  # missing stays None

    temp = by_type["temperature"]
    assert temp["location_id"] == 45825
    assert temp["sensor_id"] == 59971
    assert temp["sensor_type"] == "BME280"
    assert temp["latitude"] == 45.434
    assert temp["indoor"] == 0
    assert temp["fetched_at"] == FETCHED_AT


def test_flatten_handles_missing_sections():
    rows = flatten([{"id": 1, "sensordatavalues": []}], FETCHED_AT)
    assert rows == []
