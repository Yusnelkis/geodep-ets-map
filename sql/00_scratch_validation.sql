-- Validation over the technical extract (DuckDB). Printed by build_extract.py, never a map layer.
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
      ELSE 'Other' END AS sector
  FROM read_parquet('{SRC}')
)
SELECT sector,
       count(*)                                   AS n_installations,
       count(em_last_value_t)                     AS n_with_emissions,
       round(sum(em_last_value_t) / 1e6, 1)       AS mt_co2_last_year,
       round(min(lat), 2) AS lat_min, round(max(lat), 2) AS lat_max,
       round(min(lon), 2) AS lon_min, round(max(lon), 2) AS lon_max,
       count(*) FILTER (WHERE lat IS NULL OR lon IS NULL) AS n_null_coord
FROM s GROUP BY sector ORDER BY n_installations DESC
