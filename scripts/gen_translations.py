"""Generate strings.json and translations/{en,de}.json (run from the repo root)."""

import json
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "custom_components/kermi_xcenter"
S = {  # key: (en, de)
    "thermal_power": ("Thermal power", "Wärmeleistung"),
    "thermal_power_heating": ("Thermal power heating", "Wärmeleistung Heizen"),
    "thermal_power_dhw": ("Thermal power hot water", "Wärmeleistung Warmwasser"),
    "electrical_power": ("Electrical power", "Elektrische Leistung"),
    "electrical_power_heating": ("Electrical power heating", "Elektrische Leistung Heizen"),
    "electrical_power_dhw": ("Electrical power hot water", "Elektrische Leistung Warmwasser"),
    "cop": ("COP", "COP"),
    "cop_heating": ("COP heating", "COP Heizen"),
    "cop_dhw": ("COP hot water", "COP Warmwasser"),
    "requested_power_heating": ("Requested power heating", "Leistungsanforderung Heizen"),
    "requested_power_dhw": ("Requested power hot water", "Leistungsanforderung Warmwasser"),
    "heat_pump_state": ("Heat pump state (code)", "Status Wärmepumpe (Code)"),
    "state_since": ("State since", "Status seit"),
    "flow_temp": ("Flow temperature (B16)", "Vorlauftemperatur (B16)"),
    "return_temp": ("Return temperature (B17)", "Rücklauftemperatur (B17)"),
    "air_inlet_temp": ("Air inlet temperature (B15)", "Lufteintrittstemperatur (B15)"),
    "air_outlet_temp": ("Air outlet temperature (B14)", "Luftaustrittstemperatur (B14)"),
    "outdoor_temp_hp": ("Outdoor temperature sensor (BOT)", "Außentemperaturfühler (BOT)"),
    "spread": ("Temperature spread", "Spreizung"),
    "flow_rate": ("Flow rate (P13)", "Durchfluss (P13)"),
    "required_flow_rate": ("Required flow rate", "Erforderlicher Durchfluss"),
    "fan_speed": ("Required fan speed", "Lüfterdrehzahl (Soll)"),
    "charging_pump_power": ("Charging pump power", "Leistung Speicherladepumpe"),
    "compressor_starts": ("Compressor starts", "Verdichterstarts"),
    "hours_compressor": ("Run hours compressor", "Betriebsstunden Verdichter"),
    "hours_fan": ("Run hours fan", "Betriebsstunden Lüfter"),
    "hours_charging_pump": ("Run hours charging pump", "Betriebsstunden Speicherladepumpe"),
    "software_version": ("Software version", "Softwareversion"),
    "outdoor_temp": ("Outdoor temperature", "Außentemperatur"),
    "outdoor_temp_avg": ("Outdoor temperature (averaged)", "Außentemperatur (gemittelt)"),
    "outdoor_temp_season": ("Outdoor temperature (season)", "Außentemperatur (Saison)"),
    "circuit_temp": ("Heating circuit temperature", "Heizkreis Isttemperatur"),
    "circuit_setpoint": ("Heating circuit setpoint", "Heizkreis Solltemperatur"),
    "buffer_temp": ("Buffer temperature", "Pufferspeicher Isttemperatur"),
    "buffer_setpoint": ("Buffer setpoint", "Pufferspeicher Solltemperatur"),
    "mixer_position": ("Mixer position", "Mischeröffnung"),
    "energy_mode": ("Energy mode", "Energiemodus"),
    "circuit_pump_hours": ("Run hours heating circuit pump", "Betriebsstunden Heizkreispumpe"),
    "heater_power": ("Heater power (external heat generator)", "Heizstab Leistung (ext. WEZ)"),
    "heater_hours": ("Run hours heater (external heat generator)", "Laufzeit Heizstab (ext. WEZ)"),
    "operation": ("Operating state", "Betriebszustand"),
    "compressor_blocks": ("Active compressor blocks", "Verdichtersperren aktiv"),
    "oil_return_countdown": ("Time until oil return", "Zeit bis Ölrückführung"),
    "energy_electric_total": ("Electrical energy total", "Strom gesamt"),
    "energy_heat_total": ("Heat energy total", "Wärme gesamt"),
    "energy_electric_heating": ("Electrical energy heating", "Strom Heizen gesamt"),
    "energy_electric_dhw": ("Electrical energy hot water", "Strom Warmwasser gesamt"),
    "scop": ("SCOP", "SCOP"),
    "cop_heating_avg": ("Average COP heating", "Durchschnittlicher COP Heizen"),
    "dhw_temp": ("Hot water temperature", "Warmwasser Isttemperatur"),
    "dhw_setpoint": ("Hot water setpoint", "Warmwasser Solltemperatur"),
    "dhw_one_time_setpoint": ("One-time charge setpoint", "Sollwert Einmalladung"),
}
B = {
    "compressor_blocked": ("Compressor blocked", "Verdichter gesperrt"),
    "oil_heating": ("Oil heating", "Ölheizung"),
    "compressor_start_preparing": (
        "Compressor start preparing",
        "Verdichterstart wird vorbereitet",
    ),
    "heating_active": ("Heating", "Heizbetrieb"),
    "dhw_active": ("Hot water charging", "Warmwasserbetrieb"),
    "cooling_active": ("Cooling", "Kühlbetrieb"),
    "defrosting": ("Defrosting", "Abtauung"),
    "pv_modulation": ("PV modulation", "PV-Modulation"),
    "global_alarm": ("Global alarm", "Globaler Alarm"),
    "global_warning": ("Global warning", "Globale Warnung"),
    "charging_pump": ("Charging pump", "Speicherladepumpe"),
    "summer_mode": ("Summer mode", "Sommerbetrieb"),
    "one_time_charge": ("One-time charge", "Einmalladung aktiv"),
}
EXC = {
    "invalid_auth": (
        "The x-center rejected the password.",
        "Das x-center hat das Passwort abgelehnt.",
    ),
    "catalogue_failed": (
        "The datapoint catalogue could not be loaded: {error}",
        "Der Datenpunkt-Katalog konnte nicht geladen werden: {error}",
    ),
    "no_datapoints": (
        "No known datapoints were found in the x-center catalogue.",
        "Im Katalog des x-center wurden keine bekannten Datenpunkte gefunden.",
    ),
    "update_failed": (
        "Reading from the x-center failed: {error}",
        "Lesen vom x-center fehlgeschlagen: {error}",
    ),
    "no_values": ("The x-center returned no values.", "Das x-center hat keine Werte geliefert."),
    "write_refused": (
        "Not sent to the heat pump: {reason}",
        "Nicht an die Wärmepumpe gesendet: {reason}",
    ),
    "write_failed": (
        "The heat pump did not accept the change: {reason}",
        "Die Wärmepumpe hat die Änderung nicht angenommen: {reason}",
    ),
    "unknown_option": ("Unknown option: {option}", "Unbekannte Option: {option}"),
}
BUTTON = {"dhw_one_time_charge_start": ("Heat up hot water once", "Warmwasser einmal aufheizen")}
NUMBER = {
    "dhw_one_time_setpoint_control": (
        "One-time charge setpoint (control)",
        "Sollwert Einmalladung (Steuerung)",
    ),
    "dhw_setpoint_control": ("Hot water setpoint (control)", "Warmwasser-Sollwert (Steuerung)"),
}
OPERATION = {
    "defrosting": ("Defrosting", "Abtauen"),
    "dhw": ("Hot water", "Warmwasser"),
    "heating": ("Heating", "Heizen"),
    "cooling": ("Cooling", "Kühlen"),
    "standby": ("Standby", "Bereit"),
}
MODES = {
    "off": ("Off", "Aus"),
    "eco": ("Eco", "Eco"),
    "normal": ("Normal", "Normal"),
    "comfort": ("Comfort", "Komfort"),
    "custom": ("Custom", "Benutzerdefiniert"),
}
T = {
    "en": dict(
        title_user="Connect Kermi x-center",
        desc_user="Local connection to the x-center web interface. Read-only by default; control must be enabled explicitly in the options.",
        host="Host",
        password="Password",
        host_desc="IP address or host name of the x-center, e.g. 192.168.1.50",
        pw_desc="Password of the x-center web interface",
        title_reconf="Change connection",
        desc_reconf="Change the host or password. Leave the password empty to keep the current one.",
        title_reauth="Password rejected",
        desc_reauth="The x-center at {host} rejected the stored password. Enter the current password.",
        cannot_connect="Cannot connect to the x-center.",
        invalid_host="Enter only an IP address or host name, optionally with :port.",
        invalid_auth="The x-center rejected the password.",
        unknown="Unexpected error.",
        already_configured="This x-center is already configured.",
        reconfigure_successful="The connection was updated.",
        reauth_successful="The password was updated.",
        wrong_device="This is a different x-center than the configured one.",
        allow_writes="Allow control (writes)",
        allow_writes_desc="Off by default. Only enable this if you really want Home Assistant to change settings on the heat pump.",
        title_confirm="Really allow control?",
        desc_confirm="WARNING: With this option Home Assistant can CHANGE settings on the heat pump: start a one-time hot water charge, set the hot water setpoints (40-55 °C) and switch the energy mode of the heating circuit. Wrong settings can cause discomfort, higher energy costs or legionella risk. The write path has NOT been tested on real hardware. Every write is limited to safe ranges and to one write per value every 5 minutes and is logged. Only confirm if you accept this risk.",
        confirm="I understand the risk and want to allow writes",
        confirm_required="Please tick the confirmation box, or go back and leave control disabled.",
        title_opts="Options",
        scan="Poll interval",
        scan_desc="Seconds between two reads (minimum 15). The x-center is polled gently; on errors the interval is backed off up to 15 minutes.",
    ),
    "de": dict(
        title_user="Kermi x-center verbinden",
        desc_user="Lokale Verbindung zur Weboberfläche des x-center. Standardmässig nur lesend; Steuerung muss in den Optionen ausdrücklich freigegeben werden.",
        host="Host",
        password="Passwort",
        host_desc="IP-Adresse oder Hostname des x-center, z. B. 192.168.1.50",
        pw_desc="Passwort der x-center-Weboberfläche",
        title_reconf="Verbindung ändern",
        desc_reconf="Host oder Passwort ändern. Passwort leer lassen, um das bisherige zu behalten.",
        title_reauth="Passwort abgelehnt",
        desc_reauth="Das x-center unter {host} hat das gespeicherte Passwort abgelehnt. Bitte aktuelles Passwort eingeben.",
        cannot_connect="Keine Verbindung zum x-center möglich.",
        invalid_host="Bitte nur IP-Adresse oder Hostname angeben, optional mit :Port.",
        invalid_auth="Das x-center hat das Passwort abgelehnt.",
        unknown="Unerwarteter Fehler.",
        already_configured="Dieses x-center ist bereits eingerichtet.",
        reconfigure_successful="Die Verbindung wurde aktualisiert.",
        reauth_successful="Das Passwort wurde aktualisiert.",
        wrong_device="Das ist ein anderes x-center als das eingerichtete.",
        allow_writes="Steuerung erlauben (Schreibzugriff)",
        allow_writes_desc="Standardmässig aus. Nur einschalten, wenn Home Assistant wirklich Einstellungen an der Wärmepumpe ändern soll.",
        title_confirm="Steuerung wirklich erlauben?",
        desc_confirm="ACHTUNG: Mit dieser Option kann Home Assistant Einstellungen an der Wärmepumpe ÄNDERN: Warmwasser-Einmalladung starten, Warmwasser-Sollwerte setzen (40–55 °C) und den Energiemodus des Heizkreises umschalten. Falsche Einstellungen können zu Komfortverlust, höheren Energiekosten oder Legionellenrisiko führen. Der Schreibweg ist an echter Hardware NICHT getestet. Jeder Schreibvorgang ist auf sichere Bereiche und auf höchstens einen Schreibvorgang pro Wert alle 5 Minuten begrenzt und wird protokolliert. Nur bestätigen, wenn du dieses Risiko bewusst eingehst.",
        confirm="Ich habe die Warnung verstanden und erlaube Schreibzugriffe",
        confirm_required="Bitte die Bestätigung ankreuzen oder zurückgehen und die Steuerung ausgeschaltet lassen.",
        title_opts="Optionen",
        scan="Abfrageintervall",
        scan_desc="Sekunden zwischen zwei Abfragen (mindestens 15). Bei Fehlern wird das Intervall bis auf 15 Minuten verlängert.",
    ),
}


