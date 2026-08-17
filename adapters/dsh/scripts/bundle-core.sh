#!/usr/bin/env bash
#
# bundle-core.sh — copy the Python core (cli.py + vision_translation.py) into
# the npm package layout (`adapters/dsh/python/`) so a published
# `vision-translation-dsh` tarball ships the CLI and resolves it out of the box
# (spec D1). Runs automatically before every `npm pack` / `npm publish` via the
# package.json `prepack` hook.
#
# The generated `python/` directory is build output: it is intentionally
# .gitignore'd (see repository root .gitignore) but still included in the
# tarball because the package.json `files` whitelist has priority over
# .gitignore for npm packaging.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${PKG_DIR}/../.." && pwd)"

CORE_MAIN="${REPO_ROOT}/vision_translation.py"
CLI="${REPO_ROOT}/cli.py"
OUT_DIR="${PKG_DIR}/python"

if [[ ! -f "${CORE_MAIN}" ]]; then
  echo "bundle-core.sh: missing ${CORE_MAIN}" >&2
  exit 1
fi
if [[ ! -f "${CLI}" ]]; then
  echo "bundle-core.sh: missing ${CLI}" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"
cp -f "${CORE_MAIN}" "${OUT_DIR}/vision_translation.py"
cp -f "${CLI}" "${OUT_DIR}/cli.py"
