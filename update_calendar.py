"""Yeguada Agrado: extractor seguro, con vista previa y publicación opcional.

Importa victorias históricas españolas desde un archivo local y preserva las existentes.
No identifica automáticamente nuevas victorias: requiere un extractor de resultados validado.
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
HISTORICAL_WINS = Path('victorias_espana_2026.json')
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
