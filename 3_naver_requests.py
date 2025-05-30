
import os
import re
import time, random
import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import html
from urllib.parse import quote
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv
from google.generativeai import GenerativeModel
import google.generativeai as genai
from threading import Lock
from urllib.parse import quote

load_dotenv() 
selenium_lock = Lock()

# 채널 리스트
'''
channel_list = [
    # 전국 지상파
    'KBS1[9]', 'KBS2[7]', 'MBC[11]', 'SBS[5]',

    # 종편 + 공영 + 교양
    'JTBC[15]', 'MBN[16]', '채널A[18]', 'TV조선[19]',
    'EBS1[14]', 'EBS2[95]', 'OBS[26]',

    # 드라마/예능/영화 전문 채널
    'tvN[3]', 'OCN[44]', '스크린[46]', '씨네프[47]', 'OCN Movies2[51]',
    '캐치온1[52]', '캐치온2[53]', '채널액션[54]',
    '드라마큐브[71]', 'ENA[72]', 'ENA DRAMA[73]',
    'KBS Story[74]', 'SBS플러스[33]', 'MBC드라마넷[35]',

    # 애니메이션/키즈 채널
    '투니버스[324]', '카툰네트워크[316]',
    '애니박스[327]', '애니맥스[326]', '어린이TV[322]'
]
'''
# 스포츠는 어떻게 하지?
genre_map = {'연예/오락': '예능', '뉴스/정보': '보도', '만화': '애니', '교육': '애니', '공연/음악': '예능'}

# 장르별 서브장르 사전
subgenre_dict = {
    "드라마": [
        "해외드라마", "미국드라마", "영국드라마", "중국드라마", "일본드라마",
        "로맨스", "코미디", "판타지", "무협", "공포", "복수", "휴먼",
        "범죄 스릴러/수사극", "의학", "웹툰/소설 원작", "정치/권력", "법정",
        "청춘(성장)", "오피스 드라마", "사극/시대극", "타임슬립"
    ],
    "예능": [
        "버라이어티", "다큐멘터리", "여행", "쿡방/먹방", "연애리얼리티", "게임",
        "토크쇼", "서바이벌", "관찰리얼리티", "스포츠예능", "교육예능", "힐링예능",
        "아이돌리얼리티", "음악서바이벌", "음악예능", "코미디", "가족예능",
        "뷰티", "애니멀"
    ],
    "영화": [
        "드라마", "로맨스", "코미디", "애니메이션", "스릴러", "미스터리",
        "모험", "액션", "판타지", "SF", "공포", "다큐멘터리"
    ],
    "애니": ["키즈"],
    "보도": ["보도"],
    "스포츠": ["스포츠"]
}

def clean_name(text):
    # 괄호 및 특수 괄호 안의 내용 제거
    text = re.sub(r'\([^)]*\)', '', text)      # (내용)
    # text = re.sub(r'\[[^\]]*\]', '', text)     # [내용]
    text = re.sub(r'〈.*?〉', '', text)         # 〈내용〉
    text = re.sub(r'\<.*?\>', '', text)        # <내용>
    
    # 방송 상태 관련 단어 제거
    text = re.sub(r'\b(수목드라마|월화드라마|일일드라마|재방송\
                  |특별판|스페셜|본방송|본|재|특집|종영|마지막회\
                  |최종화|HD|SD|NEW|다시보기)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\d+부', '', text)  # 회차 정보 제거
    
    # 특수문자 정리
    text = re.sub(r'[“”"\'\:\-\|·,~!@#\$%\^&\*\+=]+', ' ', text)  # 기호 → 공백
    text = re.sub(r'\s+', ' ', text)  # 연속 공백 정리
    
    # 한글/영문 조합 불필요한 공백 제거
    #text = re.sub(r'([가-힣])\s+([A-Za-z])', r'\1\2', text)
    #text = re.sub(r'([A-Za-z])\s+([가-힣])', r'\1\2', text)
    
    # 끝에 남은 괄호 등 제거
    #text = text.strip("()[]〈〉 ")
    
    # 전체 정리 후 반환
    return text.strip()

