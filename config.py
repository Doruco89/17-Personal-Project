import os
from dotenv import load_dotenv

# 프로젝트 루트의 .env 파일을 읽어서 os.environ에 채워 넣는다.
# .env는 git에 올리지 않는 파일이라 키가 코드/저장소에 노출되지 않는다.
load_dotenv()

# 오피넷(한국석유공사) 오픈API 인증키
# 발급: https://www.opinet.co.kr/user/custapi/openApiNew.do
OPINET_API_KEY = os.environ.get("IwN3xscffjGk8uvjZWPCtyMFd7SMpHuizCVkPEE02Q", "")

# 공공데이터포털 - 한국환경공단_전기자동차 충전소 정보 서비스키
# 발급: https://www.data.go.kr/data/15076352/openapi.do (활용신청 -> 자동승인)
EV_API_KEY = os.environ.get("8cb337c7869cd0fca833b6b0e7d0a5b6c42ed84dddd05a28eee2718bd4d07fb8", "")

# 키가 없으면 데모(샘플) 데이터로 동작
OIL_DEMO_MODE = not bool(OPINET_API_KEY)
EV_DEMO_MODE = not bool(EV_API_KEY)