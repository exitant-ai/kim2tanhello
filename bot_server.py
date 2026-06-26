# -*- coding: utf-8 -*-
"""
무한순환 미니앱 봇 (Render 항상 켜짐 / 폴링 방식)
- /start  -> '설정 열기' 미니앱 버튼
- 미니앱에서 설정 완료 -> 설정 수신·저장(사용자별)
- 매일 미국 마감 직전 -> 사용자별 시그널 자동 발송
전략: 하락일 매수 + 묶음익절 + 보관 + 투입 + 쿼터 (시뮬레이터와 동일)
"""
import os, json, time, copy, urllib.request, urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN      = os.environ.get("TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://example.github.io/config.html")
SEND_H, SEND_M = 15, 50           # 미국 동부시간 발송 시각 (마감 직전)
USERS_FILE = os.environ.get("USERS_FILE", "users.json")
LABELS = {"TQQQ": "나스닥100 3배", "QLD": "나스닥100 2배", "SOXL": "반도체 3배"}
QEPS = 1.0
ET = ZoneInfo("America/New_York")
API = "https://api.telegram.org/bot" + TOKEN

# ===== 텔레그램 =====
def call(method, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(API + "/" + method, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print("[tg err]", method, e); return {}

def send(chat_id, text, reply_markup=None):
    p = {"chat_id": chat_id, "text": text}
    if reply_markup: p["reply_markup"] = reply_markup
    call("sendMessage", p)

# ===== 저장 =====
def load_users():
    if os.path.exists(USERS_FILE):
        try: return json.load(open(USERS_FILE, encoding="utf-8"))
        except Exception: return {}
    return {}
def save_users(u):
    json.dump(u, open(USERS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ===== 전략 =====
def fresh_state(cfg, start_px):
    return {"tradeCash": cfg["cap"], "vault": 0.0, "lots": [], "realized": 0.0,
            "prevPx": start_px, "peak": cfg["cap"], "storeBase": cfg["cap"],
            "curvePeak": cfg["cap"], "mdd": 0.0, "lastTotal": cfg["cap"],
            "buyCnt": 0, "tpCnt": 0, "storeCnt": 0, "injCnt": 0, "quarterCnt": 0, "last_date": ""}
def holdings(S, p): return sum(l["sh"] * p for l in S["lots"])
def total(S, p):    return S["tradeCash"] + S["vault"] + holdings(S, p)
def quarter_plan(S):
    tot = sum(l["sh"] for l in S["lots"]); tgt = tot * 0.25; sell = []
    for l in sorted(S["lots"], key=lambda l: -l["tpP"]):
        if tgt <= 1e-9: break
        take = min(l["sh"], tgt); sell.append({"tpP": l["tpP"], "sh": take}); tgt -= take
    return sell, sum(s["sh"] for s in sell)
def quarter_sell(S, price):
    sell, ssh = quarter_plan(S); prof = 0.0; tgt = ssh
    for l in sorted(S["lots"], key=lambda l: -l["tpP"]):
        if tgt <= 1e-9: break
        take = min(l["sh"], tgt); S["tradeCash"] += take * price; prof += take * (price - l["buyP"])
        l["sh"] -= take; tgt -= take
    S["lots"] = [l for l in S["lots"] if l["sh"] > 1e-9]
    S["realized"] += prof; S["quarterCnt"] += 1
    return {"soldSh": ssh, "prof": prof}
def step_day(S, price, cfg):
    is_up = price >= S["prevPx"]; ev = []
    if not is_up:
        if S["tradeCash"] < QEPS and S["lots"]:
            ev.append({"t": "quarter", **quarter_sell(S, price)})
        else:
            amt = min(total(S, price) * cfg["buyPct"] / 100.0, S["tradeCash"])
            if amt > 0.005:
                shh = amt / price; tpP = price * (1 + cfg["tpPct"] / 100.0)
                S["lots"].append({"sh": shh, "buyP": price, "tpP": tpP})
                S["tradeCash"] -= amt; S["buyCnt"] += 1
                ev.append({"t": "buy", "amt": amt, "price": price, "tpP": tpP})
    prof = sold = 0.0; remain = []
    for l in S["lots"]:
        if price >= l["tpP"]:
            S["tradeCash"] += l["sh"] * price; prof += l["sh"] * (price - l["buyP"]); sold += 1; S["tpCnt"] += 1
        else: remain.append(l)
    S["lots"] = remain
    if sold > 0: S["realized"] += prof; ev.append({"t": "tp", "prof": prof})
    tot = total(S, price)
    if S["storeBase"] > 0 and tot >= S["storeBase"] * (1 + cfg["sUp"] / 100.0):
        m = S["tradeCash"] * cfg["sPct"] / 100.0
        if m > 0.005: S["tradeCash"] -= m; S["vault"] += m; S["storeCnt"] += 1; ev.append({"t": "store", "m": m})
        S["storeBase"] = tot
    tot = total(S, price)
    if tot <= S["peak"] * (1 - cfg["iDn"] / 100.0) and S["vault"] > 0.005:
        m = S["vault"] * cfg["iPct"] / 100.0; S["vault"] -= m; S["tradeCash"] += m; S["injCnt"] += 1
        ev.append({"t": "inject", "m": m}); S["peak"] = total(S, price)
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
    conf = [(i.date().isoformat(), float(r["Close"])) for i, r in daily.iterrows() if i.date().isoformat() < today]
    try: cur = float(t.fast_info["last_price"])
    except Exception: cur = conf[-1][1] if conf else None
    return conf, cur

def money(x): return "$" + format(round(x), ",d")
def money2(x): return "$" + format(x, ",.2f")

def build_message(cfg, prov, ev, prev_px, cur):
    tk = cfg["ticker"]; chg = (cur / prev_px - 1) * 100 if prev_px else 0
    L = ["📅 " + datetime.now(ET).date().isoformat() + " · 무한순환 시그널",
         "🟢 " + tk + " (" + LABELS.get(tk, "") + ")  전일 " + money2(prev_px) + " / 현재 " + money2(cur) + " (" + format(chg, "+.2f") + "%)"]
    qt = next((e for e in ev if e["t"] == "quarter"), None)
    buy = next((e for e in ev if e["t"] == "buy"), None)
    if qt:
        L.append("🔻 쿼터(현금소진): 보유 1/4 = " + format(qt["soldSh"], ".4f") + "주 익절가 높은 순 시장가 매도")
    elif buy:
        L.append("· 하락 흐름 → LOC 매수 " + money(buy["amt"]) + " · 지정가=전일종가 " + money2(prev_px))
        L.append("· 종가가 " + money2(prev_px) + " 미만이면 체결 / 이상이면 미체결")
    else:
        L.append("· 상승 흐름 → 매수 없음 (종가 " + money2(prev_px) + " 미만이면 매수)")
    if prov["lots"]:
        m = {}
        for l in prov["lots"]:
            k = round(l["tpP"], 2); m[k] = m.get(k, 0) + l["sh"]
        it = sorted(m.items())[:5]
        L.append("📌 익절 GTC: " + " / ".join(money2(p) + " " + format(s, ".3f") + "주" for p, s in it)
                 + (" ...외 " + str(len(m) - 5) + "개" if len(m) > 5 else ""))
    L.append("📊 총자산 " + money(prov["lastTotal"]) + " · 현금 " + money(prov["tradeCash"])
             + " · 금고 " + money(prov["vault"]) + " · 보유 " + str(len(prov["lots"])) + "묶음")
    L.append("   누적익절 +" + money(prov["realized"]) + " · 보관" + str(prov["storeCnt"])
             + "/투입" + str(prov["injCnt"]) + "/쿼터" + str(prov["quarterCnt"]) + " · MDD " + format(prov["mdd"], ".1f") + "%")
    L.append("※ 봇은 직접 매매하지 않습니다. 주문은 직접 넣어주세요.")
    return "\n".join(L)

# ===== 핸들러 =====
def cmd_start(cid):
    kb = {"keyboard": [[{"text": "⚙️ 설정 열기", "web_app": {"url": WEBAPP_URL}}]],
          "resize_keyboard": True}
    send(cid, "무한순환 자동 시그널 봇이에요 🤖\n아래 [⚙️ 설정 열기]로 시드·종목·매수%·익절%를 설정하면,\n매일 미국 마감 직전에 시그널을 자동으로 보내드려요.", kb)

def on_config(cid, data_str):
    try:
        cfg = json.loads(data_str)
        for k in ("cap", "buyPct", "tpPct", "sUp", "sPct", "iDn", "iPct"): cfg[k] = float(cfg[k])
        cfg["ticker"] = str(cfg.get("ticker", "TQQQ"))
    except Exception as e:
        send(cid, "설정을 읽지 못했어요: " + str(e)); return
    users = load_users()
    users[str(cid)] = {"cfg": cfg, "state": None}   # 새 설정 -> 상태 초기화
    save_users(users)
    send(cid, "✅ 설정 저장 완료!\n종목 " + cfg["ticker"] + " · 시드 " + money(cfg["cap"])
         + " · 하락매수 " + str(cfg["buyPct"]) + "% · 익절 " + str(cfg["tpPct"]) + "%"
         + "\n매일 미국 마감 직전에 시그널을 보내드릴게요. /now 로 지금 한번 받아볼 수도 있어요.")

def run_for_user(cid, u, save=True):
    cfg = u.get("cfg")
    if not cfg: return
    try:
        conf, cur = fetch(cfg["ticker"])
    except Exception as e:
        send(cid, "데이터 오류: " + str(e)); return
    if not conf: send(cid, "데이터 없음"); return
    S = u.get("state")
    if S is None:
        S = fresh_state(cfg, conf[-1][1]); S["last_date"] = conf[-1][0]
    for d, c in conf:
        if d > S["last_date"]: step_day(S, c, cfg); S["last_date"] = d
    u["state"] = S
    prov = copy.deepcopy(S); ev = step_day(prov, cur, cfg) if cur else []
    send(cid, build_message(cfg, prov, ev, S["prevPx"], cur if cur else S["prevPx"]))

def run_daily():
    users = load_users()
    for cid, u in users.items():
        try: run_for_user(cid, u)
        except Exception as e: print("[daily err]", cid, e)
    save_users(users)

# ===== 메인 루프 =====
def main():
    if not TOKEN:
        print("TOKEN 환경변수가 없습니다."); return
    print("bot started. webapp:", WEBAPP_URL)
    offset = None; last_sent = None
    while True:
        now = datetime.now(ET)
        if now.weekday() < 5 and now.hour == SEND_H and now.minute >= SEND_M:
            today = now.date().isoformat()
            if last_sent != today:
                print("daily send", today); run_daily(); last_sent = today
        r = call("getUpdates", {"timeout": 25, "offset": offset}) if False else _get_updates(offset)
        for upd in r.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message") or {}
            cid = (msg.get("chat") or {}).get("id")
            if not cid: continue
            if msg.get("web_app_data"):
                on_config(cid, msg["web_app_data"]["data"])
            else:
                txt = msg.get("text", "")
                if txt.startswith("/start"): cmd_start(cid)
                elif txt.startswith("/now"):
                    users = load_users(); u = users.get(str(cid))
                    if u and u.get("cfg"): run_for_user(cid, u); save_users(users)
                    else: send(cid, "먼저 [⚙️ 설정 열기]로 설정해 주세요.")

def _get_updates(offset):
    q = {"timeout": 25}
    if offset is not None: q["offset"] = offset
    url = API + "/getUpdates?" + urllib.parse.urlencode(q)
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print("[poll err]", e); time.sleep(3); return {}

if __name__ == "__main__":
    main()