def build(lang):
    t = T[lang]
    i = 0 if lang == "en" else 1
    sensor = {k: {"name": v[i]} for k, v in S.items()}
    sensor["energy_mode"]["state"] = {k: v[i] for k, v in MODES.items()}
    sensor["energy_mode"]["state_attributes"] = {
        "raw_value": {"name": "Raw value" if i == 0 else "Rohwert"}
    }
    sensor["operation"]["state"] = {k: v[i] for k, v in OPERATION.items()}
    sensor["operation"]["state_attributes"] = {
        "state_code": {"name": "State code" if i == 0 else "Statuscode"}
    }
    sensor["compressor_blocks"]["state_attributes"] = {
        "active": {"name": "Active blocks" if i == 0 else "Aktive Sperren"}
    }
    return {
        "config": {
            "step": {
                "user": {
                    "title": t["title_user"],
                    "description": t["desc_user"],
                    "data": {"host": t["host"], "password": t["password"]},
                    "data_description": {"host": t["host_desc"], "password": t["pw_desc"]},
                },
                "reconfigure": {
                    "title": t["title_reconf"],
                    "description": t["desc_reconf"],
                    "data": {"host": t["host"], "password": t["password"]},
                    "data_description": {"host": t["host_desc"], "password": t["pw_desc"]},
                },
                "reauth_confirm": {
                    "title": t["title_reauth"],
                    "description": t["desc_reauth"],
                    "data": {"password": t["password"]},
                    "data_description": {"password": t["pw_desc"]},
                },
            },
            "error": {
                k: t[k] for k in ("cannot_connect", "invalid_auth", "invalid_host", "unknown")
            },
            "abort": {
                k: t[k]
                for k in (
                    "already_configured",
                    "reconfigure_successful",
                    "reauth_successful",
                    "wrong_device",
                )
            },
        },
        "options": {
            "step": {
                "init": {
                    "title": t["title_opts"],
                    "data": {"scan_interval": t["scan"], "allow_writes": t["allow_writes"]},
                    "data_description": {
                        "scan_interval": t["scan_desc"],
                        "allow_writes": t["allow_writes_desc"],
                    },
                },
                "confirm_writes": {
                    "title": t["title_confirm"],
                    "description": t["desc_confirm"],
                    "data": {"confirm_writes": t["confirm"]},
                },
            },
            "error": {"confirm_required": t["confirm_required"]},
        },
        "exceptions": {k: {"message": v[i]} for k, v in EXC.items()},
        "entity": {
            "sensor": sensor,
            "binary_sensor": {k: {"name": v[i]} for k, v in B.items()},
            "button": {k: {"name": v[i]} for k, v in BUTTON.items()},
            "number": {k: {"name": v[i]} for k, v in NUMBER.items()},
            "select": {
                "energy_mode_control": {
                    "name": "Energy mode (control)" if i == 0 else "Energiemodus (Steuerung)",
                    "state": {k: v[i] for k, v in MODES.items() if k != "off"},
                }
            },
        },
    }


for name, lang in (
    ("strings.json", "en"),
    ("translations/en.json", "en"),
    ("translations/de.json", "de"),
):
    with open(f"{root}/{name}", "w", encoding="utf-8") as fh:
        json.dump(build(lang), fh, ensure_ascii=False, indent=2)
        fh.write("\n")
