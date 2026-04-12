import os
import json
import requests
from bs4 import BeautifulSoup

# 設定
URL = "https://lightning.boxiv.co.jp/car/buy/tesla"
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
STATE_FILE = "seen_cars.json"

def get_current_cars():
    """サイトから現在の掲載車両を取得する"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(URL, headers=headers)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, 'html.parser')

    cars = {}
    
    # ★注意: 以下のセレクタは仮のものです。実際のサイトのHTMLに合わせて変更してください。
    # 例: 車両のブロックが <div class="car-item"> の場合
    items = soup.select('.car-item') 
    
    for item in items:
        # aタグのhrefからURLやIDを抽出
        link_tag = item.select_one('a')
        if not link_tag:
            continue
            
        car_url = link_tag['href']
        # URLの末尾（車両ID等）をユニークキーとして扱う
        car_id = car_url.rstrip('/').split('/')[-1] 
        
        # 車種名と価格を取得（クラス名は実際のDOMに合わせる）
        name_tag = item.select_one('.car-title')
        price_tag = item.select_one('.car-price')
        
        cars[car_id] = {
            "name": name_tag.text.strip() if name_tag else "車種不明",
            "price": price_tag.text.strip() if price_tag else "価格不明",
            "url": car_url if car_url.startswith('http') else f"https://lightning.boxiv.co.jp{car_url}"
        }
    return cars

def send_line_message(message):
    """LINEにプッシュ通知を送る"""
    api_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": message}]
    }
    response = requests.post(api_url, headers=headers, json=payload)
    response.raise_for_status()

def main():
    # 過去のデータ（通知済みリスト）を読み込む
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            seen_cars = json.load(f)
    else:
        seen_cars = {}

    current_cars = get_current_cars()
    new_cars = []

    # 新着チェック
    for car_id, info in current_cars.items():
        if car_id not in seen_cars:
            new_cars.append(info)
            seen_cars[car_id] = info

    # 新着があればLINE通知＆JSONを上書き保存
    if new_cars:
        for car in new_cars:
            msg = f"【新着テスラ入荷】\n{car['name']}\n価格: {car['price']}\n{car['url']}"
            send_line_message(msg)

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(seen_cars, f, ensure_ascii=False, indent=2)
        print(f"{len(new_cars)}件の新しい車両を通知し、状態を保存しました。")
    else:
        print("新着車両はありませんでした。")

if __name__ == "__main__":
    main()
