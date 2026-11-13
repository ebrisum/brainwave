#!/usr/bin/env bash
# Builds and runs the power-policy tests on the host (gcc, no Zephyr needed).
set -euo pipefail
cd "$(dirname "$0")"
out="$(mktemp -d)"
gcc -std=c11 -Wall -Wextra -Werror -O1 -o "$out/test_policy" test_policy.c ../../src/policy.c -lm
"$out/test_policy"
