#!/bin/bash
# Минимальная настройка без VNC

echo "🚀 Настройка Ubuntu сервера для Bobcofer (без VNC)"

# Обновление и установка Xfce
sudo apt update && sudo apt upgrade -y
sudo apt install -y xfce4 xfce4-goodies

# Установка Chrome
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update && sudo apt install -y google-chrome-stable

# Настройка Docker X11 доступа
sudo usermod -aG docker $USER
xhost +local:docker
echo "xhost +local:docker" >> ~/.bashrc

echo "✅ Настройка завершена. Перелогиньтесь и запустите: startx"
