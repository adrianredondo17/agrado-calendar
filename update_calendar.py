
"""
YEGUADA AGRADO
Extractor Todoturf - Fase 1: diagnóstico de participantes.

Sementales:
- BOW CREEK
- NOOZHOH CANARIAS
- RODABALLO
- NARANCO

Esta versión:
1. Consulta los productos de los cuatro sementales.
2. Consulta los programas de carreras de Todoturf.
3. Muestra los caballos encontrados en cada carrera.
4. Identifica coincidencias con nuestros sementales.
5. No elimina participantes ni modifica resultados históricos.
6. No publica datos automáticamente en GitHub Pages.
"""

import json
import re
import sys
import time
import unicodedata

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlencode

import requests
from bs4 import BeautifulSoup


# ============================================
# CONFIGURACIÓN
# ============================================

BASE = "https://www.todoturf.net/"

STALLIONS = (
    "BOW CREEK",
    "NOOZHOH CANARIAS",
    "RODABALLO",
    "NARANCO",
)

DATA = Path("calendar.json")

HEADERS = {
    "User-Agent": (
        "AgradoCalendar/0.1 "
        "(public racing data; low-frequency checks)"
    )
}

session = requests.Session()
session.headers.update(HEADERS)


# ============================================
# FUNCIONES AUXILIARES
# ============================================

def norm(value):
    value = unicodedata.normalize(
        "NFKD",
        str(value).upper()
    )

    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )

    return re.sub(
        r"[^A-Z0-9]+",
        " ",
        value
    ).strip()


def get(url):

    if urlparse(url).netloc not in (
        "www.todoturf.net",
        "todoturf.net",
    ):
        raise ValueError(
            "Unexpected domain: " + url
        )

    response = session.get(
        url,
        timeout=25
    )

    response.raise_for_status()

    time.sleep(0.4)

    return BeautifulSoup(
        response.content,
        "html.parser"
    )


def links(soup, filename):

    return [
        urljoin(BASE, a["href"])
        for a in soup.select("a[href]")
        if filename in a["href"]
    ]


def unique(items):

    return list(dict.fromkeys(items))


# ============================================
# PRODUCTOS DE CADA SEMENTAL
# ============================================

def horse_names(sire):

    nombre_todoturf = (
        "BOW CREEK2"
        if sire == "BOW CREEK"
        else sire
    )

    url = BASE + "productossemental2.php?" + urlencode({
        "nombresemental": nombre_todoturf
    })

    print(
        f"\nConsultando productos de {sire}: {url}",
        flush=True
    )

    soup = get(url)

    table = next(
        (
            table
            for table in soup.select("table")
            if "Madre" in table.get_text(
                " ", strip=True
            )
            and "Ganancias" in table.get_text(
                " ", strip=True
            )
        ),
        None,
    )

    if table is None:
        raise ValueError(
            "Products table not found for " + sire
        )

    names = set()

    for row in table.select("tr"):

        cells = row.find_all("td")

        if not cells:
            continue

        horse_link = cells[0].find("a")

        if not horse_link:
            continue

        name = horse_link.get_text(
            " ", strip=True
        )

        name = re.sub(
            r"\s+(?:Cas\.|C\.|Y\.|M\.).*$",
            "",
            name,
            flags=re.I,
        )

        name = re.sub(
            r"\s*\((?:FR|GB|IRE|USA|ITY|GER|SPA|POR)\)\s*$",
            "",
            name,
            flags=re.I,
        )

        name = re.sub(
            r"\s*,\s*20\d\d$",
            "",
            name,
        )

        if name:
            names.add(norm(name))

    if not names:
        raise ValueError(
            "No products found for " + sire
        )

    print(
        f"{sire}: {len(names)} productos encontrados",
        flush=True
    )

    return names


# ============================================
# LECTURA DE CARRERAS
# ============================================

