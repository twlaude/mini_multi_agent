"""백엔드의 places 응답을 카카오 지도에 표시하는 컴포넌트."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
import streamlit as st
import streamlit.components.v1 as components


def _load_local_environment() -> None:
    """로컬 실행에서 현재 프로젝트의 .env만 읽습니다."""
    project_environment = Path(__file__).resolve().parents[2] / ".env"
    if project_environment.is_file():
        load_dotenv(project_environment, override=False)


_load_local_environment()


def get_kakao_js_key() -> str:
    """환경변수 또는 Streamlit Secrets에서 JavaScript 키를 가져옵니다."""
    environment_value = os.getenv("KAKAO_JS_KEY", "").strip()
    if environment_value:
        return environment_value
    try:
        secret_value = st.secrets.get("KAKAO_JS_KEY", "")
    except (FileNotFoundError, KeyError):
        secret_value = ""
    return str(secret_value).strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _integer(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_places(places: Any) -> list[dict[str, Any]]:
    """지도에 사용할 수 있는 장소만 골라 원본과 분리된 안전한 목록을 만듭니다."""
    if not isinstance(places, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in places:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip()
        name = str(item.get("name", "")).strip()
        latitude = _number(item.get("lat"))
        longitude = _number(item.get("lng"))
        if kind not in {"origin", "landmark", "food"} or not name:
            continue
        if latitude is None or not -90 <= latitude <= 90:
            continue
        if longitude is None or not -180 <= longitude <= 180:
            continue
        minimum_day = 0 if kind == "origin" else 1
        normalized.append(
            {
                "name": name,
                "kind": kind,
                "day": max(_integer(item.get("day"), minimum_day), minimum_day),
                "order": max(_integer(item.get("order"), 0), 0),
                "lat": latitude,
                "lng": longitude,
                "address": str(item.get("address", "")).strip(),
            }
        )
    return normalized


def _safe_json(value: Any) -> str:
    """HTML script 요소를 닫는 문자열이 데이터로 삽입되지 않게 직렬화합니다."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def render_kakao_map(places: Any, height: int = 560) -> None:
    """장소 마커와 일차별 랜드마크 경로선을 렌더링합니다."""
    valid_places = normalize_places(places)
    if not valid_places:
        st.info("지도에서 확인할 수 있는 좌표가 없습니다.")
        _render_coordinate_table(valid_places)
        return

    app_key = get_kakao_js_key()
    if not app_key:
        st.warning(
            "카카오 지도를 표시하려면 Streamlit Secrets 또는 .env에 "
            "KAKAO_JS_KEY를 설정해 주세요."
        )
        _render_coordinate_table(valid_places)
        return

    places_json = _safe_json(valid_places)
    encoded_key = quote(app_key, safe="")
    safe_height = min(max(int(height), 320), 900)
    html_document = _MAP_HTML.replace("__PLACES_JSON__", places_json).replace(
        "__KAKAO_JS_KEY__", encoded_key
    )
    components.html(html_document, height=safe_height, scrolling=False)
    _render_coordinate_table(valid_places)


def _render_coordinate_table(places: list[dict[str, Any]]) -> None:
    """지도 SDK 상태와 무관하게 검증된 좌표를 보여줍니다."""
    columns = ("name", "kind", "day", "order", "address", "lat", "lng")
    table_data = {
        column: [place.get(column) for place in places] for column in columns
    }
    with st.expander("좌표로 보기"):
        if places:
            st.dataframe(table_data, hide_index=True, use_container_width=True)
        else:
            st.caption("표시할 수 있는 좌표가 없습니다.")


