import json
import os
import re
import urllib.error
import urllib.request

# 1) 예약 버튼 감시: 이름 -> 네이버 플레이스 주소
PLACES = {
    "대추밭백한의원": "https://m.place.naver.com/hospital/13258169/home",
    "지금부터핏 오류동(테스트)": "https://m.place.naver.com/place/1813888829/home",
}
# 2) 예약 가능 자리 감시: 이름 -> (네이버 예약 가게 번호, 알림을 누르면 열 주소)
BOOKINGS = {
    "대추밭백한의원": (
        "1359557",
        "https://m.booking.naver.com/booking/13/bizes/1359557",
    ),
    "지금부터핏 오류동(테스트)": (
        "981741",
        "https://m.place.naver.com/place/1813888829/home",
    ),
}
STATE_FILE = "state.json"
UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
)
TOPIC = os.environ["NTFY_TOPIC"]
BOOKING_ID = re.compile(r'"bookingBusinessId"\s*:\s*"(\d+)"')


def notify(title, message, click=None, urgent=False):
    body = {"topic": TOPIC, "title": title, "message": message}
    if click:
        body["click"] = click
    if urgent:
        body["priority"] = 5
        body["tags"] = ["rotating_light"]
    req = urllib.request.Request(
        "https://ntfy.sh/",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=20)


def fetch(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def has_booking(html):
    return BOOKING_ID.search(html) is not None


def slot_available(text):
    try:
        items = json.loads(text)
    except ValueError:
        return None
    if not isinstance(items, list):
        return None
    return any(isinstance(i, dict) and i.get("hasSlot") is True for i in items)


def main():
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)

    new_state = {}

    # 예약 버튼 감시
    for name, url in PLACES.items():
        status, html = fetch(url)
        prev = state.get(name)

        if status != 200:
            new_state[name] = {"status": "error"}
            if not prev or prev.get("status") != "error":
                notify(f"{name} 확인 실패", f"페이지를 읽지 못했어요 (HTTP {status})")
            continue

        now = has_booking(html)
        new_state[name] = {"status": "ok", "has_booking": now}

        if prev is None or "has_booking" not in prev:
            notify(
                f"{name} 감시 시작",
                "지금 예약 버튼: " + ("있음" if now else "없음"),
                url,
            )
        elif prev.get("status") == "ok" and not prev["has_booking"] and now:
            notify(f"{name} 예약 버튼 생김!", "지금 확인해 보세요", url, urgent=True)

    # 예약 가능 자리 감시
    for name, (biz, click) in BOOKINGS.items():
        key = f"{name}|예약가능"
        prev = state.get(key)
        status, text = fetch(
            f"https://api.booking.naver.com/v3.0/businesses/{biz}/biz-items"
        )
        avail = slot_available(text) if status == 200 else None

        if avail is None:
            new_state[key] = {"status": "error"}
            if not prev or prev.get("status") != "error":
                notify(f"{name} 예약 가능 확인 실패", f"HTTP {status}")
            continue

        new_state[key] = {"status": "ok", "available": avail}

        if prev is None or "available" not in prev:
            notify(
                f"{name} 예약 가능 감시 시작",
                "지금 예약 가능한 자리: " + ("있음" if avail else "없음"),
                click,
            )
        elif prev.get("status") == "ok" and not prev["available"] and avail:
            notify(
                f"{name} 예약 가능 자리 생김!",
                "지금 바로 예약 화면으로 들어가세요",
                click,
                urgent=True,
            )

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
