# Kermi x-center (lokal) – Home Assistant Integration

Standardmässig rein **lesende** Home-Assistant-Integration für das Kermi **x-center** (z. B. Heim AG
«x-center pro» mit Wärmepumpe *x-change dynamic pro*). Sie liest die Werte direkt über die
lokale Weboberfläche des x-center (kein Modbus, keine Cloud) und stellt sie als Sensoren
und Binärsensoren in Home Assistant bereit.

> Dieses Projekt ist **nicht** mit der Kermi GmbH oder der Heim AG verbunden, wird von ihnen
> weder unterstützt noch geprüft. «Kermi», «x-center» und «x-change» sind Marken ihrer
> jeweiligen Inhaber.

## Unterstützte Anlagen

Die Datenpunkte stammen aus dem Live-Katalog **einer** Anlage:

- x-center Interfacemodul
- Wärmepumpe *x-change dynamic pro S AW E* mit **Rubin-Firmware** (WP 3.8.8)
- Puffermodule «Heizen» und «Trinkwassererwärmung» (1.5.33)

Einschränkungen:

- **Klassische x-center-Firmware wird nicht unterstützt.** Ältere Anlagen mit `HP_*`-Datenpunkten
  (z. B. Energiezähler in kWh, SCOP) haben andere Datenpunkte. Dort findet die Integration wenig oder
  nichts, und die Einrichtung bricht mit «keine bekannten Datenpunkte» ab. Für solche Anlagen eignet
  sich [kermi-ha-bridge](https://github.com/m-zenker/kermi-ha-bridge).
- **Gerätenamen:** Die Geräte werden über ihre Namen gefunden («x-change», «Heizen»,
  «Trinkwasser»), wie sie die deutschsprachige x-center-Oberfläche liefert. Bei anderen Namen
  fehlen die betroffenen Geräte. Die Wärmepumpe wird ersatzweise über ihren Gerätetyp erkannt.
- **Heizkreis:** Unterstützt wird ein Heizkreis.
- **Teststand:** Version 0.1.0 ist bisher nur gegen einen Nachbau der API getestet, der aus
  diesem Katalog gebaut ist. Erfahrungsberichte von anderen Anlagen sind willkommen, bitte als
  Issue mit heruntergeladenen Diagnosedaten. Diese sind geschwärzt.

## Standard: nur lesen – technisch erzwungen

Ohne ausdrückliche Freigabe wird an der Wärmepumpe **nie** etwas verändert. Das ist im Code
erzwungen und durch Tests abgesichert:

- Jeder Lesezugriff läuft durch genau eine Funktion (`KermiClient._request` in `api.py`).
  Diese prüft den Endpunkt gegen eine feste, unveränderliche Erlaubnisliste und bricht
  **vor jedem Netzwerkzugriff** ab, wenn der Endpunkt nicht darauf steht:

  | Endpunkt | Methode | Zweck |
  |---|---|---|
  | `Security/Login` | POST | Anmelden (Session-Cookie) |
  | `Security/Logout` | POST | Abmelden beim Entladen |
  | `Device/GetAllDevices` | GET | Geräteliste |
  | `Datapoint/GetConfigsByDeviceType` | POST | Datenpunkt-Katalog |
  | `Datapoint/ReadValues` | POST | Werte lesen |

- Im Standardbetrieb gibt es nur `sensor` und `binary_sensor`. Es werden keine Dienste
  registriert.
- Die Tests in `tests/test_readonly.py` durchsuchen den gesamten Quellcode der Integration.
  Der Schreib-Endpunkt darf darin genau **einmal** vorkommen, und zwar in der abgesicherten
  Funktion `KermiClient.write_value`. Jeder andere Endpunkt ausserhalb der Liste lässt den
  Test fehlschlagen.

## Optional: Steuerung (Schreibzugriff) – an echter Hardware NICHT getestet

> **Warnung:** Der Schreibweg ist nur gegen einen Nachbau der API getestet, **nie an einer
> echten Wärmepumpe**. Er ist standardmässig ausgeschaltet. Nutzung auf eigenes Risiko;
> Eingriffe in die Steuerung können Garantie- oder Gewährleistungsansprüche berühren.

Steuer-Entitäten gibt es nur, wenn in den **Optionen** «Steuerung erlauben» eingeschaltet
und im folgenden Warnschritt ausdrücklich bestätigt wurde. Ist die Option aus, existieren
diese Entitäten **gar nicht**, auch nicht deaktiviert. Beim Ausschalten werden sie entfernt.

| Entität | Gerät | Datenpunkt | Erlaubte Werte |
|---|---|---|---|
| Button «Warmwasser einmal aufheizen» | Kermi Warmwasser | `BufferSystem_OneTimeTwe` | nur «ein» (`true`) |
| Zahl «Sollwert Einmalladung (Steuerung)» | Kermi Warmwasser | `BufferSystem_OneTimeTweSetpoint` | 40–55 °C |
| Zahl «Warmwasser-Sollwert (Steuerung)» | Kermi Warmwasser | `BufferSystem_TemperatureSetpointTwe` | 40–55 °C |
| Auswahl «Energiemodus (Steuerung)» | Kermi Heizen | `HeatingCircuit_EnergyMode` | Eco, Normal, Komfort, Benutzerdefiniert (nie «Aus») |

Mehr ist nicht beschreibbar. Heizkurven, Verdichter, Alarme/Resets, Kühlung und
Installateur-Einstellungen sind bewusst ausgeschlossen.

Jeder Schreibvorgang läuft durch die eine abgesicherte Funktion `KermiClient.write_value`.
Sie verweigert, **bevor** etwas gesendet wird, wenn nicht alle vier Bedingungen erfüllt sind:

1. Die Option `allow_writes` ist eingeschaltet (Standard: aus).
2. Der Datenpunkt steht auf der Schreib-Erlaubnisliste (`datapoints.WRITABLE`).
3. Der Wert liegt innerhalb von MinValue/MaxValue aus dem Live-Katalog **und** innerhalb
   der eigenen, engeren Sicherheitsgrenzen. Liefert der Katalog keine Grenzen, wird
   verweigert.
4. Pro Datenpunkt ist höchstens ein Schreibvorgang alle 5 Minuten erlaubt.

Jeder Versuch wird auf Stufe INFO protokolliert, auch jede Verweigerung.

Offene Punkte für einen Test an echter Hardware:

- Die Feldnamen `MinValue`/`MaxValue` im Katalog sind nicht bestätigt. Fehlen sie,
  verweigert die Integration alle Zahlen- und Auswahl-Schreibvorgänge.
- Das Nutzlastformat (`$type`, `DatapointConfigId`, `DeviceId`, `Value`) stammt aus
  kermi-ha-bridge.

## Sicherheit

- **Netzwerk:** Das x-center spricht nur unverschlüsseltes HTTP. Passwort und Session-Cookie
  gehen im Klartext durchs lokale Netz. Betreibe es nur in einem vertrauenswürdigen Netz,
  am besten in einem eigenen VLAN für die Haustechnik, und gib es nie ins Internet frei.
- **Verbindung:** Die Integration folgt keinen HTTP-Weiterleitungen. Als Host akzeptiert
  sie nur einen Hostnamen oder eine IP-Adresse, optional mit Port, keine URL mit
  Zugangsdaten. Antworten über 2 MB werden verworfen, jede Anfrage bricht nach 15 s ab.
- **Diagnose:** In den Diagnosedaten sind Passwort, Host, Seriennummern und Geräte-IDs
  geschwärzt. Von der Geräteliste werden nur Name, Typ und ID übernommen.
- **Abhängigkeiten:** Es gibt keine Fremdabhängigkeiten ausser denen von Home Assistant.
  Die CI läuft mit fest gepinnten Actions und nur Leserechten, Dependabot hält die Pins
  aktuell.
- **Schwachstellen melden:** bitte vertraulich, siehe [SECURITY.md](SECURITY.md).

## Schonender Betrieb

- Abfrage standardmässig alle **30 s** (Option, mindestens 15 s).
- Gelesen werden nur Datenpunkte, die beim Start im Live-Katalog des Geräts gefunden wurden
  (Zuordnung über Gerätename + WellKnownName bzw. exakten DisplayName, keine fest
  einprogrammierten GUIDs), in Paketen von höchstens 40 Werten.
- Eine Anmeldung pro Sitzung. Läuft die Sitzung ab (HTTP 401), wird **einmal** neu
  angemeldet und die Abfrage wiederholt.
- Wird das Passwort abgelehnt, stoppt die Abfrage sofort und Home Assistant bittet um ein
  neues Passwort (Schutz vor Sperre nach vielen Fehlversuchen).
- Bei Verbindungsfehlern verdoppelt sich das Intervall bis maximal **15 Minuten**.
- Beim Entladen und beim Beenden von Home Assistant wird abgemeldet.
- `NaN`-Werte und Temperaturen von -999.9 °C («Fühler nicht angeschlossen») werden als
  *nicht verfügbar* angezeigt.

## Installation

### Variante A: manuell

1. Den Ordner `custom_components/kermi_xcenter` nach `/config/custom_components/kermi_xcenter`
   kopieren (z. B. per Samba- oder SSH-Add-on).
2. Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → «Kermi x-center (lokal)»*.
4. Host (z. B. `192.168.1.50`) und Passwort der x-center-Weboberfläche eingeben.

### Variante B: HACS (benutzerdefiniertes Repository)

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → URL dieses Repositorys, Typ *Integration*.
2. «Kermi x-center (lokal)» installieren, Home Assistant neu starten, weiter wie oben ab 3.

### Einstellungen

- **Optionen:** Abfrageintervall in Sekunden sowie «Steuerung erlauben» (Standard aus,
  siehe oben).
- **Neu konfigurieren:** Host und/oder Passwort ändern (z. B. wenn sich die IP geändert hat).
  Die Integration prüft dabei, dass es dasselbe x-center ist.
- **Diagnose herunterladen:** enthält Katalogzuordnung und Werte; Passwort, Seriennummern
  und Geräte-IDs sind geschwärzt.

## Geräte und Entitäten

Die folgende Tabelle zeigt die lesenden Entitäten. Die optionalen Steuer-Entitäten sind
oben beschrieben.

Es entstehen drei Geräte: **Kermi Wärmepumpe**, **Kermi Heizen** und **Kermi Warmwasser**
(Hersteller, Modell und Softwareversion aus dem Katalog). Die eindeutigen IDs lauten
`<Seriennummer>_<gerät>_<schlüssel>`, z. B. `…_heat_pump_flow_temp`. Entitäten mit
«aus» sind standardmässig deaktiviert und können in Home Assistant aktiviert werden.

| Gerät | Entität | Typ | Einheit | State class | Quelle (Kermi-Gerät → DisplayName / WellKnownName) | Standard |
|---|---|---|---|---|---|---|
| Kermi Wärmepumpe | Wärmeleistung | sensor (power) | kW | measurement | x-change dynamic pro (40) → „Aktuelle Leistung“ / `Rubin_CurrentOutputCapacity` | an |
| Kermi Wärmepumpe | Wärmeleistung Heizen | sensor (power) | kW | measurement | x-change dynamic pro (40) → „Aktuelle Leistung Heizen“ / `Rubin_CurrentOutputCapacityHeating` | an |
| Kermi Wärmepumpe | Wärmeleistung Warmwasser | sensor (power) | kW | measurement | x-change dynamic pro (40) → „aktuelle Leistung Twe“ / `Rubin_CurrentOutputCapacityTwe` | an |
| Kermi Wärmepumpe | Elektrische Leistung | sensor (power) | kW | measurement | x-change dynamic pro (40) → „Akt. elektr. Leistung“ / `Rubin_CurrentPowerInverter` | an |
| Kermi Wärmepumpe | Elektrische Leistung Heizen | sensor (power) | kW | measurement | x-change dynamic pro (40) → „Akt. elektr. Leistung Heizen“ / `Rubin_CurrentPowerInverterHeating` | an |
| Kermi Wärmepumpe | Elektrische Leistung Warmwasser | sensor (power) | kW | measurement | x-change dynamic pro (40) → „akt. elektr. Leistung Twe“ / `Rubin_CurrentPowerInverterTwe` | an |
| Kermi Wärmepumpe | COP | sensor |  | measurement | x-change dynamic pro (40) → „Aktueller COP“ / `Rubin_CurrentCOP` | an |
| Kermi Wärmepumpe | COP Heizen | sensor |  | measurement | x-change dynamic pro (40) → „Aktueller COP Heizen“ / `Rubin_CurrentCOPHeating` | an |
| Kermi Wärmepumpe | COP Warmwasser | sensor |  | measurement | x-change dynamic pro (40) → „aktueller COP Twe“ / `Rubin_CurrentCOPTwe` | an |
| Kermi Wärmepumpe | Leistungsanforderung Heizen | sensor (power) | kW | measurement | x-change dynamic pro (40) → „Leistungsanforderung Heizen“ / `Rubin_RequestedPowerHeating` | an |
| Kermi Wärmepumpe | Leistungsanforderung Warmwasser | sensor (power) | kW | measurement | x-change dynamic pro (40) → „Leistungsanforderung TWE“ / `Rubin_RequestedPowerTwe` | an |
| Kermi Wärmepumpe | Status Wärmepumpe (Code) | sensor |  |  | x-change dynamic pro (40) → „Status Wärmepumpe“ / `Rubin_CombinedHeatpumpState` | an |
| Kermi Wärmepumpe | Status seit | sensor (timestamp) |  |  | x-change dynamic pro (40) → „Status seit“ / `Rubin_StateSinceUtc` | an |
| Kermi Wärmepumpe | Vorlauftemperatur (B16) | sensor (temperature) | °C | measurement | x-change dynamic pro (40) → „B16 - Vorlauftemperatur WP“ / `Rubin_Link_B16_Vorlauftemperatur_WP` | an |
| Kermi Wärmepumpe | Rücklauftemperatur (B17) | sensor (temperature) | °C | measurement | x-change dynamic pro (40) → „B17 - Rücklauftemperatur WP“ / `Rubin_Link_B17_Ruecklauftemperatur_WP` | an |
| Kermi Wärmepumpe | Lufteintrittstemperatur (B15) | sensor (temperature) | °C | measurement | x-change dynamic pro (40) → „B15 - Energiequellen Eintrittstemperatur“ | an |
| Kermi Wärmepumpe | Luftaustrittstemperatur (B14) | sensor (temperature) | °C | measurement | x-change dynamic pro (40) → „B14 - Energiequellen Austrittstemperatur“ | an |
| Kermi Wärmepumpe | Außentemperaturfühler (BOT) | sensor (temperature) | °C | measurement | x-change dynamic pro (40) → „BOT - Außentemperaturfühler“ | aus |
| Kermi Wärmepumpe | Spreizung | sensor (temperature_delta) | K | measurement | x-change dynamic pro (40) → „Aktuelle Temperaturspreizung Pufferladekreis“ | an |
| Kermi Wärmepumpe | Durchfluss (P13) | sensor (volume_flow_rate) | L/min | measurement | x-change dynamic pro (40) → „P13 - Durchfluss WP“ / `Rubin_Link_P13_Durchfluss_WP` | an |
| Kermi Wärmepumpe | Erforderlicher Durchfluss | sensor (volume_flow_rate) | L/min | measurement | x-change dynamic pro (40) → „Erforderlicher Durchfluss Ladekreis“ | aus |
| Kermi Wärmepumpe | Lüfterdrehzahl (Soll) | sensor | rpm | measurement | x-change dynamic pro (40) → „Erforderliche Lüfterdrehzahl“ | an |
| Kermi Wärmepumpe | Leistung Speicherladepumpe | sensor | % | measurement | x-change dynamic pro (40) → „Aktuelle Leistung Speicherladepumpe“ / `Rubin_AktuelleLeistungSpeicherladepumpe` | aus |
| Kermi Wärmepumpe | Verdichterstarts | sensor |  | total_increasing | x-change dynamic pro (40) → „Anzahl der Verdichterstarts“ | an |
| Kermi Wärmepumpe | Betriebsstunden Verdichter | sensor (duration) | h | total_increasing | x-change dynamic pro (40) → „Betriebsstunden - Verdichter“ / `Rubin_OperationHoursCompressor` | an |
| Kermi Wärmepumpe | Betriebsstunden Lüfter | sensor (duration) | h | total_increasing | x-change dynamic pro (40) → „Betriebsstunden - Lüfter“ | an |
| Kermi Wärmepumpe | Betriebsstunden Speicherladepumpe | sensor (duration) | h | total_increasing | x-change dynamic pro (40) → „Betriebsstunden - Speicherladepumpe“ | an |
| Kermi Wärmepumpe | Softwareversion | sensor |  |  | x-change dynamic pro (40) → „Version SW: Major“ / `Rubin_SWVersion_Major` + „Version SW: Minor“ / `Rubin_SWVersion_Minor` + „Version SW: Patch“ / `Rubin_SWVersion_Patch` | an |
| Kermi Heizen | Außentemperatur | sensor (temperature) | °C | measurement | Heizen (50) → „Außentemperatur“ / `LuftTemperatur` | an |
| Kermi Heizen | Außentemperatur (gemittelt) | sensor (temperature) | °C | measurement | Heizen (50) → „Gemittelte Außentemperatur“ / `Aussentemperatur_gemittelt` | an |
| Kermi Heizen | Außentemperatur (Saison) | sensor (temperature) | °C | measurement | Heizen (50) → „Saison-Außentemperatur“ / `HP_Aussentemperatur_Saison` | aus |
| Kermi Heizen | Heizkreis Isttemperatur | sensor (temperature) | °C | measurement | Heizen (50) → „Isttemperatur Heizkreis“ / `HeatingCircuit_TemperatureActualValue` | an |
| Kermi Heizen | Heizkreis Solltemperatur | sensor (temperature) | °C | measurement | Heizen (50) → „Solltemperatur Heizkreis“ / `HeatingCircuit_TemperatureSetpoint` | an |
| Kermi Heizen | Pufferspeicher Isttemperatur | sensor (temperature) | °C | measurement | Heizen (50) → „Isttemperatur Heizspeicher“ / `BufferSystem_HeatingTemperatureActual` | an |
| Kermi Heizen | Pufferspeicher Solltemperatur | sensor (temperature) | °C | measurement | Heizen (50) → „Solltemperatur Heizspeicher“ / `BufferSystem_HeatingSetpoint` | an |
| Kermi Heizen | Mischeröffnung | sensor | % | measurement | Heizen (50) → „Mischeröffnung“ / `HeatingCircuit_MixerPosition` | an |
| Kermi Heizen | Energiemodus | sensor (enum) | Enum |  | Heizen (50) → „Energiemodus“ / `HeatingCircuit_EnergyMode` | an |
| Kermi Heizen | Betriebsstunden Heizkreispumpe | sensor (duration) | h | total_increasing | Heizen (50) → „Heizkreispumpe Laufzeit“ / `HeatingCircuit_OperatingHoursPump` | an |
| Kermi Warmwasser | Warmwasser Isttemperatur | sensor (temperature) | °C | measurement | Trinkwassererwärmung (51) → „Isttemperatur TWE“ / `BufferSystem_TweTemperatureActual` | an |
| Kermi Warmwasser | Warmwasser Solltemperatur | sensor (temperature) | °C | measurement | Trinkwassererwärmung (51) → „Solltemperatur TWE“ / `BufferSystem_TweSetpoint` | an |
| Kermi Warmwasser | Sollwert Einmalladung | sensor (temperature) | °C | measurement | Trinkwassererwärmung (51) → „Sollwert Einmalladung TWE“ / `BufferSystem_OneTimeTweSetpoint` | aus |
| Kermi Wärmepumpe | Heizbetrieb | binary_sensor (running) |  |  | x-change dynamic pro (40) → „Heizen“ / `Rubin_IsHeatingState` | an |
| Kermi Wärmepumpe | Warmwasserbetrieb | binary_sensor (running) |  |  | x-change dynamic pro (40) → „TWE“ / `Rubin_IsTweState` | an |
| Kermi Wärmepumpe | Kühlbetrieb | binary_sensor (running) |  |  | x-change dynamic pro (40) → „Kühlen“ / `Rubin_IsCoolingState` | aus |
| Kermi Wärmepumpe | Abtauung | binary_sensor (running) |  |  | x-change dynamic pro (40) → „Abtauen“ / `Rubin_IsDefrostingState` | an |
| Kermi Wärmepumpe | PV-Modulation | binary_sensor |  |  | x-change dynamic pro (40) → „Status PV Modulation“ / `Rubin_PvIsActive` | an |
| Kermi Wärmepumpe | Globaler Alarm | binary_sensor (problem) |  |  | x-change dynamic pro (40) → „Globaler Alarm“ | an |
| Kermi Wärmepumpe | Globale Warnung | binary_sensor (problem) |  |  | x-change dynamic pro (40) → „Globale Warnung“ | an |
| Kermi Wärmepumpe | Speicherladepumpe | binary_sensor (running) |  |  | x-change dynamic pro (40) → „Betrieb Speicherladepumpe“ / `Rubin_StorageChargingPumpState` | aus |
| Kermi Heizen | Sommerbetrieb | binary_sensor |  |  | Heizen (50) → „Sommerbetrieb“ / `HeatingCircuit_SummerMode` | an |
| Kermi Warmwasser | Einmalladung aktiv | binary_sensor (running) |  |  | Trinkwassererwärmung (51) → „Einmalladung TWE“ / `BufferSystem_OneTimeTwe` | an |

### Hinweise zu einzelnen Werten

- **Energiemodus** (`HeatingCircuit_EnergyMode`): 0 = Aus, 1 = Eco, 2 = Normal,
  3 = Komfort, 4 = Benutzerdefiniert. Die Zuordnung stammt aus kermi-ha-bridge (aus der
  x-center-Weboberfläche abgeleitet). Der Katalog enthält nur die Offsets je Modus
  (hier: Eco −2 K, Normal 0 K, Komfort +2 K, Benutzerdefiniert −5 K), nicht die Zahlen
  selbst; der aktuelle Wert 2 passt zu «Normal». Der Rohwert steht im Attribut
  `raw_value`; unbekannte Werte werden als *unbekannt* angezeigt.
- **Status Wärmepumpe (Code)** (`Rubin_CombinedHeatpumpState`, Werteliste
  `Rubin_StateHP`): Die Bedeutung der Codes ist nicht dokumentiert und wird deshalb als
  Zahl angezeigt (beobachtet: 4 während Heizbetrieb).
- **Spreizung** ist eine Temperaturdifferenz (Kelvin, `temperature_delta`).

## Entwicklung

```bash
uv venv -p 3.14 .venv
uv pip install --python .venv/bin/python -r requirements-test.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Die Tests laufen vollständig offline gegen einen lokalen Nachbau der API
(`tests/fake_xcenter.py`, nur 127.0.0.1), gespeist aus dem anonymisierten Live-Katalog
(`tests/fixtures_catalog.json`). Übersetzungen werden mit `scripts/gen_translations.py`
erzeugt.

## Haftungsausschluss

Die Software wird ohne jede Gewährleistung bereitgestellt (siehe [LICENSE](LICENSE)). Die
Nutzung erfolgt auf eigenes Risiko. Das Projekt verwendet ausschliesslich die lokale
Weboberfläche des eigenen Geräts zur Interoperabilität mit Home Assistant. Es enthält
weder Firmware noch Software oder Logos von Kermi. Marken werden nur zur Beschreibung der
Kompatibilität genannt.

## Dank und Lizenz

MIT-Lizenz, siehe [LICENSE](LICENSE). Das Wissen über die lokale x-center-API (Endpunkte,
Login, Katalog, ReadValues) stammt aus
[kermi-ha-bridge](https://github.com/m-zenker/kermi-ha-bridge) von Martin Zenker
(MIT-Lizenz). Code daraus ist nicht enthalten.
