import json
import os
import urllib.error
import urllib.request

TARGETS = [
    ("대추밭백한의원", "1359557", 13),
    ("지금부터핏", "981741", 13),
]
API = "https://api.booking.naver.com/v3.0/businesses"
START = "2026-10-01T00:00:00"
END = "2027-01-31T23:59:59"
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
    for label, biz, typ in TARGETS:
        s, body = request(f"{API}/{biz}/biz-items")
        try:
            items = json.loads(body)
        except ValueError:
            items = []
        if not isinstance(items, list):
            items = []
        items = [i for i in items if isinstance(i, dict)]
        lines = [
            f"{i.get('bizItemId')} | {i.get('name')} | "
            f"hasSlot={i.get('hasSlot')} | stock={i.get('stock')}"
            for i in items
        ]
        notify(f"탐색 {label} 상품 목록", f"HTTP {s}\n" + "\n".join(lines[:15]))
        if not items:
            continue

        item = items[0].get("bizItemId")
        out = []
        for name in ("daily-schedules", "hourly-schedules", "schedules"):
            url = (
                f"{API}/{biz}/biz-items/{item}/{name}"
                f"?startDateTime={START}&endDateTime={END}&lang=ko"
            )
            s2, b2 = request(url)
            out.append(f"[{name}] HTTP {s2}\n{b2[:300]}")

        payload = json.dumps(
            {
                "operationName": "schedule",
                "variables": {
                    "scheduleParams": {
                        "businessTypeId": typ,
                        "businessId": biz,
                        "bizItemId": str(item),
                        "startDateTime": START,
                        "endDateTime": END,
                        "fixedTime": True,
                    }
                },
                "query": QUERY,
            }
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Origin": "https://m.booking.naver.com",
            "Referer": f"https://m.booking.naver.com/booking/{typ}/bizes/{biz}",
        }
        for url in (
            "https://m.booking.naver.com/graphql?opName=schedule",
            "https://api.booking.naver.com/v3/graphql?opName=schedule",
        ):
            s3, b3 = request(url, data=payload, headers=headers)
            out.append(f"[graphql] HTTP {s3}\n{b3[:300]}")

        notify(f"탐색 {label} 일정 조회", "\n\n".join(out))


if __name__ == "__main__":
    main()
