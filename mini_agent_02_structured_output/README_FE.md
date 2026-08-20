# Mini Travel Route Frontend

Streamlit 기반 여행 루트 추천 프런트엔드입니다. 여행 계획과 장소 좌표는 배포된 FastAPI 백엔드에서 받아오고, 장소는 카카오 지도에 표시합니다.

## 로컬 실행

```powershell
pip install -r requirements.txt
streamlit run frontend/app.py
```

## Streamlit Community Cloud

- Main file path: `frontend/app.py`
- Python: 3.12
- Secrets:

```toml
BACKEND_API_URL = "https://mini-multi-agent-htcs.onrender.com"
KAKAO_JS_KEY = "your-kakao-javascript-key"
```

실제 비밀값은 GitHub에 커밋하지 않습니다. Streamlit App settings의 Secrets에 직접 등록합니다.
