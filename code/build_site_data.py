"""Build the data files consumed by the narrative page (docs/index.html).

Inputs : data/ets_installations_2025.parquet (technical extract, built by build_extract.py)
         <GEODEP_SETUP_DIR>/public/external/eutl/dumps/eutl_2025_shareable/installation_year.csv (EUTL, for the
         yearly series and the EXCLUDED flag)
Outputs: docs/data/installations.csv  – one row per installation, only the fields the page uses
         docs/data/summary.json       – every number quoted in the narrative (nothing is typed by hand in the HTML)
"""
import json, os, sys
from pathlib import Path
import duckdb

REPO = Path(__file__).resolve().parents[1]
SETUP = Path(os.environ.get("GEODEP_SETUP_DIR", REPO.parent / "geodep_setup"))
SRC = REPO / "data/ets_installations_2025.parquet"
EMIS = SETUP / "public/external/eutl/dumps/eutl_2025_shareable/installation_year.csv"
OUT = REPO / "docs/data"

SECTOR = """CASE
  WHEN activity_code IN ('20','1')                              THEN 'Power & heat'
  WHEN activity_code IN ('21','2','22','3')                     THEN 'Refineries & coke'
  WHEN activity_code IN ('24','5','25','23','4','28','26','27') THEN 'Iron, steel & metals'
  WHEN activity_code IN ('29','6','30')                         THEN 'Cement & lime'
  WHEN activity_code IN ('42','43','41','38','39','40','37','44') THEN 'Chemicals'
  WHEN activity_code IN ('36','9','35')                         THEN 'Pulp & paper'
  WHEN activity_code IN ('32','8','31','7','33','34')           THEN 'Glass, ceramics & minerals'
  ELSE 'Other' END"""


