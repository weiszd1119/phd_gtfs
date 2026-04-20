from flask import Flask, render_template, request, jsonify
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
    
    # 1. Településlista
    telepulesek = conn.execute('SELECT DISTINCT TRIM(SUBSTR(stop_name, 1, INSTR(stop_name, ",") - 1)) as nev FROM stops WHERE stop_name LIKE "%,%" ORDER BY nev').fetchall()
    
    # 2. Sidebar statisztika
    top_telepulesek = conn.execute('''
        SELECT TRIM(SUBSTR(stop_name, 1, INSTR(stop_name, ",") - 1)) as t_nev, COUNT(*) as j_szam 
        FROM stop_times JOIN stops ON stop_times.stop_id = stops.stop_id 
        GROUP BY t_nev HAVING t_nev != "" ORDER BY j_szam DESC LIMIT 5
    ''').fetchall()

    res = {
        'menetrend_hk': [], 'menetrend_hv': [],
        'coords': None, 'valasztott_nev': "",
        'telepules_lista': telepulesek, 'aktualis_megallok': [], 'top_telepulesek': top_telepulesek,
        'info': {'hetvegi_arany': 0, 'ora_eloszlas': [0]*24},
        'excel_stats': {}, # Az Excel kép alapján készült adatok
        't_stats': None,   # Települési statisztika
        'form_data': {'telepules': '', 'stop_id': '', 'direction': '0'}
    }

    if request.method == 'POST':
        t_nev = request.form.get('telepules_nev')
        stop_id = request.form.get('stop_id')
        direction = request.form.get('direction', '0')
        res['form_data'] = {'telepules': t_nev, 'stop_id': stop_id, 'direction': direction}

        if t_nev:
            res['aktualis_megallok'] = conn.execute("SELECT DISTINCT stop_id, stop_name FROM stops WHERE stop_name LIKE ? ORDER BY stop_name", (f"{t_nev}%",)).fetchall()
            # Települési statisztika visszatéve
            res['t_stats'] = conn.execute("""
                SELECT COUNT(DISTINCT s.stop_id) as m_db, COUNT(st.stop_id) as j_db, COUNT(DISTINCT t.route_id) as v_db
                FROM stops s JOIN stop_times st ON s.stop_id = st.stop_id JOIN trips t ON st.trip_id = t.trip_id 
                WHERE s.stop_name LIKE ?""", (f"{t_nev}%",)).fetchone()

        if stop_id:
            query = """
                SELECT st.departure_time, r.route_short_name, t.trip_headsign, s.stop_name, s.stop_lat, s.stop_lon,
                       GROUP_CONCAT(cd.date) as naptar_napok
                FROM stop_times st
                JOIN stops s ON st.stop_id = s.stop_id
                JOIN trips t ON st.trip_id = t.trip_id
                JOIN routes r ON t.route_id = r.route_id
                LEFT JOIN calendar_dates cd ON t.service_id = cd.service_id
                WHERE s.stop_id = ? AND t.direction_id = ?
                GROUP BY t.trip_id, st.departure_time
                ORDER BY st.departure_time
            """
            rows = conn.execute(query, (stop_id, direction)).fetchall()
            
            if rows:
                ora_eloszlas = [0] * 24
                hk_idok, hv_idok = [], []
                cel_bontas = {} # Elérhető települések statisztikája

                for row in rows:
                    napok_aktiv = {i: False for i in range(7)}
                    naptar_van = False
                    if row['naptar_napok']:
                        naptar_van = True
                        for d_str in row['naptar_napok'].split(','):
                            try:
                                dt = datetime.datetime.strptime(d_str, '%Y%m%d')
                                napok_aktiv[dt.weekday()] = True
                            except: continue
                    
                    cel = row['trip_headsign']
                    if cel not in cel_bontas: cel_bontas[cel] = {'hk': 0, 'hv': 0}

                    item = {'ido': row['departure_time'][:5], 'vonal': row['route_short_name'], 'cel': cel}

                    # Naptárkezelés (Hibatűrő: ha nincs naptár, hétköznapnak vesszük)
                    is_hk = not naptar_van or any(napok_aktiv[i] for i in range(5))
                    is_hv = naptar_van and (napok_aktiv[5] or napok_aktiv[6])

                    if is_hk:
                        res['menetrend_hk'].append(item)
                        hk_idok.append(item['ido'])
                        cel_bontas[cel]['hk'] += 1
                    if is_hv:
                        res['menetrend_hv'].append(item)
                        hv_idok.append(item['ido'])
                        cel_bontas[cel]['hv'] += 1
                    
                    try:
                        ora = int(row['departure_time'].split(':')[0])
                        if ora < 24: ora_eloszlas[ora] += 1
                    except: pass

                # Excel táblázat adatai
                res['excel_stats'] = {
                    'elso_hk': min(hk_idok) if hk_idok else "-",
                    'utolso_hk': max(hk_idok) if hk_idok else "-",
                    'elso_hv': min(hv_idok) if hv_idok else "-",
                    'utolso_hv': max(hv_idok) if hv_idok else "-",
                    'osszes_hk': len(hk_idok),
                    'osszes_hv': len(hv_idok),
                    'celok': cel_bontas
                }
                res['ora_eloszlas'] = ora_eloszlas
                res['valasztott_nev'] = rows[0]['stop_name']
                res['coords'] = [rows[0]['stop_lat'], rows[0]['stop_lon']]
                res['info']['hetvegi_arany'] = round((len(hv_idok)/len(rows)*100)) if len(rows) > 0 else 0

    conn.close()
    return render_template('index.html', **res)

if __name__ == '__main__':
    app.run(port=5001, debug=True)
