# 무한순환 매매 시그널 봇 (셀프호스트)

하락 마감일에 LOC 매수하는 무한순환 전략의 **오늘 할 일**을 매일 텔레그램으로 받는 봇입니다.
각자 **자기 봇**으로 운영하며, 봇은 직접 매매하지 않고 시그널만 보냅니다.

> ⚠️ 투자 자문이 아닙니다. 설정·주문·결과의 책임은 본인에게 있습니다.

## 1. 준비물 (각자 발급, 무료)

1. **텔레그램 봇 토큰** — 텔레그램에서 `@BotFather` → `/newbot` → 이름·아이디 정하면 토큰을 줍니다.
2. **Twelve Data API 키** — [twelvedata.com](https://twelvedata.com) 무료 가입 → 대시보드의 API Key.

## 2-A. 설치 (Render 버튼 · 제일 쉬움, 비개발자용)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/exitant-ai/kim2tanhello)

1. 위 버튼 클릭 → Render 로그인
2. `TOKEN`, `TD_KEY` 입력칸에 위에서 발급한 값 붙여넣기
3. **Create** → 잠시 후 배포 완료
4. 텔레그램에서 내 봇에게 `/start`

> Render의 항상 켜진 워커는 유료(월 ~$7)예요. 무료로 돌리려면 아래 Docker로 본인 PC/서버에 띄우세요.

## 2-B. 설치 (Docker · 자기 서버/PC)

```bash
docker build -t muhan-bot .
docker run -d --name muhan-bot \
  -e TOKEN="봇토큰" \
  -e TD_KEY="트웰브데이터키" \
  -e WEBAPP_URL="https://exitant-ai.github.io/kim2tanhello/config.html" \
  muhan-bot
```

(이미지를 Docker Hub에 올려두면 `docker pull <계정>/muhan-bot` 으로 바로 받게 할 수도 있어요.)

## 3. 사용법

1. 내 봇에게 `/start`
2. **[⚙️ 설정 열기]** → 미니앱에서 시드·종목·매수%·익절%·보관·투입 설정 → **봇 시작**
3. `/now` 로 지금 시그널 한 번 받기
4. 이후 **매일 미국 마감 직전 자동 발송**

## 환경변수 정리

| 변수 | 설명 |
|---|---|
| `TOKEN` | 텔레그램 봇 토큰 (@BotFather) |
| `TD_KEY` | Twelve Data API 키 |
| `WEBAPP_URL` | 설정 미니앱 주소 (기본값 사용 권장) |
