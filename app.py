from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

app = Flask(__name__)

# === LINE 채널 정보 ===
LINE_CHANNEL_ACCESS_TOKEN = 'qW8jaVO+EKprbz/y6bPwMAcWhGLCgTS822GZGtJ3vjZsmEvH/+tPRP0BWTWktTDnuGjyfjmltnt86SdxSiZIsXdNwPVwjYRVLOz+UqWVoPBzZYMSeCpwErR7Urfp+szctzz01Tw6lxpeUOU88LvH1wdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'e042abfbb258184b5f014609d19dc52b'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


def get_timetable_for_direction(line_code: str, direction_name: str):
    try:
        JST = timezone(timedelta(hours=9))
        now = datetime.now(JST)

        weekday_map = {0: "平日", 5: "土曜", 6: "日曜・祝日"}
        day_of_week = now.weekday()
        if day_of_week in range(0, 5):
            day_type = "平日"
            kind_param = "1"
        elif day_of_week == 5:
            day_type = "土曜"
            kind_param = "2"
        else:
            day_type = "日曜・祝日"
            kind_param = "4"

        station_code = "22790"  # 타카다노바바역
        url = f"https://transit.yahoo.co.jp/timetable/{station_code}/{line_code}?ym={now.strftime('%Y%m')}&d={now.day}&kind={kind_param}"

        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()

        soup = BeautifulSoup(res.content, "html.parser")
        timetable = soup.find("table", class_="tblDiaDetail")
        if not timetable:
            return f"[{direction_name}] 시간표를 찾을 수 없습니다."

        results = []

        for row in timetable.find_all("tr", id=lambda x: x and x.startswith("hh_")):
            hour_td = row.find("td", class_="hour")
            if not hour_td or not hour_td.text.strip().isdigit():
                continue

            hour = int(hour_td.text.strip())
            if hour < now.hour and not (now.hour == 23 and hour == 0):
                continue

            ul = row.find("ul")
            if not ul:
                continue

            for li in ul.find_all("li", class_="timeNumb"):
                a_tag = li.find("a")
                if not a_tag:
                    continue
                dl = a_tag.find("dl")
                if not dl:
                    continue
                minute_tag = dl.find("dt")
                dest_tag = dl.find("dd", class_="trainFor")
                if not minute_tag or not minute_tag.text.strip().isdigit():
                    continue

                minute = int(minute_tag.text.strip())
                if hour == now.hour and minute < now.minute:
                    continue

                destination = dest_tag.text.strip() if dest_tag else "행선지 미상"
                results.append(f"🕒 {hour:02d}:{minute:02d} ({destination}행)")

                if len(results) >= 5:
                    break
            if len(results) >= 5:
                break

        reply = f"✅ {direction_name} 방면 열차\n\n"
        reply += "\n".join(results) if results else "이후 열차 정보를 찾을 수 없습니다."
        return reply

    except Exception as e:
        return f"[{direction_name}] 오류 발생: {e}"


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    print("[User message]", msg)

    if any(k in msg for k in ["열차", "야마노테", "타카다노바바"]):
        ikebukuro = get_timetable_for_direction("7170", "이케부쿠로")
        shinjuku = get_timetable_for_direction("7171", "신주쿠")
        reply = f"{ikebukuro}\n\n{shinjuku}"
    else:
        reply = "“열차”나 “야마노테”라고 보내면 타카다노바바역의 다음 열차를 알려드립니다."

    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply[:4999])
        )
        print("[Reply sent]")
    except Exception as e:
        print("[LINE reply error]", e)


# === Render용 포트 바인딩 ===
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
