from flask import Flask, render_template, request
import sqlite3
import datetime
import os

app = Flask(__name__)

DB_PATH = r'C:\Users\Vani\Desktop\DOKTORI\volan_gtfs\kozlekedes_osszes.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        conn = get_db_connection()
    except Exception as e:
        return f"<h3>Hiba:</h3><p>{e}</p>"

    telepulesek = conn.execute('SELECT DISTINCT TRIM(SUBSTR(stop_name, 1, INSTR(stop_name, ",") - 1)) as nev FROM stops WHERE stop_name LIKE "%,%" ORDER BY nev').fetchall()
    nap_nevek = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek", "Szombat", "Vasárnap"]
    
    # Aktuális dátum és időszak korlátozása (pl. mai naptól + 30 nap)
    today = datetime.date.today().strftime('%Y%m%d')
    max_date = (datetime.date.today() + datetime.timedelta(days=30)).strftime('%Y%m%d')

    selected_day = request.form.get('filter_day', 'all')
    
    res = {
        'menetrend': [],
        'valasztott_nev': "",
        'telepules_lista': telepulesek, 
        'aktualis_megallok': [],
        'nap_statisztika': {nap: 0 for nap in nap_nevek},
        'cel_statisztika': {},
        'form_data': {
            'telepules': request.form.get('telepules_nev', ''),
            'stop_id': request.form.get('stop_id', ''),
            'direction': request.form.get('direction', '1'),
            'filter_day': selected_day
        }
    }

    if request.method == 'POST' and res['form_data']['telepules']:
        t_nev = res['form_data']['telepules']
        res['aktualis_megallok'] = conn.execute("SELECT DISTINCT stop_id, stop_name FROM stops WHERE stop_name LIKE ? ORDER BY stop_name", (f"{t_nev}%",)).fetchall()

        if res['form_data']['stop_id']:
            # Szigorúbb SQL: csak az érvényes, közlekedő napokat (exception_type=1) gyűjtjük
            query = """
                SELECT st.departure_time, r.route_short_name, t.trip_headsign, s.stop_name,
                       GROUP_CONCAT(cd.date) as naptar_napok
                FROM stop_times st
                JOIN stops s ON st.stop_id = s.stop_id
                JOIN trips t ON st.trip_id = t.trip_id
                JOIN routes r ON t.route_id = r.route_id
                LEFT JOIN calendar_dates cd ON t.service_id = cd.service_id
                WHERE s.stop_id = ? 
                  AND t.direction_id = ?
                  AND cd.exception_type = 1
                  AND cd.date >= ? 
                  AND cd.date <= ?
                GROUP BY t.trip_id, st.departure_time
                ORDER BY st.departure_time
            """
            rows = conn.execute(query, (res['form_data']['stop_id'], res['form_data']['direction'], today, max_date)).fetchall()
            
            for row in rows:
                nyers_cel = row['trip_headsign'] or "Ismeretlen"
                tisztitott_cel = nyers_cel.split('-')[-1].split('–')[-1].strip()
                
                # Érkező járatok kiszűrése
                if t_nev and t_nev.lower() in tisztitott_cel.lower():
                    continue

                # Dátumok feldolgozása napokká
                naptar_str = row['naptar_napok'] or ""
                naptar_napok = naptar_str.split(',') if naptar_str else []
                aktiv_napok_index = set()
                for d_str in naptar_napok:
                    try:
                        dt = datetime.datetime.strptime(d_str, '%Y%m%d')
                        aktiv_napok_index.add(dt.weekday())
                    except: continue
                
                if not aktiv_napok_index: continue # Ha nincs érvényes nap a periódusban, kihagyjuk

                # Statisztikák (globális képhez minden napot nézünk)
                nap_pipak = []
                if tisztitott_cel not in res['cel_statisztika']:
                    res['cel_statisztika'][tisztitott_cel] = {nap: 0 for nap in nap_nevek}

                for i in range(7):
                    van_jarat = i in aktiv_napok_index
                    nap_pipak.append(van_jarat)
                    if van_jarat:
                        res['nap_statisztika'][nap_nevek[i]] += 1
                        res['cel_statisztika'][tisztitott_cel][nap_nevek[i]] += 1

                # Megjelenítés szűrése a választott napra
                should_show = (selected_day == 'all') or (selected_day.isdigit() and int(selected_day) in aktiv_napok_index)

                if should_show:
                    res['menetrend'].append({
                        'ido': row['departure_time'][:5],
                        'vonal': row['route_short_name'],
                        'cel': nyers_cel,
                        'napok': nap_pipak
                    })

            if rows:
                res['valasztott_nev'] = rows[0]['stop_name']

    conn.close()
    return render_template('index.html', **res)

if __name__ == '__main__':
    app.run(port=5001, debug=True)