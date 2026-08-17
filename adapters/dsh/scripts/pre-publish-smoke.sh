#!/usr/bin/env bash
#
# pre-publish-smoke.sh — isolated pre-publish smoke test for the dsh npm
# package (spec D4). It packs the real tarball into a fresh temp directory,
# installs it into another fresh temp directory (never the repo, never
# ~/.dsh/profiles), then verifies:
#   1. the tarball ships python/cli.py and python/vision_translation.py;
#   2. lib/vision.js can be imported from the installed package;
#   3. resolveCli({}, {}) resolves to the bundled package-internal cli.py
#      (no config, no env) instead of throwing CliMissingError.
#
# Exits non-zero on any failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/vision-translation-dsh-smoke.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT

cd "$PKG_DIR"

echo "[smoke] packing vision-translation-dsh into ${TMP_ROOT}"
TARBALL_NAME="$(npm pack --pack-destination "${TMP_ROOT}" 2>/dev/null | tail -n 1)"
TARBALL="${TMP_ROOT}/${TARBALL_NAME}"
if [[ ! -f "${TARBALL}" ]]; then
  echo "[smoke] npm pack did not produce a tarball (expected ${TARBALL})" >&2
  exit 1
fi

INSTALL_DIR="${TMP_ROOT}/install"
mkdir -p "${INSTALL_DIR}"
cd "${INSTALL_DIR}"

echo "[smoke] installing tarball into clean temp dir (${INSTALL_DIR})"
npm init -y >/dev/null 2>&1
npm install --ignore-scripts --no-audit --no-fund --legacy-peer-deps "${TARBALL}" >/dev/null

PKG_INSTALL="${INSTALL_DIR}/node_modules/vision-translation-dsh"
if [[ ! -d "${PKG_INSTALL}" ]]; then
  echo "[smoke] installed package not found at ${PKG_INSTALL}" >&2
  exit 1
fi

echo "[smoke] asserting bundled Python core files exist in the installed package"
for f in python/cli.py python/vision_translation.py; do
  if [[ ! -f "${PKG_INSTALL}/${f}" ]]; then
    echo "[smoke] FAIL: installed package is missing ${f}" >&2
    exit 1
  fi
done

echo "[smoke] probing installed lib/vision.js resolveCli (no config, no env)"
INSTALL_DIR="${INSTALL_DIR}" node --input-type=module -e '
  import { pathToFileURL } from "node:url";
  import { existsSync } from "node:fs";

  const installRoot = process.env.INSTALL_DIR;
  if (!installRoot) throw new Error("INSTALL_DIR not set");

  const visionPath = `${installRoot}/node_modules/vision-translation-dsh/lib/vision.js`;
  const { resolveCli } = await import(pathToFileURL(visionPath).href);

  // B1: fresh install, no config, no env -> the bundled python/cli.py.
  const r = resolveCli({ cliPath: "", pythonBin: "python3" }, {});
  if (!r || r.source !== "package python/cli.py") {
    throw new Error(`expected bundled resolution (package python/cli.py), got ${r && r.source}`);
  }
  if (!existsSync(r.cliPath)) {
    throw new Error(`resolveCli pointed at a missing file: ${r.cliPath}`);
  }
  if (!r.cliPath.endsWith("/node_modules/vision-translation-dsh/python/cli.py")) {
    throw new Error(`resolveCli did not resolve inside the installed package: ${r.cliPath}`);
  }
  console.log(`[smoke] resolve ok: ${r.source} -> ${r.cliPath}`);
'

echo "[smoke] OK"
