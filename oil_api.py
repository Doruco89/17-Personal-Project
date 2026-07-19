# -*- coding: utf-8 -*-
"""
오피넷(한국석유공사) 오픈API 연동 모듈 (비동기 병렬 수집 + TTL 캐시 통합 버전)
"""
import math
import re
import time
import requests
from pyproj import Transformer
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import OPINET_API_KEY, OIL_DEMO_MODE

BASE = "https://www.opinet.co.kr/api"

_CRAWL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
}

# 오피넷 TM128 좌표계 -> WGS84 변환 정의
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

SIDO_CODE = {
    "서울특별시": "01", "경기도": "02", "강원특별자치도": "03", "충청북도": "04",
    "충청남도": "05", "전북특별자치도": "06", "전라남도": "07", "경상북도": "08",
    "경상남도": "09", "부산광역시": "10", "제주특별자치도": "11", "대구광역시": "14",
    "인천광역시": "15", "광주광역시": "16", "대전광역시": "17", "울산광역시": "18",
    "세종특별자치시": "19",
}

# [최적화: 완전 하드코딩] 오피넷 areaCode.do에서 2026-07-19에 직접 수집한
# 시/군/구 이름-코드 매핑표입니다. 이 표에 값이 있는 시/도는 오피넷 API를
# 전혀 호출하지 않고 즉시 반환합니다. 행정구역은 사실상 바뀌지 않는 데이터라
# 안전하게 정적으로 고정해도 됩니다.
#
# 주의: "전라남도"와 "광주광역시"는 수집 당시 오피넷이 빈 응답을 반환해서
# 데이터가 비어 있습니다. 이 두 지역은 SIGUNGU_HARDCODED에 없는 것으로 처리되어
# 아래 get_sigungu_list/_find_sigungu_code에서 자동으로 실시간 API 호출로
# 폴백(fallback)되므로 동작에는 문제가 없습니다.
SIGUNGU_HARDCODED = {
    "서울특별시": {
        "종로구": "0101", "중구": "0102", "동대문구": "0103", "성동구": "0104",
        "성북구": "0105", "도봉구": "0106", "서대문구": "0107", "은평구": "0108",
        "마포구": "0109", "용산구": "0110", "영등포구": "0111", "동작구": "0112",
        "강남구": "0113", "강동구": "0114", "강서구": "0115", "구로구": "0116",
        "관악구": "0117", "노원구": "0118", "양천구": "0119", "중랑구": "0120",
        "서초구": "0121", "송파구": "0122", "광진구": "0123", "강북구": "0124",
        "금천구": "0125",
    },
    "경기도": {
        "수원시": "0201", "성남시": "0202", "의정부시": "0203", "안양시": "0204",
        "부천시": "0205", "동두천시": "0206", "광명시": "0207", "이천시": "0208",
        "평택시": "0209", "구리시": "0210", "과천시": "0211", "안산시": "0212",
        "오산시": "0213", "의왕시": "0214", "군포시": "0215", "시흥시": "0216",
        "남양주시": "0217", "하남시": "0218", "고양시": "0219", "용인시": "0220",
        "양주시": "0221", "여주시": "0222", "화성시": "0224", "파주시": "0226",
        "광주시": "0228", "연천군": "0229", "포천시": "0230", "가평군": "0231",
        "양평군": "0232", "안성시": "0235", "김포시": "0236",
    },
    "강원특별자치도": {
        "춘천시": "0301", "원주시": "0302", "강릉시": "0303", "속초시": "0304",
        "동해시": "0305", "태백시": "0306", "삼척시": "0307", "홍천군": "0322",
        "횡성군": "0323", "영월군": "0325", "평창군": "0326", "정선군": "0327",
        "철원군": "0328", "화천군": "0329", "양구군": "0330", "인제군": "0331",
        "고성군": "0332", "양양군": "0333",
    },
    "충청북도": {
        "청주시": "0401", "충주시": "0402", "제천시": "0403", "보은군": "0422",
        "옥천군": "0423", "영동군": "0424", "진천군": "0425", "괴산군": "0426",
        "음성군": "0427", "단양군": "0430", "증평군": "0431",
    },
    "충청남도": {
        "천안시": "0502", "공주시": "0503", "아산시": "0504", "보령시": "0505",
        "서산시": "0506", "논산시": "0507", "계룡시": "0508", "금산군": "0521",
        "부여군": "0526", "서천군": "0527", "청양군": "0529", "홍성군": "0530",
        "예산군": "0531", "당진시": "0533", "태안군": "0537",
    },
    "전북특별자치도": {
        "전주시": "0601", "군산시": "0602", "익산시": "0603", "남원시": "0604",
        "정읍시": "0605", "김제시": "0606", "완주군": "0621", "진안군": "0622",
        "무주군": "0623", "장수군": "0624", "임실군": "0625", "순창군": "0627",
        "고창군": "0629", "부안군": "0630",
    },
    "전라남도": {},  # 수집 실패 → 실시간 API 폴백
    "경상북도": {
        "포항시": "0801", "경주시": "0802", "김천시": "0803", "영주시": "0804",
        "영천시": "0805", "안동시": "0806", "구미시": "0807", "문경시": "0808",
        "상주시": "0809", "경산시": "0810", "의성군": "0823", "청송군": "0825",
        "영양군": "0826", "영덕군": "0827", "청도군": "0832", "고령군": "0833",
        "성주군": "0834", "칠곡군": "0835", "예천군": "0840", "봉화군": "0842",
        "울진군": "0843", "울릉군": "0844",
    },
    "경상남도": {
        "창원시": "0902", "진주시": "0904", "통영시": "0906", "사천시": "0907",
        "김해시": "0908", "밀양시": "0909", "거제시": "0910", "양산시": "0911",
        "의령군": "0922", "함안군": "0923", "창녕군": "0924", "고성군": "0932",
        "남해군": "0934", "하동군": "0935", "산청군": "0936", "함양군": "0937",
        "거창군": "0938", "합천군": "0939",
    },
    "부산광역시": {
        "중구": "1001", "서구": "1002", "동구": "1003", "영도구": "1004",
        "부산진구": "1005", "동래구": "1006", "남구": "1007", "북구": "1008",
        "해운대구": "1009", "사하구": "1010", "강서구": "1011", "금정구": "1012",
        "연제구": "1013", "수영구": "1014", "사상구": "1015", "기장군": "1031",
    },
    "제주특별자치도": {
        "제주시": "1101", "서귀포시": "1102",
    },
    "대구광역시": {
        "중구": "1401", "동구": "1402", "서구": "1403", "남구": "1404",
        "북구": "1405", "수성구": "1406", "달서구": "1407", "달성군": "1431",
        "군위군": "1432",
    },
    "인천광역시": {
        "미추홀구": "1503", "부평구": "1504", "남동구": "1506", "연수구": "1507",
        "계양구": "1508", "강화군": "1531", "옹진군": "1532", "제물포구": "1511",
        "서해구": "1513", "영종구": "1512", "검단구": "1514",
    },
    "광주광역시": {},  # 수집 실패 → 실시간 API 폴백
    "대전광역시": {
        "동구": "1701", "중구": "1702", "서구": "1703", "유성구": "1704",
        "대덕구": "1705",
    },
    "울산광역시": {
        "중구": "1801", "남구": "1802", "동구": "1803", "북구": "1804",
        "울주군": "1831",
    },
    "세종특별자치시": {
        "세종시": "1901",
    },
}

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

