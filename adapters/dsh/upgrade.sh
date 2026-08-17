#!/usr/bin/env bash
# upgrade.sh — pull the latest vision-translation-dsh release and refresh the
# running dsh profile.
#
# This is the local half of the tag-gated release loop: a maintainer cuts a
# `vX.Y.Z` tag → CI publishes `vision-translation-dsh@X.Y.Z` to npm → you run
# this script to (1) install the new version into your dsh profile and (2)
# remind yourself to restart dsh so Cordis reloads the bundle patch.
#
# The script delegates to dsh's own plugin manager (`dsh plugin --profile
# <name> add <pkg>`), which runs pnpm in the profile directory and reconciles
# the `dsh.profile.bundles` layer list. If dsh's pnpm is missing it tells you
# how to enable it instead of guessing an install layout.
#
# Usage:
#   ./upgrade.sh web                       # upgrade the `web` profile (default)
#   ./upgrade.sh headless                  # upgrade the `headless` profile
#   ./upgrade.sh web 0.2.0                 # pin a specific version
#
# Requirements: `dsh` on PATH (the DeepSeek Harness CLI).
set -euo pipefail

PROFILE="${1:-web}"
VERSION="${2:-latest}"
PKG="vision-translation-dsh"

if ! command -v dsh >/dev/null 2>&1; then
  echo "error: 'dsh' not found on PATH — run this from a machine with the DeepSeek Harness CLI." >&2
  exit 1
fi

SPEC="$PKG"
if [ "$VERSION" != "latest" ]; then
  SPEC="$PKG@$VERSION"
fi

echo "==> installing $SPEC into dsh profile '$PROFILE'"
dsh plugin --profile "$PROFILE" add "$SPEC"

echo
echo "==> done. Restart dsh to reload the Cordis bundle patch:"
echo "    (Ctrl-C / stop the running 'dsh $PROFILE', then start it again)"
echo
echo "Verify the tool appears next launch:"
echo "  dsh --profile $PROFILE --dump-config | grep -A4 vision-translate"
