
"""
YEGUADA AGRADO
Diagnostico de participantes de Todoturf.

VERSION DE PRUEBA - SOLO LECTURA

- Consulta los productos de los cuatro sementales.
- Consulta las carreras disponibles.
- Identifica coincidencias con los productos.
- Distingue candidatos con dorsal y jinete.
- No modifica calendar.json.
- No publica resultados ni victorias.
"""

import re
import sys
import time
import unicodedata

from datetime import date
from urllib.parse import (
    urlencode,
    urljoin,
    urlparse,
    parse_qs,
)

import requests
from bs4 import BeautifulSoup


BASE = "https://www.todoturf.net/"

STALLIONS = (
    "BOW CREEK",
    "NOOZHOH CANARIAS",
    "RODABALLO",
    "NARANCO",
)

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; AgradoCalendar/0.3)"
    )
})


# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

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


def clean_horse(value):

    value = str(value).strip()

    # Eliminar pais al final.
    value = re.sub(
        r"\s*\((?:FR|GB|IRE|USA|ITY|GER|SPA|ESP|POR)\)\s*$",
        "",
        value,
        flags=re.I,
    )

    # Eliminar año al final.
    value = re.sub(
        r"\s*,\s*20\d\d\s*$",
        "",
        value,
    )

    # Eliminar sexo y capa de Todoturf.
    # Ejemplo: ALBATROS C C -> ALBATROS
    value = re.sub(
        r"\s+(?:C|Y|M|H)\.?\s+"
        r"(?:C|A|T|R|N|Z|B)\.?$",
        "",
        value,
        flags=re.I,
    )

    return value.strip()


