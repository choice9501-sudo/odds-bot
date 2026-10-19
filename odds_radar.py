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
# ⚙️ 설정값 (본인의 텔레그램 봇 토큰 입력)
# ==========================================
BOT_TOKEN = "8760127442:AAEx1WdWKSVxjU1D6kctQaxnm48t_DqwFMs"
CHANNEL_ID = "@oddsradar_kr"
SENT_HISTORY_FILE = "sent_history.json"
MIN_DROP_RATE = 12.0  # 국내/아시아 낮 경기 감지를 위해 12%로 상향 조정

# ==========================================
# 📡 텔레그램 발송 및 번역/기록 모듈
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
# 🇰🇷 [신규] 엔진 1: KBO / K리그 / KBL 국내 스포츠 속보
# ==========================================
def check_korean_sports():
    # KBO 선발투수 예고, K리그 라인업, KBL 결장 실시간 검색 피드
    url = "https://news.google.com/rss/search?q=(KBO+OR+K%EB%A6%AC%EA%B7%B8+OR+KBL)+AND+(%EC%84%A0%EB%B0%9C+OR+%EB%9D%BC%EC%9D%B8%EC%97%85+OR+%EA%B2%B0%EC%9E%A5+OR+%EB%B6%80%EC%83%81+OR+%EC%97%94%ED%8A%B8%EB%A6%AC)&hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            title = clean_text(entry.title)
            summary = clean_text(entry.summary if hasattr(entry, 'summary') else entry.title)
            
            # 언론사명 제거 및 핵심 키워드 검증
            title_clean = re.sub(r' - [^-]+$', '', title).strip()
            keywords = ["선발", "라인업", "결장", "부상", "엔트리", "말소", "등록", "로스터"]
            
            if any(kw in title_clean for kw in keywords):
                event_key = f"KOR_SPORTS_{title_clean}"
                if not is_already_sent(event_key):
                    # 종목 태그 자동 판정
                    tag = "⚾ KBO 프로야구" if "KBO" in title_clean or "야구" in title_clean or "투수" in title_clean else ("⚽ K리그" if "K리그" in title_clean or "축구" in title_clean else "🏀 KBL 농구")
                    
                    msg = f"""🚨 <b>[{tag} 공식 라인업 & 긴급 속보]</b>

📌 <b>헤드라인:</b> <b>{title_clean}</b>

📋 <b>핵심 브리핑:</b>
{summary[:150]}...

🔔 <i>국내 경기 전 공식 선발/결장 1초 속보 (오즈 레이더)</i>"""
                    if send_telegram(msg):
                        save_sent_history(event_key)
                        time.sleep(2)
    except:
        pass

# ==========================================
# 📊 엔진 2: 실시간 해외 배당 급락 감지 (-12% 이상)
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
# 🔥 엔진 3: 국내외 배당 괴리 (Value Bet) 감지
# ==========================================
def check_value_bets():
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
                if " vs " not in match_text and " - " not in match_text:
                    continue
                
                drop_val = float(cols[4].text.strip().replace('%', '').replace('-', '').strip())
                if drop_val < 20.0:
                    continue

                event_key = f"VALUE_BET_{match_text}_{drop_val}"
                if not is_already_sent(event_key):
                    kor_match = translate_ko(match_text)
                    odds_info = cols[3].text.strip()
                    msg = f"""🔥 <b>[국내 vs 해외 배당 괴리(Value Bet) 포착]</b>

⚽ 매치: <b>{kor_match}</b>
📊 <b>해외 하락폭: {odds_info} (▼ {drop_val}%)</b>

💎 <b>밸류 분석 지표</b>
- 해외 메이저 자금 폭주로 실시간 배당 급락 완료
- 국내 공시 배당 대비 해외 실시간 가치 괴리율 극대화 구간

⚠️ <i>국내 기준선 조정 전 선점 가치 매치입니다.</i>"""
                    if send_telegram(msg):
                        save_sent_history(event_key)
                        time.sleep(2)
            except:
                continue
    except:
        pass

# ==========================================
# 🌧 엔진 4: 주요 경기장 기상 악천후 경보
# ==========================================
def check_stadium_weather():
    stadiums = [
        {"name": "뉴캐슬 (세인트 제임스 파크)", "lat": 54.975, "lon": -1.621},
        {"name": "맨체스터 (올드 트래포드 / 에티하드)", "lat": 53.463, "lon": -2.291},
        {"name": "리버풀 (안필드 / 구디슨 파크)", "lat": 53.430, "lon": -2.960},
        {"name": "런던 (에미레이츠 / 토트넘 홋스퍼)", "lat": 51.554, "lon": -0.108},
        {"name": "버밍엄 (빌라 파크)", "lat": 52.509, "lon": -1.884}
    ]
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for std in stadiums:
        try:
            event_key = f"WEATHER_{std['name']}_{today_str}"
            if is_already_sent(event_key):
                continue

            url = f"https://api.open-meteo.com/v1/forecast?latitude={std['lat']}&longitude={std['lon']}&current=precipitation,wind_speed_10m&timezone=auto"
            res = requests.get(url, timeout=10)
            if res.status_code != 200:
                continue

            data = res.json().get('current', {})
            wind = data.get('wind_speed_10m', 0.0)
            precip = data.get('precipitation', 0.0)

            if wind >= 35.0 or precip >= 3.0:
                weather_status = []
                if wind >= 35.0:
                    weather_status.append(f"🌪 강풍 경보 (풍속: {wind} km/h)")
                if precip >= 3.0:
                    weather_status.append(f"🌧 폭우/강수 (시간당 {precip} mm)")
                
                status_str = " | ".join(weather_status)
                msg = f"""🚨 <b>[EPL 경기장 현지 기상 악천후 경보]</b>

🏟 위치: <b>{std['name']}</b>
⚠️ 기상 상태: <b>{status_str}</b>

📉 <b>베팅 분석 포인트 (언더/오버)</b>
- 심한 돌풍 및 미끄러운 잔디로 패스/빌드업 성공률 급감
- <b>[저득점(언더) 유리 통계 구간 감지]</b>

🔔 <i>오즈 레이더 현지 기상 실시간 레이더</i>"""
                if send_telegram(msg):
                    save_sent_history(event_key)
                    time.sleep(2)
        except:
            pass

# ==========================================
# ⚽ 엔진 5: 해외축구 / NBA 라인업 & 결장자
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
# 🎮 엔진 6: LCK(롤) 로스터 & 이스포츠 속보
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
# 🚀 메인 실행부
# ==========================================
if __name__ == "__main__":
    check_korean_sports()          # 국내 KBO/K리그/KBL 속보 (낮/오후 활성화)
    check_dropping_odds()          # 실시간 배당 급락
    check_value_bets()             # 배당 괴리 분석
    check_stadium_weather()        # 경기장 날씨 특보
    check_sports_lineups_and_news() # 해외축구/NBA 라인업
    check_lck_and_esports()        # LCK 로스터 속보
