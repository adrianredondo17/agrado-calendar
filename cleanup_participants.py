
import argparse
import json
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

CALENDAR = Path("calendar.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    data = json.loads(CALENDAR.read_text(encoding="utf-8"))

    today = datetime.now(
        ZoneInfo("Europe/Madrid")
    ).date()

    participants = data.get("participants", [])

    if not isinstance(participants, list):
        raise ValueError("El campo participants no es una lista")

    active = []
    removed = []

    for participant in participants:
        race_date = date.fromisoformat(participant["date"])

        if race_date < today:
            removed.append(participant)
        else:
            active.append(participant)

    print(f"FECHA ACTUAL | {today.isoformat()}")
    print(f"PARTICIPACIONES ACTIVAS | {len(active)}")
    print(f"PARTICIPACIONES FINALIZADAS | {len(removed)}")

    for participant in removed:
        horse = participant.get("horse", "Desconocido")
        print(f"RETIRAR DEL CALENDARIO | {horse}")

    if not args.publish:
        print("MODO PRUEBA | Sin cambios")
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

    print("LIMPIEZA COMPLETADA")


if __name__ == "__main__":
    main()
