FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget gnupg2 xauth xvfb libxtst6 libxrandr2 \
    libasound2 libpangocairo-1.0-0 libatk1.0-0 \
    libgtk-3-0 libgdk-pixbuf2.0-0 python3-tk python3-dev \
  && wget -qO- https://dl.google.com/linux/linux_signing_key.pub \
      | apt-key add - \
  && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list \
  && apt-get update && apt-get install -y google-chrome-stable \
  && rm -rf /var/lib/apt/lists/*

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:0 \
    BROWSER=google-chrome

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "/app/tgbot.py"]
