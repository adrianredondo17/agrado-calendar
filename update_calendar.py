
"""Yeguada Agrado — Diagnóstico Todoturf v0.7.

PRUEBA TEMPORAL:
- Consulta directamente la jornada del 22/11/2026 en La Zarzuela.
- Identifica productos de los cuatro sementales.
- Examina las carreras y busca coincidencias.
- NO modifica calendar.json ni publica información.
"""

import re
import sys
import time
import unicodedata
from datetime import date, datetime
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE = "https://www.todoturf.net/"

STALLIONS = (
    "BOW CREEK",
    "NOOZHOH CANARIAS",
    "RODABALLO",
    "NARANCO",
)

# Jornada de prueba proporcionada por el usuario.
TEST_MEETINGS = [
    BASE
    + "programa2.php?fecha=2026-11-22%2000:00:00"
    + "&hipodromo=LA%20ZARZUELA"
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; AgradoCalendar/0.7; diagnostic)"
})


def norm(value):
    value = unicodedata.normalize("NFKD", str(value).upper())
    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )
    return re.sub(r"[^A-Z0-9]+", " ", value).strip()


def clean_name(value):
    value = re.sub(
        r"\s+", " ",
        str(value).replace("\xa0", " ")
    ).strip()

    value = re.sub(r",\s*20\d{2}\s*$", "", value)

    value = re.sub(
        r"\s+(?:Cas\.|C\.|Y\.|M\.|H\.)\s*[A-Z]\.\s*$",
        "",
        value,
        flags=re.I,
    )

    value = re.sub(
        r"\s+(?:CAS|C|Y|M|H)\s+(?:C|A|T|R|N|Z|B)\s*$",
        "",
        value,
        flags=re.I,
    )

    value = re.sub(
        r"\s*\((?:FR|GB|IRE|USA|ITY|GER|SPA|ESP|POR)\)\s*$",
        "",
        value,
        flags=re.I,
    )

    return value.strip()


def horse_id(anchor):
    href = urljoin(BASE, anchor.get("href", ""))
    parsed = urlparse(href)

    if parsed.netloc not in (
        "www.todoturf.net",
        "todoturf.net",
    ):
        return None

    if not parsed.path.endswith("historialcaballo2.php"):
        return None

    raw = parse_qs(parsed.query).get(
        "nombrecaballo", [""]
    )[0]

    return norm(raw) or None


def get(url):
    parsed = urlparse(url)

    if (
        parsed.scheme != "https"
        or parsed.netloc not in (
            "www.todoturf.net",
            "todoturf.net",
        )
    ):
        raise ValueError("URL no permitida: " + url)

    response = SESSION.get(url, timeout=30)
    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
        or response.encoding
    )

    time.sleep(0.3)

    return BeautifulSoup(
        response.text,
        "html.parser",
    )


def links(soup, filename):
    found = []

    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").strip()

        if filename.lower() in href.lower():
            found.append(urljoin(BASE, href))

    return list(dict.fromkeys(found))


def link_diagnostic(soup, label):
    anchors = soup.select("a[href]")

    print(
        f"DIAGNOSTICO | {label}: "
        f"{len(anchors)} enlaces | "
        f"ejemplos: "
        f"{[a.get('href') for a in anchors[:12]]}",
        flush=True,
    )

    title = (
        soup.title.get_text(" ", strip=True)
        if soup.title
        else "SIN TITULO"
    )

    print(
        f"DIAGNOSTICO | {label}: titulo={title}",
        flush=True,
    )


def products(sire):
    lookup = (
        "BOW CREEK2"
        if sire == "BOW CREEK"
        else sire
    )

    url = (
        BASE
        + "productossemental2.php?"
        + urlencode({"nombresemental": lookup})
    )

    soup = get(url)

    anchors = [
        anchor
        for anchor in soup.select("a[href]")
        if horse_id(anchor)
    ]

    ids = set()
    names = set()

    for anchor in anchors:
        identifier = horse_id(anchor)

        if identifier:
            ids.add(identifier)

            name = clean_name(
                anchor.get_text(" ", strip=True)
            )

            names.add(norm(name))

    if not ids:
        # Algunos sementales todavía pueden
        # no tener productos registrados.
        print(
            f"AVISO | {sire}: "
            "no se han encontrado productos",
            flush=True,
        )

        return ids, names

    print(
        f"PRODUCTOS | {sire}: "
        f"{len(ids)} IDs, "
        f"{len(names)} nombres | "
        f"ejemplos: {sorted(names)[:7]}",
        flush=True,
    )

    if sire == "NOOZHOH CANARIAS":
        print(
            "CONTROL | NOOZHOH CANARIAS | "
            f"EMPEL={'EMPEL' in ids or 'EMPEL' in names} | "
            f"RONCAL={'RONCAL' in ids or 'RONCAL' in names}",
            flush=True,
        )

    return ids, names


def race_date(url, soup):
    raw = parse_qs(
        urlparse(url).query
    ).get("fecha", [""])[0]

    raw = raw.strip().split(" ")[0]

    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        pass

    text = soup.get_text(" ", strip=True)

    match = re.search(
        r"\b(\d{2}/\d{2}/\d{4})\b",
        text,
    )

    if match:
        return datetime.strptime(
            match.group(1),
            "%d/%m/%Y",
        ).date().isoformat()

    return None


