from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
from bs4 import BeautifulSoup

# --- LINE 인증 정보 (여기에 직접 입력) ---
LINE_CHANNEL_ACCESS_TOKEN = 'qW8jaVO+EKprbz/y6bPwMAcWhGLCgTS822GZGtJ3vjZsmEvH/+tPRP0BWTWktTDnuWjyfjmltnt86SdxSiZIsXdNwPVwjYRVLOz+UqWVoPBzZYMSeCpwErR7Urfk+szctzz01Tw6lxpeUOU88LvH1wdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'e042abfbb258184b5f014609d19dc52b'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)

def get_next_yamanote():
    url = "https://transit.yahoo.co.jp/station/top/28561/"  # 타카다노바바역
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.content, "html.parser")

    # 새로운 구조: "発車時刻" 섹션을 기준으로 파싱
    result = []
    for section in soup.select("div.timelist"):
        line_name = section.select_one("h3").text if section.select_one("h3") else ""
        if "山手線" not in line_name:
            continue

        for li in section.select("li"):
            time_tag = li.select_one("div.time")
            dest_tag = li.select_one("div.destination")
            if not time_tag or not dest_tag:
                continue
            time_text = time_tag.get_text(strip=True)
            dest_text = dest_tag.get_text(strip=True)

            if "新宿" in dest_text:
                result.append(f"🕒 {time_text} - {dest_text}")

    return result[:3] if result else ["도착 정보가 없습니다."]

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"[ERROR] {e}")

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    print(f"[RECEIVED] {text}")

    if "야마노테" in text or "타카다노바바" in text or "열차" in text:
        trains = get_next_yamanote()
        print(f"[REPLY] {trains}")

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
