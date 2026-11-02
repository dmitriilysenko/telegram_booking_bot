FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir gunicorn

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "telegram_booking_bot.wsgi:application", "--bind", "0.0.0.0:8000"]