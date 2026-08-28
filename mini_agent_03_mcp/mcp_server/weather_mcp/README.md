# Weather MCP

기상청 API를 이용해 현재 날씨와 주간 예보를 제공하는 MCP 서버입니다.

## 제공 Tool

- `get_current_weather`
- `get_weekly_forecast`

## 설정 및 실행

```powershell
Copy-Item .env.example .env
```

생성된 `.env`의 `KMA_SERVICE_KEY`에 공공데이터포털 기상청 API 인증키를 입력한 뒤 실행합니다. 나머지 기본값은 서울 기준입니다.

```powershell
pip install -r requirements.txt
python weather_server.py
```

기본 주소는 `http://127.0.0.1:8050/mcp`입니다.
