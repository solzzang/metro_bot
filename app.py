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

def get_next_yamanote():
    """
    야후 환승 정보에서 타카다노바바 역의 다음 야마노테선 열차 5개를 스크레이핑합니다.
    요일(평일/토요일/휴일)을 자동으로 감지하여 정확한 시간표를 가져옵니다.
    """
    try:
        # 1. 현재 일본 시간(JST, UTC+9) 및 요일 정보 가져오기
        jst_tz = timezone(timedelta(hours=9))
        now = datetime.now(jst_tz)
        
        # weekday(): 월요일=0, 일요일=6
        day_of_week = now.weekday()
        if day_of_week < 5:
            day_type_text = "平日"  # 평일
        elif day_of_week == 5:
            day_type_text = "土曜"  # 토요일
        else: # 6 (일요일) 또는 공휴일(별도 처리는 생략)
            day_type_text = "休日"  # 휴일

        # 2. 현재 시간을 기준으로 URL 동적으로 생성
        url = f"https://transit.yahoo.co.jp/timetable/22790/7170?ym={now.strftime('%Y%m')}&d={now.day}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.content, "html.parser")
        print(f"[DEBUG] Page title: {soup.title.string}") # 디버깅용: 페이지 제목 출력

        # 3. 올바른 요일의 시간표 테이블 찾기
        timetable = None
        # 페이지의 모든 'h3' 태그 (보통 "平日", "土曜", "休日" 제목을 담고 있음)를 찾습니다.
        day_type_headers = soup.select('div#mdDiaTbl h3')
        for header in day_type_headers:
            if day_type_text in header.text:
                # 해당 요일(h3) 바로 다음에 오는 div 안의 table을 찾습니다.
                table_container = header.find_next_sibling('div', class_='tblDia')
                if table_container:
                    timetable = table_container.find('table', {'id': 'tblTabel'})
                break # 해당 요일의 테이블을 찾았으면 루프 종료

        if not timetable:
            return [f"'{day_type_text}' 시간표 정보를 찾을 수 없습니다. 페이지 구조가 변경되었을 수 있습니다."]

        # 4. 시간표 파싱하여 열차 정보 추출
        found_trains = []
        for row in timetable.find_all('tr'):
            hour_cell = row.find('td', class_='hour')
            if not hour_cell or not hour_cell.text.strip().isdigit():
                continue
            
            row_hour = int(hour_cell.text.strip())

            # 현재 시간보다 이전 시간의 열차는 건너뜀 (자정 넘어가는 경우 고려)
            if row_hour < now.hour and not (now.hour == 23 and row_hour == 0):
                continue
            
            for time_cell in row.find_all('td', class_='time'):
                # 'dl' 태그 안에 분, 행선지 정보가 함께 있음
                for departure_info in time_cell.find_all('dl'):
                    minute_dt = departure_info.find('dt')
                    destination_dd = departure_info.find('dd')
                    
                    if not (minute_dt and minute_dt.text.strip().isdigit() and destination_dd):
                        continue

                    departure_minute = int(minute_dt.text.strip())
                    
                    # 현재 시간과 같은 시간대의 경우, 현재 분 이후의 열차만 확인
                    if row_hour == now.hour and departure_minute < now.minute:
                        continue
                    
                    # 행선지 정보 추출 (불필요한 'Train' 아이콘 텍스트 제거)
                    destination_span = destination_dd.find('span')
                    destination = destination_span.text.strip() if destination_span else "행선지 미상"
                    
                    found_trains.append(f"🕒 {row_hour:02d}:{departure_minute:02d} ({destination}행)")

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
        # 사용자에게 즉시 피드백
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="잠시만요, 타카다노바바역 야마노테선 열차 정보를 찾고 있어요... 🚃")
        )
        
        # 시간 걸리는 작업 수행
        trains = get_next_yamanote()
        reply_text = "✅ **타카다노바바역 도착 정보 (이케부쿠로 방면)**\n\n" + "\n".join(trains)

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
