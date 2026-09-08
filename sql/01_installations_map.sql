-- Map layer (DuckDB): one row per EU ETS stationary installation with a verified coordinate.
-- Column names are display labels: Kepler shows them verbatim in filters, tooltips and legends.
-- "Sector" carries a neutral class when the installation never reported emissions.
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
      ELSE 'Other' END AS ets_sector
  FROM read_parquet('{SRC}')
)
SELECT installation_id                                        AS "Installation ID",
       installation_name                                      AS "Installation",
       account_holder                                         AS "Account holder",
       country                                                AS "Country",
       city                                                   AS "City",
       CASE WHEN em_last_value_t IS NULL THEN 'No reported emissions' ELSE ets_sector END AS "Sector",
       activity                                               AS "ETS activity",
       CAST(em_last_year AS INTEGER)                          AS "Last year reported",
       ROUND(COALESCE(em_last_value_t, 0) / 1e6, 3)           AS "CO2 last year (Mt)",
       ROUND(em_2025_t / 1e6, 3)                              AS "CO2 2025 (Mt)",
       ROUND(em_2024_t / 1e6, 3)                              AS "CO2 2024 (Mt)",
       CAST(n_years_with_emissions AS INTEGER)                AS "Years reporting",
       coord_source                                           AS "Coordinate source",
       lat                                                    AS latitude,
       lon                                                    AS longitude
FROM s
ORDER BY "CO2 last year (Mt)" DESC
