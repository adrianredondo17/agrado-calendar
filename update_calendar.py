"""Yeguada Agrado: diagnóstico de Todoturf, SOLO LECTURA.
No modifica calendar.json ni publica participaciones.
"""
import re
import sys
import time
import unicodedata
from datetime import date, datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = 'https://www.todoturf.net/'
STALLIONS = ('BOW CREEK', 'NOOZHOH CANARIAS', 'RODABALLO', 'NARANCO')
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; AgradoCalendar/0.5; diagnostic)'})


def norm(value):
    value = unicodedata.normalize('NFKD', str(value).upper())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+', ' ', value).strip()


def clean_name(value):
    value = re.sub(r'\s+', ' ', str(value).replace('\xa0', ' ')).strip()
    value = re.sub(r',\s*20\d{2}\s*$', '', value)
    # Sexo/capa de Todoturf: "Cas.C.", "C.C.", "Y.A.", etc.
    value = re.sub(r'\s+(?:Cas\.|C\.|Y\.|M\.|H\.)\s*[A-Z]\.\s*$', '', value, flags=re.I)
    value = re.sub(r'\s+(?:CAS|C|Y|M|H)\s+(?:C|A|T|R|N|Z|B)\s*$', '', value, flags=re.I)
    value = re.sub(r'\s*\((?:FR|GB|IRE|USA|ITY|GER|SPA|ESP|POR)\)\s*$', '', value, flags=re.I)
    return value.strip()


def horse_id(anchor):
    """Identificador común de enlaces de producto y de programa."""
    href = urljoin(BASE, anchor.get('href', ''))
    parsed = urlparse(href)
    if parsed.netloc not in ('www.todoturf.net', 'todoturf.net'):
        return None
    if not parsed.path.endswith('historialcaballo2.php'):
        return None
    raw = parse_qs(parsed.query).get('nombrecaballo', [''])[0]
    return norm(raw) or None


def get(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.netloc not in ('www.todoturf.net', 'todoturf.net'):
        raise ValueError('URL no permitida: ' + url)
    response = SESSION.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    time.sleep(0.3)
    return BeautifulSoup(response.text, 'html.parser')


def links(soup, filename):
    return list(dict.fromkeys(urljoin(BASE, a['href']) for a in soup.select('a[href]') if filename in a['href']))


def products(sire):
    lookup = 'BOW CREEK2' if sire == 'BOW CREEK' else sire
    url = BASE + 'productossemental2.php?' + urlencode({'nombresemental': lookup})
    soup = get(url)
    tables = [t for t in soup.select('table') if 'GANANCIAS' in norm(t.get_text(' ', strip=True)) and 'MADRE' in norm(t.get_text(' ', strip=True))]
    if not tables:
        raise RuntimeError('No se encuentra la tabla de productos: ' + sire)
    ids = set()
    names = set()
    for a in tables[0].select('a[href]'):
        identifier = horse_id(a)
        if identifier:
            ids.add(identifier)
            names.add(norm(clean_name(a.get_text(' ', strip=True))))
    print(f'PRODUCTOS | {sire}: {len(ids)} IDs, {len(names)} nombres | ejemplos: {sorted(names)[:7]}', flush=True)
    print(f'CONTROL | {sire} | EMPEL={"EMPEL" in ids or "EMPEL" in names} | RONCAL={"RONCAL" in ids or "RONCAL" in names}', flush=True)
    if sire in ('BOW CREEK', 'NOOZHOH CANARIAS') and not ids:
        raise RuntimeError('No se encontraron enlaces de productos para ' + sire)
    return ids, names


def race_date(url, soup):
    raw = parse_qs(urlparse(url).query).get('fecha', [''])[0].strip().split(' ')[0]
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        pass
    text = soup.get_text(' ', strip=True)
    match = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', text)
    return datetime.strptime(match.group(1), '%d/%m/%Y').date().isoformat() if match else None


def race_entries(url):
    soup = get(url)
    day = race_date(url, soup)
    if not day:
        print('AVISO | Fecha desconocida | ' + url, flush=True)
        return []
    if day < date.today().isoformat():
        return []
    tables = [t for t in soup.select('table') if 'CABALLO' in norm(t.get_text(' ', strip=True)) and 'JINETE' in norm(t.get_text(' ', strip=True))]
    if not tables:
        print('AVISO | Tabla de carrera ausente | ' + url, flush=True)
        return []
    entries = []
    for tr in tables[0].select('tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) < 4:
            continue
        a = next((a for a in cells[1].select('a[href]') if horse_id(a)), None)
        if not a:
            continue
        identifier = horse_id(a)
        name = clean_name(a.get_text(' ', strip=True))
        number = cells[0].get_text(' ', strip=True)
        jockey = cells[3].get_text(' ', strip=True)
        entries.append({'date': day, 'horse': name, 'horse_id': identifier, 'number': number, 'jockey': jockey, 'url': url})
    return entries


def main():
    print('=== YEGUADA AGRADO | DIAGNOSTICO SOLO LECTURA | VERSION 0.5 ===', flush=True)
    for raw, expected in [('EMPEL Cas.C., 2020', 'EMPEL'), ('RONCAL Cas.C., 2022', 'RONCAL'), ('ANOTHER ROSE Cas.C., 2022', 'ANOTHER ROSE'), ('ALBATROS C.C., 2021', 'ALBATROS')]:
        assert clean_name(raw) == expected, (raw, clean_name(raw))
    print('AUTOPRUEBA | Limpieza: OK', flush=True)
    sire_data = {sire: products(sire) for sire in STALLIONS}
