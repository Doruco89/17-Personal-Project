import requests

from bs4 import BeautifulSoup

headers = {
    "User-Agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
}

url = "https://www.opinet.co.kr/searRgSelect.do"

data = {
    "BTN_DIV": "os_btn",
    "POLL_ALL": "all",
    "SIDO_NM": "대구광역시",
    "SIGUNGU_NM": "달성군",
    "SIDO_CD": "14",
    "SIGUN_CD": "1406",
    "SIDO_NM0": "대구광역시",
    "SIGUNGU_NM0": "달성군",
    "SEARCH_MOD": "addr",
    "NORM_YN": "on",
    "SELF_DIV_CD": "on",
    "VLT_YN": "on",
    "KPETRO_YN": "on",
    "KPETRO_DP_YN": "on",
    "GOOD_OS_YN": "on",
    "POLL_DIV_CD": ["SKE", "GSC", "HDO", "SOL", "RTO", "RTX", "NHO", "ETC"],
    # 세차장/24시간은 필터가 아니라 "표시용 컬럼"으로 쓸 거라 제외
    # "CWSH_YN": "on",
    # "SEL24_YN": "on",
}
session = requests.Session()
response = session.post(url, data=data, headers=headers)
print(response.status_code)
print(response.text[:3000])  # 응답 구조 먼저 확인

print(len(response.text))

# 특정 주유소명이 실제로 응답 안에 있는지 확인 (달성군에 있던 '흥구석유' 예시)
if '흥구석유' in response.text:
    print("데이터 있음!")
else:
    print("이 주유소명은 없음 - 다른 조건이거나 목록이 다를 수 있음")

# 가격 정보 근처 텍스트 찾기
import re
idx = response.text.find('평균가격')
print(response.text[idx:idx+2000])

idx = response.text.find('흥구석유')
print(response.text[idx-500:idx+1500])