def clean_ani_title(title):
    
    # 제목 앞 대괄호 접두사 제거
    title = re.sub(r'^\[[^\]]*\]\s*', '', title)
    
    # 대괄호 안 제거
    title = re.sub(r'\[[^\]]*\]', '', title)

    # 괄호 안 제거
    title = re.sub(r'\([^)]*\)', '', title)

    # '시즌', 'part', '편', 'ep' 같은 것들 제거
    title = re.sub(r'(시즌|season|part|편|ep|에피소드)\s?\d+', '', title, flags=re.IGNORECASE)

    # 영어 OR 숫자만 덩그러니 있는 경우 제거
    title = re.sub(r'\b[a-zA-Z0-9]+\b', '', title)

    # 특수문자 제거
    title = re.sub(r'[“”"\'\:\-\|·~!@#\$%\^&\*\+=<>▶★☆●■◆♥♡]', '', title)

    # 연속 공백 정리
    title = re.sub(r'\s+', ' ', title).strip()

    return title

# runtime 계산(마지막 방송은 60분으로)
def calculate_runtime(df):

    df['airtime'] = pd.to_datetime(df['airtime'], format='%H:%M:%S')

    df['endtime'] = df['airtime'].shift(-1)
    df.loc[df.index[-1], 'endtime'] = df.loc[df.index[-1], 'airtime'] + timedelta(minutes=60)

    df['runtime'] = (df['endtime'] - df['airtime']).dt.total_seconds() // 60
    df['runtime'] = df['runtime'].astype(int)

    df['airtime'] = df['airtime'].dt.strftime('%H:%M')

    df.drop(columns=['endtime'], inplace=True)
    return df


def get_subgenres_from_gemini(description, genre):
    if not description or genre not in subgenre_dict:
        return ""

    # 애니/보도는 고정값 처리
    if genre == "애니":
        return "키즈"
    if genre == "보도":
        return "보도"
    if genre == "스포츠":
        return "스포츠"

    candidate_list = subgenre_dict[genre]
    model = genai.GenerativeModel("gemini-1.5-pro-latest")

    prompt = f"""다음 설명을 보고 아래 서브장르 중에서 해당되는 것을 골라줘. 1개 이상이면 콤마(,)로 구분해줘.

                설명:
                {description}
                
                서브장르 목록:
                {", ".join(candidate_list)}
                """

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[Gemini 오류] {description[:20]}... 처리 실패: {e}")
        return ""


# TMDB로 설명, 썸네일 추가
def get_from_tmdb(title, genre):
    search_url = f"https://api.themoviedb.org/3/search/multi"
    title = re.sub(r'\d+$', '', title)  # 끝에 붙은 숫자 제거r
    
    if genre == "애니":
        title = clean_ani_title(title)
        print(title)
        
    params = {
        "api_key": os.getenv("TMDB_API_KEY"),
        "language": "ko-KR",
        "query": title,
        "include_adult": "false"
    }

    try:
        response = requests.get(search_url, params=params)
        response.raise_for_status()
        results = response.json().get("results", [])

        if not results:
            return None, None

        # 가장 첫 번째 결과 사용
        item = results[0]
        content_id = item.get("id")
        media_type = item.get("media_type")  # movie or tv

        # 상세 정보 가져오기
        detail_url = f"https://api.themoviedb.org/3/{media_type}/{content_id}"
        detail_params = {
            "api_key": os.getenv("TMDB_API_KEY"),
            "language": "ko-KR"
        }
        detail_resp = requests.get(detail_url, params=detail_params)
        detail_resp.raise_for_status()
        detail_data = detail_resp.json()

        description = detail_data.get("overview", "").replace('\n', ' ').strip()
        thumbnail = f"https://image.tmdb.org/t/p/w500{detail_data.get('poster_path')}" if detail_data.get("poster_path") else ""

        return description, thumbnail

    except Exception as e:
        print(f"[TMDb Error] {title} 검색 실패: {e}")
        return None, None

