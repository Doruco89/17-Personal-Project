# -*- coding: utf-8 -*-
"""
오피넷(한국석유공사) 오픈API 연동 모듈.
크롤링(scrapper.py) 대신 공식 오픈API 5종 중 아래 3개를 조합해서 사용한다.
 
  1) areaCode.do    - 지역코드 조회 (시/도, 시/군/구)
  2) lowTop10.do    - 지역별 최저가 주유소 TOP20 (유종 1개 기준)
  3) detailById.do  - 주유소 상세정보 (세차장/편의점/경정비 여부 + 3개 유종 가격)
 
※ 주의: 오피넷 무료 API에는 24시간영업 여부 필드가 없다. 이 필드만큼은
   기존 방식(searRgSelect.do 지역별 조회 화면)을 보조적으로 한 번 더 호출해서
   주유소명으로 매칭해 채워 넣는 "하이브리드" 방식을 쓴다.
   (가격/세차장/편의점 등 나머지 전부는 API로만 가져온다.)
"""
import math
import re
import requests
from pyproj import Transformer
 
from config import OPINET_API_KEY, OIL_DEMO_MODE
 
BASE = "https://www.opinet.co.kr/api"
 
_CRAWL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
}
 
# 오피넷 GIS_X_COOR/GIS_Y_COOR 좌표계: TM128(일명 KATEC, 옛 다음지도 방식, Bessel 타원체)
# 실제 강남 역삼동 좌표(x=314871.8, y=544012.0)로 역산 검증해서 확인한 값.
_TM128_TO_WGS84 = Transformer.from_crs(
    "+proj=tmerc +lat_0=38 +lon_0=128 +k=0.9999 +x_0=400000 +y_0=600000 "
    "+ellps=bessel +units=m +no_defs +towgs84=-146.43,507.89,681.46",
    "EPSG:4326",
    always_xy=True,
)
 
 
def _tm128_to_latlng(x, y):
    lon, lat = _TM128_TO_WGS84.transform(float(x), float(y))
    return lat, lon
 
 
def _haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
 
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
        '경유가격': '1549', '세차장': '가능', '편의점': '있음', '24시간영업': '가능',
        '전화번호': '02-000-0000', '_lat': 37.4980, '_lng': 127.0276,
    },
    {
        '주유소명': '(데모) 역삼셀프주유소', '주소': '서울 강남구 역삼로 210', '브랜드': 'GS칼텍스',
        '브랜드로고': BRAND_LOGO_MAP['GSC'], '휘발유가격': '1685', '고급휘발유가격': '판매안함',
        '경유가격': '1538', '세차장': '불가', '편의점': '없음', '24시간영업': '불가',
        '전화번호': '02-000-0001', '_lat': 37.5006, '_lng': 127.0365,
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
    if isinstance(oil, list):
        oil = oil[0] if oil else {}
    prices = oil.get("OIL_PRICE", [])
    if isinstance(prices, dict):
        prices = [prices]
    price_by_code = {p.get("PRODCD"): p.get("PRICE") for p in prices}
 
    def price_or_na(code):
        v = price_by_code.get(code)
        return v if v else '판매안함'
 
    brand_cd = oil.get("POLL_DIV_CO") or oil.get("POLL_DIV_CD")
 
    lat, lng = None, None
    x, y = oil.get("GIS_X_COOR"), oil.get("GIS_Y_COOR")
    if x and y:
        try:
            lat, lng = _tm128_to_latlng(x, y)
        except Exception:
            lat, lng = None, None
 
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
        '_lat': lat,
        '_lng': lng,
    }
 
 
def _get_24hour_map(sido_nm, sigungu_nm):
    """
    오피넷 무료 API에는 없는 24시간영업 여부만 보조적으로 채워 넣기 위해
    지역별 조회 화면(searRgSelect.do)을 한 번 호출해서 '주유소명 -> 24시간여부'
    매핑 테이블을 만든다. 이 호출 하나로 실패해도 나머지(API 데이터)는
    영향받지 않도록 예외를 여기서 흡수한다.
    """
    url = "https://www.opinet.co.kr/searRgSelect.do"
    data = {
        "BTN_DIV": "os_btn", "POLL_ALL": "all",
        "SIDO_NM": sido_nm, "SIGUNGU_NM": sigungu_nm,
        "SIDO_NM0": sido_nm, "SIGUNGU_NM0": sigungu_nm,
        "SEARCH_MOD": "addr", "NORM_YN": "on", "SELF_DIV_CD": "on",
        "VLT_YN": "on", "KPETRO_YN": "on", "KPETRO_DP_YN": "on", "GOOD_OS_YN": "on",
        "POLL_DIV_CD": ["SKE", "GSC", "HDO", "SOL", "RTO", "RTX", "NHO", "ETC"],
    }
    try:
        res = requests.post(url, data=data, headers=_CRAWL_HEADERS, timeout=10)
        html = res.text
    except Exception:
        return {}
 
    names = re.findall(r'var OS_NM\s*=\s*"([^"]*)"', html)
    hour24_flags = re.findall(r'var SEL24_YN\s*=\s*"([^"]*)"', html)
    return {
        name.strip(): ('가능' if flag == 'Y' else '불가')
        for name, flag in zip(names, hour24_flags)
    }
 
 
def _attach_distance(stations, user_lat, user_lng):
    has_location = user_lat is not None and user_lng is not None
    for s in stations:
        if has_location and s.get('_lat') is not None and s.get('_lng') is not None:
            s['거리km'] = round(_haversine_km(user_lat, user_lng, s['_lat'], s['_lng']), 1)
        else:
            s['거리km'] = None
    return stations
 
 
def get_stations(sido_nm, sigungu_nm, fuel_type='경유가격', user_lat=None, user_lng=None):
    """지역별 최저가 TOP20 + 상세정보(세차장/편의점) + 24시간영업(보조조회) 조합 리스트 반환.
    정렬은 하지 않고 거리(km)만 계산해서 붙여준다. 실제 정렬 순서는 사용자가 체크한
    필터(세차장/편의점/24시간)에 따라 app.py에서 결정한다."""
    if OIL_DEMO_MODE:
        return _attach_distance(list(_DEMO_STATIONS), user_lat, user_lng)
 
    prodcd = FUEL_PRODCD.get(fuel_type, 'D047')
    sigungu_cd = _find_sigungu_code(sido_nm, sigungu_nm)
    if not sigungu_cd:
        raise Exception(f"'{sido_nm} {sigungu_nm}'에 해당하는 지역코드를 areaCode.do에서 찾지 못했습니다.")
 
    top = _get("lowTop10.do", {"prodcd": prodcd, "area": sigungu_cd, "cnt": 20})
    items = top.get("RESULT", {}).get("OIL", [])
    if isinstance(items, dict):
        items = [items]
    if not items:
        raise Exception(
            f"lowTop10.do 응답에 데이터가 없습니다. "
            f"(area={sigungu_cd}, prodcd={prodcd}) 원본 응답: {top}"
        )
 
    hour24_map = _get_24hour_map(sido_nm, sigungu_nm)
 
    stations = []
    last_error = None
    for item in items:
        uni_id = item.get("UNI_ID")
        try:
            detail = _get_station_detail(uni_id)
            detail['24시간영업'] = hour24_map.get(detail['주유소명'], '정보없음')
            stations.append(detail)
        except Exception as e:
            last_error = str(e)
            continue
 
    if not stations and last_error:
        raise Exception(f"detailById.do 상세정보 조회에 모두 실패했습니다: {last_error}")
 
    return _attach_distance(stations, user_lat, user_lng)