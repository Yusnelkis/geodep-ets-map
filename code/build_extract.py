"""Build the map-ready extract of EU ETS stationary installations.

Inputs (read-only, from the GEODEP workspace; override with GEODEP_SETUP_DIR):
  1. eutl_canonico_2025.parquet  – canonical EUTL installation table with verified coordinates
  2. installation_year.csv       – EUTL verified emissions per installation and year (2005-2025)

Output: data/ets_installations_2025.parquet (one row per stationary installation with coordinates)
        data/sources.json        (provenance: input paths, as_of, row counts)

Rules: join key is (REGISTRY_CODE, INSTALLATION_IDENTIFIER) – the bare identifier repeats across
registries. VERIFIED_EMISSIONS = -1 means "not reported" and becomes NULL, never 0.
"""
import json, os, sys
from pathlib import Path
import duckdb

REPO = Path(__file__).resolve().parents[1]
SETUP = Path(os.environ.get("GEODEP_SETUP_DIR", REPO.parent / "geodep_setup"))
BASE = SETUP / "public/data/_intermediate/a8_ets/eutl_canonico_2025.parquet"
EMIS = SETUP / "public/external/eutl/dumps/eutl_2025_shareable/installation_year.csv"
OUT = REPO / "data/ets_installations_2025.parquet"
MAP_OUT = REPO / "data/ets_map_layer_2025.parquet"

REQ_BASE = ["installation_id", "REGISTRY_CODE", "INSTALLATION_IDENTIFIER", "INSTALLATION_NAME",
            "ACTIVITY_TYPE_CODE", "ACTIVITY_TYPE", "PERMIT_IDENTIFIER", "PERMIT_REVOCATION_DATE", "CITY",
            "POSTAL_CODE", "YEAR_OF_FIRST_EMISSIONS", "YEAR_OF_LAST_EMISSIONS", "ACCOUNT_HOLDER_NAME",
            "holder_lei", "nace_actividad", "lat_ets_verified", "lon_ets_verified", "coord_source",
            "universo_estacionarias", "as_of", "fuente_base"]
REQ_EMIS = ["REGISTRY_CODE", "INSTALLATION_IDENTIFIER", "PERIOD_YEAR", "VERIFIED_EMISSIONS"]

SQL = f"""
WITH e AS (
  SELECT REGISTRY_CODE AS rc, INSTALLATION_IDENTIFIER AS iid,
         NULLIF(VERIFIED_EMISSIONS, -1) AS em, PERIOD_YEAR AS yr
  FROM read_csv('{EMIS.as_posix()}')
), agg AS (
  SELECT rc, iid,
         MAX(CASE WHEN yr = 2024 THEN em END)            AS em_2024_t,
         MAX(CASE WHEN yr = 2025 THEN em END)            AS em_2025_t,
         MAX(CASE WHEN em > 0 THEN yr END)               AS em_last_year,
         COUNT(CASE WHEN em > 0 THEN 1 END)              AS n_years_with_emissions,
         AVG(CASE WHEN yr BETWEEN 2021 AND 2023 AND em > 0 THEN em END) AS em_base_2021_23_t
  FROM e GROUP BY 1, 2
), last AS (
  SELECT rc, iid, em AS em_last_value_t FROM e
  QUALIFY ROW_NUMBER() OVER (PARTITION BY rc, iid ORDER BY CASE WHEN em > 0 THEN yr END DESC NULLS LAST) = 1
)
SELECT b.installation_id, b.REGISTRY_CODE AS country, b.INSTALLATION_NAME AS installation_name,
       b.ACTIVITY_TYPE_CODE AS activity_code, b.ACTIVITY_TYPE AS activity, b.nace_actividad AS nace,
       b.PERMIT_IDENTIFIER AS permit_id, b.PERMIT_REVOCATION_DATE AS permit_revocation_date,
       b.CITY AS city, b.POSTAL_CODE AS postal_code,
       b.YEAR_OF_FIRST_EMISSIONS AS year_first_emissions, b.YEAR_OF_LAST_EMISSIONS AS year_last_emissions,
       b.ACCOUNT_HOLDER_NAME AS account_holder, b.holder_lei,
       TRY_CAST(b.lat_ets_verified AS DOUBLE) AS lat, TRY_CAST(b.lon_ets_verified AS DOUBLE) AS lon, b.coord_source,
       CAST(a.em_2024_t AS DOUBLE) AS em_2024_t, CAST(a.em_2025_t AS DOUBLE) AS em_2025_t,
       a.em_last_year, CAST(CASE WHEN a.em_last_year IS NOT NULL THEN l.em_last_value_t END AS DOUBLE) AS em_last_value_t,
       COALESCE(a.n_years_with_emissions, 0)::INTEGER AS n_years_with_emissions,
       CAST(a.em_base_2021_23_t AS DOUBLE) AS em_base_2021_23_t,
       CAST(CASE WHEN a.em_base_2021_23_t > 0 AND a.em_2025_t > 0
                 THEN 100.0 * (a.em_2025_t - a.em_base_2021_23_t) / a.em_base_2021_23_t END AS DOUBLE) AS change_vs_2021_23_pct,
       b.fuente_base AS source_base, b.as_of
FROM '{BASE.as_posix()}' b
LEFT JOIN agg a ON a.rc = b.REGISTRY_CODE AND a.iid = b.INSTALLATION_IDENTIFIER
LEFT JOIN last l ON l.rc = b.REGISTRY_CODE AND l.iid = b.INSTALLATION_IDENTIFIER
WHERE b.universo_estacionarias
  AND TRY_CAST(b.lat_ets_verified AS DOUBLE) IS NOT NULL AND TRY_CAST(b.lon_ets_verified AS DOUBLE) IS NOT NULL
ORDER BY b.installation_id
"""


