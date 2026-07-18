from flask import Flask, render_template, request, jsonify, send_file
import csv
import io

import oil_api
import charger_api

app = Flask(__name__)

def _stylesheet():
    return 'style-bmw.css' if request.args.get('theme') == 'bmw' else 'style.css'

@app.route('/')
def index():
    sido_list = oil_api.get_sido_list()
    return render_template('index.html', sido_list=sido_list, stylesheet=_stylesheet())

@app.route('/api/sigungu')
def api_sigungu():
    sido = request.args.get('sido', '')
    try:
        sigungu_list = oil_api.get_sigungu_list(sido)
        return jsonify({'sigungu_list': sigungu_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/search')
def search():
    sido = request.args.get('sido', '')
    sigungu = request.args.get('sigungu', '')
    carwash_checked = request.args.get('carwash') == 'on'
    cvs_checked = request.args.get('cvs') == 'on'
    hour24_checked = request.args.get('hour24') == 'on'
    fuel_type = request.args.get('fuel_type', '경유가격')
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)

    if not sido or not sigungu:
        return render_template('results.html', stations=[], count=0, sido=sido, sigungu=sigungu,
                                fuel_type=fuel_type, stylesheet=_stylesheet())

    try:
        # [캐시 가속 적용 1] 공공 API 통신 결과만 15분 단위로 메모리 캐시에서 가져옵니다.
        raw_stations = oil_api.get_stations(sido, sigungu, fuel_type)
        
        # [캐시 가속 적용 2] 각 사용자의 실시간 GPS 기준으로 '거리 계산'만 즉석에서 수행합니다.
        stations = oil_api.attach_distance(raw_stations, user_lat=lat, user_lng=lng)
    except Exception as e:
        return render_template('results.html', stations=[], count=0, error=str(e), sido=sido, sigungu=sigungu,
                                fuel_type=fuel_type, stylesheet=_stylesheet())

    def price_value(s):
        v = s.get(fuel_type)
        return float('inf') if v in ('판매안함', None) else int(v)

    def sort_key(s):
        priority = []
        if hour24_checked:
            priority.append(0 if s['24시간영업'] == '가능' else 1)
        if carwash_checked:
            priority.append(0 if s['세차장'] == '가능' else 1)
        if cvs_checked:
            priority.append(0 if s['편의점'] == '있음' else 1)
        distance = s['거리km'] if s.get('거리km') is not None else float('inf')
        return (*priority, price_value(s), distance)

    stations = sorted(stations, key=sort_key)

    return render_template('results.html', stations=stations, count=len(stations), sido=sido, sigungu=sigungu,
                            fuel_type=fuel_type, stylesheet=_stylesheet())

@app.route('/charger/search')
def charger_search():
    sido = request.args.get('sido', '')
    sigungu = request.args.get('sigungu', '')
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    power_category = request.args.get('power_category', '일반')

    if not sido or not sigungu:
        return render_template('charger_results.html', stations=[], count=0, sido=sido, sigungu=sigungu, stylesheet=_stylesheet())

    try:
        stations = charger_api.get_stations(
            sido, sigungu, user_lat=lat, user_lng=lng, power_category=power_category
        )
    except Exception as e:
        return render_template('charger_results.html', stations=[], count=0, error=str(e), sido=sido, sigungu=sigungu, stylesheet=_stylesheet())

    return render_template('charger_results.html', stations=stations, count=len(stations), sido=sido, sigungu=sigungu, stylesheet=_stylesheet())

@app.route('/download')
def download():
    sido = request.args.get('sido', '')
    sigungu = request.args.get('sigungu', '')
    fuel_type = request.args.get('fuel_type', '경유가격')
    stations = oil_api.get_stations(sido, sigungu, fuel_type)

    if not stations:
        mem = io.BytesIO("검색 결과가 존재하지 않습니다.".encode('utf-8-sig'))
        return send_file(mem, as_attachment=True, download_name=f'{sido}_{sigungu}_공백_주유소.csv', mimetype='text/csv')

    clean_stations = [
        {k: v for k, v in s.items() if k != '브랜드로고' and not k.startswith('_')}
        for s in stations
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=clean_stations[0].keys())
    writer.writeheader()
    writer.writerows(clean_stations)

    mem = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    return send_file(mem, as_attachment=True,
                      download_name=f'{sido}_{sigungu}_주유소.csv', mimetype='text/csv')

@app.route('/charger/download')
def charger_download():
    sido = request.args.get('sido', '')
    sigungu = request.args.get('sigungu', '')
    stations = charger_api.get_stations(sido, sigungu)

    if not stations:
        mem = io.BytesIO("검색 결과가 존재하지 않습니다.".encode('utf-8-sig'))
        return send_file(mem, as_attachment=True, download_name=f'{sido}_{sigungu}_공백_전기차충전소.csv', mimetype='text/csv')

    clean_stations = [
        {k: (' / '.join(v) if k == '커넥터목록' else v)
         for k, v in s.items() if not k.startswith('_')}
        for s in stations
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=clean_stations[0].keys())
    writer.writeheader()
    writer.writerows(clean_stations)

    mem = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    return send_file(mem, as_attachment=True,
                      download_name=f'{sido}_{sigungu}_전기차충전소.csv', mimetype='text/csv')

if __name__ == '__main__':
    app.run(debug=True)