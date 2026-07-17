from flask import Flask, render_template, request, jsonify, send_file
import csv
import io
 
import oil_api
import charger_api
 
app = Flask(__name__)
 
 
@app.route('/')
def index():
    sido_list = oil_api.get_sido_list()
    return render_template('index.html', sido_list=sido_list)
 
 
# 시/도 선택 시 시/군/구 목록 (탭 종류에 따라 소스만 다르고 지역명 체계는 동일)
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
                                fuel_type=fuel_type)
 
    try:
        stations = oil_api.get_stations(sido, sigungu, fuel_type, user_lat=lat, user_lng=lng)
    except Exception as e:
        return render_template('results.html', stations=[], count=0, error=str(e), sido=sido, sigungu=sigungu,
                                fuel_type=fuel_type)
 
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
                            fuel_type=fuel_type)
 
 
@app.route('/charger/search')
def charger_search():
    sido = request.args.get('sido', '')
    sigungu = request.args.get('sigungu', '')
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
 
    if not sido or not sigungu:
        return render_template('charger_results.html', stations=[], count=0, sido=sido, sigungu=sigungu)
 
    try:
        stations = charger_api.get_stations(sido, sigungu, user_lat=lat, user_lng=lng)
    except Exception as e:
        return render_template('charger_results.html', stations=[], count=0, error=str(e), sido=sido, sigungu=sigungu)
 
    return render_template('charger_results.html', stations=stations, count=len(stations), sido=sido, sigungu=sigungu)
 
 
@app.route('/download')
def download():
    sido = request.args.get('sido', '')
    sigungu = request.args.get('sigungu', '')
    fuel_type = request.args.get('fuel_type', '경유가격')
    stations = oil_api.get_stations(sido, sigungu, fuel_type)
 
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