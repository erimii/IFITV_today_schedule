
# IFITV IPTV 편성표 & 메타데이터 수집기

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Selenium](https://img.shields.io/badge/selenium-%2334A853.svg?logo=selenium&logoColor=white)](https://www.selenium.dev/)
[![TMDB API](https://img.shields.io/badge/TMDB-API-red)](https://www.themoviedb.org/documentation/api)
[![Gemini API](https://img.shields.io/badge/Gemini-GoogleAI-yellow)](https://ai.google.dev/)

> LG U+ 실시간 채널 편성표를 크롤링하고 TMDB/Naver/Gemini를 활용해 콘텐츠 메타데이터를 보강하는 수집기입니다.  
> IFITV 프로젝트의 IPTV 콘텐츠 추천을 위한 핵심 데이터 파이프라인입니다.

---

## 📌 기능 개요

### ✅ 편성표 크롤링
- LG U+ IPTV 공식 사이트에서 채널별 실시간 편성표 수집
- Selenium + BeautifulSoup으로 구성
- 방송 시간, 제목, 장르, 시청 등급, 런타임 계산 포함

### ✅ 메타데이터 수집
- `ThreadPoolExecutor(max_workers=5)` 기반 병렬 처리
- 콘텐츠 설명 + 썸네일 수집 순서:
  1. **TMDB API**
  2. **Naver 검색 (requests)**
  3. **Gemini API (fallback)**

### ✅ 서브장르 분류
- Gemini API로 콘텐츠 설명 기반 서브장르 분류
- 장르별 수작업 후보군 활용 (예: 예능 → 관찰예능, 여행, 서바이벌 등)

---

## 📁 결과물 예시

- 경로: `./result/{채널명}_program_list.csv`
- 컬럼 구성:

```csv
channel, airtime, runtime, title, genre, subgenre, description, cast, age_rating, thumbnail
````

---

## 🛠 사용 기술

* `Python 3.9+`
* `Selenium`, `BeautifulSoup`
* `TMDB API`, `Naver`, `Gemini API`
* `pandas`, `concurrent.futures`
* `.env` 환경변수 관리



