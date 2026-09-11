FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# backend/app 이 상대 import(from .agent ...)를 쓰므로 backend 패키지 그대로 복사한다
COPY __init__.py ./backend/__init__.py
COPY app ./backend/app
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
