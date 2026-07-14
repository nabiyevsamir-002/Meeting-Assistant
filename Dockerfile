# İnkişaf mühiti üçün Docker image (Python 3.11, spec-ə uyğun)
FROM python:3.11-slim

# Sistem asılılıqlarını minimum saxlayırıq
WORKDIR /app

# Əvvəlcə requirements — layer keşindən maksimum faydalanmaq üçün
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tətbiq kodu
COPY app ./app
COPY capture ./capture

# data/ qovluğu volume kimi bağlanacaq
RUN mkdir -p data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
