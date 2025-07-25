FROM python:3.11-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99
ENV PATH="/usr/local/binPATH}"

WORKDIR /app

# 1) Установка системных пакетов и Google Chrome
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

# 2) Создаём обёртку для Chrome с --no-sandbox
RUN printf '#!/usr/bin/env bash\nexec /usr/bin/google-chrome-stable --no-sandbox --disable-gpu "$@"\n' \
       > /usr/local/bin/google-chrome-stable && chmod +x /usr/local/bin/google-chrome-stable

# 3) Копируем проект и утилиты настройки
COPY . /app
COPY setup_x11_config.sh /usr/local/bin/setup_x11_config.sh
RUN chmod +x /usr/local/bin/setup_x11_config.sh

# 4) Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# 5) Настройка VNC-пароля
RUN mkdir -p /root/.vnc \
 && x11vnc -storepasswd 12345 /root/.vnc/passwd \
 && chmod 600 /root/.vnc/passwd

# 6) Копируем скрипт старта
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# 7) Точка входа
CMD ["/usr/local/bin/start.sh"]
