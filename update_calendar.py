"""Yeguada Agrado: extractor seguro, con vista previa y publicación opcional.

No incorpora victorias: preserva siempre las existentes.
Publicación únicamente con --publish y datos confirmados.
"""
import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = 'https://www.todoturf.net/'
STALLIONS = ('BOW CREEK', 'NOOZHOH CANARIAS', 'RODABALLO', 'NARANCO')
CALENDAR = Path('calendar.json')
PREVIEW = Path('calendar-preview.json')
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; AgradoCalendar/1.0)'})


def norm(value):
    value = unicodedata.normalize('NFKD', str(value).upper())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+', ' ', value).strip()


def clean_name(value):
    value = re.sub(r'\s+', ' ', str(value).replace('\xa0', ' ')).strip()
    value = re.sub(r',\s*20\d{2}\s*$', '', value)
    value = re.sub(r'\s*\((?:FR|GB|IRE|USA|ITY|GER|SPA|ESP|POR)\)\s*$', '', value, flags=re.I)
    return value.strip()


def get(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc not in ('www.todoturf.net', 'todoturf.net'):
        raise ValueError('URL no permitida: ' + url)
    response = SESSION.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    time.sleep(0.2)
    return BeautifulSoup(response.text, 'html.parser'), response.text


def horse_id(anchor):
    href = urljoin(BASE, anchor.get('href', ''))
    parsed = urlparse(href)
    if parsed.netloc not in ('www.todoturf.net', 'todoturf.net') or not parsed.path.endswith('historialcaballo2.php'):
        return None
    return norm(parse_qs(parsed.query).get('nombrecaballo', [''])[0]) or None


def products(sire):
    lookup = 'BOW CREEK2' if sire == 'BOW CREEK' else sire
    soup, _ = get(BASE + 'productossemental2.php?' + urlencode({'nombresemental': lookup}))
    ids, names = set(), set()
    for a in soup.select('a[href]'):
        identifier = horse_id(a)
        if identifier:
            ids.add(identifier)
            names.add(norm(clean_name(a.get_text(' ', strip=True))))
    if not ids and sire in ('BOW CREEK', 'NOOZHOH CANARIAS'):
        raise RuntimeError('Lista de productos vacía: ' + sire)
    print(f'PRODUCTOS | {sire} | {len(ids)} IDs, {len(names)} nombres', flush=True)
    return ids, names


def discover_meetings():
    soup, html = get(BASE + 'programa.php')
    found = []
    # Atributos href y enlaces incrustados en JavaScript o texto HTML.
    candidates = [a.get('href', '') for a in soup.select('a[href]')]
    candidates += re.findall(r'programa2\.php\?[^\s"\'<>]+', html, flags=re.I)
    for raw in candidates:
        raw = raw.replace('&amp;', '&').strip()
        url = urljoin(BASE, raw)
        parsed = urlparse(url)
        if parsed.path.endswith('/programa2.php'):
            params = parse_qs(parsed.query)
            if params.get('fecha') and params.get('hipodromo'):
                try:
                    day = date.fromisoformat(params['fecha'][0].split(' ')[0])
                except ValueError:
                    continue
                if day >= date.today():
                    found.append(url)
    found = list(dict.fromkeys(found))
    print(f'JORNADAS | {len(found)} futuras detectadas', flush=True)
    if not found:
        raise RuntimeError('No se han descubierto jornadas futuras. No publicar. Revisar HTML de programa.php')
    return found


def race_links(meeting):
    soup, html = get(meeting)
    candidates = [a.get('href', '') for a in soup.select('a[href]')]
    candidates += re.findall(r'programa3\.php\?[^\s"\'<>]+', html, flags=re.I)
    urls = []
    for raw in candidates:
        url = urljoin(BASE, raw.replace('&amp;', '&'))
        if urlparse(url).path.endswith('/programa3.php'):
            urls.append(url)
    return list(dict.fromkeys(urls))


def race_date(url, soup):
    raw = parse_qs(urlparse(url).query).get('fecha', [''])[0].strip().split(' ')[0]
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        match = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', soup.get_text(' ', strip=True))
        return datetime.strptime(match.group(1), '%d/%m/%Y').date().isoformat() if match else None


def race_entries(url):
    soup, _ = get(url)
    day = race_date(url, soup)
    if not day:
        raise RuntimeError('Fecha de carrera desconocida: ' + url)
    title = soup.select_one('h2.mbr-section-title')
    race_name = title.get_text(' ', strip=True) if title else 'Carrera'
    entries = []
    seen = set()
    for tr in soup.select('table tr'):
        a = next((a for a in tr.select('a[href]') if horse_id(a)), None)
        if not a:
            continue
        cells = tr.find_all('td')  # Todoturf contiene celdas sin cerrar.
        if len(cells) < 4:
            continue
        identifier = horse_id(a)
        if identifier in seen:
            continue
        seen.add(identifier)
        jockey_anchor = tr.select_one('a[href*="historialjockey.php"]')
        jockey = jockey_anchor.get_text(' ', strip=True) if jockey_anchor else ''
        # Extraer SOLO el primer td, no los td anidados que podrían contaminarlo.
        number = cells[0].find('b')
        number = number.get_text(' ', strip=True) if number else cells[0].get_text(' ', strip=True).split(' ')[0]
        entries.append({'date': day, 'horse': clean_name(a.get_text(' ', strip=True)),
                        'horse_id': identifier, 'number': number, 'jockey': jockey,
                        'race': race_name, 'url': url})
    if not entries:
        raise RuntimeError('Carrera sin participantes legibles: ' + url)
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish', action='store_true', help='Publicar solo participantes confirmados')
    args = parser.parse_args()
    print('=== YEGUADA AGRADO | EXTRACTOR SEGURO V1.0 ===', flush=True)
    sire_data = {sire: products(sire) for sire in STALLIONS}
    meetings = discover_meetings()
    races = []
    for meeting in meetings:
        found = race_links(meeting)
        print(f'JORNADA | {meeting} | {len(found)} carreras', flush=True)
        if not found:
            raise RuntimeError('Jornada sin carreras legibles: ' + meeting)
        races.extend(found)
    races = list(dict.fromkeys(races))
    matches, total = [], 0
    for url in races:
        entries = race_entries(url)
        total += len(entries)
        print(f'CARRERA | {len(entries)} caballos | {url}', flush=True)
        for entry in entries:
            matching = [sire for sire, (ids, names) in sire_data.items()
                        if entry['horse_id'] in ids or norm(entry['horse']) in names]
            if len(matching) > 1:
                raise RuntimeError('Caballo asociado a varios sementales: ' + entry['horse'])
            if not matching:
                continue
            # Un dorsal cero indica que NO podemos tratarlo como confirmado.
            confirmed = entry['number'].isdigit() and int(entry['number']) > 0 and bool(entry['jockey'])
            event = {'date': entry['date'], 'horse': entry['horse'], 'stallion': matching[0],
                     'race': entry['race'], 'jockey': entry['jockey'], 'number': entry['number'],
                     'url': entry['url'], 'status': 'confirmed' if confirmed else 'pending'}
            matches.append(event)
            print(f'COINCIDENCIA | {event["horse"]} | {event["stallion"]} | {event["status"]}', flush=True)
    if total == 0:
        raise RuntimeError('CERO CABALLOS LEIDOS. No publicar.')
    confirmed = [e for e in matches if e['status'] == 'confirmed']
    print(f'RESUMEN | jornadas={len(meetings)} carreras={len(races)} caballos={total} '
          f'coincidencias={len(matches)} confirmados={len(confirmed)}', flush=True)
    PREVIEW.write_text(json.dumps({'meetings': meetings, 'totalHorses': total, 'matches': matches},
                                  ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('VISTA PREVIA | calendar-preview.json', flush=True)
    if not args.publish:
        print('SOLO PRUEBA | calendar.json intacto', flush=True)
        return
    if not confirmed:
        raise RuntimeError('Sin participantes confirmados: se impide publicar')
    if not CALENDAR.exists():
        raise RuntimeError('calendar.json no existe')
    calendar = json.loads(CALENDAR.read_text(encoding='utf-8'))
    if not isinstance(calendar.get('wins'), list) or not isinstance(calendar.get('participants'), list):
        raise RuntimeError('Estructura calendar.json inesperada')
    # Solo se reemplazan participantes futuros cuando el nuevo lote tiene confirmados.
    today = date.today().isoformat()
    old = [e for e in calendar['participants'] if not isinstance(e, dict) or str(e.get('date', '')) < today]
    calendar['participants'] = old + confirmed
    calendar['lastUpdated'] = datetime.now(timezone.utc).isoformat()
    CALENDAR.write_text(json.dumps(calendar, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PUBLICADO EN ARCHIVO LOCAL | calendar.json | wins preservadas', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('ERROR: ' + str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
