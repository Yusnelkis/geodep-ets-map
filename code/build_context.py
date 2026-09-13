"""Regional and national context for the Atlas (policy layer).

Inputs : data/ets_installations_2025.parquet (technical extract), data/ref/sources.json + the files it lists
         (NUTS-2 2024 polygons from GISCO; Eurostat regional GDP, regional population, national GHG inventory).
Outputs: data/nuts2_assignment.csv   – installation_id -> NUTS-2 code (point in polygon, DuckDB spatial)
         docs/data/context.json      – per NUTS-2 region: name, country, population, GDP; per country: national GHG total;
                                       CBAM phase-out factors. Every value carries its source key from sources.json.
Rule: nothing is estimated. A region without GDP or population in Eurostat gets null, and the page shows "—".
"""
import json, sys
from pathlib import Path
import duckdb

REPO = Path(__file__).resolve().parents[1]
REF = REPO / "data/ref"
SRC = REPO / "data/ets_installations_2025.parquet"
S = json.loads((REF / "sources.json").read_text(encoding="utf-8"))


def jsonstat_values(path: Path, dim: str = "geo") -> dict:
    """Flatten a one-dimensional Eurostat JSON-stat response (all other dims of size 1) into {geo_code: value}."""
    d = json.loads(path.read_text(encoding="utf-8"))
    ids, size = d["id"], d["size"]
    assert ids[-1] == "time" and all(n == 1 for i, n in zip(ids, size) if i != dim), (ids, size)
    idx = d["dimension"][dim]["category"]["index"]
    return {code: d["value"].get(str(i)) for code, i in idx.items() if str(i) in d["value"]}


def main():
    for k in ("nuts2", "gdp_nuts2", "pop_nuts2", "ghg_national"):
        p = REF / S[k]["file"]
        if not p.exists():
            sys.exit(f"ERROR missing {p} — download it from sources.json['{k}']['url']")
    if not SRC.exists():
        sys.exit(f"ERROR input not found: {SRC}")
    con = duckdb.connect()
    con.sql("INSTALL spatial; LOAD spatial;")
    geo = (REF / S["nuts2"]["file"]).as_posix()
    con.sql(f"""CREATE TABLE n2 AS SELECT NUTS_ID AS code, NAME_LATN AS name, CNTR_CODE AS country, geom FROM ST_Read('{geo}')""")
    con.sql(f"""CREATE TABLE s AS SELECT installation_id AS id, lat, lon, ST_Point(lon, lat) AS pt FROM read_parquet('{SRC.as_posix()}')""")
    con.sql("""CREATE TABLE a AS SELECT s.id, n2.code, 'inside' AS method FROM s LEFT JOIN n2 ON ST_Contains(n2.geom, s.pt)""")
    dup = con.sql("SELECT count(*) - count(DISTINCT id) FROM a").fetchone()[0]
    if dup:
        sys.exit(f"ERROR {dup} installations fall in more than one NUTS-2 polygon (should not happen)")
    # coastal points that the generalised coastline leaves just offshore: nearest polygon within ~5 km (0.05 degrees), flagged
    con.sql("""CREATE TABLE near AS SELECT s.id, arg_min(n2.code, ST_Distance(n2.geom, s.pt)) AS code, min(ST_Distance(n2.geom, s.pt)) AS d
               FROM s JOIN a USING (id), n2 WHERE a.code IS NULL AND ST_Distance(n2.geom, s.pt) < 0.05 GROUP BY s.id""")
    con.sql("""UPDATE a SET code = near.code, method = 'nearest_5km' FROM near WHERE a.id = near.id AND a.code IS NULL""")
    n, hit, near_n = con.sql("SELECT count(*), count(code), count(*) FILTER (WHERE method = 'nearest_5km' AND code IS NOT NULL) FROM a").fetchone()
    con.sql(f"COPY (SELECT id, code AS nuts2, method AS nuts2_method FROM a ORDER BY id) TO '{(REPO / 'data/nuts2_assignment.csv').as_posix()}' (HEADER)")
    gdp, pop, ghg = (jsonstat_values(REF / S[k]["file"]) for k in ("gdp_nuts2", "pop_nuts2", "ghg_national"))
    regions = {r[0]: {"name": r[1], "country": r[2], "gdp_meur_2023": gdp.get(r[0]), "pop_2024": pop.get(r[0])}
               for r in con.sql("SELECT code, name, country FROM n2 ORDER BY code").fetchall()}
    used = set(x[0] for x in con.sql("SELECT DISTINCT code FROM a WHERE code IS NOT NULL").fetchall())
    ctx = {
        "sources": {k: {kk: v for kk, v in S[k].items() if kk != "factors"} for k in ("nuts2", "gdp_nuts2", "pop_nuts2", "ghg_national")},
        "coverage": {"installations": n, "assigned_to_nuts2": hit, "assigned_by_nearest_polygon_within_5km": near_n, "regions_with_installations": len(used),
                      "note": "United Kingdom installations are not in NUTS 2024 (no region); a few offshore/overseas points remain unassigned.",
                      "regions_missing_gdp": sorted(c for c in used if regions[c]["gdp_meur_2023"] is None),
                      "regions_missing_pop": sorted(c for c in used if regions[c]["pop_2024"] is None)},
        "regions": {c: regions[c] for c in sorted(used)},
        # keyed by the EUTL registry code (Eurostat uses EL for Greece and UK for the United Kingdom)
        "national_ghg_mt_2023": {{"EL": "GR", "UK": "GB"}.get(k, k): v for k, v in ghg.items() if len(k) == 2},
        "cbam_phaseout": S["cbam_phaseout"],
    }
    (REPO / "docs/data/context.json").write_text(json.dumps(ctx, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(ctx["coverage"], ensure_ascii=False))
    print("national GHG countries:", len(ctx["national_ghg_mt_2023"]), "| e.g. DE", ctx["national_ghg_mt_2023"].get("DE"), "PL", ctx["national_ghg_mt_2023"].get("PL"))


if __name__ == "__main__":
    main()
