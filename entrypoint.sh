#!/bin/bash

echo "Ожидание запуска базы данных..."
sleep 3

# Код из main.py (init_db) автоматически создаст таблицы в БД
echo "Запуск бота..."
python main.py