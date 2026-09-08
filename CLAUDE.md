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
- `docker/compose.yml` → Dekart on `localhost:8080` (state in `docker/dekart-data/`, gitignored).
- `sql/` → the DuckDB queries that GeoSQL produced for the map. `maps/` → exported map config / screenshots.
- Interactive steps the user runs: `geosql` (installs the skill globally), `dekart init` (choose localhost).
- Never commit `docker/dekart-data/`, `.env`, or anything from `geodep_setup/internal/`.
- No README until the map is running and checked.
