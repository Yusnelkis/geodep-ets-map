-- Map layer: one point per EU ETS stationary installation with a verified coordinate.
-- Colour = map_class (sector, or neutral class when no emission was ever reported).
-- Size  = em_last_mt (verified CO2 of the last reported year, Mt). NULL emissions -> 0 for sizing only.
SELECT installation_id, installation_name, country, city, account_holder,
       activity_code, activity,
       CASE
         WHEN activity_code IN ('20','1')                              THEN 'Power & heat (combustion)'
         WHEN activity_code IN ('21','2','22','3')                     THEN 'Refineries & coke'
         WHEN activity_code IN ('24','5','25','23','4','28','26','27') THEN 'Iron, steel & metals'
         WHEN activity_code IN ('29','6','30')                         THEN 'Cement & lime'
         WHEN activity_code IN ('42','43','41','38','39','40','37','44') THEN 'Chemicals'
         WHEN activity_code IN ('36','9','35')                         THEN 'Pulp & paper'
         WHEN activity_code IN ('32','8','31','7','33','34')           THEN 'Glass, ceramics & minerals'
         ELSE 'Other' END AS sector,
       CASE WHEN em_last_value_t IS NULL THEN 'No reported emissions' ELSE
         CASE
           WHEN activity_code IN ('20','1')                              THEN 'Power & heat (combustion)'
           WHEN activity_code IN ('21','2','22','3')                     THEN 'Refineries & coke'
           WHEN activity_code IN ('24','5','25','23','4','28','26','27') THEN 'Iron, steel & metals'
           WHEN activity_code IN ('29','6','30')                         THEN 'Cement & lime'
           WHEN activity_code IN ('42','43','41','38','39','40','37','44') THEN 'Chemicals'
           WHEN activity_code IN ('36','9','35')                         THEN 'Pulp & paper'
           WHEN activity_code IN ('32','8','31','7','33','34')           THEN 'Glass, ceramics & minerals'
           ELSE 'Other' END END AS map_class,
       CAST(em_last_year AS INTEGER)                        AS em_last_year,
       em_last_value_t,
       ROUND(COALESCE(em_last_value_t, 0) / 1e6, 3)         AS em_last_mt,
       em_2025_t, em_2024_t,
       CAST(n_years_with_emissions AS INTEGER)              AS n_years_with_emissions,
       coord_source, as_of,
       ST_Point(lon, lat)                                   AS geometry
FROM datasets."ets_installations_2025"
ORDER BY em_last_mt DESC
