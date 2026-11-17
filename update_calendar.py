1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68
69
70
71
72
73
74
75
76
77
78
79
80
81
82
83
84
85
86
87
88
89
90
91
92
93
94
95
96
97
98
99
100
101
102
103
104
105
106
107
108
109
110
111
112
113
114
115
116
117
118
119
120
121
122
123
124
125
126
127
128
129
130
131
132
133
134
135
136
137
138
139
140
141
142
143
144
145
146
147
148
149
150
151
152
153
154
155
156
157
158
159
160
161
162
163
164
165
166
167
168
169
170
171
172
173
174
175
176
177
178
179
180
"""Yeguada Agrado: diagnóstico de participantes de Todoturf (solo lectura).
No modifica calendar.json ni publica información.
"""
import re
import sys
import time
import unicodedata
from datetime import date, datetime
from urllib.parse import urlencode, urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE = 'https://www.todoturf.net/'
STALLIONS = ('BOW CREEK', 'NOOZHOH CANARIAS', 'RODABALLO', 'NARANCO')
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; AgradoCalendar/0.4; low-frequency checks)'})


def norm(value):
    value = unicodedata.normalize('NFKD', str(value).upper())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+', ' ', value).strip()


def clean_horse(value, product=False):
    value = re.sub(r'\s+', ' ', str(value).replace('\xa0', ' ')).strip()
    value = re.sub(r'\s*\((?:FR|GB|IRE|USA|ITY|GER|SPA|ESP|POR)\)\s*$', '', value, flags=re.I)
    value = re.sub(r'\s*,\s*20\d\d\s*$', '', value)
    if product:
        # Sufijos de sexo/capa en la lista de productos; no aplicarlos a los participantes.
        value = re.sub(r'\s+(?:CAS|YEG|POT)\.?\s+[A-Z]\.?$', '', value, flags=re.I)
        value = re.sub(r'(?:\s+[A-Z]\.?)' + r'{1,4}\s*$', '', value, flags=re.I)
        value = re.sub(r'\s+(?:CAS|YEG|POT)\.?$', '', value, flags=re.I)
    return value.strip()


def self_test():
    cases = {'ALBATROS C C': 'ALBATROS', 'ADRY Y C': 'ADRY',
             'ANOTHER ROSE CAS C': 'ANOTHER ROSE', 'BOW CREEK': 'BOW CREEK',
             'EMPEL C C': 'EMPEL', 'RONCAL C C': 'RONCAL'}
    for raw, expected in cases.items():
        actual = clean_horse(raw, product=True)
        if actual != expected:
            raise RuntimeError(f'AUTOPRUEBA FALLIDA: {raw!r} => {actual!r}, esperado {expected!r}')
    print('AUTOPRUEBA | Limpieza de nombres: OK', flush=True)


