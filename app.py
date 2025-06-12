from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import os

app = Flask(__name__)

# 환경 변수 또는 직접 입력 (실서비스 시 .env 또는 Render 환경 변수 사용 권장)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', 'YOUR_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', 'YOUR_SECRET')

# 실제 토큰 (배포 시 Render 환경 변수 사용 권장)
LINE_CHANNEL_ACCESS_TOKEN = 'hjUoJOCJiIyfsuhqOumA6Qwt/YaAYTgv9W8ovWuN5LsXbB5zdJ7OZNTPr6+vyBYB0bTQoCrg+vnGIRBvWFt/UWlaeYXp8ToqA0tcAlnsNmzXv+LByNq/TqLUT2f2XtnOlexKzalcU78fPlU4BJSw+AdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '472bb56c1dbe426d6be716d40965387a'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    print("[Webhook Received]:", body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ Invalid signature. Check channel secret.")
        abort(400)

    return "OK", 200

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
        print("[Sending reply to LINE]")
        print("Reply token:", event.reply_token)
        print("Message:\n", reply)
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply[:4999])  # 5000자 제한 회피
        )
        print("[Reply sent OK ✅]")

    except Exception as e:
        print("[LINE reply error ❌]:", str(e))

def get_timetable_for_direction(line_code: str, direction_name: str):
    try:
        jst = timezone(timedelta(hours=9))
        now = datetime.now(jst)
        
        day_of_week = now.weekday()
        if day_of_week < 5:
            day_type_text = "平日"
            kind_param = "1"
        elif day_of_week == 5:
            day_type_text = "土曜"
            kind_param = "2"
        else:
            day_type_text = "日曜・祝日"
            kind_param = "4"

        station_code = "22790"  # 타카다노바바
        url = f"https://transit.yahoo.co.jp/timetable/{station_code}/{line_code}?ym={now.strftime('%Y%m')}&d={now.day}&kind={kind_param}"

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "html.parser")

        timetable_table = soup.find('table', class_='tblDiaDetail')
        if not timetable_table:
            print(f"[ERROR] 시간표 테이블 없음: {direction_name}")
            return f"{direction_name}: 시간표를 찾지 못했습니다."

        found_trains = []

        for row in timetable_table.find_all('tr', id=lambda x: x and x.startswith('hh_')):
            hour_cell = row.find('td', class_='hour')
            if not hour_cell or not hour_cell.text.strip().isdigit():
                continue

            row_hour = int(hour_cell.text.strip())

            if row_hour < now.hour and not (now.hour == 23 and row_hour == 0):
                continue

            time_list_ul = row.find('ul')
            if not time_list_ul:
                continue

            for time_li in time_list_ul.find_all('li', class_='timeNumb'):
                dl_tag = time_li.find('a').find('dl') if time_li.find('a') else None
                if not dl_tag:
                    continue

                minute_dt = dl_tag.find('dt')
                destination_dd = dl_tag.find('dd', class_='trainFor')

                if not (minute_dt and minute_dt.text.strip().isdigit()):
                    continue

                minute = int(minute_dt.text.strip())
                if row_hour == now.hour and minute < now.minute:
                    continue

                destination = destination_dd.text.strip() if destination_dd else "행선지 미상"
                found_trains.append(f"🕒 {row_hour:02d}:{minute:02d} ({destination}행)")

                if len(found_trains) >= 5:
                    break
            if len(found_trains) >= 5:
                break

        result = f"🚆 [{direction_name} 방향]\n"
        if found_trains:
            result += "\n".join(found_trains)
        else:
            result += "표시할 열차가 없습니다."
        return result

    except Exception as e:
        print(f"[ERROR] {direction_name} 시간표 오류:", e)
        return f"{direction_name}: 오류 발생 ({str(e)})"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
