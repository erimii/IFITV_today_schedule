import os
import re
import time
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

# API 인증 정보
NAVER_CLIENT_ID = 'zO9HpDRbfkJgizjZyaSL'
NAVER_CLIENT_SECRET = 'JDxZDkpg9v'
TMDB_API_KEY = "398f2e93b1b5d70c0d1229dae14bccbd"


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

# TMDB로 설명, 썸네일 추가
def get_from_tmdb(title, genre, api_key):
    search_url = f"https://api.themoviedb.org/3/search/multi"
    title = re.sub(r'\d+$', '', title)  # 끝에 붙은 숫자 제거
    
    if genre == "애니":
        title = clean_ani_title(title)
        print(title)
        
    params = {
        "api_key": api_key,
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
            "api_key": api_key,
            "language": "ko-KR"
        }
        detail_resp = requests.get(detail_url, params=detail_params)
        detail_resp.raise_for_status()
        detail_data = detail_resp.json()

        description = detail_data.get("overview", "")
        thumbnail = f"https://image.tmdb.org/t/p/w500{detail_data.get('poster_path')}" if detail_data.get("poster_path") else ""

        return description, thumbnail

    except Exception as e:
        print(f"[TMDb Error] {title} 검색 실패: {e}")
        return None, None

def infer_subgenre(desc):
    if not desc:
        return ""
    desc = desc.lower()
    if "여행" in desc:
        return "여행"
    if "음식" in desc or "먹방" in desc:
        return "음식"
    if "토크" in desc:
        return "토크"
    if "리얼" in desc or "관찰" in desc:
        return "리얼리티"
    if "게임" in desc or "퀴즈" in desc:
        return "게임"
    return "기타"

def get_from_naver(title, genre, client_id, client_secret):
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }

    #query = re.sub(r'[^가-힣A-Za-z0-9]', '', title)  # 특수문자 제거
    #query = re.sub(r'\s+', '', query)                # 공백 제거

    url = f"https://openapi.naver.com/v1/search/tv.json?query={title}"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # 404면 여기서 예외 발생

        data = response.json()
        items = data.get('items', [])

        if not items:
            return None, None, None, None

        top = items[0]

        description = re.sub('<[^>]*>', '', top.get('description', ''))
        cast = re.sub('<[^>]*>', '', top.get('actor', ''))
        thumbnail = top.get('image', '')

        subgenre = infer_subgenre(description)

        return description, cast, thumbnail, subgenre

    except Exception as e:
        print(f"[네이버 검색 실패] {title} : {e}")
        return None, None, None, None


def get_metadata(title, genre, tmdb_api_key, naver_client_id, naver_client_secret):
    # TMDb 먼저 시도
    desc, thumbnail = get_from_tmdb(title, genre, tmdb_api_key)

    return desc, thumbnail


def get_live_programs():
    channel_list = [    '투니버스[324]', '카툰네트워크[316]',
        '애니박스[327]', '애니맥스[326]', '어린이TV[322]']

    # 크롬 드라이버 설정
    options = Options()
    #options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 10)
    
    url = 'https://www.lguplus.com/iptv/channel-guide'

    table_btn_xpath = '//a[contains(text(), "채널 편성표 안내")]'
    all_channel_btn_xpath = '//a[contains(text(), "전체채널")]'
    
    driver.get(url)
    driver.execute_script("document.body.style.zoom='50%'")
    time.sleep(1)
    wait.until(EC.element_to_be_clickable((By.XPATH, table_btn_xpath))).click()
    time.sleep(1)
    wait.until(EC.element_to_be_clickable((By.XPATH, all_channel_btn_xpath))).click()
    time.sleep(1)

    # 채널별 반복 크롤링
    for channel in channel_list:
        try:
            
            # 채널 팝업 다시 열기
            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.c-btn-outline-2-s.open"))).click()
            #time.sleep(1)
    
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

            
            for i, row in df.iterrows():
                desc, thumbnail = get_metadata(
                    row['title'], row['genre'],
                    TMDB_API_KEY, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
                )
                df.at[i, 'description'] = desc
                # df.at[i, 'cast'] = cast
                df.at[i, 'thumbnail'] = thumbnail
                # df.at[i, 'subgenre'] = subgenre

            
            # 저장
            df.to_csv(f'./result/{safe_name}_program_list.csv', index=False, encoding='utf-8-sig')

            time.sleep(1)
            
            
        except Exception as e:
            print(f"[채널 오류] {channel} 처리 중 오류: {e}")
            continue
        
    driver.quit()
    print("[전체 완료] 모든 채널 크롤링 종료")

# 테스트 출력
get_live_programs()






















