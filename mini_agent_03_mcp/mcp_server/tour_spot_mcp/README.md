# Tour Spot MCP

한국관광공사 TourAPI를 이용해 대한민국 국내 관광지를 검색하는 MCP 서버입니다.

## 제공 Tool

- `search_tour_spots`

## 설정 및 실행

```powershell
Copy-Item .env.example .env
```

생성된 `.env`의 `TOUR_API_SERVICE_KEY`에 공공데이터포털 인증키를 입력한 뒤 실행합니다.

```powershell
pip install -r requirements.txt
python tour_spot_server.py
```

기본 주소는 `http://127.0.0.1:8030/mcp`입니다.
