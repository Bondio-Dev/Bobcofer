#!/usr/bin/env bash
# start.sh — запускает Xvfb, Fluxbox, x11vnc и бот
set -e

# Очистка старых процессов и блокировок
pkill -f "Xvfb|x11vnc|fluxbox" 2>/dev/null || true
rm -f /tmp/.X*-lock /tmp/.X11-unix/X* 2>/dev/null || true

echo "[start] Настройка X11..."
/usr/local/bin/setup_x11_config.sh 99

echo "[start] Запуск Xvfb :99"
/usr/bin/Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +extension RANDR +extension RENDER &
sleep 2
export DISPLAY=":99"

echo "[start] Запуск fluxbox"
fluxbox 2>/dev/null &
sleep 1

echo "[start] Запуск x11vnc"
x11vnc -display :99 -forever -shared -noxdamage \
       -rfbauth /root/.vnc/passwd -rfbport 5900 -listen 0.0.0.0 -bg
sleep 1

echo "[start] Запуск бота"
exec python /app/tgbot.py
