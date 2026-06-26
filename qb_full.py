# -*- coding: utf-8 -*-
"""
무한순환 하락일 매수 - 텔레그램 자동 봇 (TQQQ / QLD / SOXL)
시뮬레이터와 동일 로직: 하락일 매수 + 묶음별 익절 + 보관 + 투입 + 쿼터
계좌 상태를 state.json 에 기억하며 매일 이어갑니다.
"""

import os
import json
import copy
import urllib.request
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN    = os.environ.get("TOKEN", "")
CHAT_ID  = os.environ.get("CHAT_ID", "")
TICKERS  = ["TQQQ", "QLD", "SOXL"]
LABELS   = {"TQQQ": "나스닥100 3배", "QLD": "나스닥100 2배", "SOXL": "반도체 3배"}
STATE_FILE = "state.json"

CFG = {"cap": 1000, "buyPct": 3, "tpPct": 10, "sUp": 10, "sPct": 20, "iDn": 15, "iPct": 50}
QEPS = 1.0
ET = ZoneInfo("America/New_York")


def fresh_state(start_px):
    return {"tradeCash": CFG["cap"], "vault": 0.0, "lots": [], "realized": 0.0,
            "prevPx": start_px, "peak": CFG["cap"], "storeBase": CFG["cap"],
            "curvePeak": CFG["cap"], "mdd": 0.0, "lastTotal": CFG["cap"],
            "buyCnt": 0, "tpCnt": 0, "storeCnt": 0, "injCnt": 0, "quarterCnt": 0,
            "last_date": ""}

def holdings(S, p): return sum(l["sh"] * p for l in S["lots"])
def total(S, p):    return S["tradeCash"] + S["vault"] + holdings(S, p)

def quarter_plan(S):
    tot_sh = sum(l["sh"] for l in S["lots"]); target = tot_sh * 0.25
    sell = []
    for l in sorted(S["lots"], key=lambda l: -l["tpP"]):
        if target <= 1e-9: break
        take = min(l["sh"], target); sell.append({"tpP": l["tpP"], "sh": take}); target -= take
    return sell, sum(s["sh"] for s in sell)

def quarter_sell(S, price):
    sell, sell_sh = quarter_plan(S); proceeds = prof = 0.0; target = sell_sh
    for l in sorted(S["lots"], key=lambda l: -l["tpP"]):
        if target <= 1e-9: break
        take = min(l["sh"], target); proceeds += take * price; prof += take * (price - l["buyP"])
        l["sh"] -= take; target -= take
    S["lots"] = [l for l in S["lots"] if l["sh"] > 1e-9]
    S["tradeCash"] += proceeds; S["realized"] += prof; S["quarterCnt"] += 1
    return {"soldSh": sell_sh, "prof": prof, "nLots": len(sell)}

def step_day(S, price):
    is_up = price >= S["prevPx"]; ev = []
    if not is_up:
        if S["tradeCash"] < QEPS and S["lots"]:
            ev.append({"t": "quarter", **quarter_sell(S, price)})
        else:
            amt = min(total(S, price) * CFG["buyPct"] / 100.0, S["tradeCash"])
            if amt > 0.005:
                shh = amt / price; tpP = price * (1 + CFG["tpPct"] / 100.0)
                S["lots"].append({"sh": shh, "buyP": price, "tpP": tpP})
                S["tradeCash"] -= amt; S["buyCnt"] += 1
                ev.append({"t": "buy", "amt": amt, "sh": shh, "price": price, "tpP": tpP})
    prof = sold = 0.0; nlot = 0; remain = []
    for l in S["lots"]:
        if price >= l["tpP"]:
            S["tradeCash"] += l["sh"] * price; prof += l["sh"] * (price - l["buyP"])
            sold += l["sh"] * price; nlot += 1; S["tpCnt"] += 1
        else:
            remain.append(l)
    S["lots"] = remain
    if sold > 0: S["realized"] += prof; ev.append({"t": "tp", "prof": prof, "nlot": nlot})
    tot = total(S, price)
    if S["storeBase"] > 0 and tot >= S["storeBase"] * (1 + CFG["sUp"] / 100.0):
        m = S["tradeCash"] * CFG["sPct"] / 100.0
        if m > 0.005:
            S["tradeCash"] -= m; S["vault"] += m; S["storeCnt"] += 1
            ev.append({"t": "store", "m": m, "grow": (tot / S["storeBase"] - 1) * 100})
        S["storeBase"] = tot
    tot = total(S, price)
    if tot <= S["peak"] * (1 - CFG["iDn"] / 100.0) and S["vault"] > 0.005:
        m = S["vault"] * CFG["iPct"] / 100.0
        S["vault"] -= m; S["tradeCash"] += m; S["injCnt"] += 1
        ev.append({"t": "inject", "m": m, "drop": (1 - tot / S["peak"]) * 100})
        S["peak"] = total(S, price)
    tot = total(S, price)
    if tot > S["peak"]: S["peak"] = tot
    if tot > S["curvePeak"]: S["curvePeak"] = tot
    dd = (tot / S["curvePeak"] - 1) * 100
    if dd < S["mdd"]: S["mdd"] = dd
    S["prevPx"] = price; S["lastTotal"] = tot
    return ev


