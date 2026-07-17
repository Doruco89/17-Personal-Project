# -*- coding: utf-8 -*-
"""
오피넷(한국석유공사) 오픈API 연동 모듈.
크롤링(scrapper.py) 대신 공식 오픈API 5종 중 아래 3개를 조합해서 사용한다.
 
  1) areaCode.do    - 지역코드 조회 (시/도, 시/군/구)
  2) lowTop10.do    - 지역별 최저가 주유소 TOP20 (유종 1개 기준)
  3) detailById.do  - 주유소 상세정보 (세차장/편의점/경정비 여부 + 3개 유종 가격)
 
※ 주의: 오피넷 무료 API에는 "선택 지역의 주유소 전체 목록"을 한번에 주는 API가 없고,
   24시간영업 여부 필드도 제공되지 않는다. 그래서 결과는 "최저가 TOP20"이 되고,
   24시간 필터는 화면에서 제거했다.
"""
import requests
 
from config import OPINET_API_KEY, OIL_DEMO_MODE
 
BASE = "https://www.opinet.co.kr/api"
 
# 오피넷 자체 시/도 코드 (areaCode.do 응답 기준, 표준 행정코드와 다름에 주의)
SIDO_CODE = {
    "서울특별시": "01", "경기도": "02", "강원특별자치도": "03", "충청북도": "04",
    "충청남도": "05", "전북특별자치도": "06", "전라남도": "07", "경상북도": "08",
    "경상남도": "09", "부산광역시": "10", "제주특별자치도": "11", "대구광역시": "14",
    "인천광역시": "15", "광주광역시": "16", "대전광역시": "17", "울산광역시": "18",
    "세종특별자치시": "19",
}
 
# 화면 라디오버튼 값 -> 오피넷 유종코드
FUEL_PRODCD = {
    "경유가격": "D047",
    "휘발유가격": "B027",
    "고급휘발유가격": "B034",
}
 
BRAND_LOGO_MAP = {
    'SKE': 'https://www.opinet.co.kr/images/user/com/icon_sk2.gif',
    'GSC': 'https://www.opinet.co.kr/images/user/com/icon_gs2.gif',
    'HDO': 'https://www.opinet.co.kr/images/user/com/icon_hy2.gif',
    'SOL': 'https://www.opinet.co.kr/images/user/com/icon_soil2.gif',
    'RTE': 'https://www.opinet.co.kr/images/user/com/icon_rto_new2.gif',
    'RTX': 'https://www.opinet.co.kr/images/user/com/icon_rto_new2.gif',
}
BRAND_NAME_MAP = {
    'SKE': 'SK에너지', 'GSC': 'GS칼텍스', 'HDO': 'HD현대오일뱅크', 'SOL': 'S-OIL',
    'RTE': '알뜰주유소', 'RTX': '고속도로알뜰', 'NHO': '농협알뜰', 'ETC': '자가상표',
    'E1G': 'E1', 'SKG': 'SK가스',
}
 
# ---- 키가 없을 때 쓰는 데모 데이터 (실제 API 응답과 동일한 모양) ----
_DEMO_SIGUNGU = {
    "서울특별시": ["강남구", "서초구", "송파구", "마포구", "종로구"],
    "인천광역시": ["남동구", "연수구", "부평구", "미추홀구"],
}
_DEMO_STATIONS = [
    {
        '주유소명': '(데모) 강남중앙주유소', '주소': '서울 강남구 테헤란로 152', '브랜드': 'SK에너지',
        '브랜드로고': BRAND_LOGO_MAP['SKE'], '휘발유가격': '1698', '고급휘발유가격': '1920',
        '경유가격': '1549', '세차장': '가능', '편의점': '있음', '전화번호': '02-000-0000',
    },
    {
        '주유소명': '(데모) 역삼셀프주유소', '주소': '서울 강남구 역삼로 210', '브랜드': 'GS칼텍스',
        '브랜드로고': BRAND_LOGO_MAP['GSC'], '휘발유가격': '1685', '고급휘발유가격': '판매안함',
        '경유가격': '1538', '세차장': '불가', '편의점': '없음', '전화번호': '02-000-0001',
    },
]
 
 
def _get(path, params):
    params = {**params, "certkey": OPINET_API_KEY, "out": "json"}
    res = requests.get(f"{BASE}/{path}", params=params, timeout=10)
    res.raise_for_status()
    return res.json()
 
 
def get_sido_list():
    return list(SIDO_CODE.keys())
 
 
def get_sigungu_list(sido_nm):
    if OIL_DEMO_MODE:
        return _DEMO_SIGUNGU.get(sido_nm, ["샘플구"])
 
    sido_cd = SIDO_CODE.get(sido_nm)
    if not sido_cd:
        return []
    data = _get("areaCode.do", {"area": sido_cd})
    items = data.get("RESULT", {}).get("OIL", [])
    if isinstance(items, dict):
        items = [items]
    return [item["AREA_NM"] for item in items]
 
 
def _find_sigungu_code(sido_nm, sigungu_nm):
    sido_cd = SIDO_CODE.get(sido_nm)
    data = _get("areaCode.do", {"area": sido_cd})
    items = data.get("RESULT", {}).get("OIL", [])
    if isinstance(items, dict):
        items = [items]
    for item in items:
        if item.get("AREA_NM") == sigungu_nm:
            return item.get("AREA_CD")
    return None
 
 
def _get_station_detail(uni_id):
    """detailById.do 호출 -> 세차장/편의점 여부 + 유종별 가격 반환"""
    data = _get("detailById.do", {"id": uni_id})
    oil = data.get("RESULT", {}).get("OIL", {})
    prices = oil.get("OIL_PRICE", [])
    if isinstance(prices, dict):
        prices = [prices]
    price_by_code = {p.get("PRODCD"): p.get("PRICE") for p in prices}
 
    def price_or_na(code):
        v = price_by_code.get(code)
        return v if v else '판매안함'
 
    brand_cd = oil.get("POLL_DIV_CO") or oil.get("POLL_DIV_CD")
    return {
        '주유소명': oil.get('OS_NM'),
        '주소': oil.get('NEW_ADR') or oil.get('VAN_ADR'),
        '브랜드': BRAND_NAME_MAP.get(brand_cd, brand_cd),
        '브랜드로고': BRAND_LOGO_MAP.get(brand_cd),
        '휘발유가격': price_or_na('B027'),
        '고급휘발유가격': price_or_na('B034'),
        '경유가격': price_or_na('D047'),
        '세차장': '가능' if oil.get('CAR_WASH_YN') == 'Y' else '불가',
        '편의점': '있음' if oil.get('CVS_YN') == 'Y' else '없음',
        '전화번호': oil.get('TEL'),
    }
 
 
def get_stations(sido_nm, sigungu_nm, fuel_type='경유가격'):
    """지역별 최저가 TOP20 + 상세정보(세차장/편의점) 조합 리스트 반환"""
    if OIL_DEMO_MODE:
        return _DEMO_STATIONS
 
    prodcd = FUEL_PRODCD.get(fuel_type, 'D047')
    sigungu_cd = _find_sigungu_code(sido_nm, sigungu_nm)
    if not sigungu_cd:
        return []
 
    top = _get("lowTop10.do", {"prodcd": prodcd, "area": sigungu_cd, "cnt": 20})
    items = top.get("RESULT", {}).get("OIL", [])
    if isinstance(items, dict):
        items = [items]
 
    stations = []
    for item in items:
        uni_id = item.get("UNI_ID")
        try:
            detail = _get_station_detail(uni_id)
            stations.append(detail)
        except Exception:
            continue
    return stations