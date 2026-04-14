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
    """JS描画後のページから車両を取得。aタグが出現するまで待機する。"""
    cars = {}
    print("ブラウザを起動してページを取得中...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        
        try:
            # 車両リンクが表示されるまで最大30秒待機
            page.wait_for_selector('a[href*="/car/detail"]', timeout=30000)
        except:
            print("車両リストの読み込みを待機しましたが、見つかりませんでした。")
        
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)
        
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, 'html.parser')
    car_links = soup.find_all('a', href=re.compile(r'/car/detail'))

    for link in car_links:
        path = link.get('href')
        if path in cars: continue
            
        texts = link.select('.text.sd.appear')
        if len(texts) >= 5:
            price = "価格不明"
            for text in texts:
                if "¥" in text.text:
                    price = text.text.strip()
                    break

            status = texts[0].text.strip()
            name = texts[1].text.strip()
            grade = texts[2].text.strip() if "¥" not in texts[2].text else ""
            
            mileage = "不明"
            for text in reversed(texts):
                if "km" in text.text:
                    mileage = text.text.strip()
                    break

            cars[path] = {
                "name": f"{name} {grade}".strip(),
                "price": price,
                "mileage": mileage,
                "status": status,
                "url": f"https://lightning.boxiv.co.jp{path}"
            }
    
    print(f"--- 取得完了: {len(cars)}台の車両を検出 ---")
    return cars

def parse_price(price_str):
    try:
        clean_str = re.sub(r'[^\d]', '', price_str)
        return int(clean_str)
    except:
        return 0

def send_line_message(message):
    """LINEにプッシュ通知を送信"""
    if not message: return
    api_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": message}]}
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print("LINE通知を送信しました。")
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
        print(f"エラー: {e}")
        return

    new_cars = []
    discounted_cars = []

    for car_id, info in current_cars.items():
        if car_id not in seen_cars:
            new_cars.append(info)
        else:
            current_p = parse_price(info['price'])
            saved_p = parse_price(seen_cars[car_id]['price'])
            if 0 < current_p < saved_p:
                info['old_price'] = seen_cars[car_id]['price']
                discounted_cars.append(info)
        seen_cars[car_id] = info

    # ★変更ポイント: 新着または値下げがあった場合のみレポートを作成・送信
    if new_cars or discounted_cars:
        report = "【Lightning 更新がありました！】\n\n"
        if new_cars:
            report += "✨ 新着入荷:\n"
            for c in new_cars:
                report += f"・{c['name']} ({c['price']})\n"
            report += "\n"

        if discounted_cars:
            report += "🚨 値下げ:\n"
            for c in discounted_cars:
                report += f"・{c['name']} ({c['old_price']} → {c['price']})\n"
            report += "\n"

        report += "------------------\n🚘 在庫一覧(最新3台):\n"
        latest_3_keys = list(current_cars.keys())[:3]
        for key in latest_3_keys:
            c = current_cars[key]
            report += f"・{c['status']} | {c['name']}\n  {c['price']} / {c['mileage']}\n  {c['url']}\n\n"
        
        send_line_message(report)
    else:
        print("変化がないため通知をスキップしました。")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_cars, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
