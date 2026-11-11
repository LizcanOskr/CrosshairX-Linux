#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
cmake -S overlay -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
