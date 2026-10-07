import json
import os
import re
import urllib.error
import urllib.request

WITH_BUTTON = "https://m.place.naver.com/place/1813888829/home"
WITHOUT_BUTTON = "https://m.place.naver.com/hospital/13258169/home"
UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
)
TOPIC = os.environ["NTFY_TOPIC"]
PATTERN = re.compile(
    r'"([A-Za-z_]*(?:[Bb]ook|[Rr]eserv|[Nn]averPay)[A-Za-z_]*)"\s*:\s*'
    r'("(?:[^"\\]|\\.){0,60}"|[^,}\]]{0,40})'
)


def notify(title, message):
    body = {"topic": TOPIC, "title": title, "message": message[:3500]}
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


def items(html):
    found = {}
    for m in PATTERN.finditer(html):
        found.setdefault(m.group(1), m.group(2))
    return found


def main():
    s1, h1 = fetch(WITH_BUTTON)
    s2, h2 = fetch(WITHOUT_BUTTON)
    if s1 != 200 or s2 != 200:
        notify("진단 실패", f"HTTP {s1}, {s2}")
        return

    a, b = items(h1), items(h2)
    notify(
        "진단 1/3 요약",
        f"버튼O: 길이 {len(h1)}, 항목 {len(a)}개, "
        f"booking.naver.com {h1.count('booking.naver.com')}회, "
        f"'예약' {h1.count('예약')}회\n"
        f"버튼X: 길이 {len(h2)}, 항목 {len(b)}개, "
        f"booking.naver.com {h2.count('booking.naver.com')}회, "
        f"'예약' {h2.count('예약')}회",
    )

    only_a = [f"{k}={a[k]}" for k in a if k not in b]
    notify("진단 2/3 버튼O에만 있는 항목", "\n".join(only_a) or "없음")

    diff = [f"{k}: O={a[k]} / X={b[k]}" for k in a if k in b and a[k] != b[k]]
    notify("진단 3/3 값이 다른 항목", "\n".join(diff) or "없음")


if __name__ == "__main__":
    main()