# 네이버 검색으로 보완
def get_from_naver_with_driver(driver, title):
    query = f"{title} 정보"
    search_url = f"https://search.naver.com/search.naver?query={query}"
    driver.get(search_url)
    time.sleep(1.5)

    try:
        intro_elem = driver.find_element(By.CSS_SELECTOR, '.intro_box .text.no_ellipsis')
        description = intro_elem.text.strip().replace('\n', ' ')
    except:
        description = None

    try:
        thumb_elem = driver.find_element(By.CSS_SELECTOR, '.cm_info_box .detail_info a.thumb img')
        thumbnail = thumb_elem.get_attribute('src')
    except:
        thumbnail = None

    return description, thumbnail

# Naver requests
def get_from_naver_with_requests(title):
    time.sleep(random.uniform(0.5, 1.5))
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Referer": "https://www.naver.com",
            "Connection": "keep-alive"
        }

        query = f"{title} 정보"
        search_url = f"https://search.naver.com/search.naver?query={quote(query)}"
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        description = soup.select_one('.intro_box .text.no_ellipsis')
        thumbnail = soup.select_one('.cm_info_box .detail_info a.thumb img')

        desc_text = description.text.strip() if description else None
        thumb_url = thumbnail['src'] if thumbnail else None

        return desc_text, thumb_url

    except Exception as e:
        print(f"[Naver Requests 오류] {title} → {e}")
        return None, None


# Gemini API로 보완
def get_from_gemini(title: str, genre: str):
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name="gemini-2.0-flash-lite")
        prompt = f"한국 {genre} 콘텐츠 '{title}'에 대한 간단한 소개글을 작성해줘. 300자 이내로 줄바꿈 없이 부탁해."
        response = model.generate_content(prompt)
        description = response.text.strip().replace('\n', ' ')
        return description
    except Exception as e:
        print(f"[Gemini 오류] {title} 처리 실패: {e}")
        return None

def get_metadata(title, genre):
    
    desc, thumbnail = get_from_tmdb(title, genre)

    if not desc or not thumbnail:
        desc_n, thumb_n = get_from_naver_with_requests(title)
        if not desc:
            desc = desc_n
        if not thumbnail:
            thumbnail = thumb_n
    
    if not desc:
        desc = get_from_gemini(title, genre)

    return desc, thumbnail


