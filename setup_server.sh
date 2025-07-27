#!/bin/bash
# Скрипт настройки Ubuntu сервера для работы с Xfce и Chrome

set -e

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🚀 Настройка Ubuntu сервера для Bobcofer${NC}"

# 1. Обновление системы
echo -e "${YELLOW}📦 Обновление системы...${NC}"
sudo apt update && sudo apt upgrade -y

# 2. Установка Xfce
echo -e "${YELLOW}🖥️ Установка Xfce Desktop Environment...${NC}"
sudo apt install -y xfce4 xfce4-goodies

# 3. Установка Google Chrome
echo -e "${YELLOW}🌐 Установка Google Chrome...${NC}"
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install -y google-chrome-stable

# 4. Установка VNC сервера (для удаленного доступа)
echo -e "${YELLOW}📺 Установка VNC сервера...${NC}"
sudo apt install -y tightvncserver

# 5. Настройка прав Docker
echo -e "${YELLOW}🐳 Настройка прав Docker...${NC}"
sudo usermod -aG docker $USER

# 6. Разрешение подключений к X-серверу
echo -e "${YELLOW}🔓 Настройка X11 прав...${NC}"
xhost +local:docker

# 7. Создание автозапуска X11 разрешений
echo -e "${YELLOW}⚙️ Создание автозапуска X11 разрешений...${NC}"
echo "xhost +local:docker" >> ~/.bashrc

# 8. Тестирование Chrome
echo -e "${YELLOW}🧪 Тестирование Google Chrome...${NC}"
if command -v google-chrome-stable &> /dev/null; then
    echo -e "${GREEN}✅ Google Chrome установлен успешно${NC}"
    
    # Проверка запуска Chrome в headless режиме
    if google-chrome-stable --headless --no-sandbox --disable-gpu --dump-dom https://www.google.com > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Chrome headless mode работает корректно${NC}"
    else
        echo -e "${RED}❌ Проблемы с Chrome headless mode${NC}"
    fi
else
    echo -e "${RED}❌ Google Chrome не установлен${NC}"
    exit 1
fi

# 9. Проверка X-сервера
echo -e "${YELLOW}🖥️ Проверка X-сервера...${NC}"
if [ -n "$DISPLAY" ]; then
    echo -e "${GREEN}✅ DISPLAY переменная установлена: $DISPLAY${NC}"
else
    echo -e "${YELLOW}⚠️ DISPLAY не установлен. Запустите: export DISPLAY=:0${NC}"
fi

# 10. Проверка Docker
echo -e "${YELLOW}🐳 Проверка Docker...${NC}"
if docker --version > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Docker установлен${NC}"
    
    # Проверка прав Docker
    if docker ps > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Docker права настроены корректно${NC}"
    else
        echo -e "${YELLOW}⚠️ Необходимо перелогиниться для применения Docker прав${NC}"
        echo -e "${YELLOW}Выполните: newgrp docker${NC}"
    fi
else
    echo -e "${RED}❌ Docker не установлен${NC}"
fi

# 11. Создание тестового скрипта
echo -e "${YELLOW}📝 Создание тестового скрипта...${NC}"
cat > ~/test_chrome.sh << 'EOF'
#!/bin/bash
echo "🧪 Тестирование Chrome с X11..."

export DISPLAY=:0
xhost +local:docker

echo "Запуск Chrome (должно открыться окно)..."
google-chrome-stable --no-sandbox https://web.whatsapp.com &

echo "Chrome PID: $!"
echo "Для завершения теста используйте: pkill chrome"
EOF

chmod +x ~/test_chrome.sh

echo -e "${GREEN}🎉 Настройка завершена!${NC}"
echo
echo -e "${YELLOW}📋 Что нужно сделать далее:${NC}"
echo "1. Перелогиньтесь или выполните: newgrp docker"
echo "2. Запустите X-сессию: startx"
echo "3. Протестируйте Chrome: ~/test_chrome.sh"
echo "4. Соберите проект: cd /home/ubuntu/Bobcofer && make rebuild"
echo
echo -e "${GREEN}🔗 VNC подключение (если нужно):${NC}"
echo "1. Настройте VNC: vncserver :1"
echo "2. Подключайтесь: IP_сервера:5901"
