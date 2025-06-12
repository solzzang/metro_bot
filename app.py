from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import os

app = Flask(__name__)

# --- 설정 (보안을 위해 환경 변수 사용을 권장합니다) ---
# 실제 운영 시에는 아래와 같이 os.environ.get()을 사용하여 환경 변수에서 토큰을 가져오는 것이 안전합니다.
# 예: LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_ACCESS_TOKEN = 'qW8jaVO+EKprbz/y6bPwMAcWhGLCgTS822GZGtJ3vjZsmEvH/+tPRP0BWTWktTDnuWjyfjmltnt86SdxSiZIsXdNwPVwjYRVLOz+UqWVoPBzZYMSeCpwErR7Urfk+szctzz01Tw6lxpeUOU88LvH1wdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'e042abfbb258184b5f014609d19dc52b'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

def get_next_yamanote():
    """야후 환승 정보에서 타카다노바바 역의 다음 야마노테선 열차 5개를 스크레이핑합니다."""
    try:
        # 1. 현재 일본 시간(JST, UTC+9)을 가져옵니다.
        jst_tz = timezone(timedelta(hours=9))
        now = datetime.now(jst_tz)
        
        # 2. 현재 시간을 기준으로 URL을 동적으로 생성합니다.
        #    - 야후 환승 정보는 시간(hh)을 기준으로 페이지를 제공합니다.
        url = f"https://transit.yahoo.co.jp/timetable/22790/7170?ym={now.strftime('%Y%m')}&d={now.day}&hh={now.hour}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()  # 4xx 또는 5xx 에러 발생 시 예외를 던집니다.
        
        soup = BeautifulSoup(res.content, "html.parser")

        # 3. 시간표가 담긴 테이블을 찾습니다.
        timetable = soup.find('table', {'id': 'tblTabel'})
        if not timetable:
            return ["시간표 정보를 찾을 수 없습니다."]

        found_trains = []
        
        # 4. 테이블의 모든 행(tr)을 순회하며 시간 정보를 찾습니다.
        for row in timetable.find_all('tr'):
            hour_cell = row.find('td', class_='hour')
            # 시간(hour) 정보가 없는 행은 건너뜁니다.
            if not hour_cell or not hour_cell.text.isdigit():
                continue
            
            row_hour = int(hour_cell.text)

            # 현재 시간보다 이전의 시간표는 건너뜁니다. (단, 23시에서 0시로 넘어가는 경우는 예외)
            if row_hour < now.hour and not (now.hour == 23 and row_hour == 0):
                continue
            
            # 5. 한 시간(row) 내의 모든 열차 정보를 순회합니다.
            for time_cell in row.find_all('td', class_='time'):
                minute_em = time_cell.find('dt')
                destination_span = time_cell.find('dd').find('span')

                # 분(minute)과 행선지 정보가 모두 있어야 유효한 데이터로 간주합니다.
                if not minute_em or not minute_em.text.strip().isdigit() or not destination_span:
                    continue
                
                departure_minute = int(minute_em.text.strip())
                
                # 현재 시간과 같은 시간(hour)대의 열차일 경우, 현재 분(minute) 이후의 열차만 확인합니다.
                if row_hour == now.hour and departure_minute < now.minute:
                    continue

                destination = destination_span.text.strip()
                
                # "🕒 17:05 (이케부쿠로행)" 형식으로 결과를 저장합니다.
                found_trains.append(f"🕒 {row_hour:02d}:{departure_minute:02d} ({destination}행)")

                # 5개의 열차 정보를 찾으면 루프를 종료합니다.
                if len(found_trains) >= 5:
                    return found_trains
        
        return found_trains if found_trains else ["현재 시간 이후 운행 예정인 열차가 없거나 정보를 가져올 수 없습니다."]

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Network or HTTP error: {e}")
        return ["네트워크 오류로 정보를 가져올 수 없습니다."]
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred in get_next_yamanote: {e}")
        return ["정보를 처리하는 중 오류가 발생했습니다."]

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"[ERROR] Handler error: {e}")
        return "Bad Request", 400
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    print(f"[RECEIVED] {text}")

    if "야마노테" in text or "타카다노바바" in text or "열차" in text:
        # "타카다노바바역 야마노테선 (내선순환)"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="잠시만요, 타카다노바바역 야마노테선 열차 정보를 찾고 있어요... 🚃")
        )
        
        trains = get_next_yamanote()
        reply_text = "✅ **타카다노바바역 도착 정보 (이케부쿠로 방면)**\n\n" + "\n".join(trains)

        # 응답을 비동기적으로 보내기 위해 새로운 push_message를 사용합니다.
        line_bot_api.push_message(
            event.source.user_id,
            TextSendMessage(text=reply_text)
        )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="“야마노테” 또는 “열차”라고 말해보세요! 타카다노바바역의 열차 도착 정보를 알려드릴게요.")
        )

if __name__ == "__main__":
    # 포트 번호는 환경에 따라 유동적으로 설정할 수 있습니다.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
