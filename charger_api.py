# -*- coding: utf-8 -*-
"""
공공데이터포털 - 한국환경공단_전기자동차 충전소 정보 (EvCharger) 연동 모듈.
 
요청주소: http://apis.data.go.kr/B552584/EvCharger/getChargerInfo
※ 아래 응답 필드명(statNm, addr, lat, lng, chgerType, stat, busiNm, busiCall, useTime 등)은
  여러 공개 예제코드를 참고해 구성했다. 서비스키 발급 후 공공데이터포털에서 받는
  "OpenAPI 활용가이드" 문서로 필드명을 한 번 더 대조하는 걸 권장한다(버전별로 표기가
  살짝 다를 수 있음. 예: lng vs longi).
 
※ 이 API에는 충전 요금(가격) 필드가 없다. 요금은 운영기관마다 별도 체계라
   getChargerInfo 응답으로는 확인할 수 없다.
※ 이 API에는 반경(radius) 검색 파라미터가 없어서 시/도(zcode) 단위로만 조회할 수
   있다. "내 위치 기준 가까운 순"은 그 지역 안에서 클라이언트가 넘겨준 위경도로
   거리를 계산해 정렬하는 방식으로 구현한다.
"""
import math
import requests
 
from config import EV_API_KEY, EV_DEMO_MODE
 
BASE_URL = "http://apis.data.go.kr/B552584/EvCharger/getChargerInfo"
 
# 행정표준코드 기준 시/도 코드 (전국 공통, 안정적인 값)
EV_SIDO_CODE = {
    "서울특별시": "11", "부산광역시": "26", "대구광역시": "27", "인천광역시": "28",
    "광주광역시": "29", "대전광역시": "30", "울산광역시": "31", "세종특별자치시": "36",
    "경기도": "41", "강원특별자치도": "42", "충청북도": "43", "충청남도": "44",
    "전북특별자치도": "45", "전라남도": "46", "경상북도": "47", "경상남도": "48",
    "제주특별자치도": "50",
}
 
CHGER_STAT = {
    "1": "통신이상", "2": "충전대기", "3": "충전중", "4": "운영중지", "5": "점검중", "9": "상태미확인",
}
 
# 충전기 타입 코드 (공개 예제 기준 - 활용가이드로 재확인 권장)
CHGER_TYPE_NAME = {
    "01": "DC차데모", "02": "AC완속", "03": "DC차데모+AC3상",
    "04": "DC콤보", "05": "DC차데모+DC콤보", "06": "DC차데모+AC3상+DC콤보",
    "07": "AC3상", "08": "DC콤보(완속)", "09": "NACS(테슬라)",
}
# 완속(AC완속=02) 외에는 전부 급속/고속 충전으로 간주
SLOW_TYPE_CODES = {"02"}
 
_DEMO_STATIONS = [
    {
        '충전소명': '(데모) 강남역 공영주차장 충전소', '주소': '서울 강남구 테헤란로 152',
        '운영기관': '환경부', '연락처': '1600-0000', '이용가능시간': '24시간 이용가능',
        '전체칸수': 3, '충전중': 1, '충전대기': 2, '고속충전가능': True,
        '커넥터목록': ['DC차데모+AC3상+DC콤보(충전대기)', 'DC콤보(충전중)', 'AC완속(충전대기)'],
        '_lat': 37.4980, '_lng': 127.0276,
    },
    {
        '충전소명': '(데모) 역삼 e편한세상 충전소', '주소': '서울 강남구 역삼로 210',
        '운영기관': '한국전력공사', '연락처': '1588-0000', '이용가능시간': '09:00~18:00',
        '전체칸수': 1, '충전중': 1, '충전대기': 0, '고속충전가능': False,
        '커넥터목록': ['AC완속(충전중)'],
        '_lat': 37.5006, '_lng': 127.0365,
    },
]
 
 
def _haversine_km(lat1, lng1, lat2, lng2):
    """두 좌표 사이 직선거리(km), 하버사인 공식"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
 
 
def _sort_stations(stations, user_lat=None, user_lng=None):
    """충전 가능(빈 칸 있음)한 곳을 우선, 그 다음 내 위치와 가까운 순으로 정렬"""
    has_location = user_lat is not None and user_lng is not None
 
    for s in stations:
        if has_location and s.get('_lat') is not None and s.get('_lng') is not None:
            s['거리km'] = round(_haversine_km(user_lat, user_lng, s['_lat'], s['_lng']), 1)
        else:
            s['거리km'] = None
 
    def sort_key(s):
        fully_occupied = 1 if s['충전대기'] == 0 else 0  # 충전가능(0)이 먼저 오도록
        distance = s['거리km'] if s['거리km'] is not None else float('inf')
        return (fully_occupied, distance)
 
    return sorted(stations, key=sort_key)
 
 
def get_stations(sido_nm, sigungu_nm, user_lat=None, user_lng=None):
    if EV_DEMO_MODE:
        return _sort_stations(list(_DEMO_STATIONS), user_lat, user_lng)
 
    zcode = EV_SIDO_CODE.get(sido_nm, "")
    params = {
        "serviceKey": EV_API_KEY,
        "pageNo": "1",
        "numOfRows": "9999",
        "zcode": zcode,
        "dataType": "JSON",
    }
    res = requests.get(BASE_URL, params=params, timeout=15)
    res.raise_for_status()
    data = res.json()
 
    items = (
        data.get("items", {}).get("item", [])
        if isinstance(data.get("items"), dict)
        else data.get("items", [])
    )
    if isinstance(items, dict):
        items = [items]
 
    # 같은 충전소(statId)에 커넥터가 여러 개(chgerId 1,2,3...) 있을 수 있으므로
    # 충전소 단위로 커넥터 목록을 모아서 집계한다.
    stations_by_id = {}
    for item in items:
        addr = item.get("addr", "") or ""
        if sigungu_nm and sigungu_nm not in addr:
            continue
        stat_id = item.get("statId")
        if stat_id not in stations_by_id:
            lat = item.get('lat')
            lng = item.get('lng') or item.get('longi')
            stations_by_id[stat_id] = {
                '충전소명': item.get('statNm'),
                '주소': addr,
                '운영기관': item.get('busiNm'),
                '연락처': item.get('busiCall'),
                '이용가능시간': item.get('useTime'),
                '_lat': float(lat) if lat not in (None, '') else None,
                '_lng': float(lng) if lng not in (None, '') else None,
                '_connectors': [],
            }
        type_code = str(item.get('chgerType', ''))
        stat_code = str(item.get('stat', ''))
        stations_by_id[stat_id]['_connectors'].append({
            'type_code': type_code,
            'type_name': CHGER_TYPE_NAME.get(type_code, f'기타({type_code})'),
            'status': CHGER_STAT.get(stat_code, '상태미확인'),
        })
 
    stations = []
    for s in stations_by_id.values():
        connectors = s.pop('_connectors')
        s['전체칸수'] = len(connectors)
        s['충전중'] = sum(1 for c in connectors if c['status'] == '충전중')
        s['충전대기'] = sum(1 for c in connectors if c['status'] == '충전대기')
        s['고속충전가능'] = any(c['type_code'] not in SLOW_TYPE_CODES for c in connectors)
        s['커넥터목록'] = [f"{c['type_name']}({c['status']})" for c in connectors]
        stations.append(s)
 
    return _sort_stations(stations, user_lat, user_lng)