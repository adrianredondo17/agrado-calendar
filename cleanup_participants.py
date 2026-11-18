
"""Limpia participaciones finalizadas del calendario Agrado.

- Retira inmediatamente una participación si la victoria
  correspondiente ya está registrada.
- Conserva las demás durante 3 días después de la carrera.
- No modifica calendar.json sin --publish.
"""

import argparse
import json
import unicodedata
import re

from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


CALENDAR = Path("calendar.json")
RETENTION_DAYS = 3


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


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--publish",
        action="store_true"
    )

    args = parser.parse_args()

    data = json.loads(
        CALENDAR.read_text(encoding="utf-8")
    )

    today = datetime.now(
        ZoneInfo("Europe/Madrid")
    ).date()

    participants = data.get("participants", [])
    wins = data.get("wins", [])

    if not isinstance(participants, list):
        raise ValueError(
            "El campo participants no es una lista"
        )

    if not isinstance(wins, list):
        raise ValueError(
            "El campo wins no es una lista"
        )

    known_wins = {
        (
            str(win.get("date", "")),
            norm(win.get("horse", ""))
        )
        for win in wins
        if isinstance(win, dict)
    }

    active = []
    removed = []

    for participant in participants:
        race_date = date.fromisoformat(
            participant["date"]
        )

        horse = participant.get(
            "horse",
            "Desconocido"
        )

        key = (
            participant["date"],
            norm(horse)
        )

        # Si ya figura como victoria, retirar participación.
        if key in known_wins:
            removed.append((
                participant,
                "Victoria registrada"
            ))
            continue

        # Conservar participaciones de hoy y futuras.
        if race_date >= today:
            active.append(participant)
            continue

        # Conservar hasta 3 días tras la carrera.
        if today <= race_date + timedelta(
            days=RETENTION_DAYS
        ):
            active.append(participant)

            print(
                f"EN ESPERA DE RESULTADOS | {horse} | "
                f"{participant['date']}",
                flush=True
            )
            continue

        # Retirar participaciones antiguas.
        removed.append((
            participant,
            "Plazo de espera finalizado"
        ))

    print(
        f"FECHA ACTUAL | {today.isoformat()}",
        flush=True
    )

    print(
        f"PARTICIPACIONES CONSERVADAS | {len(active)}",
        flush=True
    )

    print(
        f"PARTICIPACIONES RETIRADAS | {len(removed)}",
        flush=True
    )

    for participant, reason in removed:
        print(
            f"RETIRAR | "
            f"{participant.get('horse', 'Desconocido')} | "
            f"{reason}",
            flush=True
        )

    if not args.publish:
        print(
            "MODO PRUEBA | Sin cambios",
            flush=True
        )
        return

    if removed:
        data["participants"] = active

        data["lastUpdated"] = datetime.now(
            ZoneInfo("UTC")
        ).isoformat()

        CALENDAR.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2
            ) + "\n",
            encoding="utf-8"
        )

    print(
        "LIMPIEZA COMPLETADA",
        flush=True
    )


if __name__ == "__main__":
    main()
