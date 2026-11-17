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
    # Todoturf sometimes includes coat/sex abbreviations inside the horse link,
    # e.g. 'ALBATROS C C'. Strip only the recognised TWO-token suffix.
    value = re.sub(r'\s+(?:C|Y|M|H)\.?\s+(?:C|A|T|R|N|Z|B)\.?$', '', value, flags=re.I)
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
    print(f'CONTROL | {sire} | EMPEL={"EMPEL" in names} | RONCAL={"RONCAL" in names}', flush=True)
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

