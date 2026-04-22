import sqlite3
import datetime
import os
import time
import platform
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.jinja_env.globals.update(enumerate=enumerate)

DB_PATH = r'C:\Users\Vani\Desktop\DOKTORI\volan_gtfs\kozlekedes_osszes.db'

def get_system_diagnostics():
    return {
        'db_exists': os.path.exists(DB_PATH),
        'db_size_mb': round(os.path.getsize(DB_PATH) / (1024 * 1024), 2) if os.path.exists(DB_PATH) else 0,
        'os_info': platform.system(),
        'python_version': platform.python_version(),
        'server_time': datetime.datetime.now().strftime("%H:%M:%S"),
        'last_query_time': 0,
        'sql_status': "IDLE"
    }

@app.route('/api/suggest')
def suggest():
    query = request.args.get('q', '')
    if len(query) < 2: return jsonify([])
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT stop_name FROM stops WHERE stop_name LIKE ? GROUP BY stop_name LIMIT 10", (f'%{query}%',)).fetchall()
        conn.close()
        return jsonify([{'name': r[0]} for r in rows])
    except:
        return jsonify([])

@app.route('/', methods=['GET', 'POST'])
def index():
    start_time = time.time()
    diag_data = get_system_diagnostics()
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    now = datetime.datetime.now()
    today_str = now.strftime('%Y%m%d')
    napok_nevei = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek", "Szombat", "Vasárnap"]
    
    res = {
        'menetrend': [], 'kovetkezo_ot': [], 'valasztott_nev': "", 'coords': [47.16, 19.5], 
        'diag': diag_data,
        'napi_stats': {nev: {'db': 0, 'elso': '--:--', 'utolso': '--:--'} for nev in napok_nevei},
        'cel_stats': {},
        'form_data': {'stop_name': request.form.get('stop_name', ''), 'direction': request.form.get('direction', '1')}
    }

    if request.method == 'POST' and res['form_data']['stop_name']:
        try:
            s_name = res['form_data']['stop_name']
            stops = conn.execute("SELECT stop_id, stop_lat, stop_lon FROM stops WHERE stop_name = ?", (s_name,)).fetchall()
            
            if stops:
                stop_ids = [s['stop_id'] for s in stops]
                res.update({'valasztott_nev': s_name, 'coords': [stops[0]['stop_lat'], stops[0]['stop_lon']]})
                
                query = f"""
                    SELECT st.departure_time, r.route_short_name, t.trip_headsign, GROUP_CONCAT(DISTINCT cd.date) as napok 
                    FROM stop_times st 
                    JOIN trips t ON st.trip_id = t.trip_id 
                    JOIN routes r ON t.route_id = r.route_id 
                    LEFT JOIN calendar_dates cd ON t.service_id = cd.service_id 
                    WHERE st.stop_id IN ({','.join(['?']*len(stop_ids))}) AND t.direction_id = ? 
                    GROUP BY t.trip_id, st.departure_time ORDER BY st.departure_time"""
                
                all_trips = conn.execute(query, stop_ids + [res['form_data']['direction']]).fetchall()

                for row in all_trips:
                    dep_raw = row['departure_time']
                    h, m, _ = map(int, dep_raw.split(':'))
                    dep_disp = f"{h%24:02d}:{m:02d}"
                    raw_dates = row['napok'].split(',') if row['napok'] else []
                    active_wd = {datetime.datetime.strptime(d, '%Y%m%d').weekday() for d in raw_dates if len(d)==8}
                    
                    for idx in active_wd:
                        n_nev = napok_nevei[idx]
                        res['napi_stats'][n_nev]['db'] += 1
                        if res['napi_stats'][n_nev]['elso'] == '--:--' or dep_disp < res['napi_stats'][n_nev]['elso']: res['napi_stats'][n_nev]['elso'] = dep_disp
                        if res['napi_stats'][n_nev]['utolso'] == '--:--' or dep_disp > res['napi_stats'][n_nev]['utolso']: res['napi_stats'][n_nev]['utolso'] = dep_disp
                        
                        cel = row['trip_headsign']
                        if cel not in res['cel_stats']: res['cel_stats'][cel] = {n: 0 for n in napok_nevei}
                        res['cel_stats'][cel][n_nev] += 1

                    rem = -1
                    if today_str in raw_dates and dep_raw >= now.strftime("%H:%M:%S"):
                        dep_dt = now.replace(hour=h%24, minute=m, second=0)
                        rem = round((dep_dt - now).total_seconds() / 60)
                    
                    res['menetrend'].append({'ido': dep_disp, 'vonal': row['route_short_name'], 'cel': row['trip_headsign'], 'hatralevo': rem, 'napok_pipa': [(i in active_wd) for i in range(7)]})
                
                res['kovetkezo_ot'] = [m for m in res['menetrend'] if m['hatralevo'] >= 0][:5]
                res['diag']['sql_status'] = f"OK: {len(all_trips)} járat találva"
            else:
                res['diag']['sql_status'] = "Nincs ilyen megálló"
        except Exception as e:
            res['diag']['sql_status'] = f"Hiba: {str(e)}"
    
    res['diag']['last_query_time'] = round((time.time() - start_time) * 1000, 2)
    conn.close()
    return render_template('index.html', **res)

if __name__ == '__main__':
    app.run(port=5001, debug=True)