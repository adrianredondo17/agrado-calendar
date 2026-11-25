
"""Detecta nuevas victorias españolas de sementales de Yeguada Agrado.

No importa resultados anteriores al 01/01/2026.
Comprueba el ganador en la ficha de resultados de Todoturf.
Evita duplicados por fecha y caballo.

Guarda automáticamente:
- url: enlace directo a resultados3.php
- video_url: enlace a videocarrera.php, si hay vídeo verificable

Solo modifica calendar.json con --publish.
"""

import argparse
import json
import re
import sys
import time
import unicodedata

from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import (
    parse_qs,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)

import requests
from bs4 import BeautifulSoup


BASE = "https://www.todoturf.net/"
CALENDAR = Path("calendar.json")
AGRADO = Path("caballos_agrado.json")
START_DATE = date(2026, 1, 1)

STALLIONS = (
    "BOW CREEK",
    "NOOZHOH CANARIAS",
    "RODABALLO",
    "NARANCO",
)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; AgradoCalendar/1.0)"
})


def norm(value):
    value = unicodedata.normalize(
        "NFKD",
        str(value).upper()
    )

    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )

    return re.sub(
        r"[^A-Z0-9]+",
        " ",
        value
    ).strip()


def get(url, data=None):
    parsed = urlparse(url)

    if (
        parsed.scheme != "https"
        or parsed.hostname not in (
            "todoturf.net",
            "www.todoturf.net"
        )
    ):
        raise ValueError(
            "URL no permitida: " + url
        )

    response = SESSION.post(url, data=data, timeout=30) if data is not None else SESSION.get(url, timeout=30)

    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
        or response.encoding
    )

    time.sleep(0.2)

    return BeautifulSoup(
        response.content,
        "html.parser"
    )


def horse_link(anchor):
    url = urljoin(
        BASE,
        anchor.get("href", "")
    )

    parsed = urlparse(url)

    if not parsed.path.endswith(
        "/historialcaballo2.php"
    ):
        return None

    if parsed.hostname not in (
        "todoturf.net",
        "www.todoturf.net"
    ):
        return None

    name = parse_qs(
        parsed.query
    ).get("nombrecaballo", [""])[0]

    if not name:
        return None

    return url, norm(name)


def products(sire, labels=None):
    lookup = (
        "BOW CREEK2"
        if sire == "BOW CREEK"
        else sire
    )

    url = BASE + "productossemental2.php?" + urlencode({
        "nombresemental": lookup
    })

    soup = get(url)
    found = {}

    for anchor in soup.select("a[href]"):
        result = horse_link(anchor)

        if result:
            horse_url, identifier = result
            found[identifier] = horse_url
            if labels is not None:
                labels[identifier] = anchor.get_text(" ", strip=True)

    print(
        f"PRODUCTOS | {sire} | {len(found)}",
        flush=True
    )

    if (
        sire in (
            "BOW CREEK",
            "NOOZHOH CANARIAS"
        )
        and not found
    ):
        raise RuntimeError(
            "No se encontraron productos: " + sire
        )

    return found


def video_url_from_result(result_url):
    """Construye la URL del vídeo con los mismos
    identificadores de la carrera.
    """

    parsed = urlparse(result_url)

    if not parsed.path.endswith(
        "/resultados3.php"
    ):
        return None

    params = parse_qs(parsed.query)

    required = (
        "numero",
        "fecha",
        "pais",
        "tipo",
    )

    if any(
        not params.get(key)
        for key in required
    ):
        return None

    if params["pais"][0].upper() != "ESP":
        return None

    video_path = parsed.path.replace(
        "/resultados3.php",
        "/videocarrera.php"
    )

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        video_path,
        parsed.params,
        parsed.query,
        ""
    ))


def verify_video(video_url):
    """Busca indicios explícitos de vídeo.

    Si no puede confirmarse, no publica el botón.
    Una página HTTP 200 no demuestra por sí sola
    que exista una repetición.
    """

    if not video_url:
        return False

    try:
        soup = get(video_url)

        # Reproductores HTML5.
        if soup.find("video"):
            return True

        # Fuentes de vídeo HTML5.
        if soup.find("source", src=re.compile(
            r"\.(mp4|webm|m3u8)(?:\?|$)",
            re.I
        )):
            return True

        # Reproductores externos embebidos.
        for iframe in soup.find_all("iframe"):
            src = iframe.get("src", "")

            if re.search(
                r"youtube\.com/embed/|"
                r"youtube-nocookie\.com/embed/|"
                r"player\.vimeo\.com/video/",
                src,
                re.I
            ):
                return True

        return False

    except Exception as exc:
        print(
            f"AVISO VIDEO | {video_url} | {exc}",
            flush=True
        )
        return False


