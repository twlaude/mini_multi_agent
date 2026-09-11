FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY tour_spot_server.py .
COPY tour_spot ./tour_spot
EXPOSE 8040
CMD ["python", "tour_spot_server.py"]
