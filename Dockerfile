FROM python:3.11-slim

WORKDIR /app

# Копируем необходимые файлы проекта
COPY requirements.txt .
COPY main.py .
COPY database.py .
COPY .env.example .

# Создаем директорию для данных
RUN mkdir -p /app/data

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Запускаем бота
CMD ["python", "main.py"] 