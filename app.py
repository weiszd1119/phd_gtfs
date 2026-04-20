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
    conn = get_db_connection()
    most = datetime.datetime.now()
    
    # Alapadatok
    telepulesek = conn.execute('SELECT DISTINCT TRIM(SUBSTR(stop_name, 1, INSTR(stop_name, ",") - 1)) as nev FROM stops WHERE stop_name LIKE "%,%" ORDER BY nev').fetchall()
    
    # Statisztikák
    legjobbak = conn.execute('SELECT TRIM(SUBSTR(s.stop_name, 1, INSTR(s.stop_name, ",") - 1)) as nev, COUNT(*) as c FROM stop_times st JOIN stops s ON st.stop_id = s.stop_id GROUP BY nev ORDER BY c DESC LIMIT 15').fetchall()
    problemas = conn.execute('SELECT TRIM(SUBSTR(s.stop_name, 1, INSTR(s.stop_name, ",") - 1)) as nev, COUNT(*) as c FROM stop_times st JOIN stops s ON st.stop_id = s.stop_id GROUP BY nev HAVING c BETWEEN 1 AND 10 ORDER BY c ASC LIMIT 15').fetchall()

    res = {
        'meta': {'time': most.strftime("%H:%M:%S"), 'date': most.strftime("%Y. %m. %d.")},
        'telepulesek': telepulesek, 'legjobbak': legjobbak, 'problemas': problemas,
        'menetrend': [], 'chart_data': [0]*24, 'selection': None,
        'form': {'t': request.form.get('t', ''), 's': request.form.get('s', ''), 'd': request.form.get('d', '0')},
        'megallok': []
    }

    if res['form']['t']:
        res['megallok'] = conn.execute("SELECT DISTINCT stop_id, stop_name FROM stops WHERE stop_name LIKE ? ORDER BY stop_name", (f"{res['form']['t']}%",)).fetchall()

    if res['form']['s']:
        query = """SELECT st.departure_time, r.route_short_name, t.trip_headsign, s.stop_lat, s.stop_lon, s.stop_name
                   FROM stop_times st JOIN stops s ON st.stop_id = s.stop_id JOIN trips t ON st.trip_id = t.trip_id JOIN routes r ON t.route_id = r.route_id
                   WHERE s.stop_id = ? AND t.direction_id = ? ORDER BY st.departure_time"""
        rows = conn.execute(query, (res['form']['s'], res['form']['d'])).fetchall()
        if rows:
            dist = [0]*24
            for r in rows:
                h = int(r['departure_time'].split(':')[0])
                if h < 24: dist[h] += 1
            res['menetrend'], res['chart_data'] = rows, dist
            res['selection'] = {'lat': rows[0]['stop_lat'], 'lon': rows[0]['stop_lon'], 'name': rows[0]['stop_name']}

    conn.close()
    return render_template('index.html', **res)

if __name__ == '__main__':
    app.run(port=5001, debug=True)