def get(url):

    parsed = urlparse(url)

    if (
        parsed.scheme != "https"
        or parsed.netloc not in (
            "www.todoturf.net",
            "todoturf.net",
        )
    ):
        raise ValueError(
            "Dominio no permitido: " + url
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

    time.sleep(0.4)

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def links(soup, filename):

    result = []

    for a in soup.select("a[href]"):

        href = a.get("href", "")

        if filename in href:
            result.append(
                urljoin(BASE, href)
            )

    return list(
        dict.fromkeys(result)
    )


# ==========================================
# PRODUCTOS DE LOS SEMENTALES
# ==========================================

def horse_names(sire):

    lookup = (
        "BOW CREEK2"
        if sire == "BOW CREEK"
        else sire
    )

    url = (
        BASE
        + "productossemental2.php?"
        + urlencode({
            "nombresemental": lookup
        })
    )

    soup = get(url)

    tables = [
        table
        for table in soup.select("table")
        if (
            "MADRE" in norm(
                table.get_text(" ", strip=True)
            )
            and "GANANCIAS" in norm(
                table.get_text(" ", strip=True)
            )
        )
    ]

    if not tables:
        raise RuntimeError(
            "No se encuentra la tabla "
            "de productos de " + sire
        )

    names = set()

    for row in tables[0].select("tr"):

        cells = row.find_all(
            "td",
            recursive=False
        )

        if not cells:
            cells = row.find_all("td")

        if not cells:
            continue

        horse_link = cells[0].find("a")

        if not horse_link:
            continue

        raw_name = horse_link.get_text(
            " ", strip=True
        )

        name = clean_horse(raw_name)

        if name:
            names.add(norm(name))

    print(
        f"PRODUCTOS | {sire}: {len(names)}",
        flush=True
    )

    print(
        f"EJEMPLOS | {sire}: "
        f"{sorted(names)[:12]}",
        flush=True
    )

    print(
        f"CONTROL | {sire} | "
        f"EMPEL={'EMPEL' in names} | "
        f"RONCAL={'RONCAL' in names}",
        flush=True
    )

    if sire in (
        "BOW CREEK",
        "NOOZHOH CANARIAS",
    ) and not names:
        raise RuntimeError(
            "Lista de productos vacia: " + sire
        )

    return names


# ==========================================
# FECHAS DE LAS CARRERAS
# ==========================================

def date_from_url(url):

    query = parse_qs(
        urlparse(url).query
    )

    raw = query.get(
        "fecha", [""]
    )[0].strip()

    raw = raw.split(" ")[0]

    try:
        return date.fromisoformat(
            raw
        ).isoformat()

    except ValueError:
        return None


# ==========================================
# LECTURA DE PARTICIPANTES
# ==========================================

def race_rows(url):

    race_date = date_from_url(url)

    if not race_date:
        print(
            f"AVISO | Fecha no reconocida: {url}",
            flush=True
        )
        return []

    if race_date < date.today().isoformat():
        return []

    soup = get(url)

    tables = [
        table
        for table in soup.select("table")
        if (
            "CABALLO" in norm(
                table.get_text(" ", strip=True)
            )
            and "JINETE" in norm(
                table.get_text(" ", strip=True)
            )
        )
    ]

    if not tables:
        print(
            f"AVISO | Sin tabla: {url}",
            flush=True
        )
        return []

    title = next(
        (
            h.get_text(" ", strip=True)
            for h in soup.find_all(
                ["h1", "h2", "h3"]
            )
            if "PREMIO" in norm(
                h.get_text(" ", strip=True)
            )
        ),
        "Premio por verificar"
    )

    country = parse_qs(
        urlparse(url).query
    ).get("pais", [""])[0]

    result = []

    for row in tables[0].select("tr"):

        cells = row.find_all(
            "td",
            recursive=False
        )

        if len(cells) < 4:
            cells = row.find_all("td")

        if len(cells) < 4:
            continue

        horse_link = cells[1].find("a")

        if not horse_link:
            continue

        horse = clean_horse(
            horse_link.get_text(
                " ", strip=True
            )
        )

        number = cells[0].get_text(
            " ", strip=True
        )

        jockey = cells[3].get_text(
            " ", strip=True
        )

        if not horse:
            continue

        result.append({
            "date": race_date,
            "horse": horse,
            "number": number,
            "jockey": jockey,
            "prize": title,
            "country": country,
            "raceUrl": url,
        })

    return result


# ==========================================
# PROGRAMA PRINCIPAL
# ==========================================

def main():

    print(
        "\n=== YEGUADA AGRADO ===",
        flush=True
    )

    print(
        "DIAGNOSTICO DE PARTICIPANTES",
        flush=True
    )

    print(
        "MODO SOLO LECTURA",
        flush=True
    )

    # 1. Consultar productos.

    sires = {}

    for sire in STALLIONS:
        sires[sire] = horse_names(sire)

    # 2. Consultar programa.

    print(
        "\nConsultando programa de Todoturf...",
        flush=True
    )

    program = get(
        BASE + "programa.php"
    )

    meetings = links(
        program,
        "programa2.php"
    )

    if not meetings:
        raise RuntimeError(
            "No se encontraron jornadas"
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

    race_urls = list(
        dict.fromkeys(race_urls)
    )

    if not race_urls:
        raise RuntimeError(
            "No se encontraron carreras"
        )

    print(
        f"JORNADAS: {len(meetings)}",
        flush=True
    )

    print(
        f"CARRERAS: {len(race_urls)}",
        flush=True
    )

    # 3. Leer caballos y buscar coincidencias.

    total_horses = 0
    matches = []
    candidates = []
    provisional = []

    for url in race_urls:

        entries = race_rows(url)

        total_horses += len(entries)

        for entry in entries:

            horse_key = norm(
                entry["horse"]
            )

            # IMPORTANTE:
            # Primero comprobar semental.
            # Despues comprobar dorsal y jinete.

            for sire, names in sires.items():

                if horse_key not in names:
                    continue

                match = {
                    **entry,
                    "sire": sire,
                }

                matches.append(match)

                print(
                    "\nCOINCIDENCIA | "
                    f"{entry['date']} | "
                    f"{entry['horse']} | "
                    f"{sire} | "
                    f"Dorsal: {entry['number']} | "
                    f"Jinete: {entry['jockey']} | "
                    f"{entry['raceUrl']}",
                    flush=True
                )

                number = entry["number"]
                jockey = entry["jockey"]

                if (
                    number.isdigit()
                    and int(number) > 0
                    and jockey
                ):
                    candidates.append(match)

                    print(
                        "ESTADO | Candidato con "
                        "dorsal y jinete",
                        flush=True
                    )

                else:
                    provisional.append(match)

                    print(
                        "ESTADO | Pendiente de "
                        "verificacion definitiva",
                        flush=True
                    )

                break

    # 4. Mostrar resumen.

    print(
        "\n========== RESUMEN ==========",
        flush=True
    )

    print(
        f"Jornadas: {len(meetings)}",
        flush=True
    )

    print(
        f"Carreras: {len(race_urls)}",
        flush=True
    )

    print(
        f"Caballos leidos: {total_horses}",
        flush=True
    )

    print(
        f"Coincidencias con sementales: "
        f"{len(matches)}",
        flush=True
    )

    print(
        f"Candidatos con dorsal y jinete: "
        f"{len(candidates)}",
        flush=True
    )

    print(
        f"Pendientes de verificacion: "
        f"{len(provisional)}",
        flush=True
    )

    print(
        "\ncalendar.json NO se ha modificado.",
        flush=True
    )

    print(
        "No se han importado resultados ni videos.",
        flush=True
    )


if __name__ == "__main__":

    try:
        main()

    except Exception as error:

        print(
            f"ERROR SEGURO: {error}",
            file=sys.stderr,
            flush=True
        )

        sys.exit(1)
