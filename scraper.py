import os
import json
import re
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# 設定
URL = "https://lightning.boxiv.co.jp/car/buy/tesla"
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
STATE_FILE = "seen_cars.json"

def get_current_cars():
    """本物のブラウザを裏で起動し、JS描画後のページから車両を取得する"""
    cars = {}
    print("ブラウザを起動してページを取得中（数秒かかります）...")

    # PlaywrightでChromeを起動
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # ページを開き、通信が落ち着く（JSが実行されきる）まで待機
        page.goto(URL, wait_until="networkidle", timeout=60000)
        
        # STUDIO特有のフワッと表示や遅延読み込み対策として、少しスクロールして待つ
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000) # 3秒待機
        
        html = page.content()
        browser.close()

    # ここから先は前回と同じBeautifulSoupでの解析
    soup = BeautifulSoup(html, 'html.parser')
    car_links = soup.find_all('a', href=re.compile(r'/car/detail'))

    for link in car_links:
        path = link.get('href')
        if path in cars:
            continue
            
        texts = link.select('.text.sd.appear')
        if len(texts) >= 5:
            status = texts[0].text.strip()
            name = texts[1].text.strip()
            grade = texts[2].text.strip()
            price = texts[3].text.strip()
            mileage = texts[4].text.strip()
            full_url = f"https://lightning.boxiv.co.jp{path}"
            
            cars[path] = {
                "name": f"{name} {grade}",
                "price": price,
                "mileage": mileage,
                "status": status,
                "url": full_url
            }
    
    print(f"--- 取得完了: {len(cars)}台の車両を検出しました ---")
    return cars

def send_line_message(message):
    """LINEにプッシュ通知を送る"""
    # ★動作確認が完了するまでは、LINE通知を止めておくため以下の return を活かします
    # ★ログに車両が出力されるのを確認したら、下の return を消してください
    # return 

    api_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    try:
        response = requests.post(api_url, headers=headers, json={"to": LINE_USER_ID, "messages": [{"type": "text", "text": message}]})
        response.raise_for_status()
    except Exception as e:
        print(f"LINE通知エラー: {e}")

def main():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            seen_cars = json.load(f)
    else:
        seen_cars = {}

    try:
        current_cars = get_current_cars()
    except Exception as e:
        print(f"スクレイピングエラー: {e}")
        current_cars = {}

    new_cars = []

    for car_id, info in current_cars.items():
        if car_id not in seen_cars:
            new_cars.append(info)
            seen_cars[car_id] = info

    if new_cars:
        for car in new_cars:
            msg = f"【Lightning 新着】\n{car['name']}\n価格: {car['price']}\n距離: {car['mileage']}\n状態: {car['status']}\n{car['url']}"
            send_line_message(msg)
            print(f"新着検知: {car['name']} - {car['price']}")
    else:
        print("新着はありませんでした。")

    # ★修正ポイント：新着が0件でも、エラーが起きても、絶対に最後にファイルを保存してGitエラーを防ぐ
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_cars, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
