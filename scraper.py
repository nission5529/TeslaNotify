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
            # 価格の抽出
            price = "価格不明"
            for text in texts:
                if "¥" in text.text:
                    price = text.text.strip()
                    break

            status = texts[0].text.strip()
            name = texts[1].text.strip()
            grade = texts[2].text.strip() if "¥" not in texts[2].text else ""
            
            # 走行距離の抽出（後ろから探す）
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
    """金額文字列を整数に変換"""
    try:
        clean_str = re.sub(r'[^\d]', '', price_str)
        return int(clean_str)
    except ValueError:
        return 0

def send_line_message(message):
    """LINEにプッシュ通知を送る (複数メッセージの分割送信に対応)"""
    if not message:
        return

    api_url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }

    # 1通のメッセージは最大5000文字。余裕を持って2000文字で分割してリスト化
    chunks = [message[i:i+2000] for i in range(0, len(message), 2000)]
    
    # LINEの1回のリクエストでは最大5つの吹き出し（メッセージオブジェクト）が送れる
    messages_payload = [{"type": "text", "text": chunk} for chunk in chunks[:5]]
    
    payload = {
        "to": LINE_USER_ID,
        "messages": messages_payload
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
        current_cars = {}
        return

    new_cars = []
    discounted_cars = []

    # 新着＆値下げチェック
    for car_id, info in current_cars.items():
        if car_id not in seen_cars:
            new_cars.append(info)
        else:
            current_price_int = parse_price(info['price'])
            saved_price_int = parse_price(seen_cars[car_id]['price'])

            if 0 < current_price_int < saved_price_int:
                info['old_price'] = seen_cars[car_id]['price']
                discounted_cars.append(info)
                
        # 状態を最新に更新
        seen_cars[car_id] = info

    # ----- LINEに送るメッセージの作成 -----
    # 更新があったかどうかでヘッダーを変える
    if new_cars or discounted_cars:
        report = "【Lightning 更新がありました！】\n\n"
    else:
        report = "【Lightning 更新はありません】\n\n"

    # 新着があれば追加
    if new_cars:
        report += "✨ 新着車両:\n"
        for c in new_cars:
            report += f"・{c['name']} ({c['price']})\n"
        report += "\n"

    # 値下げがあれば追加
    if discounted_cars:
        report += "🚨 値下げ車両:\n"
        for c in discounted_cars:
            report += f"・{c['name']} ({c['old_price']} → {c['price']})\n"
        report += "\n"

    # ★重要：更新があろうとなかろうと、全在庫を必ずメッセージに追加する
    report += "------------------\n🚘 現在の在庫一覧:\n"
    for car_id, c in current_cars.items():
        report += f"・{c['status']} | {c['name']}\n  {c['price']} / {c['mileage']}\n  {c['url']}\n\n"

    # LINEへ送信
    send_line_message(report)

    # 最後に必ずJSONを上書き保存
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_cars, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
