"""Yeguada Agrado — Todoturf participant diagnostic, safe read-only version.

Matches offspring BEFORE checking provisional race declarations.
Does not change calendar.json or publish any data.
"""
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE = 'https://www.todoturf.net/'
STALLIONS = ('BOW CREEK', 'NOOZHOH CANARIAS', 'RODABALLO', 'NARANCO')
DATA = Path('calendar.json')
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; AgradoCalendar/0.2; low-frequency public-data checks)'})


def norm(value):
    value = unicodedata.normalize('NFKD', str(value).upper())
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r'[^A-Z0-9]+', ' ', value).strip()


def clean_horse(value):
    value = re.sub(r'\s*\((?:FR|GB|IRE|USA|ITY|GER|SPA|ESP|POR)\)\s*$', '', value, flags=re.I)
    value = re.sub(r'\s*,\s*20\d\d\s*$', '', value)
    return value.strip()


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
        raise RuntimeError(f'No se encuentra la tabla de productos de {sire}: {url}')
    names = set()
    for row in tables[0].select('tr'):
        cells = row.find_all('td', recursive=False)
        if not cells:
            cells = row.find_all('td')
        if not cells:
            continue
        link = cells[0].find('a')
        if link:
            name = clean_horse(link.get_text(' ', strip=True))
            if name:
                names.add(norm(name))
    print(f'PRODUCTOS | {sire}: {len(names)} | ejemplos: {sorted(names)[:8]}', flush=True)
    if sire in ('BOW CREEK', 'NOOZHOH CANARIAS') and not names:
        raise RuntimeError(f'Lista de productos vacía para {sire}')
    return names


def date_from_url(url):
    raw = parse_qs(urlparse(url).query).get('fecha', [''])[0].strip()
    raw = raw.split(' ')[0]
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def race_rows(url):
    soup = get(url)
    race_date = date_from_url(url)
    if not race_date or race_date < date.today().isoformat():
        return []
    tables = [t for t in soup.select('table') if 'CABALLO' in norm(t.get_text(' ', strip=True)) and 'JINETE' in norm(t.get_text(' ', strip=True))]
    if not tables:
        print(f'AVISO | Sin tabla de participantes: {url}', flush=True)
        return []
    title = next((h.get_text(' ', strip=True) for h in soup.find_all(['h1', 'h2', 'h3']) if 'PREMIO' in norm(h.get_text(' ', strip=True))), 'Premio por verificar')
    rows = []
    for row in tables[0].select('tr'):
        cells = row.find_all('td')
        if len(cells) < 4:
            continue
        horse_link = cells[1].find('a')
        if not horse_link:
            continue
        horse = clean_horse(horse_link.get_text(' ', strip=True))
        number = cells[0].get_text(' ', strip=True)
        jockey = cells[3].get_text(' ', strip=True)
        rows.append({'date': race_date, 'horse': horse, 'number': number, 'jockey': jockey, 'prize': title, 'raceUrl': url})
    return rows


def main():
    if not DATA.exists():
        raise RuntimeError('Falta calendar.json')
    json.loads(DATA.read_text(encoding='utf-8'))  # Validate only; NEVER write.
    print('=== YEGUADA AGRADO | DIAGNÓSTICO SOLO LECTURA ===', flush=True)
    offspring = {sire: horse_names(sire) for sire in STALLIONS}
    reverse = {}
    for sire, names in offspring.items():
        for name in names:
            reverse.setdefault(name, set()).add(sire)
    program = get(BASE + 'programa.php')
    meetings = links(program, 'programa2.php')
    if not meetings:
        raise RuntimeError('No se encontraron jornadas')
    race_urls = []
    for meeting in meetings:
        race_urls.extend(links(get(meeting), 'programa3.php'))
    race_urls = list(dict.fromkeys(race_urls))
    if not race_urls:
        raise RuntimeError('No se encontraron carreras')
    print(f'JORNADAS: {len(meetings)} | CARRERAS: {len(race_urls)}', flush=True)
    matches = []
    total_rows = 0
    for url in race_urls:
        for entry in race_rows(url):
            total_rows += 1
            horse_key = norm(entry['horse'])
            sires = reverse.get(horse_key, set())
            if not sires:
                continue
            # CRITICAL: match offspring BEFORE provisional/confirmed filtering.
            confirmed = entry['number'].isdigit() and int(entry['number']) > 0 and bool(entry['jockey'])
            status = 'POSIBLE PARTICIPANTE - REVISAR DEFINITIVOS' if not confirmed else 'CANDIDATO CONFIRMADO - VERIFICAR PROGRAMA'
            for sire in sorted(sires):
                matches.append((entry, sire, status))
                print(f"COINCIDENCIA | {entry['date']} | {entry['horse']} | {sire} | {status} | dorsal={entry['number']!r} | jinete={entry['jockey']!r} | {entry['raceUrl']}", flush=True)
    print('\n=== RESUMEN ===', flush=True)
    print(f'Jornadas: {len(meetings)} | Carreras: {len(race_urls)} | Caballos leídos: {total_rows}', flush=True)
    print(f'Coincidencias con sementales: {len(matches)}', flush=True)
    print(f"Candidatos con dorsal y jinete: {sum('CANDIDATO CONFIRMADO' in status for _, _, status in matches)}", flush=True)
    print(f"Provisionales o pendientes: {sum('POSIBLE PARTICIPANTE' in status for _, _, status in matches)}", flush=True)
    print('calendar.json NO se ha modificado. No se han importado resultados ni vídeos.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('ERROR SEGURO: ' + str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
