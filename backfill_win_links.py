
"""Completa enlaces de resultados y vídeos de victorias españolas.

Busca las carreras en los historiales de Todoturf.
Verifica el ganador antes de asociar un enlace.
No crea ni elimina victorias.
Solo publica cambios con --publish.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

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
                race_date = datetime.strptime(
                    cells[0].get_text(" ", strip=True),
                    "%d/%m/%Y"
                ).date().isoformat()
            except ValueError:
                continue

            position = cells[4].get_text(
                " ", strip=True
            )

            if not re.fullmatch(r"1\s*/\s*\d+", position):
                continue

            anchor = cells[0].select_one(
                'a[href*="resultados3.php"]'
            )

            if not anchor:
                continue

            url = urljoin(BASE, anchor["href"])
            parsed = urlparse(url)
            params = parse_qs(parsed.query)

            if params.get("pais", [""])[0].upper() != "ESP":
                continue

            results.append({
                "date": race_date,
                "url": url,
            })

        break

    return results


def build_index():
    index = {}
    checked = set()

    for sire in STALLIONS:
        for identifier, horse_url in products(sire).items():
            if identifier in checked:
                continue

            checked.add(identifier)

            parsed = urlparse(horse_url)
            horse_name = parse_qs(parsed.query).get(
                "nombrecaballo", [""]
            )[0]

            horse_name = re.sub(
                r",\s*20\d{2}$", "", horse_name
            ).strip()

            horse_name = re.sub(
                r"\s*\((FR|GB|IRE|USA|ITY|GER|SPA|ESP|POR)\)$",
                "",
                horse_name,
                flags=re.I
            ).strip()

            for result in history_results(horse_url):
                key = (
                    result["date"],
                    norm(horse_name)
                )

                index.setdefault(key, []).append({
                    "url": result["url"],
                    "identifier": identifier,
                    "stallion": sire,
                })

    return index


def is_spanish(win):
    venue = norm(win.get("venue", ""))
    source = str(win.get("source", ""))

    return (
        source in (
            "historical_squarespace_2026",
            "todoturf_auto"
        )
        or "ESPANA" in venue
        or "LA ZARZUELA" in venue
        or "DOS HERMANAS" in venue
        or "SAN SEBASTIAN" in venue
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    data = json.loads(
        CALENDAR.read_text(encoding="utf-8")
    )

    wins = data.get("wins", [])

    if not isinstance(wins, list):
        raise ValueError("wins debe ser una lista")

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
        flush=True
    )

    if not pending:
        print("SIN CAMBIOS", flush=True)
        return

    index = build_index()
    changes = 0

    for win in pending:
        horse = win.get("horse", "")
        day = win.get("date", "")
        sire = norm(win.get("stallion", ""))

        key = (day, norm(horse))
        candidates = index.get(key, [])

        valid_urls = []

        for candidate in candidates:
            if norm(candidate["stallion"]) != sire:
                continue

            try:
                verify_result(
                    candidate,
                    candidate["identifier"]
                )
                valid_urls.append(candidate["url"])
            except Exception as exc:
                print(
                    f"NO VERIFICADO | {horse} | {exc}",
                    flush=True
                )

        valid_urls = list(dict.fromkeys(valid_urls))

        # Nunca asociar una carrera ambigua.
        if len(valid_urls) != 1:
            print(
                f"SIN COINCIDENCIA ÚNICA | {horse} | "
                f"{day} | opciones={len(valid_urls)}",
                flush=True
            )
            continue

        result_url = valid_urls[0]

        # No sustituir enlaces existentes a otra carrera.
        existing_url = win.get("url", "")

        if existing_url and existing_url != result_url:
            print(
                f"CONFLICTO DE ENLACE | {horse} | {day}",
                flush=True
            )
            continue

        if not existing_url:
            win["url"] = result_url
            changes += 1

            print(
                f"RESULTADOS | {horse} | {result_url}",
                flush=True
            )

        if not win.get("video_url"):
            video = get_video_url(result_url)

            if video:
                win["video_url"] = video
                changes += 1

                print(
                    f"REPETICION | {horse} | {video}",
                    flush=True
                )

    print(
        f"RESUMEN | campos actualizados={changes}",
        flush=True
    )

    if not args.publish:
        print(
            "MODO PRUEBA | No se modifica calendar.json",
            flush=True
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
                indent=2
            ) + "\n",
            encoding="utf-8"
        )

    print("PROCESO COMPLETADO", flush=True)


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
