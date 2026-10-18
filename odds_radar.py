import os
import time
import json
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import cloudscraper
import feedparser

# ==========================================
# ⚙️ 설정값 (본인의 봇 토큰 입력)
# ==========================================
BOT_TOKEN = "8760127442:AAEx1WdWKSVxjU1D6kctQaxnm48t_DqwFMs"
CHANNEL_ID = "@oddsradar_kr"
SENT_HISTORY_FILE = "sent_history.json"
MIN_DROP_RATE = 15.0

# ==========================================
# 📡 텔레그램 발송 및 번역 엔진
# ==========================================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHANNEL_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    try:
        res = requests.post(url, data=payload, timeout=10)
        return res.status_code == 200
    except:
        return False

def clean_text(raw_html):
    if not raw_html:
        return ""
    text = BeautifulSoup(raw_html, "html.parser").get_text()
    return re.sub(r'\s+', ' ', text).strip()

def translate_ko(text):
    cleaned = clean_text(text)
    if not cleaned:
        return ""
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": cleaned[:400]}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, params=params, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return "".join([item[0] for item in data[0] if item[0]])
        return cleaned
    except:
        return cleaned

def is_already_sent(unique_key):
    if not os.path.exists(SENT_HISTORY_FILE):
        return False
    try:
        with open(SENT_HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
            return unique_key in history
    except:
        return False

def save_sent_history(unique_key):
    history = []
    if os.path.exists(SENT_HISTORY_FILE):
        try:
            with open(SENT_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except:
            history = []
    history.append(unique_key)
    history = history[-500:]
    with open(SENT_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False)

# ==========================================
# 📊 수집 엔진 1: 해외 배당 급락 감지
# ==========================================
def check_dropping_odds():
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    url = "https://www.betshoot.com/dropping-odds/"
    try:
        response = scraper.get(url, timeout=15)
        if response.status_code != 200:
            return
        soup = BeautifulSoup(response.text, 'html.parser')
        for row in soup.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) < 5:
                continue
            try:
                match_text = cols[1].text.strip()
                if " vs " in match_text:
                    home, away = match_text.split(" vs ", 1)
                elif " - " in match_text:
                    home, away = match_text.split(" - ", 1)
                else:
                    continue
                
                odds_info = cols[3].text.strip()
                drop_val = float(cols[4].text.strip().replace('%', '').replace('-', '').strip())
                if drop_val < MIN_DROP_RATE:
                    continue

                event_key = f"ODDS_{home}_{away}_{drop_val}"
                if not is_already_sent(event_key):
                    kor_home = translate_ko(home)
                    kor_away = translate_ko(away)
                    msg = f"""📉 <b>[실시간 해외 배당 급락 감지]</b>

⚽ 매치: <b>{kor_home} vs {kor_away}</b>
📊 <b>배당 변동: {odds_info} (▼ {drop_val}% 급락)</b>

💡 <b>데이터 분석 포인트</b>
- 글로벌 메이저 북메이커 실시간 자금 쏠림 포착
- 상대 전력 누수 또는 이상 베팅 흐름 감지

🔔 <i>오즈 레이더 봇이 24시간 실시간 감지 중입니다.</i>"""
                    if send_telegram(msg):
                        save_sent_history(event_key)
                        time.sleep(2)
            except:
                continue
    except:
        pass

# ==========================================
# ⚽ 수집 엔진 2: 축구/농구 라인업 & 결장자 속보
# ==========================================
def check_sports_lineups_and_news():
    feed_urls = [
        "https://www.espn.com/espn/rss/soccer/news",
        "https://www.espn.com/espn/rss/nba/news"
    ]
    for feed_url in feed_urls:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                title = entry.title
                summary = entry.summary if hasattr(entry, 'summary') else entry.title
                keywords = ["lineup", "starting", "injury", "ruled out", "roster", "xi", "squad", "miss", "waiv", "sign", "pick"]
                if any(kw in title.lower() or kw in summary.lower() for kw in keywords):
                    event_key = f"LINEUP_NEWS_{entry.id if hasattr(entry, 'id') else title}"
                    if not is_already_sent(event_key):
                        kor_title = translate_ko(title)
                        time.sleep(1)
                        kor_summary = translate_ko(summary)
                        sport = "⚽ 해외축구" if "soccer" in feed_url else "🏀 NBA 농구"
                        msg = f"""🚨 <b>[{sport} 라인업 & 긴급 속보]</b>

📌 <b>헤드라인:</b> <b>{kor_title}</b>

📋 <b>핵심 브리핑:</b>
{kor_summary}

🔔 <i>경기 전 공식 라인업/결장 1초 속보 (오즈 레이더)</i>"""
                        if send_telegram(msg):
                            save_sent_history(event_key)
                            time.sleep(2)
        except:
            pass

# ==========================================
# 🎮 수집 엔진 3: LCK(롤) 로스터 & 이스포츠 속보
# ==========================================
def check_lck_and_esports():
    url = "https://www.dexerto.com/league-of-legends/feed/"
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            title = entry.title
            summary = entry.summary if hasattr(entry, 'summary') else entry.title
            keywords = ["lck", "t1", "faker", "gen.g", "roster", "worlds", "starting", "bench", "sign"]
            if any(kw in title.lower() for kw in keywords):
                event_key = f"LCK_{entry.id if hasattr(entry, 'id') else title}"
                if not is_already_sent(event_key):
                    kor_title = translate_ko(title)
                    time.sleep(1)
                    kor_summary = translate_ko(summary)
                    msg = f"""🎮 <b>[LCK & 롤 공식 속보 / 로스터]</b>

🏆 <b>{kor_title}</b>

💡 <b>핵심 내용 요약:</b>
{kor_summary}

🔔 <i>LCK 경기 전 로스터 및 속보 알림 (오즈 레이더)</i>"""
                    if send_telegram(msg):
                        save_sent_history(event_key)
                        time.sleep(2)
    except:
        pass

# ==========================================
# 🚀 1회 실행 후 종료 (깃허브 클라우드가 15분마다 재실행)
# ==========================================
if __name__ == "__main__":
    check_dropping_odds()
    check_sports_lineups_and_news()
    check_lck_and_esports()
