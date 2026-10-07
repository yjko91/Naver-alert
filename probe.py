import json
import os
import urllib.error
import urllib.request

BIZ = "1359557"
ITEM = "6566444"
API = "https://api.booking.naver.com/v3.0/businesses"
UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
)
TOPIC = os.environ["NTFY_TOPIC"]


def notify(title, message):
    body = {"topic": TOPIC, "title": title, "message": message[:3000]}
    req = urllib.request.Request(
        "https://ntfy.sh/",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=20)
    except Exception:
        pass


def request(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8", "ignore")
        except Exception:
            return e.code, ""
    except Exception as e:
        return 0, str(e)


def slim(d):
    return {k: v for k, v in d.items() if k != "prices"}


def main():
    base = f"{API}/{BIZ}/biz-items/{ITEM}"

    s, body = request(
        f"{base}/daily-schedules?startDateTime=2026-10-01T00:00:00"
        f"&endDateTime=2027-01-31T23:59:59&lang=ko"
    )
    try:
        data = json.loads(body)
    except ValueError:
        notify("탐색 일별 실패", f"HTTP {s}\n{body[:500]}")
        return
    dates = sorted(data)

    pick = [d for d in dates if "2026-10-07" <= d <= "2026-10-12"]
    notify(
        "탐색 A 10/7~10/12 (7수휴무 8마감 9휴무 10마감)",
        "\n".join(json.dumps(slim(data[d]), ensure_ascii=False) for d in pick),
    )

    pick = [d for d in dates if d in ("2026-11-30", "2026-12-01", "2026-12-02", dates[-1])]
    notify(
        "탐색 B 11/30, 12/1(미오픈), 12/2, 마지막날",
        "\n".join(json.dumps(slim(data[d]), ensure_ascii=False) for d in pick),
    )

    combos = {}
    free = []
    for d in dates:
        v = data[d]
        key = (v.get("isBusinessDay"), v.get("isSaleDay"), v.get("isHoliday"))
        combos[key] = combos.get(key, 0) + 1
        st, bc = v.get("stock"), v.get("bookingCount")
        if isinstance(st, int) and isinstance(bc, int) and st > bc:
            free.append(d)
    notify(
        "탐색 C 요약",
        f"날짜 {len(dates)}개 ({dates[0]}~{dates[-1]})\n"
        f"(영업일,판매일,휴일) 조합: {combos}\n"
        f"stock>bookingCount인 날짜 {len(free)}개: {free[:20]}",
    )

    s2, b2 = request(
        f"{base}/hourly-schedules?startDateTime=2026-10-08T00:00:00"
        f"&endDateTime=2026-10-08T23:59:59&lang=ko"
    )
    try:
        slots = json.loads(b2)
    except ValueError:
        notify("탐색 D 시간대 실패", f"HTTP {s2}\n{b2[:500]}")
        return
    if isinstance(slots, list):
        txt = "\n".join(json.dumps(x, ensure_ascii=False)[:450] for x in slots[:4])
        notify("탐색 D 10/8(마감) 시간대", f"HTTP {s2}, 슬롯 {len(slots)}개\n{txt}")
    else:
        notify("탐색 D 시간대", f"HTTP {s2}\n{b2[:800]}")


if __name__ == "__main__":
    main()
