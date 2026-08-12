#!/usr/bin/env bash
# One-shot bootstrap: install Hermes config + skills + SOUL into ~/.hermes,
# then bring up docker-compose (finance-mcp + hermes gateway).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_DIR="${HERMES_DATA:-$HOME/.hermes}"

echo "[1/4] Preparing $HERMES_DIR"
mkdir -p "$HERMES_DIR/skills"

echo "[2/4] Installing config + SOUL (existing files backed up as *.bak)"
for f in config.yaml SOUL.md; do
  src="$ROOT/config/$( [ "$f" = "config.yaml" ] && echo hermes.config.yaml || echo SOUL.md )"
  dst="$HERMES_DIR/$f"
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then
    cp "$dst" "$dst.bak.$(date +%s)"
  fi
  cp "$src" "$dst"
done

echo "[3/4] Symlinking finance-skills → $HERMES_DIR/skills"
for skill in "$ROOT"/finance-skills/*/; do
  name="$(basename "$skill")"
  ln -snf "$skill" "$HERMES_DIR/skills/$name"
done

echo "[4/4] docker compose up"
cd "$ROOT/docker"
docker compose up -d --build

cat <<EOF

Done.

Hermes gateway  : http://localhost:8642  (OpenAI-compatible API)
Hermes dashboard: http://localhost:9119
finance-mcp     : http://localhost:7800/mcp

Try:
  docker exec -it hermes hermes chat
  > analyze NVDA

EOF
