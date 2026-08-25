"""웹캠 또는 이미지에서 번호판을 읽어 주차 게이트 API로 전송합니다."""

import argparse
import re
import time
from pathlib import Path
from typing import Any

try:
    import cv2
    import easyocr
except ModuleNotFoundError:
    cv2 = None
    easyocr = None

from clients.parking_client import submit_gate
from core.api_client import BackendAPIError


PLATE_PATTERN = re.compile(r"\d{2,3}[가-힣]\d{4}")


def plate_from_results(results: list, confidence: float) -> str | None:
    texts = [str(item[1]) for item in results if len(item) >= 3 and float(item[2]) >= confidence]
    for text in [*texts, "".join(texts)]:
        normalized = re.sub(r"[\s\-·]", "", text)
        match = PLATE_PATTERN.search(normalized)
        if match:
            return match.group(0)
    return None


def recognize(reader: Any, frame: Any, confidence: float) -> str | None:
    return plate_from_results(reader.readtext(frame, detail=1), confidence)


def send_gate(plate: str, mode: str, direction: str) -> tuple[str, str]:
    try:
        result = submit_gate(plate, direction, mode)
        return str(result.get("decision", "unknown")), str(result.get("reason", ""))
    except (BackendAPIError, ValueError) as error:
        return "error", str(error)


def run_image(args: Any, reader: Any) -> int:
    image_path = Path(args.image)
    frame = cv2.imread(str(image_path))
    if frame is None:
        print(f"이미지를 열 수 없습니다: {image_path}")
        return 1
    plate = recognize(reader, frame, args.confidence)
    if not plate:
        print("번호판 형식을 찾지 못했습니다.")
        return 2
    decision, reason = send_gate(plate, args.mode, args.direction)
    print(f"인식 번호: {plate} | decision={decision} | reason={reason}")
    cv2.putText(frame, f"{plate} / {decision}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.imshow("Parking plate reader", frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    return 0


def run_camera(args: Any, reader: Any) -> int:
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        print(f"웹캠 {args.camera}번을 열 수 없습니다. --image 옵션을 사용해 보세요.")
        return 1

    last_plate = None
    consecutive = 0
    cooldowns: dict[str, float] = {}
    display_message = "Waiting for plate"
    print("종료하려면 화면에서 q를 누르세요.")
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("카메라 프레임을 읽지 못했습니다.")
                return 2
            plate = recognize(reader, frame, args.confidence)
            if plate and plate == last_plate:
                consecutive += 1
            elif plate:
                last_plate, consecutive = plate, 1
            else:
                last_plate, consecutive = None, 0

            now = time.monotonic()
            if plate and consecutive >= 3 and now >= cooldowns.get(plate, 0):
                decision, reason = send_gate(plate, args.mode, args.direction)
                cooldowns[plate] = now + 30
                display_message = f"{plate} / {decision}"
                print(f"인식 번호: {plate} | decision={decision} | reason={reason}")
                consecutive = 0

            cv2.putText(frame, display_message, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            cv2.imshow("Parking plate reader", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return 0
    finally:
        camera.release()
        cv2.destroyAllWindows()


def parse_args():
    parser = argparse.ArgumentParser(description="주차장 번호판 OCR 리더")
    parser.add_argument("--mode", choices=["workflow", "agent"], default="workflow")
    parser.add_argument("--direction", choices=["enter", "exit"], default="enter")
    parser.add_argument("--camera", type=int, default=0, help="웹캠 장치 번호")
    parser.add_argument("--image", help="웹캠 대신 사용할 이미지 파일")
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--gpu", action="store_true", help="EasyOCR GPU 사용")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if cv2 is None or easyocr is None:
        print("카메라 패키지가 없습니다. 프로젝트 requirements.txt를 설치해 주세요.")
        return 3
    print("EasyOCR 모델을 불러오는 중입니다. 최초 실행에는 시간이 걸릴 수 있습니다.")
    reader = easyocr.Reader(["ko", "en"], gpu=args.gpu)
    return run_image(args, reader) if args.image else run_camera(args, reader)


if __name__ == "__main__":
    raise SystemExit(main())