def check_columns(con, path, required):
    cols = {r[0] for r in con.sql(f"DESCRIBE SELECT * FROM '{path.as_posix()}'").fetchall()}
    if missing := [c for c in required if c not in cols]:
        sys.exit(f"ERROR {path.name}: missing columns {missing}")


def main():
    for p in (BASE, EMIS):
        if not p.exists():
            sys.exit(f"ERROR input not found: {p}")
    con = duckdb.connect()
    check_columns(con, BASE, REQ_BASE)
    check_columns(con, EMIS, REQ_EMIS)

    OUT.parent.mkdir(exist_ok=True)
    con.sql(f"COPY ({SQL}) TO '{OUT.as_posix()}' (FORMAT parquet)")
    out = f"'{OUT.as_posix()}'"
    n, n_ids, n_neg, n_em, n_stat = con.sql(f"""
        SELECT count(*), count(DISTINCT installation_id),
               count(*) FILTER (WHERE least(em_2024_t, em_2025_t, em_last_value_t) < 0),
               count(em_last_year),
               (SELECT count(*) FROM '{BASE.as_posix()}' WHERE universo_estacionarias)
        FROM {out}""").fetchone()
    if n != n_ids:
        sys.exit(f"ERROR installation_id is not unique ({n} rows, {n_ids} ids)")
    if n_neg:
        sys.exit(f"ERROR {n_neg} negative emissions survived (-1 sentinel leak)")

    cols = [r[0] for r in con.sql(f"DESCRIBE SELECT * FROM {out}").fetchall()]
    as_of = [r[0] for r in con.sql(f"SELECT DISTINCT CAST(as_of AS VARCHAR) FROM {out} WHERE as_of IS NOT NULL ORDER BY 1").fetchall()]
    prov = {
        "output": OUT.name, "rows": n, "columns": cols,
        "stationary_in_base": n_stat, "dropped_without_coordinates": n_stat - n,
        "rows_with_any_emission": n_em,
        "inputs": [{"file": BASE.name, "role": "installations + verified coordinates", "as_of": as_of},
                   {"file": EMIS.name, "role": "verified emissions 2005-2025 (EUTL public data download)"}],
        "sentinel_rule": "VERIFIED_EMISSIONS = -1 (not reported) -> NULL, never 0",
        "join_key": "(REGISTRY_CODE, INSTALLATION_IDENTIFIER)",
    }
    (OUT.parent / "sources.json").write_text(json.dumps(prov, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in prov.items() if k != "columns"}, indent=2, ensure_ascii=False))

    # Map layer: run the versioned DuckDB SQL over the extract (same SQL GeoSQL validated in Dekart).
    sql = lambda name: (REPO / "sql" / name).read_text(encoding="utf-8").replace("{SRC}", OUT.as_posix())
    print("\nValidation (sql/00):")
    print(con.sql(sql("00_scratch_validation.sql")))
    con.sql(f"COPY ({sql('01_installations_map.sql')}) TO '{MAP_OUT.as_posix()}' (FORMAT parquet)")
    n_map = con.sql(f"SELECT count(*) FROM '{MAP_OUT.as_posix()}'").fetchone()[0]
    if n_map != n:
        sys.exit(f"ERROR map layer has {n_map} rows, extract has {n}")
    print(f"map layer: {MAP_OUT.name} ({n_map} rows)")


if __name__ == "__main__":
    main()
