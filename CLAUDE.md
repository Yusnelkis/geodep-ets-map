# geodep-ets-map — CLAUDE.md

## WHAT
Sandbox / portfolio project: an interactive map of EU ETS stationary installations built with
**DuckDB spatial SQL** and the **GeoSQL** skill (map-in-the-loop via a local **Dekart** server in Docker).
Stack: Python 3.14 (venv `../_venvs/ets_map`), DuckDB 1.4.3, `geosql` + `dekart` CLIs, Docker.
Audience: public GitHub repo (`Yusnelkis/geodep-ets-map`).

## WHY
Explore whether an agent that writes spatial SQL and *looks at the rendered map* produces a better
map than text-only iteration. Data are public (EU Transaction Log). This repo is **not** part of the
GEODEP pipeline or methodology: it only reads two public files from the sibling `geodep_setup`
workspace and never writes there.

## HOW
- `code/build_extract.py` → `data/ets_installations_2025.parquet` + `data/sources.json` (provenance).
  Join key `(REGISTRY_CODE, INSTALLATION_IDENTIFIER)`; `-1` emissions → `NULL`, never `0`.
- `code/build_context.py` → `data/nuts2_assignment.csv` + `docs/data/context.json` (NUTS-2 regions, Eurostat GDP /
  population / national GHG, CBAM phase-out factors). External sources are registered in `data/ref/sources.json`
  (url, licence, download date) and downloaded next to it with `curl`; the code never carries a URL.
- `code/build_site_data.py` → `docs/data/installations.csv` (tonne precision, never rounded before display) +
  `docs/data/summary.json`; `docs/index.html` is the published page (GitHub Pages, `main:/docs`).
- Scope rule (2026-09-13): plants and operators of record only. No companies, groups, GUO or GLEIF: that is GEODEP.
- v2.0 (2026-09-17), after the pilot's feedback ("overloaded, too dark"): light palette taken from the author's bivariate climate map
  (bg #eae6de, data #5e4f66, teal down, magenta up), one search box, answer first, one breakdown with a selector, Refine collapsed,
  story as a secondary view behind the header link, card over the map, sites under 0.1 Mt hidden at European scale (`SMALL`,
  "show all" in the legend). Built by `scratchpad/v2_assemble.py` (head + body + engine replacements) over the v1 engine; the
  calculations did not change. Sector and semantic colours validated with the dataviz palette validator on #eae6de.
- v1.0 closed 2026-09-14. Parked, code kept in `docs/index.html`: the year selector (`applyYear`, hidden `#f-year`, `y=` in the hash
  ignored) — reopen only as a timeline under the answer with per-year status. Next candidates: hex hotspots (~20 km), NUTS-3.
- `docker/compose.yml` → Dekart on `localhost:8080` (state in `docker/dekart-data/`, gitignored).
- `sql/` → the DuckDB queries that GeoSQL produced for the map. `maps/` → exported map config / screenshots.
- CLIs live in the venv: `../_venvs/ets_map/Scripts/{dekart,geosql}.exe`. In shell calls prepend that
  directory to `PATH` (`export PATH="/c/Users/Usuario/Documents/geodep/_venvs/ets_map/Scripts:$PATH"`)
  so the `/geosql` skill finds `dekart`. The CLI is configured against `http://localhost:8080`.
- Interactive step the user runs once: `dekart init` (authorizes the CLI against the local server).
- Map v1 lives in report `maps/report_ids.json` (local instance only). Flow used: upload parquet as
  dataset `ets_installations_2025` → DuckDB queries `sql/00_*` (scratch) and `sql/01_*` (map layer,
  write-once) → `maps/map_config.json` applied with `update_report_map_config`.
- **Known Dekart client bug (v0.24.1 image, 2026-09-07):** opening a report whose `map_config` was set
  by the CLI can crash `reportUpdate` (`reading 'visState'`) when the first stream message arrives
  before Kepler mounts; datasets then never download. Workaround: with the page open, trigger a new
  stream message, e.g. `dekart call --name update_report_title --args '{"report_id":"<id>","title":"<same title>"}'`.
  Kepler auto-creates layers for every dataset without one, so `map_config.json` carries hidden layers
  for the source and scratch datasets.
- Never commit `docker/dekart-data/`, `.env`, or anything from `geodep_setup/internal/`.
- `README.md` (2026-09-13) is the public face: every figure in it is re-derived from `docs/data/*.json`, never typed. Keep it in
  sync when the data or the page change; `docs/assets/screenshot.png` is captured from a real Chrome window (headless Chrome does
  not render the CARTO basemap).