def get(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc not in ('www.todoturf.net', 'todoturf.net'):
        raise ValueError('Dominio no permitido: ' + url)
    response = SESSION.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    time.sleep(0.4)
    return BeautifulSoup(response.text, 'html.parser')


def links(soup, filename):
    return list(dict.fromkeys(urljoin(BASE, a['href']) for a in soup.select('a[href]') if filename in a['href']))


def horse_names(sire):
    lookup = 'BOW CREEK2' if sire == 'BOW CREEK' else sire
    url = BASE + 'productossemental2.php?' + urlencode({'nombresemental': lookup})
    soup = get(url)
    tables = [t for t in soup.select('table') if 'MADRE' in norm(t.get_text(' ', strip=True)) and 'GANANCIAS' in norm(t.get_text(' ', strip=True))]
    if not tables:
        raise RuntimeError('No se encuentra la tabla de productos: ' + sire)
    names = set()
    for row in tables[0].select('tr'):
        cells = row.find_all('td', recursive=False) or row.find_all('td')
        if cells:
            link = cells[0].find('a')
            if link:
                name = norm(clean_horse(link.get_text(' ', strip=True), product=True))
                if name:
                    names.add(name)
    print(f'PRODUCTOS | {sire}: {len(names)} | ejemplos: {sorted(names)[:10]}', flush=True)
    print(f'CONTROL | {sire} | EMPEL={"EMPEL" in names} | RONCAL={"RONCAL" in names}', flush=True)
    if sire in ('BOW CREEK', 'NOOZHOH CANARIAS') and not names:
        raise RuntimeError('Lista de productos vacía: ' + sire)
    return names


def date_from_url(url):
    raw = parse_qs(urlparse(url).query).get('fecha', [''])[0].strip().split(' ')[0]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def race_rows(url):
    soup = get(url)
    race_date = date_from_url(url)
    if race_date and race_date < date.today().isoformat():
        return []
    if not race_date:
        print(f'AVISO | Fecha no reconocida, se revisa igualmente: {url}', flush=True)
    tables = [t for t in soup.select('table') if 'CABALLO' in norm(t.get_text(' ', strip=True)) and 'JINETE' in norm(t.get_text(' ', strip=True))]
    if not tables:
        print(f'AVISO | Sin tabla de participantes: {url}', flush=True)
        return []
    title = next((h.get_text(' ', strip=True) for h in soup.find_all(['h1', 'h2', 'h3']) if 'PREMIO' in norm(h.get_text(' ', strip=True))), 'Premio por verificar')
    entries = []
    for row in tables[0].select('tr'):
        cells = row.find_all('td', recursive=False) or row.find_all('td')
        if len(cells) < 4:
            continue
        link = cells[1].find('a')
        if not link:
            continue
        horse = clean_horse(link.get_text(' ', strip=True))
        if not horse:
            continue
        entries.append({'date': race_date or 'SIN FECHA', 'horse': horse,
                        'number': cells[0].get_text(' ', strip=True),
                        'jockey': cells[3].get_text(' ', strip=True),
                        'prize': title, 'raceUrl': url})
    return entries


def main():
    print('=== YEGUADA AGRADO | DIAGNÓSTICO SOLO LECTURA ===', flush=True)
    self_test()
    sires = {sire: horse_names(sire) for sire in STALLIONS}
    program = get(BASE + 'programa.php')
    meetings = links(program, 'programa2.php')
    if not meetings:
        raise RuntimeError('No se encontraron jornadas en programa.php')
    races = []
    for meeting in meetings:
        races.extend(links(get(meeting), 'programa3.php'))
    races = list(dict.fromkeys(races))
    if not races:
        raise RuntimeError('No se encontraron carreras')
    read_count = match_count = candidates = pending = unknown_dates = 0
    for url in races:
        entries = race_rows(url)
        read_count += len(entries)
        for entry in entries:
            horse_key = norm(entry['horse'])
            for sire, names in sires.items():
                if horse_key not in names:
                    continue
                match_count += 1
                if entry['date'] == 'SIN FECHA':
                    unknown_dates += 1
                number = entry['number']
                jockey = entry['jockey']
                has_details = number.isdigit() and int(number) > 0 and bool(jockey)
                if has_details:
                    candidates += 1
                else:
                    pending += 1
                print(f'COINCIDENCIA | {entry["date"]} | {entry["horse"]} | {sire} | dorsal={number!r} | jinete={jockey!r} | {entry["raceUrl"]}', flush=True)
                print('ESTADO | ' + ('Con dorsal y jinete; verificar declaración oficial' if has_details else 'Pendiente de verificar'), flush=True)
                break
    print('\n========== RESUMEN ==========', flush=True)
    print(f'Jornadas: {len(meetings)}', flush=True)
    print(f'Carreras: {len(races)}', flush=True)
    print(f'Caballos leídos: {read_count}', flush=True)
    print(f'Coincidencias con sementales: {match_count}', flush=True)
    print(f'Candidatos con dorsal y jinete: {candidates}', flush=True)
    print(f'Pendientes de verificación: {pending}', flush=True)
    print(f'Coincidencias sin fecha reconocida: {unknown_dates}', flush=True)
    print('calendar.json NO se ha modificado. NO se han importado resultados ni vídeos.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR SEGURO: {exc}', file=sys.stderr, flush=True)
        sys.exit(1)
