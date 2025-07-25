#!/usr/bin/env bash
# start.sh — запускает Xvfb, Fluxbox, x11vnc и бота
set -e

# Очистка
pkill -f "Xvfb|x11vnc|fluxbox" 2>/dev/null || true
rm -f /tmp/.X*-lock /tmp/.X11-unix/X* 2>/dev/null || true

# Генерация X11-config и .Xauthority
echo "[start] Настройка X11..."
/usr/local/bin/setup_x11_config.sh 99

# Запуск Xvfb
echo "[start] Xvfb :99"
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +extension RANDR +extension RENDER &
sleep 2

# Экспорт дисплея
export DISPLAY=":99"

# Запуск Fluxbox без спама в логи
echo "[start] fluxbox"
fluxbox 2>/dev/null &
sleep 1

# Запуск x11vnc
echo "[start] x11vnc"
x11vnc -display :99 -forever -shared -noxdamage \
       -rfbauth /root/.vnc/passwd -rfbport 5900 -listen 0.0.0.0 -bg
sleep 1

# Запуск бота
echo "[start] python bot"
exec python /app/tgbot.py
