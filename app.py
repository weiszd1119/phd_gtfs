import sqlite3
import datetime
import requests
import json
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.jinja_env.globals.update(enumerate=enumerate)

DB_PATH = r'C:\Users\Vani\Desktop\DOKTORI\volan_gtfs\kozlekedes_osszes.db'
GOOGLE_MAPS_API_KEY = "API_KEY"

def get_google_delay_refined(lat, lon):
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    diag = {"delay_min": 0, "status": "Nincs élő adat", "raw_json": "{}"}
    try:
        payload = {
            "origin": {"location": {"latLng": {"latitude": float(lat), "longitude": float(lon)}}},
            "destination": {"location": {"latLng": {"latitude": float(lat)+0.005, "longitude": float(lon)+0.005}}},
            "travelMode": "DRIVE", "routingPreference": "TRAFFIC_AWARE",
        }
        headers = {'Content-Type': 'application/json', 'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
                   'X-Goog-FieldMask': 'routes.duration,routes.staticDuration'}
        response = requests.post(url, json=payload, headers=headers, timeout=3)
        if response.status_code == 200:
            data = response.json()
            diag["raw_json"] = json.dumps(data, indent=2, ensure_ascii=False)
            if 'routes' in data and len(data['routes']) > 0:
                route = data['routes'][0]
                diff = (int(route.get('duration','0s').replace('s','')) - int(route.get('staticDuration','0s').replace('s','')))
                diag["delay_min"] = round(((max(0, diff) * 1.3) / 60) + 1.5)
                diag["status"] = "Google OK"
    except: diag["status"] = "API Timeout"
    return diag

@app.route('/api/suggest')
def suggest():
    query = request.args.get('q', '')
    if len(query) < 2: return jsonify([])
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT stop_name FROM stops WHERE stop_name LIKE ? GROUP BY stop_name LIMIT 15", (f'%{query}%',)).fetchall()
    conn.close()
    return jsonify([{'name': r[0]} for r in rows])

@app.route('/', methods=['GET', 'POST'])
def index():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    now = datetime.datetime.now()
    today_str = now.strftime('%Y%m%d')
    
    napok_nevei = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek", "Szombat", "Vasárnap"]
    
    # ALAPHELYZET: Üres struktúra inicializálása, hogy a Jinja ne dobjon hibát
    res = {
        'menetrend': [], 'kovetkezo_ot': [], 'valasztott_nev': "", 'coords': [47.16, 19.5], 
        'diag': {'status': 'Várakozás...', 'raw_json': '{}', 'delay_min': 0},
        'napi_stats': {nev: {'db': 0, 'elso': '-', 'utolso': '-'} for nev in napok_nevei},
        'cel_stats': {},
        'form_data': {'stop_name': request.form.get('stop_name', ''), 'direction': request.form.get('direction', '1'), 'filter_day': request.form.get('filter_day', 'all')}
    }

    if request.method == 'POST' and res['form_data']['stop_name']:
        s_name = res['form_data']['stop_name']
        stops = conn.execute("SELECT stop_id, stop_lat, stop_lon FROM stops WHERE stop_name = ?", (s_name,)).fetchall()
        
        if stops:
            stop_ids = [s['stop_id'] for s in stops]
            res.update({'valasztott_nev': s_name, 'coords': [stops[0]['stop_lat'], stops[0]['stop_lon']]})
            res['diag'] = get_google_delay_refined(stops[0]['stop_lat'], stops[0]['stop_lon'])
            delay = res['diag'].get('delay_min', 0)
            
            placeholders = ','.join(['?'] * len(stop_ids))
            all_trips = conn.execute(f"""
                SELECT st.departure_time, r.route_short_name, t.trip_headsign, GROUP_CONCAT(cd.date) as napok
                FROM stop_times st 
                JOIN trips t ON st.trip_id = t.trip_id 
                JOIN routes r ON t.route_id = r.route_id
                LEFT JOIN calendar_dates cd ON t.service_id = cd.service_id
                WHERE st.stop_id IN ({placeholders}) AND (t.direction_id = ? OR t.direction_id IS NULL)
                GROUP BY t.trip_id, st.departure_time ORDER BY st.departure_time
            """, stop_ids + [res['form_data']['direction']]).fetchall()

            for row in all_trips:
                dep, cel = row['departure_time'][:5], row['trip_headsign']
                raw_dates = row['napok'].split(',') if row['napok'] else []
                active_wd_indices = {datetime.datetime.strptime(d, '%Y%m%d').weekday() for d in raw_dates if len(d) == 8}
                
                for idx in active_wd_indices:
                    n_nev = napok_nevei[idx]
                    res['napi_stats'][n_nev]['db'] += 1
                    if res['napi_stats'][n_nev]['elso'] == '-' or dep < res['napi_stats'][n_nev]['elso']: res['napi_stats'][n_nev]['elso'] = dep
                    if res['napi_stats'][n_nev]['utolso'] == '-' or dep > res['napi_stats'][n_nev]['utolso']: res['napi_stats'][n_nev]['utolso'] = dep
                    if cel not in res['cel_stats']: res['cel_stats'][cel] = {n: 0 for n in napok_nevei}
                    res['cel_stats'][cel][n_nev] += 1

                f_day = res['form_data']['filter_day']
                if f_day == 'all' or (f_day.isdigit() and int(f_day) in active_wd_indices):
                    rem = -1
                    if today_str in raw_dates and row['departure_time'] >= now.strftime("%H:%M:%S"):
                        dep_dt = datetime.datetime.strptime(row['departure_time'], "%H:%M:%S").replace(year=now.year, month=now.month, day=now.day)
                        rem = round(((dep_dt - now).total_seconds() / 60) + delay)
                    
                    res['menetrend'].append({
                        'ido': dep, 'vonal': row['route_short_name'], 'cel': cel, 
                        'hatralevo': rem, 'napok_pipa': [(i in active_wd_indices) for i in range(7)]
                    })
            
            res['kovetkezo_ot'] = [m for m in res['menetrend'] if m['hatralevo'] >= 0][:5]
    
    conn.close()
    return render_template('index.html', **res)

if __name__ == '__main__':
    app.run(port=5001, debug=True)
