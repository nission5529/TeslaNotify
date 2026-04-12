import os
import json
import requests
from bs4 import BeautifulSoup
import re

# 設定
URL = "https://lightning.boxiv.co.jp/car/buy/tesla"
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
STATE_FILE = "seen_cars.json"

def get_current_cars():
    """サイトから現在の掲載車両を詳細URLをキーにして取得する"""
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    res = requests.get(URL, headers=headers)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, 'html.parser')

    cars = {}
    
    # 1. 車両詳細ページへのリンク（/car/detail/数字）を持つaタグをすべて探す
    # サイトにより /car/detail/ だったり /car/details/ だったりするので両方対応
    car_links = soup.find_all('a', href=re.compile(r'/car/detail'))

    for link in car_links:
        path = link.get('href')
        # 重複排除のため、すでに取得したパスならスキップ
        if path in cars:
            continue
            
        # 2. そのaタグの中にあるテキスト要素（pタグ）をすべて取得
        texts = link.select('.text.sd.appear')
        
        # 車両情報の塊であれば、通常5つ以上のテキスト要素が含まれる
        if len(texts) >= 5:
            status = texts[0].text.strip()
            name = texts[1].text.strip()
            grade = texts[2].text.strip()
            price = texts[3].text.strip()
            mileage = texts[4].text.strip()
            
            # フルURLを作成
            full_url = f"https://lightning.boxiv.co.jp{path}"
            
            # 詳細URLの末尾の数字などをIDとして使用
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
    # 動作確認が取れるまで、実際にLINEを送る場合は下のreturnをコメントアウトしてください
    # return 

    api_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": message}]
    }
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"LINE送信エラー: {e}")

def main():
    # 過去のデータを読み込み
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

    # 新着があれば通知
    if new_cars:
        for car in new_cars:
            msg = f"【Lightning 新着入荷】\n{car['name']}\n価格: {car['price']}\n距離: {car['mileage']}\n状態: {car['status']}\n{car['url']}"
            send_line_message(msg)
            print(f"通知送信: {car['name']}")

        # 状態を保存
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(seen_cars, f, ensure_ascii=False, indent=2)
    else:
        print("新着はありませんでした。")

if __name__ == "__main__":
    main()
