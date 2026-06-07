import time
import json
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# --- 설정 정보 ---
GAS_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbxagBJ1FrUDpPsHm88Nfn2mbqw9XW13jqnkGGW-iz9p7gBcnHLP2hoez1zOmHCy355hHA/exec"  # 본인의 구글 웹앱 URL 주소를 넣으세요.

def get_target_list():
    """GAS로부터 아이디, 주소, 현재 소속 대학명을 받아옵니다."""
    response = requests.get(f"{GAS_WEBAPP_URL}?action=getUnivMatchList")
    if response.status_code == 200:
        return response.json()
    else:
        print("GAS 데이터를 가져오는데 실패했습니다.")
        return []

def crawl_univ_match(url, current_company):
    """주소로 접속하여 데이터를 긁어오고, 전체 성적 및 현재 소속팀 성적을 분리 집계합니다."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    # 전체 성적 카운트
    win_count = 0
    lose_count = 0
    
    # [신규 추가] 현재 소속팀과 일치하는 매치의 성적 카운트
    company_win_count = 0
    company_lose_count = 0
    
    match_details = []
    
    try:
        driver.get(url)
        time.sleep(2)
        
        # 동적 스크롤링 (끝까지 스크롤 다운)
        last_height = driver.execute_script("return document.body.scrollHeight")
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        board_div = soup.select_one("div.list-board")
        if not board_div:
            return 0, 0, 0, 0, []
            
        tbody = board_div.find('tbody')
        if not tbody:
            return 0, 0, 0, 0, []
            
        tr_list = tbody.find_all('tr', recursive=False)
        
        for tr in tr_list:
            tds = tr.find_all('td', recursive=False)
            if len(tds) < 7:
                continue
                
			# 7번째 td: 매치명 필터링
            match_name = tds[6].get_text(strip=True)
            
            # --- [수정] 제외할 단어 목록을 여기에 다 적으세요 (띄어쓰기 주의) ---
            exclude_keywords = [
                "CK", "ck", "평가전", " PL", "이벤트전", "친선전", 
                "연습전", "테스트", "내전", "스크림", "위너스리그", "티어 대전", "프로리그", "중간고사", "vs 오똔대", "vs FA", "현 JSA vs 전 JSA", "모의고사", "티어 멸망전"
            ]
            
            # 대소문자 무관하게 검사하기 위해 매치명을 대문자로 변환
            match_name_upper = match_name.upper()
            
            # 리스트에 있는 단어 중 하나라도 매치명에 포함되어 있다면 패스(continue)
            if any(keyword.upper() in match_name_upper for keyword in exclude_keywords):
                continue
                
            # 1번째 td: 승패(배경색) 및 날짜
            td1 = tds[0]
            style = td1.get('style', '')
            
            is_win = False
            is_lose = False
            result = "알수없음"
            
            if '#0CF' in style or '#0cf' in style:
                result = "승"
                is_win = True
                win_count += 1
            elif '#434348' in style:
                result = "패"
                is_lose = True
                lose_count += 1
                
            date_text = td1.find('a').get_text(strip=True) if td1.find('a') else td1.get_text(strip=True)
            opponent = tds[2].get_text(strip=True)
            
            # 6번째 td: 대전 당시 소속 대학 이름 (team)
            my_team = tds[5].get_text(strip=True)
            
            # [핵심 로직] 시트상의 현재 소속 대학명과 대전 당시 대학명이 동일한지 판정
            # 공백 제거 후 비교하여 매칭 정확도를 높입니다.
            if current_company.replace(" ", "") == my_team.replace(" ", ""):
                if is_win:
                    company_win_count += 1
                elif is_lose:
                    company_lose_count += 1
            
            match_details.append({
                "date": date_text,
                "result": result,
                "opponent": opponent,
                "team": my_team,
                "matchName": match_name
            })
            
    except Exception as e:
        print(f"크롤링 에러 ({url}): {e}")
    finally:
        driver.quit()
        
    return win_count, lose_count, company_win_count, company_lose_count, match_details

def send_to_gas(payload):
    headers = {"Content-Type": "application/json"}
    data = {
        "action": "updateUnivMatch",
        "payload": payload
    }
    response = requests.post(GAS_WEBAPP_URL, data=json.dumps(data), headers=headers)
    print(f"GAS 전송 결과: {response.text}")

def main():
    print("1. GAS 데이터 요청 중...")
    target_list = get_target_list()
    if not target_list:
        print("타겟 리스트가 없습니다.")
        return
        
    total_len = len(target_list)
    print(f"총 {total_len}명의 데이터를 가공합니다.")
    payload = []
    
    for idx, target in enumerate(target_list):
        s_id = target.get('sId')
        url = target.get('univUrl')
        current_company = target.get('currentCompany', '')
        name = target.get('streamerName', '')  # ◀ 공백 규격을 완전히 통일했습니다.
        
        print(f"[{idx+1}/{total_len}] {name} {s_id} (현재소속: {current_company}) 크롤링...")
        win, lose, c_win, c_lose, details = crawl_univ_match(url, current_company)
        print(f"   -> 전체: {win}승 {lose}패 | 소속팀({current_company}) 매칭: {c_win}승 {c_lose}패")
        
        payload.append({
            "sId": s_id,
			"currentCompany": current_company,
            "winCount": win,
            "loseCount": lose,
            "companyWinCount": c_win,
            "companyLoseCount": c_lose,
            "matchDetails": details
        })
        time.sleep(1)
        
    if payload:
        print("2. 구글 시트로 집계 데이터 일괄 전송 중...")
        send_to_gas(payload)
        print("모든 수치 반영 완료!")

if __name__ == "__main__":
    main()