def race_entries(url):
    soup = get(url)
    day = race_date(url, soup)

    if not day:
        print(
            "AVISO | Fecha desconocida | " + url,
            flush=True,
        )
        return []

    # Se permite leer jornadas pasadas en esta
    # prueba para no descartar datos de diagnóstico.

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
            "AVISO | Tabla de carrera ausente | "
            + url,
            flush=True,
        )

        link_diagnostic(
            soup,
            "CARRERA SIN TABLA",
        )

        return []

    entries = []

    for tr in tables[0].select("tr"):
        cells = tr.find_all(
            "td",
            recursive=False,
        )

        if len(cells) < 4:
            continue

        anchor = next(
            (
                a
                for a in cells[1].select("a[href]")
                if horse_id(a)
            ),
            None,
        )

        if not anchor:
            continue

        identifier = horse_id(anchor)

        name = clean_name(
            anchor.get_text(" ", strip=True)
        )

        number = cells[0].get_text(
            " ", strip=True
        )

        jockey = cells[3].get_text(
            " ", strip=True
        )

        entries.append({
            "date": day,
            "horse": name,
            "horse_id": identifier,
            "number": number,
            "jockey": jockey,
            "url": url,
        })

    return entries


def main():
    print(
        "=== YEGUADA AGRADO | "
        "DIAGNOSTICO SOLO LECTURA | "
        "VERSION 0.7 ===",
        flush=True,
    )

    tests = [
        ("EMPEL Cas.C., 2020", "EMPEL"),
        ("RONCAL Cas.C., 2022", "RONCAL"),
        (
            "ANOTHER ROSE Cas.C., 2022",
            "ANOTHER ROSE",
        ),
        ("ALBATROS C.C., 2021", "ALBATROS"),
    ]

    for raw, expected in tests:
        actual = clean_name(raw)

        assert actual == expected, (
            raw,
            actual,
        )

    print(
        "AUTOPRUEBA | Limpieza: OK",
        flush=True,
    )

    sire_data = {
        sire: products(sire)
        for sire in STALLIONS
    }

    # CAMBIO PRINCIPAL:
    # Usamos directamente la jornada conocida.
    meetings = TEST_MEETINGS

    print(
        f"DIAGNOSTICO | "
        f"Jornadas de prueba: {len(meetings)}",
        flush=True,
    )

    races = []

    for meeting in meetings:
        print(
            "CONSULTANDO JORNADA | " + meeting,
            flush=True,
        )

        meeting_soup = get(meeting)

        meeting_races = links(
            meeting_soup,
            "programa3.php",
        )

        print(
            f"DIAGNOSTICO | Jornada: "
            f"{len(meeting_races)} carreras",
            flush=True,
        )

        if not meeting_races:
            link_diagnostic(
                meeting_soup,
                "JORNADA SIN CARRERAS",
            )

        races.extend(meeting_races)

    races = list(dict.fromkeys(races))

    if not races:
        raise RuntimeError(
            "No se encontraron enlaces de carreras "
            "en la jornada de prueba"
        )

    total = 0
    matches = 0
    declared = 0
    pending = 0

    for race in races:
        print(
            "LEYENDO CARRERA | " + race,
            flush=True,
        )

        entries = race_entries(race)

        total += len(entries)

        print(
            f"DIAGNOSTICO | "
            f"{len(entries)} caballos leidos",
            flush=True,
        )

        for entry in entries:
            for sire, (ids, names) in sire_data.items():
                if (
                    entry["horse_id"] not in ids
                    and norm(entry["horse"]) not in names
                ):
                    continue

                matches += 1

                is_declared = (
                    entry["number"].isdigit()
                    and int(entry["number"]) > 0
                    and bool(entry["jockey"])
                )

                if is_declared:
                    declared += 1
                else:
                    pending += 1

                status = (
                    "CANDIDATO CON DORSAL Y JINETE"
                    if is_declared
                    else "PENDIENTE DE CONFIRMACION"
                )

                print(
                    f"COINCIDENCIA | "
                    f"{entry['date']} | "
                    f"{entry['horse']} | "
                    f"{sire} | "
                    f"{status} | "
                    f"{entry['url']}",
                    flush=True,
                )

                break

    print(
        "========== RESUMEN ==========",
        flush=True,
    )

    print(
        f"Jornadas: {len(meetings)} | "
        f"Carreras: {len(races)} | "
        f"Caballos leidos: {total}",
        flush=True,
    )

    print(
        f"Coincidencias: {matches} | "
        f"Candidatos con dorsal y jinete: "
        f"{declared} | "
        f"Pendientes: {pending}",
        flush=True,
    )

    if total == 0:
        raise RuntimeError(
            "CERO CABALLOS LEIDOS: "
            "revisar estructura de las tablas; "
            "no publicar"
        )

    print(
        "PRUEBA COMPLETADA. "
        "calendar.json NO se ha modificado. "
        "No se han publicado datos.",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            "ERROR DE DIAGNOSTICO: " + str(exc),
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
