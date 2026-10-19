#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Run with Python 3.12 on the same Linux architecture as the target image.
"${PYTHON:-python3}" -m pip download --only-binary=:all: -r requirements.txt -d .wheelhouse
docker compose build --build-arg OFFLINE_BUILD=1
