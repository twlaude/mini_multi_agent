# Weather MCP

기상청 API를 이용해 전국 주요 지역의 현재 날씨와 주간 예보를 제공하는 MCP 서버입니다.

## 제공 Tool

- `get_current_weather(region="")` — 현재 날씨 (기온·습도·강수상태)
- `get_weekly_forecast(region="")` — 오늘부터 7일 예보 (최저/최고기온·하늘상태·강수확률)
- `list_regions()` — 지원 지역 목록

`region`에 지역명(예: 서울, 부산, 제주, 강릉)을 넣으면 해당 지역을 조회합니다.
"부산광역시", "제주도"처럼 행정 접미사가 붙어도 인식합니다. 생략하면 `.env`의 기본 지역을 씁니다.

지원 지역 (26곳): 서울, 인천, 수원, 파주, 춘천, 원주, 강릉, 속초, 대전, 세종, 청주, 충주,
광주, 목포, 여수, 전주, 군산, 대구, 포항, 안동, 부산, 울산, 창원, 진주, 제주, 서귀포

## 설정 및 실행

```powershell
Copy-Item .env.example .env
```

생성된 `.env`의 `KMA_SERVICE_KEY`에 공공데이터포털 기상청 API 인증키를 입력한 뒤 실행합니다.
나머지 값은 region 인자를 생략했을 때 쓰는 기본 지역(서울)입니다.

```powershell
pip install -r requirements.txt
python weather_server.py
```

기본 주소는 `http://127.0.0.1:8050/mcp`입니다.
