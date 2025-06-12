from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import os

app = Flask(__name__)

# 환경 변수 또는 하드코딩 (보안상 운영 시에는 환경 변수로만)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', 'qW8jaVO+EKprbz/y6bPwMAcWhGLCgTS822GZGtJ3vjZsmEvH/+tPRP0BWTWktTDnuGjyfjmltnt86SdxSiZIsXdNwPVwjYRVLOz+UqWVoPBzZYMSeCpwErR7Urfp+szctzz01Tw6lxpeUOU88LvH1wdB04t89/1O/w1cDnyilFU=')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', 'e042abfbb258184b5f014609d19dc52b')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


def get_timetable_for_direction(line_code: str, direction_name: str):
    try:
        jst = timezone(timedelta(hours=9))
        now = datetime.now(jst)

        day_type = {0: "平日", 5: "土曜", 6: "日曜・祝日"}.get(now.weekday(), "平日")
        kind = {'平日': '1', '土曜': '2', '日曜・祝日': '4'}.get(day_type, '1')

        url = f"https://transit.yahoo.co.jp/timetable/22790/{line_code}?ym={now.strftime('%Y%m')}&d={now.day}&kind={kind}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "html.parser")
        table = soup.find('table', class_='tblDiaDetail')

        if not table:
            return f"{direction_name}의 시간표 테이블을 찾을 수 없습니다."

        trains = []
        for row in table.find_all('tr', id=lambda x: x and x.startswith('hh_')):
            hour_td = row.find('td', class_='hour')
            if not hour_td or not hour_td.text.strip().isdigit():
                continue
            hour = int(hour_td.text.strip())

            if hour < now.hour and not (now.hour == 23 and hour == 0):
                continue

            ul = row.find('ul')
            if not ul:
                continue

            for li in ul.find_all('li', class_='timeNumb'):
                a_tag = li.find('a')
                if not a_tag:
                    continue
                dl = a_tag.find('dl')
                if not dl:
                    continue
                minute_tag = dl.find('dt')
                dest_tag = dl.find('dd', class_='trainFor')
                if not minute_tag or not minute_tag.text.strip().isdigit():
                    continue

                minute = int(minute_tag.text.strip())
                if hour == now.hour and minute < now.minute:
                    continue

                destination = dest_tag.text.strip() if dest_tag else "행선지 미상"
                trains.append(f"🕒 {hour:02d}:{minute:02d} ({destination}행)")

                if len(trains) >= 5:
                    break
            if len(trains) >= 5:
                break

        result = f"✅ {direction_name} 시간표\n\n"
        if trains:
            result += "\n".join(trains)
        else:
            result += "현재 이후 열차가 없습니다."
        return result

    except Exception as e:
        return f"{direction_name} 시간표 불러오기 실패: {e}"


@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"[ERROR] {e}")
    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()

    if any(keyword in msg for keyword in ["열차", "타카다노바바", "야마노테"]):
        reply_ikebukuro = get_timetable_for_direction("7170", "이케부쿠로 방면")
        reply_shinjuku = get_timetable_for_direction("7171", "신주쿠 방면")
        full_reply = reply_ikebukuro + "\n\n" + reply_shinjuku
    else:
        full_reply = "“열차”나 “야마노테”라고 입력하면 타카다노바바역의 다음 열차를 알려드립니다."

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=full_reply)
    )


# ✅ Render 배포를 위한 포트 설정
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render가 지정한 포트 사용
    app.run(host="0.0.0.0", port=port)