def get_video_url(result_url):
    """Devuelve el enlace de repetición únicamente
    cuando se detecta un reproductor reconocible.
    """

    candidate = video_url_from_result(
        result_url
    )

    if not candidate:
        return None

    if verify_video(candidate):
        print(
            f"VIDEO ENCONTRADO | {candidate}",
            flush=True
        )
        return candidate

    print(
        f"VIDEO NO CONFIRMADO | {candidate}",
        flush=True
    )

    return None


# -----------------------------------------
# PROCESO PRINCIPAL
# -----------------------------------------


def clean(value):
    value = str(value).strip()
    value = re.sub(r'\s+(?:CAS\.\s*)?[YCMH]\.\s*(?:C|A|T|TOR|N|AL)\.\s*(?:,\s*\d+\s*a\.)?$', '', value, flags=re.I)
    value = re.sub(r'\s*\((?:FR|GB|IRE|USA|ITY|GER|SPA|ESP|POR|a)\)\s*$', '', value, flags=re.I)
    value = re.sub(r'\s*\((?:FR|GB|IRE|USA|ITY|GER|SPA|ESP|POR|a)\)\s*$', '', value, flags=re.I)
    return value.strip()

def key(value):
    return norm(clean(value))

def links(soup, endpoint):
    return sorted({urljoin(BASE,a['href']) for a in soup.select('a[href]') if urlparse(urljoin(BASE,a['href'])).path == '/'+endpoint})

def winners(soup):
    for row in soup.select('tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells)<2 or not re.fullmatch(r'1(?:\s*[º°.]|\s*ex\.?)*',cells[0].get_text(' ',strip=True),re.I):
            continue
        a = cells[1].select_one('a[href*="historialcaballo2.php"]')
        if a and horse_link(a):
            yield clean(a.get_text(' ',strip=True)), horse_link(a)[1]

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--publish',action='store_true'); args=parser.parse_args()
    calendar=json.loads(CALENDAR.read_text(encoding='utf-8'))
    roster={key(x['horse']):x for x in json.loads(AGRADO.read_text(encoding='utf-8'))}
    sire_ids={}
    for sire in STALLIONS:
        for identifier in products(sire):
            if identifier in sire_ids and sire_ids[identifier]!=sire: raise RuntimeError('Padre ambiguo: '+identifier)
            sire_ids[identifier]=sire
    existing={}; duplicates=0
    for old in calendar['wins']:
        w=dict(old); k=(w['date'],key(w['horse']))
        if k in existing:
            duplicates+=1
            for field,val in w.items():
                if val and not existing[k].get(field): existing[k][field]=val
        else: existing[k]=w
    new_count=0; checked=0; meetings_count=0
    for year in range(START_DATE.year,date.today().year+1):
        index=get(BASE+'resultados.php', {'ano':str(year),'hipodromo':'ESPANA','Submit':'Buscar'})
        meetings=links(index,'resultados2.php')
        if not meetings: raise RuntimeError('Sin jornadas para '+str(year))
        for meeting in meetings:
            params=parse_qs(urlparse(meeting).query); day=params['fecha'][0][:10]; venue=params['hipodromo'][0]
            if date.fromisoformat(day)<START_DATE: continue
            meetings_count+=1
            races=links(get(meeting),'resultados3.php')
            races=[u for u in races if parse_qs(urlparse(u).query).get('pais',[''])[0].upper()=='ESP']
            if not races: raise RuntimeError('Sin carreras españolas: '+meeting)
            for url in races:
                soup=get(url); checked+=1
                title=soup.select_one('h2.mbr-section-title'); ws=list(winners(soup))
                if not title or not ws: raise RuntimeError('Resultado no interpretable: '+url)
                for name,identifier in ws:
                    record=roster.get(key(name)); sire=sire_ids.get(identifier)
                    if not record and not sire: continue
                    if record: name=record['horse']
                    k=(day,key(name)); old=existing.get(k)
                    win={'date':day,'horse':name,'stallion':sire or 'YEGUADA AGRADO','race':title.get_text(' ',strip=True),'venue':venue+', España','url':url,'source':'todoturf_auto'}
                    if record: win['agrado_categories']=record['categories']
                    if old and old.get('video_url'): win['video_url']=old['video_url']
                    else:
                        v=get_video_url(url)
                        if v: win['video_url']=v
                    if old: existing[k]={**old,**win}
                    else: existing[k]=win; new_count+=1; print('NUEVA VICTORIA |',name,day,flush=True)
            print('JORNADA |',day,venue,len(races),flush=True)
    print(f'RESUMEN | jornadas={meetings_count} carreras={checked} nuevas={new_count} duplicados={duplicates} total={len(existing)}',flush=True)
    if args.publish:
        calendar['wins']=sorted(existing.values(),key=lambda w:w['date'],reverse=True)
        calendar['lastUpdated']=datetime.now(timezone.utc).isoformat()
        CALENDAR.write_text(json.dumps(calendar,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    else: print('MODO PRUEBA | No se modifica calendar.json',flush=True)

if __name__=='__main__': main()
