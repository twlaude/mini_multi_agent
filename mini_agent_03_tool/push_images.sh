#!/usr/bin/env bash
# Docker Hub에 Backend·Frontend Image를 올린다 (compose.release.yml이 이 이름을 pull 한다).
# 맥북(arm64)에서 빌드해도 Windows/Intel PC가 받을 수 있게 amd64+arm64 멀티 아키텍처로 빌드·푸시한다.
# 사전 조건: docker login 완료. 사용법: bash push_images.sh [버전]   (기본 1.0.0)
set -euo pipefail
HUB_ID=twlaude
VERSION=${1:-1.0.0}
cd "$(dirname "$0")"
docker buildx build --platform linux/amd64,linux/arm64 -t "$HUB_ID/mini-agent-03-tool-backend:$VERSION"  --push ./backend
docker buildx build --platform linux/amd64,linux/arm64 -t "$HUB_ID/mini-agent-03-tool-frontend:$VERSION" --push ./frontend
echo "pushed: $HUB_ID/mini-agent-03-tool-{backend,frontend}:$VERSION"
