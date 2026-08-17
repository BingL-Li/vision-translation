#!/usr/bin/env bash
# upgrade.sh — refresh the Hermes native plugin copy of vision-translation.
#
# Hermes loads the plugin in-process from a git checkout at
#   $HERMES_PLUGIN_DIR/vision-translation   (default ~/.hermes/plugins/vision-translation)
# It is a plain `git clone` of this repository — NOT an npm package like the
# dsh adapter. Shipping a new release therefore has two independent delivery
# legs that must BOTH be refreshed:
#
#   tag vX.Y.Z → CI publishes vision-translation-dsh@X.Y.Z to npm
#              → adapters/dsh/upgrade.sh   (dsh side, npm)
#              → adapters/hermes/upgrade.sh (Hermes side, git)   ← this script
#
# The Hermes copy is refreshed by pulling the same git history it was cloned
# from. It must be updated ONLY through git (fetch + checkout) — never by
# copying files from a working tree. A file copy silently drops any local
# divergence, breaks the git connection, and turns the next `git pull` into a
# conflict. See the 2026-08-17 convention in CONTRIBUTING.md.
#
# Usage:
#   ./adapters/hermes/upgrade.sh              # refresh the default plugin copy
#   ./adapters/hermes/upgrade.sh /path/to/copy  # refresh a different checkout
#   HERMES_HOME=/tmp/x ./adapters/hermes/upgrade.sh  # respect a custom home
#
# After the refresh you MUST restart the Hermes process hosting the
# conversation (the plugin is imported in-process at startup; a running
# gateway keeps the module it loaded first). `hermes gateway restart`.
set -euo pipefail

DEFAULT_DIR="${HERMES_HOME:-$HOME/.hermes}/plugins/vision-translation"
TARGET="${1:-$DEFAULT_DIR}"
BRANCH="${BRANCH:-main}"

if [ ! -d "$TARGET/.git" ]; then
  echo "error: '$TARGET' is not a git checkout (no .git directory)." >&2
  echo "  install it first with: git clone https://github.com/BingL-Li/vision-translation \"$TARGET\"" >&2
  exit 1
fi

# Resolve the plugin copy's own remote so we pull from the same source it was
# cloned from, rather than hard-coding a URL that may have been changed.
REMOTE="$(git -C "$TARGET" remote get-url origin 2>/dev/null || echo '')"
if [ -z "$REMOTE" ]; then
  echo "error: '$TARGET' has no 'origin' remote." >&2
  exit 1
fi

echo "==> refreshing Hermes plugin copy at $TARGET"
echo "    remote: $REMOTE"

BEFORE="$(git -C "$TARGET" log --oneline -1 2>/dev/null || echo none)"

git -C "$TARGET" fetch origin

# Update the tracked branch to match origin exactly (this is the same
# mechanism the dsh profile uses for its bundle layer: adopt upstream's view,
# drop nothing, keep the single source of truth in the repo).
git -C "$TARGET" checkout -B "$BRANCH" "origin/$BRANCH" 2>&1 | tail -2

AFTER="$(git -C "$TARGET" log --oneline -1 2>/dev/null || echo none)"

echo
if [ "$BEFORE" = "$AFTER" ]; then
  echo "==> already up to date at $AFTER"
else
  echo "==> updated:"
  echo "    $BEFORE"
  echo "    $AFTER"
fi

echo
echo "==> done. Restart Hermes to load the refreshed plugin (in-process import):"
echo "    hermes gateway restart"
echo
echo "Verify:"
echo "  hermes plugins list | grep vision-translation"
echo "  grep version ~/.hermes/plugins/vision-translation/plugin.yaml"