from flask import Flask, render_template, request, jsonify, send_file
import scrapper
import csv
import io

app = Flask(__name__)

@app.route('/')
def index():
    sido_list = scrapper.get_sido_list()
    return render_template('index.html', sido_list=sido_list)

# 시/도 선택 시 시/군/구 목록 실시간으로 가져오는 API (JS에서 fetch)
@app.route('/api/sigungu')
def api_sigungu():
    sido = request.args.get('sido', '')
    try:
        sigungu_list = scrapper.get_sigungu_list(sido)
        return jsonify({'sigungu_list': sigungu_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/search')
def search():
    sido = request.args.get('sido', '')
    sigungu = request.args.get('sigungu', '')

    if not sido or not sigungu:
        return render_template('results.html', stations=[], count=0, sido=sido, sigungu=sigungu)

    try:
        stations = scrapper.get_stations(sido, sigungu)
    except Exception as e:
        return render_template('results.html', stations=[], count=0, error=str(e), sido=sido, sigungu=sigungu)

    # 필터 옵션 (체크박스)
    if request.args.get('carwash') == 'on':
        stations = [s for s in stations if s['세차장'] == '가능']
    if request.args.get('hour24') == 'on':
        stations = [s for s in stations if s['24시간영업'] == '가능']
    if request.args.get('cvs') == 'on':
        stations = [s for s in stations if s['편의점'] == '있음']

    return render_template('results.html', stations=stations, count=len(stations), sido=sido, sigungu=sigungu)

@app.route('/download')
def download():
    sido = request.args.get('sido', '')
    sigungu = request.args.get('sigungu', '')
    stations = scrapper.get_stations(sido, sigungu)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=stations[0].keys())
    writer.writeheader()
    writer.writerows(stations)

    mem = io.BytesIO(output.getvalue().encode('utf-8-sig'))
    return send_file(mem, as_attachment=True,
                      download_name=f'{sido}_{sigungu}_주유소.csv', mimetype='text/csv')

if __name__ == '__main__':
    app.run(debug=True)