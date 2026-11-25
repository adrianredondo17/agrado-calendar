
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


def get(url):
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

    response = SESSION.get(
        url,
        timeout=30
    )

    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
        or response.encoding
    )

    time.sleep(0.2)

    return BeautifulSoup(
        response.text,
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


def history_wins(horse_url):
    soup = get(horse_url)
    wins = []

    history_table = None

    for table in soup.find_all("table"):
        header = norm(" ".join(
            th.get_text(" ", strip=True)
            for th in table.select("th")
        ))

        if (
            "FECHA" in header
            and "HIPODROMO" in header
            and "POS" in header
        ):
            history_table = table
            break

    if history_table is None:
        raise RuntimeError(
            "No se encontró la tabla de historial: "
            + horse_url
        )

    for tr in history_table.select("tr"):
        cells = tr.find_all("td")

        if len(cells) < 9:
            continue

        raw_date = cells[0].get_text(
            " ",
            strip=True
        )

        position = cells[4].get_text(
            " ",
            strip=True
        )

        try:
            day = datetime.strptime(
                raw_date,
                "%d/%m/%Y"
            ).date()
        except ValueError:
            continue

        if (
            day < START_DATE
            or day > date.today()
        ):
            continue

        if not re.fullmatch(
            r"1\s*/\s*\d+",
            position
        ):
            continue

        anchor = cells[0].select_one(
            'a[href*="resultados3.php"]'
        )

        if anchor is None:
            continue

        result_url = urljoin(
            BASE,
            anchor["href"]
        )

        params = parse_qs(
            urlparse(result_url).query
        )

        if (
            params.get("pais", [""])[0].upper()
            != "ESP"
        ):
            continue

        wins.append({
            "date": day.isoformat(),
            "venue": cells[1].get_text(
                " ",
                strip=True
            ),
            "url": result_url,
        })

    return wins


def verify_result(candidate, horse_identifier):
    url = candidate["url"]
    soup = get(url)

    heading = soup.find(
        lambda tag:
            tag.name in (
                "h1", "h2", "h3", "h4", "h5"
            )
            and "PREMIO" in norm(
                tag.get_text(" ", strip=True)
            )
    )

    if heading is None:
        raise RuntimeError(
            "Premio no identificado: " + url
        )

    race = heading.get_text(
        " ",
        strip=True
    )

    race = re.sub(
        r"^Premio\s+",
        "",
        race,
        flags=re.I
    ).strip()

    verified = False

    for table in soup.find_all("table"):
        rows = table.find_all("tr")

        for tr in rows:
            cells = tr.find_all("td")

            if len(cells) < 2:
                continue

            place = cells[0].get_text(
                " ",
                strip=True
            )

            if place != "1":
                continue

            anchor = next(
                (
                    a for a in cells[1].select("a[href]")
                    if horse_link(a)
                ),
                None
            )

            if anchor:
                _, winner_id = horse_link(anchor)

                if winner_id == horse_identifier:
                    verified = True
                    break

        if verified:
            break

    if not verified:
        raise RuntimeError(
            "No se pudo verificar el ganador: "
            + url
        )

    return race


# -----------------------------------------
# NUEVO: ENLACES AUTOMÁTICOS DE REPETICIÓN
# -----------------------------------------

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

def display_name(value):
    value = re.sub(r",\s*(?:19|20)\d{2}$", "", str(value)).strip()
    return re.sub(r"\s*\([A-Z]{2,3}\)$", "", value, flags=re.I).strip()


def build_groups():
    records = json.loads(AGRADO.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise RuntimeError("caballos_agrado.json no contiene una lista")
    cache = {}
    groups = []
    relations = {}
    names = {}

    def lookup(sire):
        key = norm(sire)
        if key not in cache:
            labels = {}
            horses = products(sire, labels)
            cache[key] = (horses, labels)
        return cache[key]

    for sire in STALLIONS:
        horses, labels = lookup(sire)
        groups.append((sire, horses))
        names.update({i: display_name(labels.get(i) or i) for i in horses})

    extra = {}
    for record in records:
        name = str(record.get("horse", "")).strip()
        if not name:
            continue
        matches = {}
        for sire in record.get("sires", []):
            if not str(sire).strip():
                continue
            try:
                horses, labels = lookup(str(sire).strip().upper())
            except Exception as exc:
                print(f"AVISO PADRE | {name} | {sire} | {exc}", flush=True)
                continue
            for identifier, url in horses.items():
                label = display_name(labels.get(identifier) or identifier)
                if norm(label) == norm(display_name(name)):
                    matches[identifier] = url
        if len(matches) != 1:
            print(f"AGRADO SIN IDENTIFICAR | {name} | coincidencias={len(matches)}", flush=True)
            continue
        identifier, url = next(iter(matches.items()))
        extra[identifier] = url
        names[identifier] = display_name(name)
        relations[identifier] = sorted(set(relations.get(identifier, []) + record.get("categories", [])))
    groups.append(("YEGUADA AGRADO", extra))
    print(f"AGRADO | identificados={len(extra)} | registros={len(records)}", flush=True)
    return groups, names, relations


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--publish",
        action="store_true"
    )

    args = parser.parse_args()

    if not CALENDAR.exists():
        raise RuntimeError(
            "No existe calendar.json"
        )

    calendar = json.loads(
        CALENDAR.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        calendar.get("wins"),
        list
    ):
        raise RuntimeError(
            "calendar.json no contiene wins válido"
        )

    existing = calendar["wins"]

    known = {
        (
            str(w.get("date", "")),
            norm(w.get("horse", ""))
        )
        for w in existing
        if isinstance(w, dict)
    }

    new_wins = []
    checked = set()

    groups, names, relations = build_groups()

    for sire, horses in groups:
        for identifier, horse_url in horses.items():
            if identifier in checked:
                continue

            checked.add(identifier)

            candidates = history_wins(
                horse_url
            )

            for candidate in candidates:

                parsed = urlparse(
                    horse_url
                )

                horse = parse_qs(
                    parsed.query
                ).get(
                    "nombrecaballo",
                    [""]
                )[0]

                horse = re.sub(
                    r",\s*20\d{2}$",
                    "",
                    horse
                ).strip()

                horse = re.sub(
                    r"\s*\((FR|GB|IRE|USA|ITY|GER|SPA|ESP|POR)\)$",
                    "",
                    horse,
                    flags=re.I
                ).strip()

                horse = names.get(identifier, horse)
                key = (
                    candidate["date"],
                    norm(horse)
                )

                if key in known or (candidate["date"], identifier) in known:
                    continue

                # Verificación del ganador.
                race = verify_result(
                    candidate,
                    identifier
                )

                # Nuevo: búsqueda automática del vídeo.
                video_url = get_video_url(
                    candidate["url"]
                )

                win = {
                    "date": candidate["date"],
                    "horse": horse,
                    "stallion": sire,
                    "race": race,
                    "venue": (
                        candidate["venue"]
                        + ", España"
                    ),
                    "url": candidate["url"],
                    "source": "todoturf_auto"
                }

                if identifier in relations:
                    win["agrado_categories"] = relations[identifier]

                # No se inventan enlaces a vídeos.
                if video_url:
                    win["video_url"] = video_url

                new_wins.append(win)
                known.add(key)

                print(
                    f"NUEVA VICTORIA | {horse} | "
                    f"{race} | {candidate['date']}",
                    flush=True
                )

    print(
        f"RESUMEN | caballos revisados={len(checked)} "
        f"nuevas victorias={len(new_wins)}",
        flush=True
    )

    if not args.publish:
        print(
            "MODO PRUEBA | No se modifica calendar.json",
            flush=True
        )
        return

    if new_wins:
        existing.extend(new_wins)

        existing.sort(
            key=lambda w: str(
                w.get("date", "")
            ),
            reverse=True
        )

        calendar["lastUpdated"] = datetime.now(
            timezone.utc
        ).isoformat()

        CALENDAR.write_text(
            json.dumps(
                calendar,
                ensure_ascii=False,
                indent=2
            ) + "\n",
            encoding="utf-8"
        )

    print(
        f"VICTORIAS PUBLICADAS | "
        f"nuevas={len(new_wins)} "
        f"total={len(existing)}",
        flush=True
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        print(
            "ERROR: " + str(exc),
            file=sys.stderr,
            flush=True
        )
        sys.exit(1)
