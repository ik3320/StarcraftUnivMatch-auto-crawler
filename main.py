import time
import json
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# --- 설정 정보 ---
GAS_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbyh42kxRzPkHYedYaHl_M98ECqti9pYuYfdeYNvP4VPr_wsb9-oieHPUr8uM9YLACrJLA/exec"  # 본인의 구글 웹앱 URL 주소를 넣으세요.

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
    
    # 디버깅을 위한 원인 추적용 카운터
    skipped_by_filter = 0
    unknown_color_count = 0
    
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
        
        # [로그 추가] div.list-board 영역을 찾지 못하는 경우 체크
        board_div = soup.select_one("div.list-board")
        if not board_div:
            print(f"   [주의] 'div.list-board' 요소를 찾을 수 없습니다. (웹페이지 구조 변경 가능성)")
            return 0, 0, 0, 0, []
            
        # [로그 추가] tbody 영역을 찾지 못하는 경우 체크
        tbody = board_div.find('tbody')
        if not tbody:
            print(f"   [주의] 'tbody' 요소를 찾을 수 없습니다. (데이터가 아예 없는 페이지일 수 있음)")
            return 0, 0, 0, 0, []
            
        tr_list = tbody.find_all('tr', recursive=False)
        
        # [로그 추가] 불러온 행(판수)이 총 몇 개인지 체크
        total_rows_found = len(tr_list)
        
        for tr in tr_list:
            tds = tr.find_all('td', recursive=False)
            if len(tds) < 7:
                continue
                
            # 7번째 td: 매치명 필터링
            match_name = tds[6].get_text(strip=True)
            
            exclude_keywords = [
                "CK", "ck", "평가전", " PL", "이벤트전", "친선전", 
                "연습전", "테스트", "내전", "스크림", "위너스리그", "루저스리그","티어 대전", "프로리그", "중간고사", "vs 오똔대", "vs FA", "현 JSA vs 전 JSA", "모의고사", "티어 멸망전"
            ]
            
            match_name_upper = match_name.upper()
            
            # [로그 추가] 필터링 단어에 걸려서 제외되는 경우 추적
            if any(keyword.upper() in match_name_upper for keyword in exclude_keywords):
                skipped_by_filter += 1
                # 너무 많은 로그 방지를 위해 주석 처리 해두었으나, 필요시 아래 줄 주석을 풀면 어떤 매치가 제외되었는지 볼 수 있습니다.
                # print(f"   -> [필터링 제외] {match_name}")
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
            else:
                # [로그 추가] 승리(#0CF)나 패배(#434348) 색상 코드가 둘 다 발견되지 않은 경우
                unknown_color_count += 1
                # 어떤 style 문자열이 들어왔는지 출력하여 색상 변경 여부를 판단합니다.
                print(f"   -> [색상 미매칭 인지불가] 매치명: {match_name} / style값: {style}")
                
            date_text = td1.find('a').get_text(strip=True) if td1.find('a') else td1.get_text(strip=True)
            opponent = tds[2].get_text(strip=True)
            
            # 6번째 td: 대전 당시 소속 대학 이름 (team)
            my_team = tds[5].get_text(strip=True)
            
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
            
        # [로그 추가] 전체 탐색 종료 후 요약 리포트를 콘솔에 출력
        if win_count == 0 and lose_count == 0:
            print(f"   ℹ️ [분석 리포트] 웹상 발견된 총 전적 행: {total_rows_found}개")
            print(f"   ℹ️ 필터링 단어('CK', '평가전' 등)에 의해 제외된 판수: {skipped_by_filter}개")
            print(f"   ℹ️ 승/패 배경색을 인식하지 못해 버려진 판수: {unknown_color_count}개")
            
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
