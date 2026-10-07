import json
import os
import re
import urllib.error
import urllib.request

BIZ = "1359557"
TYPE = "13"
PAGE = f"https://m.booking.naver.com/booking/{TYPE}/bizes/{BIZ}"
UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
)
TOPIC = os.environ["NTFY_TOPIC"]

QUERY = (
    "query schedule($scheduleParams: ScheduleParams) { "
    "schedule(input: $scheduleParams) { bizItemSchedule { daily { "
    "date stock bookingCount isBusinessDay isSaleDay isUnitSaleDay "
    "isUnitBusinessDay } } } }"
)


def notify(title, message):
    body = {"topic": TOPIC, "title": title, "message": message[:3500]}
    req = urllib.request.Request(
        "https://ntfy.sh/",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=20)


def request(url, data=None, headers=None):
    h = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "ignore")
        except Exception:
            body = ""
        return e.code, body
    except Exception as e:
        return 0, str(e)


def main():
    s, html = request(PAGE)
    ids = sorted(set(re.findall(r'bizItemId["\s:]+"?(\d{4,})', html)))[:5]
    item_urls = sorted(set(re.findall(r"/items/(\d+)", html)))[:5]
    pos = html.find("bizItem")
    snippet = html[pos : pos + 300] if pos >= 0 else "없음"
    notify(
        "탐색 1/4 예약 페이지",
        f"HTTP {s}, 길이 {len(html)}\nbizItemId {ids}\nitems 경로 {item_urls}\n"
        f"'마감' {html.count('마감')}회\n조각: {snippet}",
    )

    s2, b2 = request(f"https://api.booking.naver.com/v3.0/businesses/{BIZ}/biz-items")
    notify("탐색 2/4 상품 목록 API", f"HTTP {s2}\n{b2[:800]}")

    item = ids[0] if ids else (item_urls[0] if item_urls else None)
    if not item:
        notify("탐색 3/4, 4/4 건너뜀", "상품 번호(bizItemId)를 찾지 못했어요")
        return

    payload = json.dumps(
        {
            "operationName": "schedule",
            "variables": {
                "scheduleParams": {
                    "businessTypeId": int(TYPE),
                    "businessId": BIZ,
                    "bizItemId": item,
                    "startDateTime": "2026-10-01T00:00:00",
                    "endDateTime": "2026-10-31T23:59:59",
                    "fixedTime": True,
                }
            },
            "query": QUERY,
        }
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://m.booking.naver.com",
        "Referer": PAGE,
    }
    for n, url in enumerate(
        [
            "https://m.booking.naver.com/graphql?opName=schedule",
            "https://api.booking.naver.com/v3/graphql?opName=schedule",
        ],
        start=3,
    ):
        s3, b3 = request(url, data=payload, headers=headers)
        notify(f"탐색 {n}/4 일정 조회", f"{url}\nHTTP {s3}\n{b3[:800]}")


if __name__ == "__main__":
    main()
