import requests
import re

from bs4 import BeautifulSoup

headers = {
    "User-Agent" : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
}

def get_sido_list():
    """시/도 목록 (고정값)"""
    return ["서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
            "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
            "충청북도", "충청남도", "전북특별자치도", "전라남도",
            "경상북도", "경상남도", "제주특별자치도"]

def get_sigungu_list(sido_nm):
    url = "https://www.opinet.co.kr/common/sigunguGisSelect.do"
    data = {"SIDO_NM": sido_nm}
    res = requests.post(url, data=data, headers=headers, timeout=10)
    result = res.json().get('result', [])
    return [item['SIGUNGU_NM'] for item in result]

def get_stations(sido_nm, sigungu_nm):
    url = "https://www.opinet.co.kr/searRgSelect.do"
    data = {
        "BTN_DIV": "os_btn", "POLL_ALL": "all",
        "SIDO_NM": sido_nm, "SIGUNGU_NM": sigungu_nm,
        "SIDO_NM0": sido_nm, "SIGUNGU_NM0": sigungu_nm,
        "SEARCH_MOD": "addr", "NORM_YN": "on", "SELF_DIV_CD": "on",
        "VLT_YN": "on", "KPETRO_YN": "on", "KPETRO_DP_YN": "on", "GOOD_OS_YN": "on",
        "POLL_DIV_CD": ["SKE", "GSC", "HDO", "SOL", "RTO", "RTX", "NHO", "ETC"],
    }
    res = requests.post(url, data=data, headers=headers, timeout=10)
    html = res.text

    fields = ['OS_NM', 'RD_ADDR', 'POLL_DIV_NM', 'B027_P', 'D047_P',
              'CWSH_YN', 'SEL24_YN', 'CVS_YN', 'PHN_NO']
    extracted = {f: re.findall(rf'var {f}\s*=\s*"([^"]*)"', html) for f in fields}

    count = len(extracted['OS_NM'])
    stations = []
    for i in range(count):
        stations.append({
            '주유소명': extracted['OS_NM'][i],
            '주소': extracted['RD_ADDR'][i],
            '브랜드': extracted['POLL_DIV_NM'][i],
            '휘발유가격': extracted['B027_P'][i],
            '경유가격': extracted['D047_P'][i],
            '세차장': '가능' if extracted['CWSH_YN'][i] == 'Y' else '불가',
            '24시간영업': '가능' if extracted['SEL24_YN'][i] == 'Y' else '불가',
            '편의점': '있음' if extracted['CVS_YN'][i] == 'Y' else '없음',
            '전화번호': extracted['PHN_NO'][i],
        })
    return stations
