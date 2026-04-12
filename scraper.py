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
    print("ブラウザを起動してページを取得中...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # 変更点1: "networkidle" をやめ、HTMLの枠組みが読み込まれた時点("domcontentloaded")で次に進む
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        
        try:
            # 変更点2: 車の詳細ページへのリンク（aタグ）が画面に出現するまで最大30秒待つ（これが一番確実）
            page.wait_for_selector('a[href*="/car/detail"]', timeout=30000)
        except Exception as e:
            print("車両リストの読み込みに時間がかかっているか、要素が見つかりません。")
        
        # 念のため一番下までスクロールして少し待つ
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
            price = "価格不明"
            for text in texts:
                if "¥" in text.text:
                    price = text.text.strip()
                    break

            status = texts[0].text.strip()
            name = texts[1].text.strip()
            grade = texts[2].text.strip() if "¥" not in texts[2].text else ""
            
            mileage = "距離不明"
            for text in reversed(texts):
                if "km" in text.text:
                    mileage = text.text.strip()
                    break

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
    try:
        clean_str = re.sub(r'[^\d]', '', price_str)
        return int(clean_str)
    except ValueError:
        return 0

def send_line_message(message):
    """LINEにプッシュ通知を送る"""
    if not message:
        return

    api_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }

    # 最新3台＋ヘッダーなら文字数制限(5000字)に収まるため分割なしで送信
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": message}]
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        print("LINEへの通知が成功しました。")
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
        return

    new_cars = []
    discounted_cars = []

    # 差分チェックは「全車両」に対して行う
    for car_id, info in current_cars.items():
        if car_id not in seen_cars:
            new_cars.append(info)
        else:
            current_price_int = parse_price(info['price'])
            saved_price_int = parse_price(seen_cars[car_id]['price'])

            if 0 < current_price_int < saved_price_int:
                info['old_price'] = seen_cars[car_id]['price']
                discounted_cars.append(info)
                
        # 内部状態（JSON）は常に全車両の最新状態に更新
        seen_cars[car_id] = info

    # ----- メッセージ作成 -----
    if new_cars or discounted_cars:
        report = "【Lightning 更新がありました！】\n\n"
    else:
        report = "【Lightning 更新はありません】\n\n"

    # 新着・値下げがあればその詳細を優先して表示
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

    # ★在庫一覧は「最新の3台」だけを表示するようにスライス
    report += "------------------\n🚘 在庫一覧(最新3台を抜粋):\n"
    # dictionaryの先頭3つを取得
    latest_3_keys = list(current_cars.keys())[:3]
    for key in latest_3_keys:
        c = current_cars[key]
        report += f"・{c['status']} | {c['name']}\n  {c['price']} / {c['mileage']}\n  {c['url']}\n\n"

    if len(current_cars) > 3:
        report += f"※他 {len(current_cars) - 3} 台の在庫があります。"

    # LINE送信
    send_line_message(report)

    # 状態保存
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_cars, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
