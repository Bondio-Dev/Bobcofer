#!/usr/bin/env bash
# setup_x11_config.sh
# Генерирует валидный Xauthority и минимальные конфиги Fluxbox
set -e

DISPLAY_NUM="${1#:}"
export DISPLAY=":${DISPLAY_NUM}"

# Минимальная конфигурация Fluxbox
FLUX_DIR="/root/.fluxbox"
mkdir -p "${FLUX_DIR}"
cat > "${FLUX_DIR}/init" <<EOF
session.screen0.workspaces: 1
session.screen0.toolbar.visible: false
session.screen0.slit.autoHide: true
EOF
touch "${FLUX_DIR}/keys" "${FLUX_DIR}/menu" "${FLUX_DIR}/apps"
chmod 644 "${FLUX_DIR}/"{init,keys,menu,apps}

# Генерация MIT-MAGIC-COOKIE-1
Xvfb "${DISPLAY}" -screen 0 1x1x16 -ac &
XVFB_PID=$!
sleep 1
xauth generate "${DISPLAY}" . trusted >/dev/null
kill $XVFB_PID || true

# Убедимся, что ~/.Xauthority существует
XAUTH_FILE="/root/.Xauthority"
touch "${XAUTH_FILE}"
chmod 600 "${XAUTH_FILE}"

echo "[setup] X11 и Fluxbox настроены"
