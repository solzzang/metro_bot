from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import os

app = Flask(__name__)

# --- 설정 (보안을 위해 환경 변수 사용을 권장합니다) ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', 'YOUR_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', 'YOUR_CHANNEL_SECRET')

# 제공된 토큰 값으로 다시 설정합니다. 실제 운영 시에는 위와 같이 환경 변수를 사용하세요.
LINE_CHANNEL_ACCESS_TOKEN = 'qW8jaVO+EKprbz/y6bPwMAcWhGLCgTS822GZGtJ3vjZsmEvH/+tPRP0BWTWktTDnuWjyfjmltnt86SdxSiZIsXdNwPVwjYRVLOz+UqWVoPBzZYMSeCpwErR7Urfk+szctzz01Tw6lxpeUOU88LvH1wdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'e042abfbb258184b5f014609d19dc52b'


line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

def get_timetable_for_direction(line_code: str, direction_name: str):
    """
    지정된 노선 코드(방향)에 대한 야마노테선 시간표를 스크레이핑합니다.
    
    Args:
        line_code (str): 야후 환승 정보의 노선 코드 (예: '7170' for 이케부쿠로, '7171' for 신주쿠)
        direction_name (str): 응답 메시지에 표시될 방향 이름.
    """
    try:
        # 1. 현재 일본 시간(JST, UTC+9) 및 요일 정보 가져오기
        jst_tz = timezone(timedelta(hours=9))
        now = datetime.now(jst_tz)
        
        day_of_week = now.weekday()
        if day_of_week < 5: day_type_text = "平日"
        elif day_of_week == 5: day_type_text = "土曜"
        else: day_type_text = "休日"

        # 2. URL 동적으로 생성
        station_code = "22790" # 타카다노바바 역 코드
        url = f"https://transit.yahoo.co.jp/timetable/{station_code}/{line_code}?ym={now.strftime('%Y%m')}&d={now.day}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.content, "html.parser")

        # 3. 올바른 요일의 시간표 테이블 찾기
        timetable = None
        day_type_headers = soup.select('div#mdDiaTbl h3')
        for header in day_type_headers:
            if day_type_text in header.text:
                table_container = header.find_next_sibling('div', class_='tblDia')
                if table_container:
                    timetable = table_container.find('table', {'id': 'tblTabel'})
                break

        if not timetable:
            return f"'{direction_name}'의 '{day_type_text}' 시간표를 찾지 못했습니다."

        # 4. 시간표 파싱하여 열차 정보 추출
        found_trains = []
        for row in timetable.find_all('tr'):
            hour_cell = row.find('td', class_='hour')
            if not hour_cell or not hour_cell.text.strip().isdigit():
                continue
            
            row_hour = int(hour_cell.text.strip())

            if row_hour < now.hour and not (now.hour == 23 and row_hour == 0):
                continue
            
            for time_cell in row.find_all('td', class_='time'):
                for departure_info in time_cell.find_all('dl'):
                    minute_dt = departure_info.find('dt')
                    destination_dd = departure_info.find('dd')
                    
                    if not (minute_dt and minute_dt.text.strip().isdigit() and destination_dd):
                        continue

                    departure_minute = int(minute_dt.text.strip())
                    
                    if row_hour == now.hour and departure_minute < now.minute:
                        continue
                    
                    destination_span = destination_dd.find('span')
                    destination = destination_span.text.strip() if destination_span else "행선지 미상"
                    
                    found_trains.append(f"🕒 {row_hour:02d}:{departure_minute:02d} ({destination}행)")

                    if len(found_trains) >= 5:
                        break
                if len(found_trains) >= 5:
                    break
        
        # 결과 포매팅
        result_text = f"✅ **{direction_name}**\n\n"
        if found_trains:
            result_text += "\n".join(found_trains)
        else:
            result_text += "현재 시간 이후 운행 예정인 열차가 없거나 정보를 가져올 수 없습니다."
        return result_text

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Network error for {direction_name}: {e}")
        return f"{direction_name}: 네트워크 오류로 정보를 가져올 수 없습니다."
    except Exception as e:
        print(f"[ERROR] Unexpected error for {direction_name}: {e}")
        return f"{direction_name}: 정보를 처리하는 중 오류가 발생했습니다."

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
        # 사용자에게 즉시 피드백
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="잠시만요, 타카다노바바역 야마노테선 열차 정보를 찾고 있어요... 🚃")
        )
        
        # 이케부쿠로 방면 (내선순환, 7170) 정보 가져오기
        ikebukuro_info = get_timetable_for_direction('7170', '이케부쿠로·우에노 방면 (내선)')
        
        # 신주쿠 방면 (외선순환, 7171) 정보 가져오기
        shinjuku_info = get_timetable_for_direction('7171', '신주쿠·시부야 방면 (외선)')

        # 두 방향의 정보를 합쳐서 최종 메시지 생성
        reply_text = f"**타카다노바바역 실시간 도착 정보**\n\n" \
                     f"--------------------\n" \
                     f"{ikebukuro_info}\n\n" \
                     f"--------------------\n" \
                     f"{shinjuku_info}"

        # push 메시지로 최종 결과 전송
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
