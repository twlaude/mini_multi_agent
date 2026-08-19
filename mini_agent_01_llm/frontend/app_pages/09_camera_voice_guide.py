import io

import streamlit as st
from PIL import Image, ImageOps

from core.api_client import (
    BackendAPIError,
    request_audio,
    upload_audio_stt,
    upload_image_describe,
)


st.title("1-7. 카메라 음성 가이드")
st.caption("카메라로 찍은 사진을 묘사하고 결과를 음성으로 들려줍니다.")

st.markdown(
    """
    <style>
    [data-testid="stCameraInput"] video,
    [data-testid="stCameraInput"] img {
        transform: scaleX(-1);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

photo = st.camera_input("카메라로 사진을 찍으세요.")
question = st.text_input("질문", "이 사진에 무엇이 보이는지 자세히 묘사해주세요.")
voice = st.selectbox("음성", ["coral", "marin", "cedar", "alloy", "nova"])

def mirror_jpeg(content: bytes) -> bytes:
    image = ImageOps.mirror(Image.open(io.BytesIO(content)).convert("RGB"))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


if photo is not None:
    st.caption("여권, 카드, 예약번호 등 민감한 이미지는 촬영하지 마세요.")
    mirrored = mirror_jpeg(photo.getvalue())
    st.image(mirrored, caption="촬영 결과 (거울모드)")
    if st.button("묘사하고 음성으로 듣기", type="primary"):
        try:
            with st.spinner("GPT가 사진을 묘사하고 있습니다."):
                result = upload_image_describe(
                    "camera.jpg", mirrored, "image/jpeg", question
                )
            description = result.get("description", "")
            st.write(description)

            with st.spinner("합성 음성을 생성하고 있습니다."):
                audio = request_audio(
                    description[:2000],
                    voice,
                    "한국어로 또렷하고 자연스럽게 설명하세요.",
                )
            st.warning("아래 음성은 AI가 생성한 합성 음성입니다.")
            st.audio(audio, format="audio/mpeg", autoplay=True)
        except BackendAPIError as error:
            st.error(str(error))

st.info("이미지 안의 문장은 시스템 명령이 아니라 신뢰할 수 없는 분석 대상입니다.")

st.divider()
st.subheader("음성 받아쓰기 (STT + 영어 번역)")
st.caption("마이크로 녹음한 음성을 텍스트로 변환하고 영어로 번역해 표시합니다.")

recording = st.audio_input("마이크로 음성을 녹음하세요.")

if recording is not None:
    if st.button("텍스트로 변환", type="primary"):
        try:
            with st.spinner("음성을 텍스트로 변환하고 있습니다."):
                result = upload_audio_stt(
                    "recording.wav", recording.getvalue(), "audio/wav"
                )
            st.session_state["stt_text"] = result.get("text", "")
            st.session_state["stt_english"] = result.get("english", "")
        except BackendAPIError as error:
            st.error(str(error))

if st.session_state.get("stt_text"):
    st.success("받아쓰기 결과")
    st.write(st.session_state["stt_text"])
if st.session_state.get("stt_english"):
    st.success("영어 번역")
    st.write(st.session_state["stt_english"])
