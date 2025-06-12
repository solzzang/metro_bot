from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
from bs4 import BeautifulSoup

# --- LINE 인증 정보 (직접 입력) ---
LINE_CHANNEL_ACCESS_TOKEN = '여qW8jaVO+EKprbz/y6bPwMAcWhGLCgTS822GZGtJ3vjZsmEvH/+tPRP0BWTWktTDnuWjyfjmltnt86SdxSiZIsXdNwPVwjYRVLOz+UqWVoPBzZYMSeCpwErR7Urfk+szctzz01Tw6lxpeUOU88LvH1wdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'e042abfbb258184b5f014609d19dc52b'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)

# --- 야마노테선 도착 시간 가져오기 ---
def get_next_yamanote():
    url = "https://transit.yahoo.co.jp/station/top/28561/"  # 타카다노바바역
    res = requests.get(url)
    soup = BeautifulSoup(res.content, "html.parser")

    results = []
    for table in soup.select("table.timeTable tr"):
        if '山手線' in table.text and '新宿' in table.text:
            cells = table.find_all("td")
            if len(cells) >= 2:
                train_time = cells[0].get_text(strip=True)
                dest = cells[1].get_text(strip=True)
                results.append(f"🕒 {train_time} - {dest}")
    return results[:3] if results else ["현재 도착 정보가 없습니다."]

# --- Webhook 엔드포인트 ---
@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"[ERROR] {e}")
    return "OK"

# --- 메시지 응답 처리 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    if "야마노테" in text or "타카다노바바" in text or "열차" in text:
        trains = get_next_yamanote()
        reply = "\n".join(trains)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="“야마노테” 또는 “열차”라고 말해보세요!")
        )

# --- 로컬 테스트용 ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)