_MAP_HTML = r"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; background: #f8fafc; font-family: Arial, sans-serif; }
    #map-wrap { position: relative; width: 100%; height: 540px; overflow: hidden; border: 1px solid #e2e8f0; border-radius: 14px; }
    #map { width: 100%; height: 100%; }
    #message { display: none; position: absolute; inset: 0; z-index: 20; align-items: center; justify-content: center; padding: 24px; color: #991b1b; background: #fff7ed; text-align: center; }
    .legend { position: absolute; z-index: 10; top: 12px; left: 12px; padding: 9px 12px; border-radius: 10px; background: rgba(255,255,255,.94); box-shadow: 0 2px 8px rgba(15,23,42,.16); color: #334155; font-size: 12px; }
    .legend-row { display: flex; align-items: center; gap: 6px; margin: 3px 0; }
    .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .origin { background: #16a34a; }
    .landmark { background: #2563eb; }
    .food { background: #ef4444; }
    .info { min-width: 180px; max-width: 260px; padding: 10px 12px; color: #1e293b; font-size: 12px; line-height: 1.45; }
    .info strong { display: block; margin-bottom: 3px; color: #0f172a; font-size: 14px; }
  </style>
</head>
<body>
  <div id="map-wrap">
    <div id="map"></div>
    <div class="legend">
      <div class="legend-row"><span class="dot origin"></span>출발지 마커</div>
      <div class="legend-row"><span class="dot landmark"></span>랜드마크·일차별 경로</div>
      <div class="legend-row"><span class="dot food"></span>음식점 마커</div>
    </div>
    <div id="message"></div>
  </div>
  <script id="places-data" type="application/json">__PLACES_JSON__</script>
  <script>
    const places = JSON.parse(document.getElementById("places-data").textContent);
    const message = document.getElementById("message");
    const routeColors = ["#2563eb", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#be123c"];
    let kakaoLoadTimer = null;

    function showError(text) {
      message.textContent = text;
      message.style.display = "flex";
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function markerImage(kind) {
      const color = kind === "origin" ? "#16a34a" : kind === "food" ? "#ef4444" : "#2563eb";
      const label = kind === "origin" ? "O" : kind === "food" ? "F" : "L";
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44"><path fill="${color}" stroke="white" stroke-width="2" d="M17 1C8.2 1 1 8.2 1 17c0 12 16 26 16 26s16-14 16-26C33 8.2 25.8 1 17 1z"/><circle cx="17" cy="17" r="9" fill="white"/><text x="17" y="21" text-anchor="middle" font-family="Arial" font-size="11" font-weight="700" fill="${color}">${label}</text></svg>`;
      const source = `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
      return new kakao.maps.MarkerImage(
        source,
        new kakao.maps.Size(34, 44),
        { offset: new kakao.maps.Point(17, 43) }
      );
    }

    function renderMap() {
      if (!window.kakao || !kakao.maps || typeof kakao.maps.Map !== "function") {
        showError("카카오 지도 코어가 준비되지 않았습니다.");
        return;
      }

        const first = places[0];
        const map = new kakao.maps.Map(document.getElementById("map"), {
          center: new kakao.maps.LatLng(first.lat, first.lng),
          level: 6
        });
        const bounds = new kakao.maps.LatLngBounds();
        let openedInfoWindow = null;
        const routes = {};

        places.forEach((place) => {
          const position = new kakao.maps.LatLng(place.lat, place.lng);
          const marker = new kakao.maps.Marker({
            map,
            position,
            image: markerImage(place.kind),
            title: place.name
          });
          bounds.extend(position);

          const typeLabel = place.kind === "origin" ? "출발지" : place.kind === "food" ? "음식점" : "랜드마크";
          const dayLabel = place.kind === "origin" ? "" : ` · ${place.day}일차`;
          const orderLabel = place.kind === "landmark" && place.order > 0
            ? ` · ${place.order}번째 방문`
            : "";
          const content = `<div class="info"><strong>${escapeHtml(place.name)}</strong>${escapeHtml(typeLabel)}${escapeHtml(dayLabel)}${escapeHtml(orderLabel)}<br>${escapeHtml(place.address || "주소 정보 없음")}</div>`;
          const infoWindow = new kakao.maps.InfoWindow({ content, removable: true });
          kakao.maps.event.addListener(marker, "click", function () {
            if (openedInfoWindow) openedInfoWindow.close();
            infoWindow.open(map, marker);
            openedInfoWindow = infoWindow;
          });

          if (place.kind === "landmark") {
            const day = String(place.day);
            routes[day] = routes[day] || [];
            routes[day].push(place);
          }
        });

        Object.keys(routes)
          .sort((a, b) => Number(a) - Number(b))
          .forEach((day, index) => {
            const route = routes[day].sort((a, b) => a.order - b.order);
            if (route.length < 2) return;
            new kakao.maps.Polyline({
              map,
              path: route.map((place) => new kakao.maps.LatLng(place.lat, place.lng)),
              strokeWeight: 5,
              strokeColor: routeColors[index % routeColors.length],
              strokeOpacity: 0.82,
              strokeStyle: "solid"
            });
          });

        if (places.length === 1) {
          map.setCenter(new kakao.maps.LatLng(first.lat, first.lng));
          map.setLevel(5);
        } else {
          map.setBounds(bounds, 45, 45, 45, 45);
        }
    }

    function bootKakao() {
      if (!window.kakao || !kakao.maps) {
        showError("카카오 지도 SDK 로더를 불러오지 못했습니다.");
        return;
      }

      if (typeof kakao.maps.Map === "function") {
        renderMap();
        return;
      }

      if (typeof kakao.maps.load !== "function") {
        showError("카카오 지도 SDK 초기화 함수를 찾지 못했습니다.");
        return;
      }

      kakaoLoadTimer = window.setTimeout(function () {
        showError("카카오 지도 코어 로딩 시간이 초과되었습니다.");
      }, 8000);

      try {
        kakao.maps.load(function () {
          window.clearTimeout(kakaoLoadTimer);
          if (typeof kakao.maps.Map !== "function") {
            showError("카카오 지도 코어 초기화에 실패했습니다.");
            return;
          }
          renderMap();
        });
      } catch (error) {
        window.clearTimeout(kakaoLoadTimer);
        showError("카카오 지도 코어를 초기화하지 못했습니다.");
      }
    }

    const sdk = document.createElement("script");
    sdk.src = "https://dapi.kakao.com/v2/maps/sdk.js?appkey=__KAKAO_JS_KEY__&autoload=false";
    sdk.async = true;
    sdk.onload = bootKakao;
    sdk.onerror = function () {
      showError("카카오 지도 SDK 연결에 실패했습니다. 네트워크와 등록 도메인을 확인해 주세요.");
    };
    document.head.appendChild(sdk);
  </script>
</body>
</html>
"""
