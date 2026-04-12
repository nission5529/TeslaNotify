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
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    res = requests.get(URL, headers=headers)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, 'html.parser')

    cars = {}
    
    # 判明したSTUDIO特有のIDで車両ブロックを狙い撃ち
    items = soup.select('div[data-s-0fbeb8fe-b209-4f19-a0ea-7757ad4e5073]') 
    
    # ★GitHubのログで確認するためのPrint文
    print(f"--- 取得テスト: 車両ブロックを {len(items)} 件見つけました ---")

    for item in items:
        texts = item.select('.text.sd.appear')
        
        if len(texts) >= 5:
            status = texts[0].text.strip()  # 例: 出品中
            name = texts[1].text.strip()    # 例: TESLA Model3
            grade = texts[2].text.strip()   # 例: RWD 2022
            price = texts[3].text.strip()   # 例: ¥2,500,000
            mileage = texts[4].text.strip() # 例: 35,867km
            
            # 車両を一意に識別するためのID（車種＋グレード＋価格＋距離ならまず被らない）
            car_id = f"{name}_{grade}_{price}_{mileage}"
            
            cars[car_id] = {
                "name": f"{name} ({grade})",
                "price": price,
                "mileage": mileage,
                "status": status,
                "url": URL
            }
            # ★GitHubのログで確認するためのPrint文
            print(f"データ取得成功: {name} | {grade} | {price} | {mileage}")
            
    return cars

def send_line_message(message):
    """LINEにプッシュ通知を送る"""
    # ★テスト段階でLINEが鳴りやまなくなるのを防ぐため、一旦通知をオフ（return）にしています。
    # データが取れることが確認できたら、下の `return` を消してください。
    return 

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
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            seen_cars = json.load(f)
    else:
        seen_cars = {}

    current_cars = get_current_cars()
    new_cars = []

    for car_id, info in current_cars.items():
        if car_id not in seen_cars:
            new_cars.append(info)
            seen_cars[car_id] = info

    if new_cars:
        for car in new_cars:
            msg = f"【新着テスラ】\n{car['status']}: {car['name']}\n価格: {car['price']}\n距離: {car['mileage']}\n{car['url']}"
            send_line_message(msg)
        print(f"\n{len(new_cars)}件の新しい車両を処理しました。")
    else:
        print("\n新着車両はありませんでした。")

    # 新着の有無にかかわらず、最後に必ず状態を保存（エラー回避）
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_cars, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
