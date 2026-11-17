
"""Yeguada Agrado — diagnóstico Todoturf v0.9.

Prueba la jornada de La Zarzuela del 22/11/2026.
Investiga por qué BOLONIA no coincide con los productos
de NOOZHOH CANARIAS.

SOLO LECTURA: no modifica calendar.json.
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

TEST_MEETINGS = [
    BASE
    + "programa2.php?fecha=2026-11-22%2000:00:00"
    + "&hipodromo=LA%20ZARZUELA"
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; AgradoCalendar/0.9; diagnostic)"
    )
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
    return re.sub(r"[^A-Z0-9]+", " ", value).strip()


def clean_name(value):
    value = re.sub(
        r"\s+",
        " ",
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
        "nombrecaballo",
        [""]
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

    ids = set()
    names = set()

    for anchor in soup.select("a[href]"):
        identifier = horse_id(anchor)

        if identifier:
            ids.add(identifier)
            names.add(
                norm(
                    clean_name(
                        anchor.get_text(" ", strip=True)
                    )
                )
            )

    if not ids and sire in (
        "BOW CREEK",
        "NOOZHOH CANARIAS",
    ):
        raise RuntimeError(
            "No se han podido cargar los productos de "
            + sire
        )

    print(
        f"PRODUCTOS | {sire}: "
        f"{len(ids)} IDs, "
        f"{len(names)} nombres",
        flush=True,
    )

    if sire == "NOOZHOH CANARIAS":
        print(
            "CONTROL | "
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

    match = re.search(
        r"\b(\d{2}/\d{2}/\d{4})\b",
        soup.get_text(" ", strip=True),
    )

    if match:
        return datetime.strptime(
            match.group(1),
            "%d/%m/%Y",
        ).date().isoformat()

    return None


def parse_race_entries(soup, url):
    day = race_date(url, soup)

    if not day:
        raise RuntimeError(
            "Fecha desconocida en carrera: " + url
        )

    entries = []

    for table in soup.select("table"):
        for tr in table.select("tr"):
            horse_anchor = next(
                (
                    a for a in tr.select("a[href]")
                    if horse_id(a)
                ),
                None,
            )

            if not horse_anchor:
                continue

            # Todoturf contiene algunas etiquetas td
            # sin cerrar. No usar recursive=False.
            cells = tr.find_all("td")

            if len(cells) < 4:
                continue

            number = cells[0].get_text(
                " ", strip=True
            )

            jockey_anchor = tr.select_one(
                'a[href*="historialjockey.php"]'
            )

            jockey = (
                jockey_anchor.get_text(" ", strip=True)
                if jockey_anchor
                else ""
            )

            entries.append({
                "date": day,
                "horse": clean_name(
                    horse_anchor.get_text(
                        " ", strip=True
                    )
                ),
                "horse_id": horse_id(horse_anchor),
                "number": number,
                "jockey": jockey,
                "url": url,
            })

    return entries


def race_entries(url):
    return parse_race_entries(get(url), url)


def main():
    print(
        "=== YEGUADA AGRADO | "
        "DIAGNOSTICO SOLO LECTURA | "
        "VERSION 0.9 ===",
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
        assert clean_name(raw) == expected, (
            raw,
            clean_name(raw),
        )

    print(
        "AUTOPRUEBA | Limpieza: OK",
        flush=True,
    )

    sire_data = {
        sire: products(sire)
        for sire in STALLIONS
    }

    # NUEVO: comprobar cómo aparece BOLONIA
    # en las listas de productos.
    print(
        "========== DIAGNOSTICO BOLONIA ==========",
        flush=True,
    )

    for sire, (ids, names) in sire_data.items():
        matching_ids = sorted(
            x for x in ids
            if "BOLONIA" in x
        )

        matching_names = sorted(
            x for x in names
            if "BOLONIA" in x
        )

        print(
            f"BOLONIA | {sire} | "
            f"IDs: {matching_ids} | "
            f"NOMBRES: {matching_names}",
            flush=True,
        )

    print(
        "BOLONIA | Identificador conocido "
        "en carrera: BOLONIA II | "
        "Nombre visible: BOLONIA (FR)",
        flush=True,
    )

    races = []

    for meeting in TEST_MEETINGS:
        meeting_races = links(
            get(meeting),
            "programa3.php",
        )

        print(
            f"JORNADA | {meeting} | "
            f"{len(meeting_races)} carreras",
            flush=True,
        )

        races.extend(meeting_races)

    races = list(dict.fromkeys(races))

    if not races:
        raise RuntimeError(
            "No se encontraron carreras "
            "en la jornada de prueba"
        )

    total = 0
    matches = 0
    candidates = 0
    pending = 0

    for race in races:
        entries = race_entries(race)
        total += len(entries)

        print(
            f"CARRERA | {race} | "
            f"{len(entries)} caballos",
            flush=True,
        )

        for entry in entries:

            # NUEVO: mostrar el identificador real
            # de BOLONIA cuando aparece en una carrera.
            if "BOLONIA" in norm(entry["horse"]):
                print(
                    "BOLONIA EN CARRERA | "
                    f"Nombre: {entry['horse']} | "
                    f"ID: {entry['horse_id']} | "
                    f"Fecha: {entry['date']}",
                    flush=True,
                )

                ids, names = sire_data[
                    "NOOZHOH CANARIAS"
                ]

                print(
                    "BOLONIA | "
                    "Coincide ID con NOOZHOH: "
                    f"{entry['horse_id'] in ids} | "
                    "Coincide nombre con NOOZHOH: "
                    f"{norm(entry['horse']) in names}",
                    flush=True,
                )

            for sire, (ids, names) in sire_data.items():
                if (
                    entry["horse_id"] not in ids
                    and norm(entry["horse"]) not in names
                ):
                    continue

                matches += 1

                confirmed_candidate = (
                    entry["number"].isdigit()
                    and int(entry["number"]) > 0
                    and bool(entry["jockey"])
                )

                candidates += int(confirmed_candidate)
                pending += int(not confirmed_candidate)

                status = (
                    "CANDIDATO CON DORSAL Y JINETE"
                    if confirmed_candidate
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
        f"Jornadas: {len(TEST_MEETINGS)} | "
        f"Carreras: {len(races)} | "
        f"Caballos leidos: {total}",
        flush=True,
    )

    print(
        f"Coincidencias: {matches} | "
        f"Candidatos con dorsal y jinete: "
        f"{candidates} | "
        f"Pendientes: {pending}",
        flush=True,
    )

    if total == 0:
        raise RuntimeError(
            "CERO CABALLOS LEIDOS: no publicar"
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
