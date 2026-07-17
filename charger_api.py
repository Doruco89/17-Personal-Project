# -*- coding: utf-8 -*-
"""
공공데이터포털 - 한국환경공단_전기자동차 충전소 정보 (EvCharger) 연동 모듈.
 
요청주소: http://apis.data.go.kr/B552584/EvCharger/getChargerInfo
※ 아래 응답 필드명(statNm, addr, lat, lng, chgerType, stat, busiNm, busiCall, useTime 등)은
  여러 공개 예제코드를 참고해 구성했다. 서비스키 발급 후 공공데이터포털에서 받는
  "OpenAPI 활용가이드" 문서로 필드명을 한 번 더 대조하는 걸 권장한다(버전별로 표기가
  살짝 다를 수 있음. 예: lng vs longi).
"""
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
 
_DEMO_STATIONS = [
    {
        '충전소명': '(데모) 강남역 공영주차장 충전소', '주소': '서울 강남구 테헤란로 152',
        '충전기타입': 'DC차데모/AC3상/DC콤보(50kW)', '충전기상태': '충전대기',
        '운영기관': '환경부', '연락처': '1600-0000', '이용가능시간': '24시간 이용가능',
    },
    {
        '충전소명': '(데모) 역삼 e편한세상 충전소', '주소': '서울 강남구 역삼로 210',
        '충전기타입': 'AC완속(7kW)', '충전기상태': '충전중',
        '운영기관': '한국전력공사', '연락처': '1588-0000', '이용가능시간': '09:00~18:00',
    },
]
 
 
def get_stations(sido_nm, sigungu_nm):
    if EV_DEMO_MODE:
        return _DEMO_STATIONS
 
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
 
    seen_stat_ids = set()
    stations = []
    for item in items:
        addr = item.get("addr", "") or ""
        if sigungu_nm and sigungu_nm not in addr:
            continue
        stat_id = item.get("statId")
        # 같은 충전소에 충전기가 여러 개면 한 번만 표시
        if stat_id in seen_stat_ids:
            continue
        seen_stat_ids.add(stat_id)
 
        stations.append({
            '충전소명': item.get('statNm'),
            '주소': addr,
            '충전기타입': item.get('chgerType'),
            '충전기상태': CHGER_STAT.get(str(item.get('stat')), '알 수 없음'),
            '운영기관': item.get('busiNm'),
            '연락처': item.get('busiCall'),
            '이용가능시간': item.get('useTime'),
        })
    return stations