def main():
    for p in (SRC, EMIS):
        if not p.exists():
            sys.exit(f"ERROR input not found: {p}")
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.sql(f"""CREATE TABLE s AS
      SELECT *, {SECTOR} AS sector,
             CASE WHEN em_2025_t > 0 THEN ROW_NUMBER() OVER (ORDER BY CASE WHEN em_2025_t > 0 THEN em_2025_t END DESC NULLS LAST) END AS rank_2025,
             TRY_CAST(SUBSTR(permit_revocation_date, 1, 4) AS INTEGER) AS revoked_year,
             CASE WHEN permit_revocation_date IS NOT NULL THEN 'closed' WHEN em_2025_t > 0 THEN 'reporting'
                  WHEN em_last_value_t IS NULL THEN 'never' ELSE 'stopped' END AS status
      FROM read_parquet('{SRC.as_posix()}')""")
    con.sql(f"""CREATE TABLE e AS SELECT REGISTRY_CODE rc, INSTALLATION_IDENTIFIER iid, PERIOD_YEAR yr,
             NULLIF(VERIFIED_EMISSIONS, -1) em, EXCLUDED ex, NULLIF(ALLOCATION, -1) alloc FROM read_csv('{EMIS.as_posix()}')""")
    # free allocation 2025 per installation (Mt); NULL when no allocation row
    con.sql("""CREATE TABLE a25 AS SELECT rc || '_' || iid AS id, ROUND(MAX(alloc) / 1e6, 3) AS alloc_2025, MAX(alloc) AS alloc_t FROM e WHERE yr = 2025 AND alloc > 0 GROUP BY 1""")

    # 1. per-installation CSV (compact: rounded numbers, short names) + yearly trajectory 2013-2025 in Mt
    con.sql("""CREATE TABLE traj AS SELECT rc || '_' || iid AS id, yr, ROUND(em / 1e6, 3) AS mt FROM e WHERE yr BETWEEN 2013 AND 2025 AND em IS NOT NULL""")
    years = ", ".join(f"MAX(CASE WHEN yr = {y} THEN mt END) AS y{y}" for y in range(2013, 2026))
    con.sql(f"""COPY (SELECT s.installation_id AS id, installation_name AS name, account_holder AS holder, country, city, activity,
              sector, status, rank_2025 AS rank, em_last_year AS last_year, revoked_year,
              ROUND(em_last_value_t / 1e6, 3) AS mt_last, ROUND(em_2025_t / 1e6, 3) AS mt_2025, ROUND(em_base_2021_23_t / 1e6, 3) AS mt_base,
              ROUND(change_vs_2021_23_pct, 1) AS chg, a25.alloc_2025, ROUND(lat, 5) AS lat, ROUND(lon, 5) AS lon, {", ".join(f"y{y}" for y in range(2013, 2026))}
              FROM s LEFT JOIN (SELECT id, {years} FROM traj GROUP BY id) t ON t.id = s.installation_id LEFT JOIN a25 ON a25.id = s.installation_id
              ORDER BY em_2025_t DESC NULLS LAST) TO '{(OUT / 'installations.csv').as_posix()}' (HEADER)""")

    rows = lambda q: [dict(zip([d[0] for d in con.sql(q).description], r)) for r in con.sql(q).fetchall()]
    one = lambda q: con.sql(q).fetchone()
    n, n_coord_em, n_em25, mt25 = one("SELECT count(*), count(em_last_year), count(*) FILTER (WHERE em_2025_t > 0), round(sum(em_2025_t)/1e6, 1) FROM s")
    conc = rows("""WITH r AS (SELECT em_2025_t, rank_2025, sum(em_2025_t) OVER () tot FROM s WHERE em_2025_t > 0)
                   SELECT k AS top_n, round(100.0 * sum(em_2025_t) / max(tot), 1) AS share_pct
                   FROM r, (VALUES (20),(100),(500),(1000),(2000),(4000)) v(k) WHERE rank_2025 <= k GROUP BY k ORDER BY k""")
    lorenz = rows("""WITH r AS (SELECT rank_2025 rk, sum(em_2025_t) OVER (ORDER BY rank_2025) cum, sum(em_2025_t) OVER () tot,
                                count(*) OVER () n FROM s WHERE em_2025_t > 0)
                     SELECT round(100.0 * rk / n, 2) AS pct_installations, round(100.0 * cum / tot, 2) AS pct_co2
                     FROM r WHERE rk % 50 = 0 OR rk <= 20 OR rk = n ORDER BY rk""")
    top20 = rows("""SELECT rank_2025 AS rank, installation_name AS name, account_holder AS holder, country, city, sector,
                    round(em_2025_t/1e6, 2) AS mt_2025, round(change_vs_2021_23_pct, 1) AS chg, lat, lon
                    FROM s WHERE rank_2025 <= 20 ORDER BY rank_2025""")
    sectors = rows("""SELECT sector, count(*) AS n, count(*) FILTER (WHERE em_2025_t > 0) AS n_2025,
                      round(sum(em_2025_t)/1e6, 1) AS mt_2025, round(sum(em_2024_t)/1e6, 1) AS mt_2024,
                      round(100.0 * count(*) / (SELECT count(*) FROM s), 1) AS pct_n,
                      round(100.0 * sum(em_2025_t) / (SELECT sum(em_2025_t) FROM s), 1) AS pct_mt
                      FROM s GROUP BY sector ORDER BY mt_2025 DESC""")
    countries = rows("""SELECT country, count(*) AS n, round(sum(em_2025_t)/1e6, 1) AS mt_2025 FROM s
                        GROUP BY country ORDER BY mt_2025 DESC NULLS LAST LIMIT 10""")
    series = rows("""SELECT yr AS year, round(sum(em)/1e6, 0) AS mt, count(*) FILTER (WHERE em > 0) AS n_emitting,
                     count(*) FILTER (WHERE ex) AS n_excluded
                     FROM e JOIN s ON s.installation_id = e.rc || '_' || e.iid
                     WHERE yr BETWEEN 2013 AND 2025 GROUP BY yr ORDER BY yr""")
    revoked = rows("""SELECT revoked_year AS year, count(*) AS n, round(sum(em_last_value_t)/1e6, 1) AS mt_last
                      FROM s WHERE revoked_year BETWEEN 2005 AND 2026 GROUP BY 1 ORDER BY 1""")
    last_year = rows("""SELECT em_last_year AS year, count(*) AS n FROM s WHERE em_last_year BETWEEN 2013 AND 2024 GROUP BY 1 ORDER BY 1""")
    spike = one("""WITH u AS (SELECT * FROM s WHERE em_last_year = 2020),
                   x AS (SELECT u.installation_id, bool_or(e.ex) FILTER (WHERE e.yr >= 2021) ex_post FROM u
                         JOIN e ON u.installation_id = e.rc || '_' || e.iid GROUP BY 1)
                   SELECT count(*), count(*) FILTER (WHERE u.permit_revocation_date IS NOT NULL),
                          count(*) FILTER (WHERE u.permit_revocation_date IS NULL AND x.ex_post),
                          count(*) FILTER (WHERE u.permit_revocation_date IS NULL AND NOT coalesce(x.ex_post, false))
                   FROM u JOIN x USING (installation_id)""")
    status = rows("SELECT status, count(*) AS n FROM s GROUP BY 1 ORDER BY n DESC")
    change = one("""SELECT count(*), round(100 * (sum(em_2025_t) - sum(em_base_2021_23_t)) / sum(em_base_2021_23_t), 1),
                    round(median(change_vs_2021_23_pct), 1),
                    round(100.0 * count(*) FILTER (WHERE change_vs_2021_23_pct <= -10) / count(*), 1),
                    round(100.0 * count(*) FILTER (WHERE change_vs_2021_23_pct >= 10) / count(*), 1)
                    FROM s WHERE change_vs_2021_23_pct IS NOT NULL""")
    change_sector = rows("""SELECT sector, count(*) AS n, round(sum(em_base_2021_23_t)/1e6, 1) AS base_mt, round(sum(em_2025_t)/1e6, 1) AS mt_2025,
                            round(100 * (sum(em_2025_t) - sum(em_base_2021_23_t)) / sum(em_base_2021_23_t), 1) AS chg_pct,
                            round((sum(em_2025_t) - sum(em_base_2021_23_t))/1e6, 1) AS delta_mt
                            FROM s WHERE change_vs_2021_23_pct IS NOT NULL GROUP BY 1 ORDER BY delta_mt""")
    core = one("""SELECT count(*), round(sum(em_2025_t)/1e6, 1), round(sum(em_base_2021_23_t) FILTER (WHERE change_vs_2021_23_pct IS NOT NULL)/1e6, 1),
                  round(sum(em_2025_t) FILTER (WHERE change_vs_2021_23_pct IS NOT NULL)/1e6, 1)
                  FROM s WHERE sector IN ('Cement & lime','Iron, steel & metals','Refineries & coke')""")
    s13, s25 = one("SELECT (SELECT round(sum(em)/1e6,0) FROM e JOIN s ON s.installation_id = e.rc || '_' || e.iid WHERE yr = 2013), (SELECT round(sum(em_2025_t)/1e6,0) FROM s)")
    as_of = one("SELECT min(as_of), max(as_of) FROM s")
    summary = {
        "source": {"dataset": "EU Transaction Log (EUTL), European Commission — public data download",
                   "extract_as_of": str(as_of[1]), "emissions_years": "2005-2025", "build": "code/build_extract.py + code/build_site_data.py"},
        "totals": {"installations": n, "with_any_reported_emission": n_coord_em, "emitting_2025": n_em25, "mt_2025": mt25},
        "concentration": conc, "lorenz": lorenz, "top20": top20, "sectors": sectors, "countries": countries,
        "series": series, "revoked_by_year": revoked, "last_year_hist": last_year,
        "spike_2020": {"total": spike[0], "revoked": spike[1], "excluded_from_2021": spike[2], "unexplained": spike[3]},
        "status": status,
        "allocation_2025": {"alloc_mt": one("SELECT round(sum(alloc_2025), 1) FROM a25 JOIN s ON s.installation_id = a25.id")[0],
                            "installations_with_allocation": one("SELECT count(*) FROM a25 JOIN s ON s.installation_id = a25.id")[0],
                            "installations_surplus": one("SELECT count(*) FROM a25 JOIN s ON s.installation_id = a25.id WHERE em_2025_t > 0 AND alloc_t > em_2025_t")[0],
                            "by_sector": rows("""SELECT sector, round(sum(alloc_2025), 1) AS alloc_mt, round(sum(em_2025_t)/1e6, 1) AS em_mt FROM s LEFT JOIN a25 ON a25.id = s.installation_id GROUP BY 1 ORDER BY em_mt DESC""")},
        "trend": {"mt_2013": s13, "mt_2025": s25, "pct_2013_2025": round(100 * (s25 - s13) / s13, 1)},
        "hard_to_abate_core": {"sectors": ["Cement & lime", "Iron, steel & metals", "Refineries & coke"], "installations": core[0], "mt_2025": core[1],
                               "base_mt_same_sites": core[2], "mt_2025_same_sites": core[3],
                               "chg_pct_same_sites": round(100 * (core[3] - core[2]) / core[2], 1)},
        "change_vs_baseline": {"installations": change[0], "aggregate_pct": change[1], "median_pct": change[2],
                                "pct_down_10": change[3], "pct_up_10": change[4], "baseline": "mean of 2021-2023 (years with emissions > 0)",
                                "by_sector": change_sector},
        "data_quality": {"coordinate_error_example": {"id": "GB_918", "note": "INEOS CHP plant 'Cleveland' geocoded to Cleveland, Ohio (41.5N, -81.7E); the plant is in Cleveland, UK. Left as-is to show the kind of error a map catches."},
                          "sentinel_rule": "VERIFIED_EMISSIONS = -1 means 'not reported' and is treated as missing, never as zero"},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("totals", "concentration", "spike_2020", "change_vs_baseline")}, indent=1, default=str)[:1500])
    print("series:", [(r["year"], r["mt"], r["n_emitting"]) for r in series])
    print("csv rows:", one(f"SELECT count(*) FROM read_csv('{(OUT / 'installations.csv').as_posix()}')")[0])


if __name__ == "__main__":
    main()
