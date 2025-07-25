# Dockerfile
FROM python:3.11-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99

WORKDIR /app

# Установка системных пакетов и Google Chrome
RUN apt-get update && apt-get install --no-install-recommends -y \
      curl wget gnupg gcc libsqlite3-dev \
      xvfb x11vnc fluxbox \
      x11-utils xauth procps net-tools \
      fonts-liberation libxss1 libcanberra-gtk3-0 \
      libgl1-mesa-dri libgl1-mesa-glx libpango1.0-0 \
      libpulse0 libv4l-0 fonts-symbola \
  && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
  && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
         > /etc/apt/sources.list.d/google-chrome.list \
  && apt-get update && apt-get install --no-install-recommends -y \
         google-chrome-stable \
  && rm -rf /var/lib/apt/lists/*

# Копирование проекта и скрипта настройки
COPY . /app
COPY setup_x11_config.sh /usr/local/bin/setup_x11_config.sh
RUN chmod +x /usr/local/bin/setup_x11_config.sh

# Установка Python-зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Настройка VNC-пароля и Fluxbox (минимальные файлы создаст скрипт)
RUN mkdir -p /root/.vnc \
 && x11vnc -storepasswd 12345 /root/.vnc/passwd \
 && chmod 600 /root/.vnc/passwd

# Создание скрипта запуска сервисов
RUN printf '#!/bin/bash\n\
set -e\n\
# Очистка старых процессов и блокировок\n\
pkill -f "Xvfb|x11vnc|fluxbox" 2>/dev/null || true\n\
rm -f /tmp/.X*-lock /tmp/.X11-unix/X* 2>/dev/null || true\n\
\n\
# Генерация X11 конфигов и .Xauthority\n\
echo \"[setup] Generating X11 configs\"\n\
/usr/local/bin/setup_x11_config.sh :99\n\
\n\
# Запуск Xvfb\n\
echo \"[start] Xvfb\"\n\
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +extension RANDR +extension RENDER &\n\
sleep 2\n\
export DISPLAY=\":99\"\n\
\n\
# Запуск Fluxbox\n\
echo \"[start] fluxbox\"\n\
fluxbox 2>/dev/null &\n\
sleep 1\n\
\n\
# Запуск x11vnc\n\
echo \"[start] x11vnc\"\n\
x11vnc -display :99 -forever -shared -noxdamage \\\n\
       -rfbauth /root/.vnc/passwd -rfbport 5900 -listen 0.0.0.0 -bg\n\
sleep 1\n\
\n\
# Старт бота\n\
echo \"[start] python bot\"\n\
python /app/tgbot.py\n' > /start.sh && chmod +x /start.sh

CMD ["/start.sh"]