def get_live_programs():
    start_time = time.time()
    
    channel_list = [# 전국 지상파
    'KBS1[9]', 'KBS2[7]', 'MBC[11]', 'SBS[5]',

    # 종편 + 공영 + 교양
    'JTBC[15]', 'MBN[16]', '채널A[18]', 'TV조선[19]',
    'EBS1[14]', 'EBS2[95]', 'OBS[26]',

    # 드라마/예능/영화 전문 채널
    'tvN[3]', 'OCN[44]', '스크린[46]', '씨네프[47]', 'OCN Movies2[51]',
    '캐치온1[52]', '캐치온2[53]', '채널액션[54]',
    '드라마큐브[71]', 'ENA[72]', 'ENA DRAMA[73]',
    'KBS Story[74]', 'SBS플러스[33]', 'MBC드라마넷[35]',

    # 애니메이션/키즈 채널
    '투니버스[324]', '카툰네트워크[316]',
    '애니박스[327]', '애니맥스[326]', '어린이TV[322]']

    # 편성표 크롤링용 드라이버
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 10)
    
    # naver 메타데이터용 드라이버
    options2 = Options()
    options2.add_argument('--no-sandbox')
    options2.add_argument('--disable-dev-shm-usage')
    options2.add_argument('--headless')
    driver_metadata = webdriver.Chrome(options=options2)
    
    url = 'https://www.lguplus.com/iptv/channel-guide'

    table_btn_xpath = '//a[contains(text(), "채널 편성표 안내")]'
    all_channel_btn_xpath = '//a[contains(text(), "전체채널")]'
    
    driver.get(url)
    driver.execute_script("document.body.style.zoom='50%'")
    time.sleep(1)
    wait.until(EC.element_to_be_clickable((By.XPATH, table_btn_xpath))).click()
    #time.sleep(1)
    wait.until(EC.element_to_be_clickable((By.XPATH, all_channel_btn_xpath))).click()
    #time.sleep(1)

    # 채널별 반복 크롤링
    for channel in channel_list:
        try:
            
            # 채널 팝업 다시 열기
            # 채널 펼침 버튼 찾기
            open_btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.c-btn-outline-2-s.open")))
            
            # 화면 중앙까지 스크롤해서 겹치는 요소 제거
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", open_btn)
            time.sleep(0.3)  # 혹시 모를 렌더링 대기
            
            # JavaScript로 강제 클릭
            driver.execute_script("arguments[0].click();", open_btn)
    
            # 채널 버튼 클릭
            channel_xpath = f'//a[contains(text(), "{channel}")]'
            wait.until(EC.element_to_be_clickable((By.XPATH, channel_xpath))).click()
            time.sleep(1)
            
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            program_soup_list = soup.select('tr.point')
    
            program_list = []
            safe_name = re.sub(r'\s*(\[[^]]*\])', '', channel).strip()
    
            for item in program_soup_list:
                try:
                    tds = item.select('td')
                    time_text = tds[0].text.strip()
                    name_parts = tds[1].text.split('\n')
                    raw_name = name_parts[1].strip() if len(name_parts) > 1 else tds[1].text.strip()
                    name = clean_name(raw_name)
                    
                    genre = genre_map.get(tds[2].text.strip(), tds[2].text.strip())
                    
                    # 시청 등급 추출
                    all_flags = tds[1].select("small.c-flag")
                    age_rating = None
                    for flag in all_flags:
                        text = flag.text.strip()
                        if text in ['All', '7', '12', '15', '19']:
                            age_rating = text
                            break
                    
                    program_list.append([safe_name, time_text, '', name, genre, '', '', '', age_rating, ''])

                except Exception as e:
                    print(f"[프로그램 처리 오류] {e}")
                    continue
                
            # 결과 저장
            
            df = pd.DataFrame(program_list, columns = ['channel', 'airtime', 'runtime', 'title', 'genre', 'subgenre', 'description','cast', 'age_rating', 'thumbnail'])
            
            
            # 런타임 계산 추가 적용 및 추가 전처리
            df = calculate_runtime(df)
            df = df[~df['title'].str.contains(r'방송\s*시간\s*이\s*아닙니다\.?', regex=True)].reset_index(drop=True)
            df['description'] = df['description'].str.replace('\n', ' ', regex=False)

            
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def process_metadata(i, row):
                try:
                    desc, thumbnail = get_metadata(row['title'], row['genre'])
                    subgenre = get_subgenres_from_gemini(desc, row['genre'])
                    return i, desc, thumbnail, subgenre
                except Exception as e:
                    print(f"[병렬 처리 오류] {row['title']} 실패: {e}")
                    return i, None, None, None
            
            # 병렬 처리로 메타데이터 보강
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(process_metadata, i, row) for i, row in df.iterrows()]
                for future in as_completed(futures):
                    i, desc, thumbnail, subgenre = future.result()
                    if desc:
                        df.at[i, 'description'] = desc
                    if thumbnail:
                        df.at[i, 'thumbnail'] = thumbnail
                    if subgenre:
                        df.at[i, 'subgenre'] = subgenre


            
            # 저장
            df.to_csv(f'./result/{safe_name}_program_list.csv', index=False, encoding='utf-8-sig')
            print(f'{safe_name} 완료')
            
            
        except Exception as e:
            print(f"[채널 오류] {channel} 처리 중 오류: {e}")
            continue
        
    driver.quit()
    print("[전체 완료] 모든 채널 크롤링 종료")
    end_time = time.time()
    elapsed = end_time - start_time
    print(f"총 소요 시간: {elapsed:.2f}초 ({elapsed/60:.2f}분)")

# 테스트 출력
get_live_programs()






















