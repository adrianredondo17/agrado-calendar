
"""Yeguada Agrado - enlaces automáticos de victorias.

Busca resultados históricos en Todoturf mediante:
1. Historiales de productos.
2. Jornadas por fecha e hipódromo.
3. Verificación del ganador en cada carrera.

No crea ni elimina victorias.
No publica coincidencias ambiguas.
Solo escribe calendar.json con --publish.
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
    "PINEDA": "DOS HERMANAS",
}

COUNTRIES = (
    "FR", "GB", "IRE", "USA", "ITY",
    "GER", "SPA", "ESP", "POR",
)


def clean_name(value):
    value = str(value or "").strip()

    value = re.sub(
        r",\s*20\d{2}$",
        "",
        value,
    )

    value = re.sub(
        r"\s*\((" + "|".join(COUNTRIES) + r")\)$",
        "",
        value,
        flags=re.I,
    )

    return norm(value)


def race_identity(url):
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    if not parsed.path.endswith("/resultados3.php"):
        return None

    if params.get("pais", [""])[0].upper() != "ESP":
        return None

    number = params.get("numero", [""])[0]
    day = params.get("fecha", [""])[0][:10]
    kind = params.get("tipo", [""])[0]

    if not number or not day or not kind:
        return None

    return (day, number, kind.upper())


def unique_urls(urls):
    result = {}

    for url in urls:
        identity = race_identity(url)

        if identity:
            result.setdefault(identity, url)

    return list(result.values())


def is_spanish(win):
    source = str(win.get("source", ""))
    venue = norm(win.get("venue", ""))

    if source in (
        "historical_squarespace_2026",
        "todoturf_auto",
    ):
        return True

    return any(
        value in venue
        for value in (
            "ESPANA",
            "LA ZARZUELA",
            "MADRID",
            "SAN SEBASTIAN",
            "DOS HERMANAS",
            "LASARTE",
        )
    )


def venue_name(win):
    value = norm(win.get("venue", ""))

    for key, venue in VENUES.items():
        if key in value:
            return venue

    return None


def history_results(horse_url):
    soup = get(horse_url)
    results = []

    for table in soup.find_all("table"):
        header = norm(" ".join(
            th.get_text(" ", strip=True)
            for th in table.select("th")
        ))

        if not all(
            key in header
            for key in ("FECHA", "HIPODROMO", "POS")
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

            if race_identity(url):
                results.append({
                    "date": day,
                    "url": url,
                })

        break

    return results


def build_index():
    index = defaultdict(list)
    known_horses = defaultdict(set)

    for sire in STALLIONS:
        horses = products(sire)

        for identifier, horse_url in horses.items():
            parsed = urlparse(horse_url)

            raw_name = parse_qs(
                parsed.query
            ).get("nombrecaballo", [""])[0]

            name = clean_name(raw_name)
            sire_key = norm(sire)

            known_horses[
                (sire_key, name)
            ].add(identifier)

            try:
                results = history_results(horse_url)

            except Exception as exc:
                print(
                    f"AVISO HISTORIAL | "
                    f"{raw_name} | {exc}",
                    flush=True,
                )
                continue

            for result in results:
                index[
                    (result["date"], name, sire_key)
                ].append({
                    "url": result["url"],
                    "identifier": identifier,
                })

    return index, known_horses


def result_links(soup, day):
    found = []

    for anchor in soup.select(
        'a[href*="resultados3.php"]'
    ):
        url = urljoin(
            BASE,
            anchor.get("href", ""),
        )

        identity = race_identity(url)

        if identity and identity[0] == day:
            found.append(url)

    return unique_urls(found)


def meeting_urls(day, venue):
    dates = [
        day + " 00:00:00",
        day,
    ]

    urls = []

    for date_value in dates:
        params = {
            "fecha": date_value,
            "hipodromo": venue,
        }

        urls.append(
            BASE + "resultados2.php?"
            + urlencode(params)
        )

    return urls


def discover_meeting(day, venue):
    urls = []

    for meeting_url in meeting_urls(day, venue):
        try:
            soup = get(meeting_url)

            urls.extend(
                result_links(soup, day)
            )

        except Exception as exc:
            print(
                f"AVISO JORNADA | "
                f"{meeting_url} | {exc}",
                flush=True,
            )

    urls = unique_urls(urls)

    print(
        f"JORNADA | {day} | {venue} | "
        f"carreras={len(urls)}",
        flush=True,
    )

    return urls


def winner_names(soup):
    """Lee los nombres visibles de los ganadores.

    Todoturf puede mostrar:
        PRETTY ROSE (FR)

    Aunque el identificador interno sea:
        PRETTY ROSE II

    Para comparar con el calendario debemos
    utilizar el nombre visible.
    """

    winners = set()

    for table in soup.find_all("table"):
        headers = [
            norm(th.get_text(" ", strip=True))
            for th in table.select("thead th")
        ]

        # Solo analizar la tabla de resultados.
        if not (
            len(headers) >= 2
            and headers[0].rstrip(".") == "P"
            and headers[1] == "CABALLO"
        ):
            continue

        for row in table.select("tbody tr"):
            cells = row.find_all("td")

            if len(cells) < 2:
                continue

            position = cells[0].get_text(
                " ", strip=True
            )

            # El ganador aparece con posición 1.
            if position != "1":
                continue

            anchor = cells[1].select_one(
                'a[href*="historialcaballo2.php"]'
            )

            if not anchor:
                continue

            # Leer el texto mostrado en la tabla.
            visible_name = anchor.get_text(
                " ", strip=True
            )

            horse_name = clean_name(visible_name)

            if horse_name:
                winners.add(horse_name)

    return winners


def verify_by_name(url, horse):
    """Comprueba el nombre exacto del ganador.

    No acepta coincidencias parciales.
    La filiación debe estar previamente
    respaldada por el calendario.
    """

    soup = get(url)
    target = clean_name(horse)

    if not target:
        return False

    heading = soup.find(
        lambda tag:
        tag.name in ("h1", "h2", "h3", "h4", "h5")
        and "PREMIO" in norm(
            tag.get_text(" ", strip=True)
        )
    )

    if heading is None:
        return False

    winners = winner_names(soup)

    return target in winners


def verify_candidate(url, win, known_horses):
    identity = race_identity(url)

    if not identity:
        return False

    if identity[0] != str(win.get("date", "")):
        return False

    horse = str(win.get("horse", ""))
    sire = norm(win.get("stallion", ""))

    known_ids = known_horses.get(
        (sire, clean_name(horse)),
        set(),
    )

    # Primero comprobar directamente el nombre
    # visible del ganador en la carrera.
    if not verify_by_name(url, horse):
        return False

    # Si hay identificadores conocidos, realizar
    # también la comprobación del historial.
    if known_ids:
        for identifier in known_ids:
            try:
                verified = verify_result(
                    {"url": url},
                    identifier,
                )

                if verified:
                    return True

            except Exception:
                continue

        # El nombre visible ya está confirmado,
        # pero el identificador puede diferir.
        # No aceptar automáticamente un conflicto
        # con un identificador conocido.
        return False

    # Si el listado de productos no proporciona
    # identificador, utilizar el nombre visible.
    return True


def find_from_history(win, index):
    key = (
        str(win.get("date", "")),
        clean_name(win.get("horse", "")),
        norm(win.get("stallion", "")),
    )

    valid = []

    for candidate in index.get(key, []):
        try:
            verified = verify_result(
                candidate,
                candidate["identifier"],
            )

            if verified:
                valid.append(candidate["url"])

        except Exception as exc:
            print(
                f"AVISO VERIFICACION HISTORIAL | "
                f"{win.get('horse')} | {exc}",
                flush=True,
            )

    return unique_urls(valid)


def find_from_meeting(
    win,
    known_horses,
    meeting_cache,
):
    day = str(win.get("date", ""))
    venue = venue_name(win)

    if not venue:
        print(
            f"HIPODROMO DESCONOCIDO | "
            f"{win.get('horse')} | "
            f"{win.get('venue')}",
            flush=True,
        )
        return []

    cache_key = (day, venue)

    if cache_key not in meeting_cache:
        meeting_cache[cache_key] = (
            discover_meeting(day, venue)
        )

    valid = []

    for url in meeting_cache[cache_key]:
        try:
            if verify_candidate(
                url, win, known_horses
            ):
                valid.append(url)

        except Exception as exc:
            print(
                f"AVISO CARRERA | {url} | {exc}",
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
        f"VICTORIAS PENDIENTES | "
        f"{len(pending)}",
        flush=True,
    )

    if not pending:
        print("SIN CAMBIOS", flush=True)
        return

    index, known_horses = build_index()
    meeting_cache = {}

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

        valid = find_from_history(
            win, index
        )

        # Si el historial no encuentra una
        # coincidencia única, buscar la jornada.
        if len(valid) != 1:
            fallback = find_from_meeting(
                win,
                known_horses,
                meeting_cache,
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
        existing = win.get("url", "")

        if existing:
            if race_identity(existing) != (
                race_identity(result_url)
            ):
                unmatched += 1

                print(
                    f"CONFLICTO | {horse} | {day}",
                    flush=True,
                )
                continue

        matched += 1

        if not existing:
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
        f"pendientes={len(pending)} "
        f"encontradas={matched} "
        f"sin_coincidencia={unmatched} "
        f"campos_actualizados={changes}",
        flush=True,
    )

    if not args.publish:
        print(
            "MODO PRUEBA | "
            "calendar.json intacto",
            flush=True,
        )
        return

    if changes:
        data["lastUpdated"] = (
            datetime.now(timezone.utc).isoformat()
        )

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
