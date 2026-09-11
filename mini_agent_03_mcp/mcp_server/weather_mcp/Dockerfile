FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY weather_server.py .
EXPOSE 8050
CMD ["python", "weather_server.py"]
