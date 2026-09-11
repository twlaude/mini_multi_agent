#!/usr/bin/env bash
# Docker Hub에 Image 5개(backend·frontend·hotel/tour_spot/weather MCP)를 올린다.
# 맥북(arm64)에서 빌드해도 Windows/Intel PC가 받을 수 있게 amd64+arm64 멀티 아키텍처로 빌드·푸시한다.
# 사전 조건: docker login 완료. 사용법: bash push_images.sh [버전]   (기본 1.0.0)
set -euo pipefail
HUB_ID=twlaude
VERSION=${1:-1.0.0}
cd "$(dirname "$0")"
build() { docker buildx build --platform linux/amd64,linux/arm64 -t "$HUB_ID/mini-agent-03-$1:$VERSION" --push "$2"; }
build hotel-mcp     ./mcp_server/hotel_mcp
build tour-spot-mcp ./mcp_server/tour_spot_mcp
build weather-mcp   ./mcp_server/weather_mcp
build backend       ./backend
build frontend      ./frontend
echo "pushed: $HUB_ID/mini-agent-03-{hotel-mcp,tour-spot-mcp,weather-mcp,backend,frontend}:$VERSION"
