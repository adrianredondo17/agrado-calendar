
"""Completa automáticamente resultados y vídeos de victorias españolas.

1. Busca en los historiales de los productos de los sementales.
2. Si no encuentra una carrera, consulta los resultados de la jornada.
3. Verifica que el ganador corresponde al caballo.
4. No crea, elimina ni duplica victorias.
5. Solo modifica calendar.json con --publish.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import (
    parse_qs,
    urlencode,
    urljoin,
    urlparse,
)

from auto_wins import (
    BASE,
    STALLIONS,
    get,
    horse_link,
    norm,
    products,
    verify_result,
    get_video_url,
)

CALENDAR = Path("calendar.json")

VENUES = {
    "LA ZARZUELA": "LA ZARZUELA",
    "MADRID": "LA ZARZUELA",
    "SAN SEBASTIAN": "SAN SEBASTIAN",
    "LASARTE": "SAN SEBASTIAN",
    "DOS HERMANAS": "DOS HERMANAS",
    "GRAN HIPODROMO DE ANDALUCIA": "DOS HERMANAS",
    "PINEDA": "DOS HERMANAS",
}


def clean_name(value):
    value = re.sub(
        r",\s*20\d{2}$",
        "",
        str(value),
    ).strip()

    value = re.sub(
        r"\s*\((FR|GB|IRE|USA|ITY|GER|SPA|ESP|POR)\)$",
        "",
        value,
        flags=re.I,
    ).strip()

    return norm(value)


def race_key(url):
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    if not parsed.path.endswith("/resultados3.php"):
        return None

    if params.get("pais", [""])[0].upper() != "ESP":
        return None

    number = params.get("numero", [""])[0]
    day = params.get("fecha", [""])[0][:10]

    if not number or not day:
        return None

    return (day, number)


def unique_urls(urls):
    found = {}

    for url in urls:
        key = race_key(url)

        if key:
            found.setdefault(key, url)

    return list(found.values())


def history_results(horse_url):
    soup = get(horse_url)
    results = []

    for table in soup.find_all("table"):
        header = norm(" ".join(
            th.get_text(" ", strip=True)
            for th in table.select("th")
        ))

        if not all(
            word in header
            for word in ("FECHA", "HIPODROMO", "POS")
        ):
            continue

        for row in table.select("tr"):
            cells = row.find_all("td")

            if len(cells) < 9:
                continue

            try:
                day = datetime.strptime(
                    cells[0].get_text(" ", strip=True),
                    "%d/%m/%Y",
                ).date().isoformat()
            except ValueError:
                continue

            position = cells[4].get_text(
                " ", strip=True
            )

            if not re.fullmatch(
                r"1\s*/\s*\d+",
                position,
            ):
                continue

            anchor = cells[0].select_one(
                'a[href*="resultados3.php"]'
            )

            if not anchor:
                continue

            url = urljoin(BASE, anchor["href"])

            if race_key(url):
                results.append({
                    "date": day,
                    "url": url,
                })

        break

    return results


def build_index():
    index = defaultdict(list)
    horse_ids = defaultdict(set)
    checked = set()

    for sire in STALLIONS:
        horses = products(sire)

        for identifier, horse_url in horses.items():
            if (sire, identifier) in checked:
                continue

            checked.add((sire, identifier))

            parsed = urlparse(horse_url)
            raw_name = parse_qs(
                parsed.query
            ).get("nombrecaballo", [""])[0]

            name = clean_name(raw_name)

            horse_ids[(norm(sire), name)].add(
                identifier
            )

            try:
                results = history_results(horse_url)
            except Exception as exc:
                print(
                    f"AVISO HISTORIAL | {raw_name} | {exc}",
                    flush=True,
                )
                continue

            for result in results:
                key = (result["date"], name)

                index[key].append({
                    "url": result["url"],
                    "identifier": identifier,
                    "stallion": norm(sire),
                })

    print(
        f"INDICE | caballos={len(checked)} "
        f"claves={len(index)}",
        flush=True,
    )

    return index, horse_ids


def is_spanish(win):
    venue = norm(win.get("venue", ""))
    source = str(win.get("source", ""))

    if source in (
        "historical_squarespace_2026",
        "todoturf_auto",
    ):
        return True

    return any(
        word in venue
        for word in (
            "ESPANA",
            "LA ZARZUELA",
            "MADRID",
            "DOS HERMANAS",
            "SAN SEBASTIAN",
            "LASARTE",
        )
    )


def venue_code(win):
    venue = norm(win.get("venue", ""))

    for key, code in VENUES.items():
        if key in venue:
            return code

    return None


def meeting_urls(win):
    day = str(win.get("date", ""))
    venue = venue_code(win)

    if not venue or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", day
    ):
        return []

    dates = [
        day + " 00:00:00",
        day,
    ]

    return [
        BASE + "resultados2.php?" + urlencode({
            "fecha": date_value,
            "hipodromo": venue,
        })
        for date_value in dates
    ]


def extract_race_urls(soup, expected_day):
    urls = []

    for anchor in soup.select(
        'a[href*="resultados3.php"]'
    ):
        url = urljoin(
            BASE,
            anchor.get("href", ""),
        )

        key = race_key(url)

        if key and key[0] == expected_day:
            urls.append(url)

    return unique_urls(urls)


def find_meeting_results(win):
    day = str(win.get("date", ""))
    found = []

    for meeting_url in meeting_urls(win):
        try:
            soup = get(meeting_url)

            found.extend(
                extract_race_urls(soup, day)
            )

        except Exception as exc:
            print(
                f"AVISO JORNADA | {day} | {exc}",
                flush=True,
            )

    found = unique_urls(found)

    print(
        f"JORNADA | {day} | "
        f"{win.get('venue', '')} | "
        f"carreras={len(found)}",
        flush=True,
    )

    return found


def winner_identifiers(soup):
    """Extrae los identificadores de los ganadores
    de la tabla de resultados.
    """
    winners = set()

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")

            if len(cells) < 2:
                continue

            position = cells[0].get_text(
                " ", strip=True
            )

            if position != "1":
                continue

            for anchor in cells[1].select("a[href]"):
                result = horse_link(anchor)

                if result:
                    _, identifier = result
                    winners.add(identifier)

    return winners


def verified_from_index(win, index):
    key = (
        str(win.get("date", "")),
        clean_name(win.get("horse", "")),
    )

    sire = norm(win.get("stallion", ""))
    candidates = index.get(key, [])
    valid = []

    for candidate in candidates:
        if candidate["stallion"] != sire:
            continue

        try:
            verify_result(
                candidate,
                candidate["identifier"],
            )

            valid.append(candidate["url"])

        except Exception as exc:
            print(
                f"NO VERIFICADO HISTORIAL | "
                f"{win.get('horse')} | {exc}",
                flush=True,
            )

    return unique_urls(valid)


def verified_from_meeting(win, horse_ids):
    sire = norm(win.get("stallion", ""))
    name = clean_name(win.get("horse", ""))

    identifiers = horse_ids.get(
        (sire, name), set()
    )

    if not identifiers:
        print(
            f"SIN IDENTIFICADOR | "
            f"{win.get('horse')} | {sire}",
            flush=True,
        )
        return []

    valid = []

    for url in find_meeting_results(win):
        try:
            soup = get(url)
            winners = winner_identifiers(soup)

            matching = winners.intersection(
                identifiers
            )

            if not matching:
                continue

            # Verificación adicional mediante
            # la función existente.
            for identifier in matching:
                verify_result(
                    {"url": url},
                    identifier,
                )

                valid.append(url)
                break

        except Exception as exc:
            print(
                f"AVISO VERIFICACION | {url} | {exc}",
                flush=True,
            )

    return unique_urls(valid)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--publish",
        action="store_true",
    )

    args = parser.parse_args()

    data = json.loads(
        CALENDAR.read_text(encoding="utf-8")
    )

    wins = data.get("wins", [])

    if not isinstance(wins, list):
        raise ValueError(
            "wins debe ser una lista"
        )

    pending = [
        win for win in wins
        if isinstance(win, dict)
        and is_spanish(win)
        and (
            not win.get("url")
            or not win.get("video_url")
        )
    ]

    print(
        f"VICTORIAS PENDIENTES | {len(pending)}",
        flush=True,
    )

    if not pending:
        print("SIN CAMBIOS", flush=True)
        return

    index, horse_ids = build_index()

    changes = 0
    matched = 0
    unmatched = 0

    for win in pending:
        horse = str(win.get("horse", ""))
        day = str(win.get("date", ""))

        print(
            f"REVISANDO | {horse} | {day}",
            flush=True,
        )

        valid = verified_from_index(
            win, index
        )

        # Segunda búsqueda cuando el historial
        # no ofrece una coincidencia única.
        if len(valid) != 1:
            fallback = verified_from_meeting(
                win, horse_ids
            )

            valid = unique_urls(
                valid + fallback
            )

        if len(valid) != 1:
            unmatched += 1

            print(
                f"SIN COINCIDENCIA UNICA | "
                f"{horse} | {day} | "
                f"opciones={len(valid)}",
                flush=True,
            )
            continue

        result_url = valid[0]
        existing_url = win.get("url", "")

        # Comparamos la identidad de la carrera,
        # no solo el formato de la URL.
        if existing_url:
            if race_key(existing_url) != race_key(
                result_url
            ):
                print(
                    f"CONFLICTO DE ENLACE | "
                    f"{horse} | {day}",
                    flush=True,
                )
                unmatched += 1
                continue

        matched += 1

        if not existing_url:
            win["url"] = result_url
            changes += 1

            print(
                f"RESULTADOS | {horse} | "
                f"{result_url}",
                flush=True,
            )

        if not win.get("video_url"):
            video = get_video_url(result_url)

            if video:
                win["video_url"] = video
                changes += 1

                print(
                    f"REPETICION | {horse} | "
                    f"{video}",
                    flush=True,
                )

    print(
        f"RESUMEN | "
        f"victorias_pendientes={len(pending)} "
        f"coincidencias={matched} "
        f"sin_coincidencia={unmatched} "
        f"campos_actualizados={changes}",
        flush=True,
    )

    if not args.publish:
        print(
            "MODO PRUEBA | "
            "No se modifica calendar.json",
            flush=True,
        )
        return

    if changes:
        data["lastUpdated"] = datetime.now(
            timezone.utc
        ).isoformat()

        CALENDAR.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    print(
        "PROCESO COMPLETADO",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        print(
            "ERROR: " + str(exc),
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
