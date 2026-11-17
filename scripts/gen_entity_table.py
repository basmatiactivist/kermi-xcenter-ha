"""Regenerate the entity table in README.md (PYTHONPATH=. python scripts/gen_entity_table.py)."""

import json
import re
from pathlib import Path

from custom_components.kermi_xcenter.binary_sensor import BINARY_SENSORS
from custom_components.kermi_xcenter.datapoints import DATAPOINTS_BY_KEY, ROLE_DEVICE_NAMES
from custom_components.kermi_xcenter.sensor import SENSORS

DE = json.loads(Path("custom_components/kermi_xcenter/translations/de.json").read_text("utf-8"))
DEVICE = {
    "heat_pump": "x-change dynamic pro (40)",
    "heating": "Heizen (50)",
    "dhw": "Trinkwassererwärmung (51)",
}


def _source(desc) -> str:
    keys = desc.datapoints
    if len(keys) > 4:
        return f"{len(keys)} Sperr-Datenpunkte (siehe Anleitung)"
    parts = []
    for key in keys:
        dp = DATAPOINTS_BY_KEY[key]
        text = f"„{dp.display_name}“" if dp.display_name else ""
        if dp.wkn:
            text += (" / " if text else "") + f"`{dp.wkn}`"
        parts.append(text)
    return " + ".join(parts)


def rows() -> list[str]:
    out = [
        "| Gerät | Entität | Typ | Einheit | State class | Quelle (Kermi-Gerät → DisplayName / WellKnownName) | Standard |",
        "|---|---|---|---|---|---|---|",
    ]
    for platform, descs in (("sensor", SENSORS), ("binary_sensor", BINARY_SENSORS)):
        for d in descs:
            classic = all(
                (DATAPOINTS_BY_KEY[k].wkn or "").startswith("HP_")
                and not DATAPOINTS_BY_KEY[k].display_name
                for k in d.datapoints
            )
            unit = (
                getattr(d, "suggested_unit_of_measurement", None)
                or getattr(d, "native_unit_of_measurement", None)
                or ""
            )
            if getattr(d, "device_class", None) == "enum":
                unit = "Auswahl"
            sc = getattr(d, "state_class", None)
            typ = platform + (f" ({d.device_class})" if d.device_class else "")
            default = "an" if d.entity_registry_enabled_default else "aus"
            if classic:
                default += ", nur klassische Firmware"
            out.append(
                f"| {ROLE_DEVICE_NAMES[d.role]} | {DE['entity'][platform][d.translation_key]['name']} "
                f"| {typ} | {unit} | {sc.value if sc else ''} "
                f"| {DEVICE[d.role.value]} → {_source(d)} | {default} |"
            )
    return out


if __name__ == "__main__":
    readme = Path("README.md")
    text = readme.read_text("utf-8")
    table = "\n".join(rows())
    new = re.sub(
        r"<!-- ENTITIES:START -->.*<!-- ENTITIES:END -->",
        f"<!-- ENTITIES:START -->\n{table}\n<!-- ENTITIES:END -->",
        text,
        flags=re.S,
    )
    readme.write_text(new, "utf-8")
