"""Model the citizen and reference sensors as an RDF graph with SAREF, and query it in SPARQL.

This is an optional, self-contained phase (it does not feed the analysis). It reads the committed
M5 artifact `artifacts/reference_pairs.csv` -- so it runs offline from a clean checkout -- and
builds a small graph:

- each citizen location and each ARPA station is a `saref:Sensor` with a WGS84 location and a
  `saref:measuresProperty` link to PM2.5;
- each daily reading is a `saref:Measurement` (value, unit, timestamp, property) made by a sensor;
- each citizen sensor links to its nearest reference sensor (`ex:nearestReference`).

Terms from SAREF core (https://saref.etsi.org/core/) and WGS84 geo are used as-is; project-specific
predicates (network, nearestReference, distanceToReferenceKm) live in a local namespace and are
labelled as such. See DESIGN.md decision 17.

    python -m sensor_reliability.semantic.graph
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF, RDFS, XSD

SAREF = Namespace("https://saref.etsi.org/core/")
GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
EX = Namespace("https://w3id.org/milan-sensors#")

PM25 = EX["PM2.5"]
UGM3 = EX["ug-m3"]


def _sensor(graph: Graph, uri, label: str, network: str, lat: float, lon: float) -> None:
    graph.add((uri, RDF.type, SAREF.Sensor))
    graph.add((uri, RDFS.label, Literal(label)))
    graph.add((uri, EX.network, Literal(network)))
    graph.add((uri, SAREF.measuresProperty, PM25))
    graph.add((uri, GEO.lat, Literal(lat, datatype=XSD.decimal)))
    graph.add((uri, GEO.long, Literal(lon, datatype=XSD.decimal)))


def _measurement(graph: Graph, uri, sensor, value: float, date: str) -> None:
    graph.add((uri, RDF.type, SAREF.Measurement))
    graph.add((sensor, SAREF.makesMeasurement, uri))
    graph.add((uri, SAREF.hasValue, Literal(round(value, 2), datatype=XSD.decimal)))
    graph.add((uri, SAREF.isMeasuredIn, UGM3))
    graph.add((uri, SAREF.relatesToProperty, PM25))
    graph.add((uri, SAREF.hasTimestamp, Literal(date, datatype=XSD.date)))


def build_graph(pairs: pd.DataFrame) -> Graph:
    """Build the RDF graph from the M5 citizen-reference pairs table."""
    g = Graph()
    g.bind("saref", SAREF)
    g.bind("geo", GEO)
    g.bind("ex", EX)

    g.add((PM25, RDF.type, SAREF.Property))
    g.add((PM25, RDFS.label, Literal("PM2.5")))
    g.add((UGM3, RDF.type, SAREF.UnitOfMeasure))
    g.add((UGM3, RDFS.label, Literal("ug/m3")))

    # Reference sensors and their measurements (one per station-day).
    for idsensore, rows in pairs.groupby("idsensore"):
        ref = EX[f"reference-{int(idsensore)}"]
        first = rows.iloc[0]
        _sensor(g, ref, str(first["station_name"]), "reference",
                float(first["station_lat"]), float(first["station_lon"]))
        for date, day in rows.groupby("date"):
            _measurement(g, EX[f"m-reference-{int(idsensore)}-{date}"], ref,
                         float(day.iloc[0]["ref_pm25"]), str(date))

    # Citizen sensors, their nearest reference, and their measurements.
    for location_id, rows in pairs.groupby("location_id"):
        cit = EX[f"citizen-{int(location_id)}"]
        first = rows.iloc[0]
        _sensor(g, cit, f"citizen node {int(location_id)}", "citizen",
                float(first["lat"]), float(first["lon"]))
        g.add((cit, EX.nearestReference, EX[f"reference-{int(first['idsensore'])}"]))
        g.add((cit, EX.distanceToReferenceKm,
               Literal(round(float(first["dist_km"]), 1), datatype=XSD.decimal)))
        for row in rows.itertuples(index=False):
            _measurement(g, EX[f"m-citizen-{int(location_id)}-{row.date}"], cit,
                         float(row.cit_pm25), str(row.date))
    return g


# --- SPARQL queries -----------------------------------------------------------------------------

Q_SENSORS_PER_NETWORK = """
PREFIX saref: <https://saref.etsi.org/core/>
PREFIX ex: <https://w3id.org/milan-sensors#>
SELECT ?network (COUNT(?s) AS ?sensors) WHERE {
  ?s a saref:Sensor ; ex:network ?network .
} GROUP BY ?network ORDER BY ?network
"""

Q_MEAN_PM25_PER_NETWORK = """
PREFIX saref: <https://saref.etsi.org/core/>
PREFIX ex: <https://w3id.org/milan-sensors#>
SELECT ?network (ROUND(AVG(?v)*10)/10 AS ?meanPm25) (COUNT(?m) AS ?n) WHERE {
  ?s a saref:Sensor ; ex:network ?network ; saref:makesMeasurement ?m .
  ?m saref:relatesToProperty ex:PM2.5 ; saref:hasValue ?v .
} GROUP BY ?network ORDER BY ?network
"""

# Join each citizen sensor to its nearest reference on the same day, in SPARQL, and average the
# bias -- reproducing the core of M5 as a graph query.
Q_BIAS_PER_LOCATION = """
PREFIX saref: <https://saref.etsi.org/core/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX ex: <https://w3id.org/milan-sensors#>
SELECT ?citizen (ROUND(AVG(?b)*10)/10 AS ?meanBias) (COUNT(?d) AS ?days) WHERE {
  ?cs ex:network "citizen" ; rdfs:label ?citizen ; ex:nearestReference ?rs ;
      saref:makesMeasurement ?cm .
  ?cm saref:hasTimestamp ?d ; saref:hasValue ?cv .
  ?rs saref:makesMeasurement ?rm .
  ?rm saref:hasTimestamp ?d ; saref:hasValue ?rv .
  BIND(?cv - ?rv AS ?b)
} GROUP BY ?citizen ORDER BY ?meanBias
"""

QUERIES = {
    "sensors per network": Q_SENSORS_PER_NETWORK,
    "mean PM2.5 per network": Q_MEAN_PM25_PER_NETWORK,
    "mean bias per citizen location (citizen - nearest reference)": Q_BIAS_PER_LOCATION,
}


def main() -> None:
    pairs = pd.read_csv("artifacts/reference_pairs.csv")
    g = build_graph(pairs)

    out = Path("artifacts/graph.ttl")
    g.serialize(destination=out, format="turtle")
    print(f"graph: {len(g)} triples -> {out}")

    for title, query in QUERIES.items():
        print(f"\n# {title}")
        for row in g.query(query):
            print("  " + "  ".join(str(v) for v in row))


if __name__ == "__main__":
    main()
