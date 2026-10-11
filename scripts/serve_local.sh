#!/usr/bin/env bash
# Serve the repo root locally (supports HTTP range requests for the video).
# Open: http://localhost:8000/task/index.html?study=heights-film&dim=anxiety&reset=1
#   (study = a folder in studies/; dim = a rating dimension of that study)
#   test near the end of the film: ...&start_time=780   (testing parameters work locally)
cd "$(dirname "$0")/.." && exec npx --yes http-server -p "${PORT:-8000}" -c-1 .