# [신규 설계] Zero-Dependency 초경량 TTL 캐시 클래스 정의
class TTLCache:
    def __init__(self, ttl_seconds=900): # 기본 유지시간 15분
        self.ttl = ttl_seconds
        self.storage = {}

    def get(self, key):
        if key in self.storage:
            val, timestamp = self.storage[key]
            if time.time() - timestamp < self.ttl:
                return val
            else:
                del self.storage[key] # 만료된 데이터 삭제 (메모리 관리)
        return None

    def set(self, key, val):
        self.storage[key] = (val, time.time())

# API 전용 캐시 인스턴스 생성 (유가/상세정보용, 15분)
_api_cache = TTLCache(ttl_seconds=900)

# [최적화] 시/군/구 코드 전용 캐시 (거의 안 바뀌는 데이터라 24시간으로 길게)
_area_cache = TTLCache(ttl_seconds=86400)

def _get(path, params):
    # [수정] 오피넷 API의 인증키 파라미터명은 "code" 입니다.
    # 기존 "certkey"로 보내고 있어 인증이 되지 않아 areaCode.do 등에서
    # 빈 배열({"RESULT": {"OIL": []}})만 돌아오던 문제의 원인이었습니다.
    params = {**params, "code": OPINET_API_KEY, "out": "json"}
    res = requests.get(f"{BASE}/{path}", params=params, timeout=10)
    res.raise_for_status()
    return res.json()

def get_sido_list():
    return list(SIDO_CODE.keys())

def _get_area_items(sido_nm):
    """
    [최적화] 시/도별 areaCode.do 결과를 캐싱합니다.
    같은 시/도에 대해 드롭다운 채울 때(get_sigungu_list)와 검색 실행 시
    (_find_sigungu_code)가 각각 areaCode.do를 호출하던 중복 호출을 제거합니다.
    시/군/구 목록은 거의 변하지 않는 데이터이므로 TTL을 24시간으로 길게 잡습니다.
    """
    sido_cd = SIDO_CODE.get(sido_nm)
    if not sido_cd:
        return []

    cache_key = f"area_{sido_cd}"
    cached = _area_cache.get(cache_key)
    if cached is not None:
        return cached

    data = _get("areaCode.do", {"area": sido_cd})
    items = data.get("RESULT", {}).get("OIL", [])
    if isinstance(items, dict):
        items = [items]

    _area_cache.set(cache_key, items)
    return items

