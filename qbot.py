# -*- coding: utf-8 -*-
"""
무한순환 하락일 매수 - 텔레그램 시그널 봇 (TQQQ / QLD / SOXL)
토큰은 파일에 안 적고 터미널에서 넘깁니다. 파일을 열 필요가 없어요.

준비 (한 번만):  pip install yfinance

테스트(콘솔 출력):
    python qbot.py

텔레그램으로 받기:
    set TOKEN=여기에_토큰
    set CHAT_ID=1763661127
    python qbot.py
"""

import os
import urllib.request
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN    = os.environ.get("TOKEN", "")
CHAT_ID  = os.environ.get("CHAT_ID", "1763661127")
TICKERS  = ["TQQQ", "QLD", "SOXL"]
SEED_USD = 1000
BUY_PCT  = 3
TP_PCT   = 10

ET = ZoneInfo("America/New_York")


def get_prices(ticker):
    import yfinance as yf
    t = yf.Ticker(ticker)
    daily = t.history(period="7d", interval="1d", auto_adjust=False)
    today = datetime.now(ET).date().isoformat()
    prev_close = None
    for idx, row in daily.iterrows():
        if idx.date().isoformat() < today:
            prev_close = float(row["Close"])
    if prev_close is None:
        prev_close = float(daily["Close"].iloc[-2])
    try:
        cur = float(t.fast_info["last_price"])
    except Exception:
        cur = float(daily["Close"].iloc[-1])
    return prev_close, cur


def ticker_block(ticker):
    try:
        prev_close, cur = get_prices(ticker)
    except Exception as e:
        return "- " + ticker + ": data error (" + str(e) + ")"
    chg = (cur / prev_close - 1) * 100
    buy_amt = SEED_USD * BUY_PCT / 100.0
    tp_price = prev_close * (1 + TP_PCT / 100.0)
    if cur < prev_close:
        return ("[BUY] " + ticker + "  down " + format(chg, "+.2f") + "%\n"
                "   LOC buy $" + format(buy_amt, ",.0f") + " / limit = prev close $" + format(prev_close, ".2f") + "\n"
                "   fills if close < $" + format(prev_close, ".2f") + "\n"
                "   take-profit +" + str(TP_PCT) + "% (~$" + format(tp_price, ".2f") + ")")
    else:
        return ("[SKIP] " + ticker + "  up " + format(chg, "+.2f") + "% - no buy\n"
                "   if it closes < $" + format(prev_close, ".2f") + " buy $" + format(buy_amt, ",.0f"))


def build_message():
    today = datetime.now(ET).date().isoformat()
    parts = ["[" + today + "] infinite-cycle down-day signal", ""]
    for tk in TICKERS:
        parts.append(ticker_block(tk))
        parts.append("")
    parts.append("Bot does not trade. Place orders yourself.")
    return "\n".join(parts)


def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        print("[no token/chat id -> console only]\n")
        print(text)
        return
    url = "https://api.telegram.org/bot" + TOKEN + "/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            print("[sent] check telegram." if r.status == 200 else "[failed] " + str(r.status))
    except Exception as e:
        print("[send error]", e)


def main():
    try:
        import yfinance  # noqa: F401
    except ModuleNotFoundError:
        print("yfinance not installed. run:  pip install yfinance")
        return
    send_telegram(build_message())


if __name__ == "__main__":
    main()
