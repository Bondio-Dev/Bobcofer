#!/usr/bin/env bash
# setup_x11_config.sh
# usage: setup_x11_config.sh <display>
set -e

DISPLAY_NUM="${1#:}"    # убираем ведущий :
export DISPLAY=":${DISPLAY_NUM}"

# Создаём минимальную конфигурацию Fluxbox
FLUX_DIR="/root/.fluxbox"
mkdir -p "${FLUX_DIR}"
cat > "${FLUX_DIR}/init" <<EOF
session.screen0.workspaces: 1
session.screen0.toolbar.visible: false
session.screen0.slit.autoHide: true
EOF
# Пустые файлы для избежания предупреждений
touch "${FLUX_DIR}/keys" "${FLUX_DIR}/menu" "${FLUX_DIR}/apps"
chmod 644 "${FLUX_DIR}/"{init,keys,menu,apps}

# Генерация валидного X authority cookie
echo "[setup] Generating Xauthority for display ${DISPLAY}"
# Запустим временно Xvfb для создания cookie
Xvfb "${DISPLAY}" -screen 0 1x1x16 -ac & 
XVFB_PID=$!
sleep 1
# Генерация cookie
xauth generate "${DISPLAY}" . trusted >/dev/null
# Остановка временного Xvfb
kill $XVFB_PID || true

# Гарантируем наличие файла ~/.Xauthority
XAUTH_FILE="/root/.Xauthority"
if [ ! -f "${XAUTH_FILE}" ]; then
  echo "[setup] Creating dummy .Xauthority"
  touch "${XAUTH_FILE}"
fi
chmod 600 "${XAUTH_FILE}"

echo "[setup] X11 configuration completed"