def fetch(ticker):
    import yfinance as yf
    t = yf.Ticker(ticker)
    daily = t.history(period="1mo", interval="1d", auto_adjust=False)
    today = datetime.now(ET).date().isoformat()
    confirmed = [(idx.date().isoformat(), float(row["Close"]))
                 for idx, row in daily.iterrows() if idx.date().isoformat() < today]
    try:
        cur = float(t.fast_info["last_price"])
    except Exception:
        cur = confirmed[-1][1] if confirmed else None
    return confirmed, cur


def money(x): return "$" + format(round(x), ",d")
def money2(x): return "$" + format(x, ",.2f")
def shf(x): return format(x, ".4f") + "주"

def build_block(tk, prov, ev, prev_px, cur):
    chg = (cur / prev_px - 1) * 100 if prev_px else 0
    L = ["🟢 " + tk + " (" + LABELS[tk] + ")  전일 " + money2(prev_px) + " / 현재 " + money2(cur) + " (" + format(chg, "+.2f") + "%)"]
    qt = next((e for e in ev if e["t"] == "quarter"), None)
    buy = next((e for e in ev if e["t"] == "buy"), None)
    if qt:
        L.append("   🔻 쿼터(현금소진): 보유 1/4 = " + shf(qt["soldSh"]) + " 익절가 높은 순 시장가 매도")
    elif buy:
        L.append("   · 하락 흐름 → LOC 매수 " + money(buy["amt"]) + " · 지정가=전일종가 " + money2(prev_px))
        L.append("   · 종가가 " + money2(prev_px) + " 미만이면 체결 / 이상이면 미체결")
    else:
        L.append("   · 상승 흐름 → 오늘 매수 없음 (종가 " + money2(prev_px) + " 미만이면 매수)")
    if prov["lots"]:
        m = {}
        for l in prov["lots"]:
            k = round(l["tpP"], 2); m[k] = m.get(k, 0) + l["sh"]
        items = sorted(m.items())[:5]
        L.append("   📌 익절 GTC: " + " / ".join(money2(p) + " " + shf(s) for p, s in items)
                 + (" ...외 " + str(len(m) - 5) + "개" if len(m) > 5 else ""))
    L.append("   📊 총자산 " + money(prov["lastTotal"]) + " · 현금 " + money(prov["tradeCash"])
             + " · 금고 " + money(prov["vault"]) + " · 보유 " + str(len(prov["lots"])) + "묶음")
    L.append("       누적익절 +" + money(prov["realized"]) + " · 보관" + str(prov["storeCnt"])
             + "/투입" + str(prov["injCnt"]) + "/쿼터" + str(prov["quarterCnt"]) + " · MDD " + format(prov["mdd"], ".1f") + "%")
    return "\n".join(L)


def load_state():
    if os.path.exists(STATE_FILE):
        try: return json.load(open(STATE_FILE, encoding="utf-8"))
        except Exception: return {}
    return {}

def save_state(state):
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        print("[no token/chat id -> console only]\n"); print(text); return
    url = "https://api.telegram.org/bot" + TOKEN + "/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            print("[sent]" if r.status == 200 else "[failed] " + str(r.status))
    except Exception as e:
        print("[send error]", e)


def main():
    try:
        import yfinance  # noqa: F401
    except ModuleNotFoundError:
        print("pip install yfinance"); return
    state = load_state()
    today = datetime.now(ET).date().isoformat()
    blocks = []
    for tk in TICKERS:
        try:
            confirmed, cur = fetch(tk)
        except Exception as e:
            blocks.append("⚠️ " + tk + " 데이터 오류: " + str(e)); continue
        if not confirmed:
            blocks.append("⚠️ " + tk + " 데이터 없음"); continue
        S = state.get(tk)
        if S is None:
            S = fresh_state(confirmed[-1][1]); S["last_date"] = confirmed[-1][0]
        for d, c in confirmed:
            if d > S["last_date"]:
                step_day(S, c); S["last_date"] = d
        state[tk] = S
        prov = copy.deepcopy(S)
        ev = step_day(prov, cur) if cur else []
        blocks.append(build_block(tk, prov, ev, S["prevPx"], cur if cur else S["prevPx"]))
    save_state(state)
    msg = "📅 " + today + " · 무한순환 자동 시그널\n\n" + "\n\n".join(blocks) + \
          "\n\n※ 봇은 직접 매매하지 않습니다. 주문은 직접 넣어주세요."
    send_telegram(msg)


if __name__ == "__main__":
    main()