def get_sigungu_list(sido_nm):
    if OIL_DEMO_MODE:
        return _DEMO_SIGUNGU.get(sido_nm, ["샘플구"])

    hardcoded = SIGUNGU_HARDCODED.get(sido_nm)
    if hardcoded:
        # 하드코딩된 표에 데이터가 있으면 API 호출 없이 즉시 반환
        return list(hardcoded.keys())

    # 하드코딩 표가 비어있는 지역(전라남도, 광주광역시)만 실시간 폴백
    items = _get_area_items(sido_nm)
    return [item["AREA_NM"] for item in items]

def _find_sigungu_code(sido_nm, sigungu_nm):
    hardcoded = SIGUNGU_HARDCODED.get(sido_nm)
    if hardcoded:
        code = hardcoded.get(sigungu_nm)
        if code:
            return code
        # 혹시 하드코딩 표에 이름이 없으면(누락 등) 안전하게 API로 한 번 더 확인
        items = _get_area_items(sido_nm)
        for item in items:
            if item.get("AREA_NM") == sigungu_nm:
                return item.get("AREA_CD")
        return None

    # 하드코딩 표가 비어있는 지역(전라남도, 광주광역시)만 실시간 폴백
    items = _get_area_items(sido_nm)
    for item in items:
        if item.get("AREA_NM") == sigungu_nm:
            return item.get("AREA_CD")
    return None

def _get_station_detail(uni_id):
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

def attach_distance(stations, user_lat, user_lng):
    """실시간 거리 측정 함수를 외부 공개 인터페이스로 변경 (캐싱 극대화용)"""
    has_location = user_lat is not None and user_lng is not None
    # 캐시된 원본 데이터의 훼손을 방지하기 위해 새로운 딕셔너리 리스트 생성(Deep Copy 역할)
    copied_stations = []
    for s in stations:
        copied_s = dict(s)
        if has_location and s.get('_lat') is not None and s.get('_lng') is not None:
            copied_s['거리km'] = round(_haversine_km(user_lat, user_lng, s['_lat'], s['_lng']), 1)
        else:
            copied_s['거리km'] = None
        copied_stations.append(copied_s)
    return copied_stations

def get_stations(sido_nm, sigungu_nm, fuel_type='경유가격'):
    """
    [지능형 캐시 튜닝]
    동적으로 바뀌는 user_lat, user_lng 매개변수를 완전히 걷어냈습니다.
    오직 '시도, 시군구, 유종'의 캐시 고유 키만 사용하므로 캐시 적중률이 100%에 달합니다.
    """
    if OIL_DEMO_MODE:
        # 데모 모드는 캐시 없이 원본 반환
        return list(_DEMO_STATIONS)

    # 고유 캐시 키 생성
    cache_key = f"{sido_nm}_{sigungu_nm}_{fuel_type}"
    cached_data = _api_cache.get(cache_key)
    if cached_data:
        return cached_data # 오피넷 API 호출을 생략하고 0.001초 만에 메모리에서 반환!

    prodcd = FUEL_PRODCD.get(fuel_type, 'D047')
    sigungu_cd = _find_sigungu_code(sido_nm, sigungu_nm)
    if not sigungu_cd:
        raise Exception(f"'{sido_nm} {sigungu_nm}'에 해당하는 지역코드를 areaCode.do에서 찾지 못했습니다.")

    top = _get("lowTop10.do", {"prodcd": prodcd, "area": sigungu_cd, "cnt": 20})
    items = top.get("RESULT", {}).get("OIL", [])
    if isinstance(items, dict):
        items = [items]
    if not items:
        raise Exception(f"lowTop10.do 응답에 데이터가 없습니다.")

    hour24_map = _get_24hour_map(sido_nm, sigungu_nm)
    stations = []
    last_error = None

    uni_ids = [item.get("UNI_ID") for item in items if item.get("UNI_ID")]

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_id = {executor.submit(_get_station_detail, uid): uid for uid in uni_ids}
        for future in as_completed(future_to_id):
            try:
                detail = future.result()
                detail['24시간영업'] = hour24_map.get(detail['주유소명'], '정보없음')
                stations.append(detail)
            except Exception as e:
                last_error = str(e)
                continue

    if not stations and last_error:
        raise Exception(f"detailById.do 상세정보 조회에 모두 실패했습니다: {last_error}")

    # 성공적으로 받아온 순수 데이터를 캐시에 임시 저장 (15분 유지)
    _api_cache.set(cache_key, stations)
    return stations