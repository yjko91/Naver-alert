import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

# 감시 대상 (대추밭백한의원 네이버 예약)
NAME = "대추밭백한의원"
BIZ = "1359557"
ITEM = "6566444"
PLACE_URL = "https://m.place.naver.com/hospital/13258169/home"
CLICK = "https://m.booking.naver.com/booking/13/bizes/1359557"

API = "https://api.booking.naver.com/v3.0/businesses"
DAYS_AHEAD = 365  # 오늘부터 1년 뒤까지 모든 달을 확인
STATE_FILE = "state.json"
KST = timezone(timedelta(hours=9))
WEEK = "월화수목금토일"
UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
)
TOPIC = os.environ["NTFY_TOPIC"]
BOOKING_ID = re.compile(r'"bookingBusinessId"\s*:\s*"(\d+)"')


def quiet_now():
    """수면 시간(한국시간 00:00 ~ 06:30)이면 True."""
    t = datetime.now(KST)
    return (t.hour, t.minute) < (6, 30)


def notify(title, message, click=None, urgent=False):
    body = {"topic": TOPIC, "title": title, "message": message[:3000]}
    if click:
        body["click"] = click
    if quiet_now():
        # 수면 시간에는 소리와 진동 없이 조용히 알림 목록에만 쌓아요.
        body["priority"] = 2
    elif urgent:
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


def get_json(url):
    status, text = fetch(url)
    if status != 200:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def chunks(start, end, size=31):
    cur = start
    while cur <= end:
        last = min(cur + timedelta(days=size - 1), end)
        yield cur, last
        cur = last + timedelta(days=1)


def range_url(kind, a, b):
    return (
        f"{API}/{BIZ}/biz-items/{ITEM}/{kind}"
        f"?startDateTime={a.isoformat()}T00:00:00"
        f"&endDateTime={b.isoformat()}T23:59:59&lang=ko"
    )


def booking_page_open():
    """플레이스 페이지에 예약 버튼(예약 번호)이 있으면 예약창이 열린 것."""
    status, html = fetch(PLACE_URL)
    if status != 200:
        return None
    return BOOKING_ID.search(html) is not None


def fetch_open_dates(today):
    """예약 일정이 열려 있는(영업일) 날짜들. 휴무일과 아직 안 열린 날은 제외."""
    found = set()
    for a, b in chunks(today, today + timedelta(days=DAYS_AHEAD)):
        data = get_json(range_url("daily-schedules", a, b))
        if not isinstance(data, dict):
            return None
        for d, v in data.items():
            if (
                isinstance(v, dict)
                and v.get("isBusinessDay") is True
                and not v.get("isHoliday")
            ):
                found.add(d)
    return found


def fetch_available(open_dates, now):
    """열린 날짜의 시간대 중 지금 예약 가능한 칸 {날짜: [시각들]}."""
    groups = []
    for d in sorted(open_dates):
        dd = date.fromisoformat(d)
        if groups and (dd - groups[-1][0]).days <= 30:
            groups[-1][1] = dd
        else:
            groups.append([dd, dd])

    avail = {}
    total = 0
    sample = None
    for a, b in groups:
        slots = get_json(range_url("hourly-schedules", a, b))
        if not isinstance(slots, list):
            return None
        for s in slots:
            if not isinstance(s, dict):
                continue
            if not (s.get("isUnitBusinessDay") and s.get("isUnitSaleDay")):
                continue
            try:
                dt = datetime.fromisoformat(s.get("unitStartDateTime"))
            except (TypeError, ValueError):
                continue
            total += 1
            stock, booked = s.get("unitStock"), s.get("unitBookingCount")
            if sample is None:
                sample = f"{dt:%m/%d %H:%M} 정원 {stock} / 예약 {booked}"
            if dt <= now:
                continue
            if isinstance(stock, int) and isinstance(booked, int) and stock > booked:
                avail.setdefault(dt.strftime("%Y-%m-%d"), []).append(dt.strftime("%H:%M"))
    return avail, total, sample


def has_slot_flag():
    items = get_json(f"{API}/{BIZ}/biz-items")
    if not isinstance(items, list):
        return None
    return any(isinstance(i, dict) and i.get("hasSlot") is True for i in items)


def fmt_date(d):
    dd = date.fromisoformat(d)
    return f"{dd.month}/{dd.day}({WEEK[dd.weekday()]})"


def avail_lines(avail, dates, limit=6):
    return [f"{fmt_date(d)} " + ", ".join(sorted(avail[d])[:6]) for d in dates[:limit]]


def save(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def main():
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
    prev = state.get(NAME)

    now = datetime.now(KST)
    today = now.date()

    is_open = booking_page_open()
    open_dates = fetch_open_dates(today)
    result = fetch_available(open_dates, now) if open_dates is not None else None

    if result is None or is_open is None:
        if not prev or not prev.get("error"):
            notify(f"{NAME} 확인 실패", "예약 정보를 읽지 못했어요")
        keep = dict(prev or {})
        keep["error"] = True
        state[NAME] = keep
        save(state)
        return

    avail, total, sample = result
    flag = has_slot_flag()
    open_list = sorted(open_dates)

    if prev is None or "open_dates" not in prev:
        span = f"{open_list[0]} ~ {open_list[-1]}" if open_list else "없음"
        notify(
            f"{NAME} 감시 시작",
            f"예약창: {'열림' if is_open else '닫힘'}\n"
            f"열린 날짜 {len(open_list)}일 ({span})\n"
            f"예약 시간대 {total}칸 중 빈 자리 {sum(len(v) for v in avail.values())}칸\n"
            f"예시 칸: {sample}",
            CLICK,
        )
    else:
        was_open = prev.get("open", False)
        reopened = is_open and not was_open
        suffix = "" if is_open else " (예약창은 아직 닫힘)"
        tail = (
            "\n지금 바로 예약 화면으로 들어가세요"
            if is_open
            else "\n예약창이 열리면 따로 알려드릴게요"
        )

        new_open = sorted(set(open_list) - set(prev.get("open_dates", [])))
        new_avail = sorted(set(avail) - set(prev.get("avail_dates", [])))

        if reopened:
            if avail:
                body = (
                    "\n".join(avail_lines(avail, sorted(avail)))
                    + "\n지금 바로 예약 화면으로 들어가세요"
                )
            else:
                body = "아직 빈 날짜는 안 보여요. 예약 화면에서 확인해 보세요"
            notify(f"{NAME} 예약창이 열렸어요!", body, CLICK, urgent=True)

        if new_open:
            shown = ", ".join(fmt_date(d) for d in new_open[:8])
            more = f" 외 {len(new_open) - 8}일" if len(new_open) > 8 else ""
            notify(
                f"{NAME} 새 예약일 오픈!{suffix}",
                f"열린 날짜: {shown}{more}",
                CLICK,
                urgent=True,
            )

        if new_avail and not reopened:
            title = (
                f"{NAME} 예약 가능 자리 생김!"
                if is_open
                else f"{NAME} 빈자리 발생!{suffix}"
            )
            notify(
                title,
                "\n".join(avail_lines(avail, new_avail)) + tail,
                CLICK,
                urgent=True,
            )
        elif flag and not prev.get("has_slot") and not reopened:
            notify(
                f"{NAME} 예약 가능 자리 생김! (신호 감지){suffix}",
                "예약 화면에서 확인해 보세요",
                CLICK,
                urgent=True,
            )

    state[NAME] = {
        "open": bool(is_open),
        "open_dates": open_list,
        "avail_dates": sorted(avail),
        "has_slot": bool(flag),
    }
    save(state)


if __name__ == "__main__":
    main()
