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
LINE_CHANNEL_ACCESS_TOKEN = 'qW8jaVO+EKprbz/y6bPwMAcWhGLCgTS822GZGtJ3vjZsmEvH/+tPRP0BWTWktTDnuGjyfjmltnt86SdxSiZIsXdNwPVwjYRVLOz+UqWVoPBzZYMSeCpwErR7Urfp+szctzz01Tw6lxpeUOU88LvH1wdB04t89/1O/w1cDnyilFU='
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
        if day_of_week < 5: 
            day_type_text = "平日" # 평일
            day_type_class = "weekday"
        elif day_of_week == 5: 
            day_type_text = "土曜" # 토요일
            day_type_class = "saturday"
        else: 
            day_type_text = "日曜・祝日" # 일요일/공휴일
            day_type_class = "holiday"

        # 2. URL 동적으로 생성
        station_code = "22790" # 타카다노바바 역 코드
        # Yahoo Transit은 요일에 따라 URL 파라미터 'kind'를 사용할 수 있습니다.
        # kind=1: 平日, kind=2: 土曜, kind=4: 日曜・祝日 (HTML에서 확인된 값)
        kind_param = {'平日': '1', '土曜': '2', '日曜・祝日': '4'}.get(day_type_text, '1')
        url = f"https://transit.yahoo.co.jp/timetable/{station_code}/{line_code}?ym={now.strftime('%Y%m')}&d={now.day}&kind={kind_param}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status() # HTTP 오류 발생 시 예외 발생
        
        soup = BeautifulSoup(res.content, "html.parser")

        # 3. 올바른 요일의 시간표 테이블 찾기 (새로운 구조 반영)
        # tblDiaDetail 클래스를 가진 테이블을 직접 찾습니다.
        # 이 테이블 안에는 모든 요일의 정보가 들어있으므로, 내부에서 요일 필터링이 필요합니다.
        timetable_table = soup.find('table', class_='tblDiaDetail')

        if not timetable_table:
            print(f"[ERROR] Could not find 'tblDiaDetail' table for {direction_name}.")
            return f"'{direction_name}'의 시간표 테이블을 찾지 못했습니다."

        # 현재 요일에 해당하는 시간표 행을 찾습니다.
        # HTML 구조상, 요일 정보는 <ul class="navDayOfWeek"> 안에 <li class="weekday/saturday/holiday"><span>요일</span></li> 로 되어있습니다.
        # 그리고 이 <ul>은 시간표 테이블의 첫 번째 행 (<tr>) 안에 있습니다.
        
        # 실제 열차 시간 정보가 있는 행들을 찾습니다.
        # 요일별 구분은 URL의 'kind' 파라미터로 이미 되었을 가능성이 높습니다.
        # 따라서, 직접 'tblDiaDetail' 테이블 내의 시간 행을 파싱합니다.
        
        found_trains = []
        
        # 시간(hour)과 분(minute)이 들어있는 행들을 순회합니다.
        # 첫 번째 <tr>은 헤더이므로 건너뛰거나, id가 'hh_'로 시작하는 <tr>만 선택할 수 있습니다.
        for row in timetable_table.find_all('tr', id=lambda x: x and x.startswith('hh_')):
            hour_cell = row.find('td', class_='hour')
            if not hour_cell or not hour_cell.text.strip().isdigit():
                continue
            
            row_hour = int(hour_cell.text.strip())

            # 현재 시간보다 이전 시간의 열차는 건너뜁니다 (23시-0시 넘김 처리 포함)
            if row_hour < now.hour and not (now.hour == 23 and row_hour == 0):
                continue
            
            # 각 시간(hour) 셀 안의 개별 열차 정보들을 찾습니다.
            # HTML 구조상, 각 열차 정보는 <td> 다음의 <ul> 안에 <li class="timeNumb">으로 있습니다.
            # 그리고 각 <li> 안에는 <a href="..."> 태그가 있고, 그 안에 <dl><dt>분</dt><dd>행선지</dd></dl>가 있습니다.
            
            # `<td>` 태그 다음에 오는 `<ul>` 안의 모든 `<li>` 태그를 찾습니다.
            time_list_ul = row.find('ul') 
            if not time_list_ul:
                continue

            for time_li in time_list_ul.find_all('li', class_='timeNumb'):
                # 각 <li> 안의 <a> 태그를 찾고, 그 안의 <dl> 태그를 찾습니다.
                dl_tag = time_li.find('a').find('dl') if time_li.find('a') else None
                
                if not dl_tag:
                    continue

                minute_dt = dl_tag.find('dt')
                destination_dd = dl_tag.find('dd', class_='trainFor') # 행선지 클래스 변경 확인
                
                if not (minute_dt and minute_dt.text.strip().isdigit()):
                    continue

                departure_minute = int(minute_dt.text.strip())
                
                # 현재 분보다 이전 열차는 건너뜁니다.
                if row_hour == now.hour and departure_minute < now.minute:
                    continue
                
                # 행선지 정보 추출: class="trainFor"인 dd 태그의 텍스트
                destination = destination_dd.text.strip() if destination_dd else "행선지 미상"
                
                found_trains.append(f"🕒 {row_hour:02d}:{departure_minute:02d} ({destination}행)")

                if len(found_trains) >= 5: # 최대 5개 열차 정보만 표시
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
        return f"{direction_name}: 정보를 처리하는 중 오류가 발생했습니다. ({e})" # 어떤 오류인지 메시지에 포함
