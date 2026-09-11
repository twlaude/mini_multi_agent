FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY hotel_server.py .
COPY app ./app
EXPOSE 8030
CMD ["python", "hotel_server.py"]
