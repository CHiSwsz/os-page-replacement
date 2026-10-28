#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ "$#" -eq 0 ]; then
    printf 'Usage: %s TRACE.txt [--format text|csv|json] [--page-format hex|decimal|token]\n' "$0" >&2
    exit 2
fi
if command -v cmake >/dev/null 2>&1; then
    cmake -S "$project_dir" -B "$project_dir/build-live" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF >&2
    cmake --build "$project_dir/build-live" --config Release -j 4 >&2
else
    mkdir -p "$project_dir/build-live"
    "${CXX:-c++}" -std=c++17 -O3 -Wall -Wextra -I"$project_dir/include" \
        "$project_dir/src/paging.cpp" "$project_dir/src/adaptive.cpp" "$project_dir/src/context.cpp" \
        "$project_dir/src/main.cpp" "$project_dir/src/contest.cpp" -o "$project_dir/build-live/pager"
fi
exec "$project_dir/build-live/pager" --contest "$@"
