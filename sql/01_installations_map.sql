-- Map layer (DuckDB): one row per EU ETS stationary installation with a verified coordinate.
-- Column names are display labels: Kepler shows them verbatim in filters, tooltips and legends.
-- "Sector" carries a neutral class when the installation never reported emissions.
-- "Status": closure requires a permit-revocation signal (rule shared with GEODEP F2). Of the 1,615
--   installations whose last emission year is 2020: 430 revoked, 386 flagged EXCLUDED from 2021 (phase-4
--   small-emitter opt-out), 799 stopped reporting with no reason in the registry (unexplained gap).
-- "Emitter rank": rank by verified CO2 2025 (top 500 = 71.5% of 2025 CO2).
-- "CO2 change vs 2021-23 (%)": 2025 vs the phase-4 baseline (mean of 2021-2023 years with emissions > 0).
-- {SRC} is replaced by the extract path.
WITH s AS (
  SELECT *,
    CASE
      WHEN activity_code IN ('20','1')                              THEN 'Power & heat (combustion)'
      WHEN activity_code IN ('21','2','22','3')                     THEN 'Refineries & coke'
      WHEN activity_code IN ('24','5','25','23','4','28','26','27') THEN 'Iron, steel & metals'
      WHEN activity_code IN ('29','6','30')                         THEN 'Cement & lime'
      WHEN activity_code IN ('42','43','41','38','39','40','37','44') THEN 'Chemicals'
      WHEN activity_code IN ('36','9','35')                         THEN 'Pulp & paper'
      WHEN activity_code IN ('32','8','31','7','33','34')           THEN 'Glass, ceramics & minerals'
      ELSE 'Other' END AS ets_sector,
    CASE WHEN em_2025_t > 0 THEN ROW_NUMBER() OVER (ORDER BY CASE WHEN em_2025_t > 0 THEN em_2025_t END DESC NULLS LAST) END AS rank_2025
  FROM read_parquet('{SRC}')
)
SELECT installation_id                                        AS "Installation ID",
       installation_name                                      AS "Installation",
       account_holder                                         AS "Account holder",
       country                                                AS "Country",
       city                                                   AS "City",
       CASE WHEN em_last_value_t IS NULL THEN 'No reported emissions' ELSE ets_sector END AS "Sector",
       activity                                               AS "ETS activity",
       CASE WHEN rank_2025 <= 20 THEN 'Top 20' WHEN rank_2025 <= 100 THEN 'Top 100'
            WHEN rank_2025 <= 500 THEN 'Top 500' WHEN rank_2025 IS NOT NULL THEN 'Other emitter 2025'
            ELSE 'No 2025 emissions' END                      AS "Emitter rank",
       CASE WHEN permit_revocation_date IS NOT NULL THEN 'Closed (permit revoked)'
            WHEN em_2025_t > 0 THEN 'Reporting in 2025'
            WHEN em_last_value_t IS NULL THEN 'Never reported'
            ELSE 'Stopped reporting (not revoked)' END        AS "Status",
       CAST(em_last_year AS INTEGER)                          AS "Last year reported",
       TRY_CAST(SUBSTR(permit_revocation_date, 1, 4) AS INTEGER) AS "Permit revoked (year)",
       ROUND(COALESCE(em_last_value_t, 0) / 1e6, 3)           AS "CO2 last year (Mt)",
       ROUND(em_2025_t / 1e6, 3)                              AS "CO2 2025 (Mt)",
       ROUND(em_2024_t / 1e6, 3)                              AS "CO2 2024 (Mt)",
       ROUND(em_base_2021_23_t / 1e6, 3)                      AS "CO2 baseline 2021-23 (Mt)",
       ROUND(change_vs_2021_23_pct, 1)                        AS "CO2 change vs 2021-23 (%)",
       CAST(n_years_with_emissions AS INTEGER)                AS "Years reporting",
       coord_source                                           AS "Coordinate source",
       lat                                                    AS latitude,
       lon                                                    AS longitude
FROM s
ORDER BY "CO2 last year (Mt)" DESC
