from flask import Flask, render_template, request
import sqlite3
import datetime

app = Flask(__name__)
DB_PATH = r'C:\Users\Vani\Desktop\DOKTORI\volan_gtfs\kozlekedes_osszes.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/', methods=['GET', 'POST'])
def index():
    conn = get_db_connection()
    most = datetime.datetime.now()
    
    # 1. Alapadatok a toplistákhoz (Mindig megjelennek)
    telepulesek = conn.execute('SELECT DISTINCT TRIM(SUBSTR(stop_name, 1, INSTR(stop_name, ",") - 1)) as nev FROM stops WHERE stop_name LIKE "%,%" ORDER BY nev').fetchall()
    legjobbak = conn.execute('SELECT TRIM(SUBSTR(s.stop_name, 1, INSTR(s.stop_name, "," ) - 1)) as nev, COUNT(*) as c FROM stop_times st JOIN stops s ON st.stop_id = s.stop_id GROUP BY nev ORDER BY c DESC LIMIT 15').fetchall()
    problemas = conn.execute('SELECT TRIM(SUBSTR(s.stop_name, 1, INSTR(s.stop_name, "," ) - 1)) as nev, COUNT(*) as c FROM stop_times st JOIN stops s ON st.stop_id = s.stop_id GROUP BY nev HAVING c BETWEEN 1 AND 20 ORDER BY c ASC LIMIT 15').fetchall()

    res = {
        'meta': {'time': most.strftime("%H:%M:%S"), 'date': most.strftime("%Y. %m. %d.")},
        'telepulesek': telepulesek, 'legjobbak': legjobbak, 'problemas': problemas,
        'selection': None, 'megallok': [], 'atszallasok': [], 'chart_data': [0]*24,
        'stats_0': {'elso': 'N/A', 'utolso': 'N/A', 'ossz': 0, 'dests': {}},
        'stats_1': {'elso': 'N/A', 'utolso': 'N/A', 'ossz': 0, 'dests': {}},
        'form': {'t': request.form.get('t', ''), 's': request.form.get('s', '')}
    }

    if res['form']['t']:
        res['megallok'] = conn.execute("SELECT DISTINCT stop_id, stop_name FROM stops WHERE stop_name LIKE ? ORDER BY stop_name", (f"{res['form']['t']}%",)).fetchall()

    if res['form']['s']:
        s_id = res['form']['s']
        s_info = conn.execute("SELECT stop_name, stop_lat, stop_lon FROM stops WHERE stop_id = ?", (s_id,)).fetchone()
        
        if s_info:
            res['selection'] = {'lat': s_info['stop_lat'], 'lon': s_info['stop_lon'], 'name': s_info['stop_name']}
            
            # Menetrendi adatok lekérése (Egyszerűsített, naptárfüggetlen lekérdezés)
            rows = conn.execute("""
                SELECT st.departure_time, t.direction_id, t.trip_headsign, r.route_short_name
                FROM stop_times st
                JOIN trips t ON st.trip_id = t.trip_id
                JOIN routes r ON t.route_id = r.route_id
                WHERE st.stop_id = ?
            """, (s_id,)).fetchall()

            chart_data = [0]*24
            atsz_vonalak = set()

            for r in rows:
                time = r['departure_time'][:5]
                hour = int(time.split(':')[0])
                if hour < 24: chart_data[hour] += 1
                atsz_vonalak.add(r['route_short_name'])

                # Statisztikák irányonként (0 vagy 1)
                st = res['stats_0'] if r['direction_id'] == 0 else res['stats_1']
                st['ossz'] += 1
                if st['elso'] == 'N/A' or time < st['elso']: st['elso'] = time
                if st['utolso'] == 'N/A' or time > st['utolso']: st['utolso'] = time
                
                dest = r['trip_headsign']
                st['dests'][dest] = st['dests'].get(dest, 0) + 1

            res['chart_data'] = chart_data
            res['atszallasok'] = sorted(list(atsz_vonalak))

    conn.close()
    return render_template('index.html', **res)

if __name__ == '__main__':
    app.run(port=5001, debug=True)
