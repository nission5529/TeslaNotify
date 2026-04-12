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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)
        
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)
        
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, 'html.parser')
    car_links = soup.find_all('a', href=re.compile(r'/car/detail'))

    for link in car_links:
        path = link.get('href')
        if path in cars:
            continue
            
        texts = link.select('.text.sd.appear')
        if len(texts) >= 5:
            # 「値下げ」バッジ等の影響で配列がズレる対策（価格は必ず ¥ が含まれると仮定）
            price = "価格不明"
            for text in texts:
                if "¥" in text.text:
                    price = text.text.strip()
                    break

            status = texts[0].text.strip()
            name = texts[1].text.strip()
            
            # グレード情報の取得（texts[2]が¥を含まないならグレードとみなす）
            grade = texts[2].text.strip() if "¥" not in texts[2].text else ""
            
            # 走行距離の取得（後ろから探す）
            mileage = texts[-1].text.strip()
            if "km" not in mileage and len(texts) >= 2:
                 mileage = texts[-2].text.strip()

            full_url = f"https://lightning.boxiv.co.jp{path}"
            
            cars[path] = {
                "name": f"{name} {grade}".strip(),
                "price": price,
                "mileage": mileage,
                "status": status,
                "url": full_url
            }
    
    print(f"--- 取得完了: {len(cars)}台の車両を検出しました ---")
    return cars

def parse_price(price_str):
    """「¥2,500,000」などの文字列から数字だけを抽出して整数にする"""
    try:
        # 数字以外の文字（¥やカンマなど）を全て削除
        clean_str = re.sub(r'[^\d]', '', price_str)
        return int(clean_str)
    except ValueError:
        return 0

def send_line_message(message):
    """LINEにプッシュ通知を送る"""
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
    discounted_cars = []

    # 新着＆値下げチェック
    for car_id, info in current_cars.items():
        if car_id not in seen_cars:
            # 完全に新しい車の場合
            new_cars.append(info)
            seen_cars[car_id] = info
        else:
            # 既に知っている車の場合、価格を比較する
            current_price_int = parse_price(info['price'])
            saved_price_int = parse_price(seen_cars[car_id]['price'])

            # 前回保存した価格より安くなっていたら「値下げ」と判定
            if 0 < current_price_int < saved_price_int:
                drop_amount = saved_price_int - current_price_int
                info['drop_amount'] = drop_amount
                info['old_price'] = seen_cars[car_id]['price']
                discounted_cars.append(info)
                
            # 価格やステータス（商談中など）の最新状態を上書き保存
            seen_cars[car_id] = info

    # 新着通知
    if new_cars:
        for car in new_cars:
            msg = f"【✨新着テスラ】\n{car['name']}\n価格: {car['price']}\n距離: {car['mileage']}\n状態: {car['status']}\n{car['url']}"
            send_line_message(msg)
            print(f"新着通知送信: {car['name']}")

    # 値下げ通知
    if discounted_cars:
        for car in discounted_cars:
            # 値下がり額を「万円」単位に変換
            drop_man = car['drop_amount'] // 10000 
            msg = f"【🚨値下げ速報！ {drop_man}万円DOWN】\n{car['name']}\n旧価格: {car['old_price']}\n新価格: {car['price']} 🉐\n距離: {car['mileage']}\n{car['url']}"
            send_line_message(msg)
            print(f"値下げ通知送信: {car['name']} ({car['old_price']} -> {car['price']})")

    if not new_cars and not discounted_cars:
        print("新着・値下げはありませんでした。")

    # 状態を保存
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_cars, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
