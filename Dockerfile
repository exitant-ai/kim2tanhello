# 무한순환 시그널 봇 - 셀프호스트용 도커 이미지
FROM python:3.12-slim
WORKDIR /app
# zoneinfo(미국 동부시간) 용 타임존 데이터
RUN pip install --no-cache-dir tzdata
COPY bot_server.py .
# 환경변수: TOKEN(봇토큰), TD_KEY(Twelve Data 키), WEBAPP_URL(설정 미니앱 주소)
CMD ["python", "bot_server.py"]
