import time
import json
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# --- 설정 정보 ---
GAS_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbxE2AsR5cigM-Ua_YzITB32nwQj6Fg1RyEROe_oc-v_gyJ9f4aMZR2qF9jACpNM_jMc0A/exec"  # 본인의 구글 웹앱 URL 주소를 넣으세요.

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
    
    win_count = 0
    lose_count = 0
    company_win_count = 0
    company_lose_count = 0
    match_details = []
    
    try:
        driver.get(url)
        
        # 명시적 대기 (WebDriverWait)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.list-board"))
            )
        except Exception:
            # ◀ [수정] 0으로 초기화하지 않고, 실패했다는 의미로 None을 반환합니다.
            print(f"   [경고] 10초간 대기했으나 'div.list-board' 요소를 로딩하지 못했습니다. ({url}) -> 기존 데이터 유지")
            return None
            
        time.sleep(1)
        
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
            print(f"   [주의] 'div.list-board'를 찾을 수 없습니다. -> 기존 데이터 유지")
            return None
            
        tbody = board_div.find('tbody')
        if not tbody:
            print(f"   [주의] 'tbody'를 찾을 수 없습니다. -> 기존 데이터 유지")
            return None
            
        tr_list = tbody.find_all('tr', recursive=False)
        
        for tr in tr_list:
            tds = tr.find_all('td', recursive=False)
            if len(tds) < 7:
                continue
                
            match_name = tds[6].get_text(strip=True)
            exclude_keywords = [
                "CK", "ck", "평가전", " PL", "이벤트전", "친선전", 
                "연습전", "테스트", "내전", "스크림", "위너스리그", "루저스리그","티어 대전", "프로리그", "중간고사", "vs 오똔대", "vs FA", "현 JSA vs 전 JSA", "모의고사", "티어 멸망전"
            ]
            match_name_upper = match_name.upper()
            if any(keyword.upper() in match_name_upper for keyword in exclude_keywords):
                continue
                
            td1 = tds[0]
            style = td1.get('style', '')
            is_win, is_lose = False, False
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
            my_team = tds[5].get_text(strip=True)
            
            if current_company.replace(" ", "") == my_team.replace(" ", ""):
                if is_win:
                    company_win_count += 1
                elif is_lose:
                    company_lose_count += 1
            
            match_details.append({
                "date": date_text, "result": result, "opponent": opponent, "team": my_team, "matchName": match_name
            })
            
        return win_count, lose_count, company_win_count, company_lose_count, match_details

    except Exception as e:
        print(f"크롤링 에러 ({url}): {e} -> 기존 데이터 유지")
        return None # ◀ [수정] 에러가 터져도 None을 반환하여 시트 오염을 막습니다.
    finally:
        driver.quit()

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
        name = target.get('streamerName', '')
        
        print(f"[{idx+1}/{total_len}] {name} {s_id} (현재소속: {current_company}) 크롤링...")
        
        crawl_result = crawl_univ_match(url, current_company)
        
        # -------------------------------------------------------------
        # [핵심 변경] 크롤링 결과가 None(실패)이면 시트에 반영하지 않고 스킵하도록 처리
        # -------------------------------------------------------------
        if crawl_result is None:
            payload.append({
                "sId": s_id,
				"currentCompany": current_company,
                "status": "skip"  # GAS에게 이 학생은 건너뛰라고 신호를 보냅니다.
            })
            continue
            
        win, lose, c_win, c_lose, details = crawl_result
        print(f"   -> 전체: {win}승 {lose}패 | 소속팀({current_company}) 매칭: {c_win}승 {c_lose}패")
        
        payload.append({
            "sId": s_id,
            "status": "success", # 정상 성공 신호
            "currentCompany": current_company,
            "winCount": win,
            "loseCount": lose,
            "companyWinCount": c_win,
            "companyLoseCount": c_lose,
            "matchDetails": details
        })
        
        if idx < total_len - 1:
            time.sleep(1)
        
    if payload:
        print("2. 구글 시트로 집계 데이터 일괄 전송 중...")
        send_to_gas(payload)
        print("모든 수치 반영 완료!")

if __name__ == "__main__":
    main()