def race_data(url):

    soup = get(url)

    title = next(
        (
            element
            for element in soup.find_all(
                ["h1", "h2", "h3"]
            )
            if "Premio " in element.get_text(
                " ", strip=True
            )
        ),
        None,
    )

    if not title:
        print(
            f"DIAGNÓSTICO | Sin título de premio: {url}",
            flush=True
        )
        return []

    heading = title.get_text(
        " ", strip=True
    )

    match = re.search(
        r"carrera.*?(\d\d/\d\d/\d{4}).*?"
        r"hip[oó]dromo de\s+(.+)",
        soup.get_text(" ", strip=True),
        re.I,
    )

    if not match:
        print(
            f"DIAGNÓSTICO | Fecha o hipódromo "
            f"no reconocido: {url}",
            flush=True
        )
        return []

    day, venue = match.groups()

    iso_date = datetime.strptime(
        day, "%d/%m/%Y"
    ).strftime("%Y-%m-%d")

    if iso_date < datetime.now(
        timezone.utc
    ).date().isoformat():
        return []

    table = next(
        (
            table
            for table in soup.select("table")
            if "Caballo" in table.get_text(
                " ", strip=True
            )
            and "Jinete" in table.get_text(
                " ", strip=True
            )
        ),
        None,
    )

    if table is None:
        print(
            f"DIAGNÓSTICO | Tabla de participantes "
            f"no encontrada: {url}",
            flush=True
        )
        return []

    participants = []

    for row in table.select("tr"):

        cells = row.find_all("td")

        if len(cells) < 4:
            continue

        horse_link = cells[1].find("a")

        if not horse_link:
            continue

        horse = horse_link.get_text(
            " ", strip=True
        )

        horse = re.sub(
            r"\s*\((?:FR|GB|IRE|USA|ITY|GER|SPA|POR)\).*$",
            "",
            horse,
            flags=re.I,
        ).strip()

        number = cells[0].get_text(
            " ", strip=True
        )

        jockey = cells[3].get_text(
            " ", strip=True
        )

        # DIAGNÓSTICO:
        # Mostrar los caballos leídos por Todoturf.
        print(
            f"DIAGNÓSTICO | "
            f"Fecha: {iso_date} | "
            f"Caballo: {horse!r} | "
            f"Dorsal: {number!r} | "
            f"Jinete: {jockey!r} | "
            f"Carrera: {url}",
            flush=True
        )

        # No incluir inscripciones claramente provisionales.
        if (
            not number.isdigit()
            or int(number) == 0
            or not jockey
        ):
            continue

        participants.append({
            "date": iso_date,
            "horse": horse,
            "prize": heading,
            "venue": venue,
            "raceUrl": url,
            "status": "participant",
            "source": "todoturf",
            "jockey": jockey,
            "number": number,
        })

    return participants


# ============================================
# PROGRAMA PRINCIPAL
# ============================================

def main():

    if not DATA.exists():
        raise RuntimeError(
            "calendar.json missing"
        )

    original = json.loads(
        DATA.read_text(
            encoding="utf-8"
        )
    )

    existing = original.get(
        "participants", []
    )

    print(
        "\n=== YEGUADA AGRADO: EXTRACCIÓN TODOTURF ===",
        flush=True
    )

    sires = {
        sire: horse_names(sire)
        for sire in STALLIONS
    }

    print(
        "\nConsultando programa de Todoturf...",
        flush=True
    )

    program = get(
        BASE + "programa.php"
    )

    meetings = unique(
        links(
            program,
            "programa2.php"
        )
    )

    if not meetings:
        raise RuntimeError(
            "No meeting links found: "
            "site structure may have changed"
        )

    race_urls = []

    for meeting in meetings:

        meeting_page = get(meeting)

        race_urls.extend(
            links(
                meeting_page,
                "programa3.php"
            )
        )

    race_urls = unique(
        race_urls
    )

    if not race_urls:
        raise RuntimeError(
            "No race links found: "
            "site structure may have changed"
        )

    print(
        f"\nJornadas encontradas: {len(meetings)}",
        flush=True
    )

    print(
        f"Carreras encontradas: {len(race_urls)}",
        flush=True
    )

    found = []

    for url in race_urls:

        entries = race_data(url)

        for entry in entries:

            for sire, names in sires.items():

                if norm(entry["horse"]) in names:

                    print(
                        f"\nCOINCIDENCIA ENCONTRADA | "
                        f"{entry['horse']} | "
                        f"{sire} | "
                        f"{entry['date']}",
                        flush=True
                    )

                    found.append({
                        **entry,
                        "sire": sire,
                        "id": (
                            entry["date"]
                            + "|"
                            + norm(entry["horse"])
                            + "|"
                            + urlparse(url).query
                        ),
                    })

                    break

    # Conservar los participantes existentes.
    # No eliminar nada hasta implementar
    # la comprobación de resultados oficiales.

    by_id = {
        item["id"]: item
        for item in existing
        if isinstance(item, dict)
        and "id" in item
    }

    for item in found:
        by_id[item["id"]] = item

    original["participants"] = sorted(
        by_id.values(),
        key=lambda item: (
            item.get("date", ""),
            item.get("horse", ""),
        ),
    )

    original["stallions"] = list(
        STALLIONS
    )

    original["lastUpdated"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    DATA.write_text(
        json.dumps(
            original,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(
        "\n========== RESUMEN ==========",
        flush=True
    )

    print(
        f"Jornadas consultadas: {len(meetings)}",
        flush=True
    )

    print(
        f"Carreras consultadas: {len(race_urls)}",
        flush=True
    )

    print(
        f"Participantes encontrados: {len(found)}",
        flush=True
    )

    print(
        f"Total participantes: "
        f"{len(original['participants'])}",
        flush=True
    )

    print(
        "Resultados y vídeos: pendientes de integración.",
        flush=True
    )

    print(
        "NOTA: Esta prueba no publica cambios "
        "en GitHub Pages.",
        flush=True
    )


if __name__ == "__main__":

    try:
        main()

    except Exception as error:

        print(
            f"SAFE FAILURE: {error}",
            file=sys.stderr,
            flush=True
        )

        sys.exit(1)


