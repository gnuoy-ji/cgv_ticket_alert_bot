import time
import requests
import re
import os
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# ================= 설정 영역 =================
load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# 알림을 받고 싶은 특정 영화 제목 (없으면 빈 문자열 '' 로 입력)
TARGET_MOVIE = '프로젝트 헤일메리' 
TARGET_DATE = '20260404' # 예매창 달력 세팅용 날짜 (YYYYMMDD)

# 🌟 극장 리스트 (이름, 고유번호)
TARGET_THEATERS = [
    {"name": "용산아이파크몰", "site_no": "0013"},
    {"name": "영등포", "site_no": "0059"}
]
# =============================================

def send_discord_alert(message):
    """디스코드로 메시지를 전송합니다.""" 
    data = {"content": message}
    requests.post(DISCORD_WEBHOOK_URL, json=data)

def extract_schedules(text, movie_title):
    """모든 CGV 지점의 텍스트 레이아웃을 아우르는 궁극의 하이브리드 파서입니다."""
    if not movie_title:
        return "자세한 시간표는 링크를 통해 확인해주세요."
        
    try:
        chunk = text.split(movie_title)[1]
        lines = [line.strip() for line in chunk.split('\n') if line.strip()]
        
        schedules = []
        current_screen = "상영관 정보 없음"
        
        # 상영관 이름인지 판별하는 똑똑한 내부 함수
        def is_screen_name(line_text):
            # 극장 이름으로 쓰이는 대표 키워드들 (영등포 스페셜관 포함)
            keywords = ['관', '시네마', 'STARIUM', 'THX', 'BOX', 'GOLD', '씨네']
            if not any(kw in line_text for kw in keywords):
                return False
            if re.match(r'^\d{2}:\d{2}', line_text): # 시간표면 탈락
                return False
            if '석' in line_text or '매진' in line_text or '준비' in line_text: # 좌석 정보면 탈락
                return False
            return True

        for i, line in enumerate(lines):
            if i > 80: # 너무 깊게 탐색하지 않도록 방어선 구축
                break
                
            # 🌟 위에서 내려오면서 상영관 이름이 보이면 무조건 갱신하여 기억!
            if is_screen_name(line):
                current_screen = line

            # 시간표 데이터를 찾은 경우
            if re.match(r'^\d{2}:\d{2}', line):
                time_info = line
                screen_info = current_screen # 기본값은 위에서 기억해둔 이름
                
                # 🌟 시간표 바로 밑 1~3줄 이내에 상영관 이름이 또 있는지 확인
                for j in range(1, 4):
                    if i + j < len(lines):
                        next_line = lines[i+j]
                        if re.match(r'^\d{2}:\d{2}', next_line): # 다음 시간표가 나오면 탐색 중단
                            break
                        if is_screen_name(next_line):
                            screen_info = next_line # 아래에서 찾은 이름으로 덮어쓰기!
                            break
                            
                schedules.append(f"► {screen_info} ⏰ {time_info}")
        
        # 중복 제거 (순서 유지)
        unique_schedules = []
        for s in schedules:
            if s not in unique_schedules:
                unique_schedules.append(s)
        
        if unique_schedules:
            return "\n".join(unique_schedules)
        else:
            return "시간표 세부 정보 추출 실패"
            
    except Exception as e:
        return f"시간표 정보 파싱 에러: {e}"

def check_cgv_schedule(theater):
    """특정 극장의 상영시간표가 열렸는지 확인합니다."""
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080") 
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36")
    
    prefs = {
        'profile.default_content_setting_values.geolocation': 2,
        'profile.default_content_setting_values.notifications': 2
    }
    chrome_options.add_experimental_option('prefs', prefs)
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        book_url = f"https://cgv.co.kr/cnm/movieBook/cinema?siteNo={theater['site_no']}&siteNm={theater['name']}&scnYmd={TARGET_DATE}"
        driver.get(book_url)
        time.sleep(5) 
        
        body_text = driver.find_element(By.TAG_NAME, 'body').text
        
        empty_keywords = ["스케줄이 없습니다", "조회가능한 상영시간", "선택된 상영관이 없습니다"]
        if any(keyword in body_text for keyword in empty_keywords):
            return False, ""
            
        if TARGET_MOVIE != '':
            if TARGET_MOVIE in body_text and ":" in body_text:
                # 🌟 영화가 열렸다면, 위에서 만든 추출 함수를 실행하여 결과물(디테일)도 같이 가져옵니다!
                details = extract_schedules(body_text, TARGET_MOVIE)
                return True, details
        else:
            if ":" in body_text:
                return True, "스케줄 상세 확인 불가 (전체 감시 모드)"
                
        return False, ""
            
    except Exception as e:
        print(f"[{theater['name']}] 확인 중 오류 발생: {e}")
        return False, ""
    finally:
        driver.quit()

# ----------------- 봇 무한 루프 -----------------
print(f"\n🚀 CGV 상영시간표 다중 감시 봇을 시작합니다! (대상: 용산, 영등포)")

# 무한 루프 시작
while True:
    for theater in TARGET_THEATERS:
        current_time = time.strftime('%H:%M:%S')
        print(f"[{current_time}] '{theater['name']}' 스케줄 확인 중...")
        
        # 🌟 is_opened 상태와 추출된 시간표 세부정보(schedule_details)를 함께 받습니다.
        is_opened, schedule_details = check_cgv_schedule(theater)

        if is_opened:
            print(f"🎉 [{theater['name']}] 조건 만족! 디스코드로 알림을 전송합니다.")
            
            # 열린 극장에 맞춤화된 예매 전용 직링크 자동 생성!
            direct_book_url = f"https://cgv.co.kr/cnm/movieBook/cinema?siteNo={theater['site_no']}&siteNm={theater['name']}&scnYmd={TARGET_DATE}"
            
            # 🌟 디스코드 알림 메시지에 추출한 상영관/시간표 목록을 덧붙입니다!
            alert_message = (
                f"🚨 **CGV {theater['name']}** [{TARGET_MOVIE}] 예매 오픈! 🚨\n\n"
                f"🎬 **[오픈된 상영관 및 시간]**\n"
                f"{schedule_details}\n\n"
                f"🔗 **바로가기**: {direct_book_url}"
            )
            
            send_discord_alert(alert_message)
            
            # 알림을 보낸 극장은 감시 리스트에서 제외하여 중복 알람을 방지합니다.
            TARGET_THEATERS.remove(theater)
            
            # 남은 극장이 없다면 봇을 완전히 종료합니다.
            if not TARGET_THEATERS:
                print("모든 극장의 알림 전송이 완료되어 봇을 종료합니다.")
                exit()
            
    # 한 바퀴(3개 극장)를 다 돌고 나면 1분 쉬었다가 다시 순찰합니다.
    time.sleep(60)