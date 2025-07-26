#!/usr/bin/env bash
# Создаёт минимальный конфиг Fluxbox и валидный X-cookie
set -e

DISPLAY_NUM="${1#:}"
export DISPLAY=":${DISPLAY_NUM}"

# ── Fluxbox: минимальный набор файлов ──────────────────
FLUX_DIR="/root/.fluxbox"
mkdir -p "${FLUX_DIR}"
cat > "${FLUX_DIR}/init" <<EOF
session.screen0.workspaces: 1
session.screen0.toolbar.visible: false
session.screen0.slit.autoHide: true
EOF
touch "${FLUX_DIR}/"{keys,menu,apps}
chmod 644 "${FLUX_DIR}/"{init,keys,menu,apps}

# ── Генерация Xauthority ───────────────────────────────
Xvfb "${DISPLAY}" -screen 0 1x1x16 -ac &
XVFB_PID=$!
sleep 1
xauth generate "${DISPLAY}" . trusted >/dev/null
kill "${XVFB_PID}" || true

touch /root/.Xauthority
chmod 600 /root/.Xauthority

echo "[setup] X11 environment ready on display ${DISPLAY}"
