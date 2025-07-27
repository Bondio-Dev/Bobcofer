# Настройка сервера для бота

1) установка UI: [Шаг 2, Xfce](https://habr.com/ru/companies/selectel/articles/928734/)

2) что то для мышки ```sudo apt-get install python3-tk python3-dev```

3) установка терминала для Xfce: ```sudo apt-get install --reinstall xfce4-terminal```

4) создание виртуального окружения и установка туда зависимостей
```
# Создать виртуальное окружение с именем bot_env
python3 -m venv bot_env

# Активировать его (для bash/zsh)
source bot_env/binactivate

# Установить зависимости из файла requirements.txt
pip install -r requirements.txt
```

5) переключение юзера ```su - myuser``` Password: 000

6) настройка прав
```
ls -l ~/.Xauthority

# Если его нет или он принадлежит root:

sudo cp /var/run/lightdm/root/:0 ~/.Xauthority

sudo chown $USER:$USER ~/.Xauthority

export DISPLAY=:0

export XAUTHORITY=$HOME/.Xauthority

xhost +local:$USER
sudo xhost +
```
7) Установка screen: ```sudo apt install screen```

8) запуск:  ```sudo screen -dmS bobcofer_bot python3 ~/Bobcofer/tgbot.py```

проверка ```screen -ls```

подключение ```screen -r bobcofer_bot```

9) остановка ```screen -S bobcofer_bot -X quit```


