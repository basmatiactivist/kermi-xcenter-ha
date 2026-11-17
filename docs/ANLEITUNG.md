# Anleitung: Kermi x-center (lokal)

Diese Anleitung beschreibt Schritt für Schritt Installation, Einrichtung, Betrieb und
Fehlersuche. Der Schwerpunkt liegt auf den beiden Betriebsarten **Nur lesen** (Standard)
und **Steuerung**: was sie bedeuten, wie man zwischen ihnen wechselt und wie man jederzeit
prüft, welche gerade aktiv ist.

> **Kurzfassung:** Nach der Installation liest die Integration nur. An der Wärmepumpe
> wird nichts verändert, solange niemand in den Optionen «Steuerung erlauben» einschaltet
> und die Warnung ausdrücklich bestätigt.

## Inhalt

1. [Überblick](#1-überblick)
2. [Voraussetzungen](#2-voraussetzungen)
3. [Installation](#3-installation)
4. [Einrichtung](#4-einrichtung)
5. [Geräte und Entitäten](#5-geräte-und-entitäten)
6. [Abfrageintervall](#6-abfrageintervall)
7. [Betriebsarten: Nur lesen und Steuerung](#7-betriebsarten-nur-lesen-und-steuerung)
8. [IP-Adresse oder Passwort ändern](#8-ip-adresse-oder-passwort-ändern)
9. [Updates und Zurückrollen](#9-updates-und-zurückrollen)
10. [Diagnose und Protokolle](#10-diagnose-und-protokolle)
11. [Fehlersuche](#11-fehlersuche)
12. [Umstieg von kermi-ha-bridge (AppDaemon)](#12-umstieg-von-kermi-ha-bridge-appdaemon)
13. [Deinstallieren](#13-deinstallieren)

---

## 1. Überblick

Die Integration verbindet sich direkt mit der lokalen Weboberfläche des x-center im
Heimnetz. Sie braucht keine Cloud, kein Modbus und keine Zusatzsoftware.

| | **Nur lesen** (Standard) | **Steuerung** (optional) |
|---|---|---|
| Sensoren, Binärsensoren | ja | ja |
| Buttons, Zahlen, Auswahlen | **nicht vorhanden** | 4 Steuer-Entitäten |
| Schreibzugriff auf die Wärmepumpe | technisch gesperrt | nur über die abgesicherte Funktion |
| Einschalten | ab Installation aktiv | Optionen und ausdrückliche Bestätigung |
| An echter Hardware getestet | ja | **nein** |

## 2. Voraussetzungen

- Home Assistant **2025.2** oder neuer.
- Kermi x-center mit einer Wärmepumpe mit **Rubin-Firmware** (z. B. *x-change dynamic pro*).
  Klassische Firmware mit `HP_*`-Datenpunkten wird nicht unterstützt, siehe README,
  Abschnitt «Unterstützte Anlagen».
- Die IP-Adresse des x-center. Am besten reservierst du sie im Router fest, sonst musst du
  die Integration nach jedem Adresswechsel neu konfigurieren (Abschnitt 8).
- Das Passwort der x-center-Weboberfläche. Prüfe es zuerst im Browser unter
  `http://<IP-des-x-center>`, denn nach mehreren Fehlversuchen kann sich das x-center
  vorübergehend sperren.
- Home Assistant und x-center müssen sich im Netz erreichen können. Das x-center spricht
  nur unverschlüsseltes HTTP und gehört nie direkt ins Internet (siehe
  [SECURITY.md](../SECURITY.md)).

## 3. Installation

### Variante A: Marketplace bzw. HACS (empfohlen)

So bekommst du Updates automatisch angezeigt.

1. Öffne in Home Assistant den **Marketplace**. Ab HA 2026.11 ist HACS eingebaut und heisst
   so; bei älteren Versionen öffnest du HACS.
2. Klicke oben rechts auf **Über Link hinzufügen** (bei HACS: ⋮ → *Benutzerdefinierte
   Repositories*).
3. Trage `https://github.com/basmatiactivist/kermi-xcenter-ha` ein, bei HACS mit dem Typ
   *Integration*.
4. Ist der Marketplace noch nicht mit GitHub verbunden, fragt er danach. Klicke auf
   *Fortfahren*, melde dich auf github.com an und gib dort den angezeigten Code ein. Die
   Verbindung liest nur öffentliche Daten und lässt sich in den GitHub-Einstellungen
   widerrufen.
5. Öffne «Kermi x-center (lokal)» und klicke auf **Installieren**.
6. Fordert Home Assistant einen Neustart, starte neu (*Einstellungen → System → ⏻ → Neu
   starten*).

### Variante B: von Hand

1. Lade das neueste Release von
   <https://github.com/basmatiactivist/kermi-xcenter-ha/releases> herunter.
2. Kopiere den Ordner `custom_components/kermi_xcenter` nach
   `/config/custom_components/kermi_xcenter`, zum Beispiel mit dem Samba-, SSH- oder File-Editor-Add-on.
3. Starte Home Assistant neu.

Bei dieser Variante bekommst du keine Update-Hinweise. Für ein Update kopierst du den
Ordner erneut und startest neu.

## 4. Einrichtung

1. Öffne *Einstellungen → Geräte & Dienste → Integration hinzufügen* und wähle **Kermi
   x-center (lokal)**.
2. **Host:** nur die IP-Adresse oder den Hostnamen eintragen, z. B. `192.168.1.50`, optional
   mit Port (`192.168.1.50:80`). Ohne `http://`, ohne Pfad, ohne Benutzername.
3. **Passwort:** das Passwort der x-center-Weboberfläche.
4. Klicke auf **OK**. Die Integration meldet sich einmal an, liest die Geräteliste und
   erkennt das x-center an seiner Seriennummer. Danach meldet sie sich wieder ab.

Mögliche Meldungen:

| Meldung | Bedeutung | Was tun |
|---|---|---|
| Keine Verbindung zum x-center möglich | Host nicht erreichbar, falsche IP oder das Gerät ist kein x-center | IP prüfen (im Browser öffnen), Netz prüfen |
| Das x-center hat das Passwort abgelehnt | Passwort falsch | Passwort im Browser prüfen. Nicht oft hintereinander versuchen, sonst sperrt sich das x-center. |
| Bitte nur IP-Adresse oder Hostname angeben | Eingabe enthält `@`, Leerzeichen oder einen ungültigen Port | nur `IP` oder `IP:Port` eintragen |
| Dieses x-center ist bereits eingerichtet | Es gibt schon einen Eintrag für dieses Gerät | «Neu konfigurieren» verwenden (Abschnitt 8) |

Das Passwort speichert Home Assistant im Eintrag der Integration. In Diagnosedaten und
Protokollen erscheint es nie.

## 5. Geräte und Entitäten

Es entstehen drei Geräte: **Kermi Wärmepumpe**, **Kermi Heizen** und **Kermi Warmwasser**.
Die vollständige Liste der Entitäten mit Einheit und Quelle steht im
[README](../README.md#geräte-und-entitäten).

- Entitäten, die in der Tabelle als «aus» markiert sind, sind standardmässig
  deaktiviert. Aktivieren: *Einstellungen → Geräte & Dienste → Entitäten*, Entität öffnen,
  ⚙ → *Aktiviert*.
- **Nicht verfügbar** bedeutet: Das x-center liefert keinen gültigen Wert, zum Beispiel
  `NaN` beim COP Warmwasser, solange kein Warmwasser bereitet wird, oder -999,9 °C bei
  einem nicht angeschlossenen Fühler. Das ist normal und kein Fehler.
- Die Entity-IDs sind stabil. Du kannst sie in Home Assistant umbenennen, Dashboards und
  Statistik folgen der neuen ID.

## 6. Abfrageintervall

*Einstellungen → Geräte & Dienste → Kermi x-center (lokal) → **Konfigurieren***

- **Abfrageintervall:** Sekunden zwischen zwei Abfragen, Standard 30, Minimum 15.
- Fällt eine Abfrage aus, verdoppelt sich das Intervall bis maximal 15 Minuten. Nach der
  nächsten erfolgreichen Abfrage gilt wieder das eingestellte Intervall.
- Nach dem Speichern lädt die Integration automatisch neu.

## 7. Betriebsarten: Nur lesen und Steuerung

### 7.1 Nur lesen (Standard)

So läuft die Integration nach der Installation. Sie ruft dann ausschliesslich diese
Endpunkte des x-center auf:

| Endpunkt | Zweck |
|---|---|
| `Security/Login`, `Security/Logout` | An- und Abmelden |
| `Device/GetAllDevices` | Geräteliste |
| `Datapoint/GetConfigsByDeviceType` | Datenpunkt-Katalog |
| `Datapoint/ReadValues` | Werte lesen |

Jeder andere Aufruf wird **vor** dem Senden abgebrochen. Ohne Freigabe gibt es keine
Buttons, Zahlen oder Auswahlen und keine Dienste. Es existiert schlicht nichts, womit man
etwas ändern könnte.

### 7.2 Welche Betriebsart ist gerade aktiv?

Jede dieser drei Prüfungen reicht:

1. *Einstellungen → Geräte & Dienste → Kermi x-center (lokal) → **Konfigurieren***: Ist
   **Steuerung erlauben** aus, ist der Nur-Lese-Modus aktiv. Schliesse den Dialog danach
   mit ✕, ohne zu speichern.
2. *Einstellungen → Geräte & Dienste → **Entitäten***, nach «kermi» filtern: Gibt es
   **keine** Einträge mit `button.`, `number.` oder `select.`, ist der Nur-Lese-Modus aktiv.
3. Diagnose herunterladen (Abschnitt 10): Unter `entry → options` steht
   `"allow_writes": false` oder der Eintrag fehlt ganz.

### 7.3 Steuerung einschalten

> **Warnung:** Der Schreibweg ist nur gegen einen Nachbau der API getestet, **nie an einer
> echten Wärmepumpe**. Falsche Einstellungen können Komfortverlust, höhere Energiekosten
> oder ein Legionellenrisiko bei zu niedriger Warmwassertemperatur verursachen. Die
> Nutzung erfolgt auf eigenes Risiko und kann Garantie- oder Gewährleistungsansprüche
> berühren.

1. *Einstellungen → Geräte & Dienste → Kermi x-center (lokal) → **Konfigurieren***.
2. **Steuerung erlauben (Schreibzugriff)** einschalten und auf **Absenden** klicken.
3. Es folgt der Schritt **«Steuerung wirklich erlauben?»** mit der Warnung. Kreuze
   **«Ich habe die Warnung verstanden und erlaube Schreibzugriffe»** an und sende ab.
   Ohne Häkchen bleibt die Steuerung aus.
4. Die Integration lädt neu und legt diese Entitäten an:

| Entität | Gerät | Wirkung | Erlaubte Werte |
|---|---|---|---|
| Button **Warmwasser einmal aufheizen** | Kermi Warmwasser | startet eine Einmalladung | nur «ein» |
| Zahl **Sollwert Einmalladung (Steuerung)** | Kermi Warmwasser | Zieltemperatur der Einmalladung | 40–55 °C, Schritt 1 |
| Zahl **Warmwasser-Sollwert (Steuerung)** | Kermi Warmwasser | konstanter Warmwasser-Sollwert | 40–55 °C, Schritt 1 |
| Auswahl **Energiemodus (Steuerung)** | Kermi Heizen | Energiemodus des Heizkreises | Eco, Normal, Komfort, Benutzerdefiniert |

Mehr lässt sich nicht verändern. Heizkurven, Verdichter, Alarme und Resets, Kühlung und
Installateur-Einstellungen sind bewusst ausgeschlossen. «Aus» ist beim Energiemodus nicht
wählbar.

### 7.4 Schutzregeln bei jedem Schreibvorgang

Jeder Schreibvorgang wird **vor** dem Senden geprüft. Er wird nur ausgeführt, wenn alle
vier Bedingungen erfüllt sind:

1. «Steuerung erlauben» ist eingeschaltet.
2. Der Datenpunkt steht auf der Schreib-Erlaubnisliste (die vier Einträge oben).
3. Der Wert liegt in unserem Sicherheitsbereich (siehe Tabelle) **und** innerhalb der
   Grenzen, die das x-center selbst im Katalog meldet (`MinValue`/`MaxValue`). Meldet das
   x-center keine Grenzen, wird nicht geschrieben.
4. Auf denselben Datenpunkt wurde in den letzten **5 Minuten** nicht schon geschrieben,
   egal mit welchem Wert. Auch ein fehlgeschlagener Versuch zählt. Nach einem Neustart oder
   Neuladen der Integration beginnt sie von vorn.

Wird ein Schreibvorgang verweigert, erscheint in Home Assistant die Meldung **«Nicht an
die Wärmepumpe gesendet: …»** mit dem Grund. Lehnt das x-center selbst die Änderung ab,
lautet die Meldung **«Die Wärmepumpe hat die Änderung nicht angenommen: …»**.

Nach einem erfolgreichen Schreibvorgang liest die Integration sofort neu, damit der neue
Wert sichtbar wird.

### 7.5 Schreibvorgänge mitprotokollieren

Jeder Versuch wird auf Stufe INFO protokolliert, auch jede Verweigerung. Damit diese
Zeilen im Protokoll erscheinen, ergänzt du in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.kermi_xcenter: info
```

Danach Home Assistant neu starten. Die Zeilen findest du unter *Einstellungen → System →
Protokolle* (ganzes Protokoll anzeigen), zum Beispiel:

```text
Write ww_setpoint_constant=48 requested
Write ww_setpoint_constant=48.0: sending to x-center
Write ww_setpoint_constant=48.0: accepted by x-center
Write ww_setpoint_constant=49 REFUSED: rate limit, next write allowed in 270 s
```

### 7.6 Steuerung wieder ausschalten (zurück zu «Nur lesen»)

1. *Einstellungen → Geräte & Dienste → Kermi x-center (lokal) → **Konfigurieren***.
2. **Steuerung erlauben** ausschalten und auf **Absenden** klicken. Eine Bestätigung ist
   nicht nötig.
3. Die Integration lädt neu. Die vier Steuer-Entitäten werden **vollständig entfernt**,
   auch aus der Entitätenliste. Dashboard-Karten, die sie verwendet haben, zeigen danach
   «Entität nicht gefunden». Diese Karten entfernst du von Hand.
4. Prüfe mit Abschnitt 7.2, dass der Nur-Lese-Modus wieder aktiv ist.

Automationen und Skripte, die Steuer-Entitäten verwenden, schlagen danach fehl. Nimm sie
vorher heraus oder deaktiviere sie.

### 7.7 Steuerung in einer Installation dauerhaft ausschliessen

Soll in einer Installation nie geschrieben werden:

- Schalte «Steuerung erlauben» nie ein. Ohne die ausdrückliche Bestätigung im Warnschritt
  geht das auch nicht aus Versehen.
- Nur Administratoren können die Optionen einer Integration ändern. Normale Benutzer
  sehen den Dialog nicht.
- Prüfe nach jedem Update mit Abschnitt 7.2. Ein Update schaltet die Option nie
  selbst ein, sie bleibt so, wie sie gespeichert ist.

## 8. IP-Adresse oder Passwort ändern

**IP-Adresse oder Passwort geändert:**
*Einstellungen → Geräte & Dienste → Kermi x-center (lokal) → ⋮ → **Neu konfigurieren***.
Trage die neue Adresse ein. Das Passwortfeld kannst du leer lassen, dann bleibt das bisherige.
Die Integration prüft, ob es dasselbe x-center ist (über die Seriennummer). Ein anderes
Gerät wird abgelehnt.

**Passwort am x-center geändert:**
Bei der nächsten Abfrage lehnt das x-center ab. Die Integration fragt dann **nicht** immer
wieder an, damit sich das x-center nicht sperrt. Stattdessen erscheint unter
*Einstellungen → Geräte & Dienste* ein Hinweis, dass die Integration eine erneute
Anmeldung braucht. Klicke darauf und gib das neue Passwort ein.

## 9. Updates und Zurückrollen

- Neue Versionen erscheinen bei Variante A unter *Einstellungen → **Updates***, sobald es
  auf GitHub ein neues Release gibt. Installieren und Home Assistant neu starten, wenn es
  dazu auffordert.
- Was sich geändert hat, steht in den Release-Notes:
  <https://github.com/basmatiactivist/kermi-xcenter-ha/releases>.
- Einstellungen, Passwort, Optionen und Entity-IDs bleiben bei Updates erhalten.
- **Zurückrollen:** Marketplace → «Kermi x-center (lokal)» → ⋮ → **Erneut herunterladen**,
  die gewünschte ältere Version wählen und neu starten.

## 10. Diagnose und Protokolle

**Diagnose herunterladen:** *Einstellungen → Geräte & Dienste → Kermi x-center (lokal) → ⋮
→ **Diagnose herunterladen***. Die Datei enthält die Zuordnung der Datenpunkte, die
aktuellen Werte und die Optionen. **Geschwärzt** sind Passwort, Host, Seriennummern und
Geräte-IDs. Die Datei kannst du bei einer Fehlermeldung im GitHub-Issue anhängen.

**Ausführliches Protokoll:** Auf der Seite der Integration ⋮ → **Debug-Protokollierung
aktivieren**, den Fehler auslösen, dann **Debug-Protokollierung deaktivieren**. Home
Assistant bietet das Protokoll dann zum Herunterladen an. Es enthält kein Passwort.

## 11. Fehlersuche

| Symptom | Ursache | Lösung |
|---|---|---|
| Einrichtung: «Keine Verbindung» | falsche IP, x-center nicht erreichbar | IP im Browser prüfen. Den genauen Grund zeigt das Protokoll als Warnung «Cannot connect to x-center at …». |
| Einrichtung: «Passwort abgelehnt» | falsches Passwort | Passwort im Browser prüfen, dann erneut versuchen |
| Integration startet nicht, Meldung «keine bekannten Datenpunkte» | Anlage mit klassischer Firmware | wird nicht unterstützt (siehe README) |
| Alle Werte «nicht verfügbar» | x-center nicht erreichbar | Netz und Strom prüfen. Die Integration versucht es mit wachsendem Abstand bis 15 Minuten weiter. |
| Einzelne Werte «nicht verfügbar» | Wert gerade nicht definiert (NaN) oder Fühler nicht angeschlossen | normal |
| Hinweis zur erneuten Anmeldung | Passwort am x-center geändert | Hinweis anklicken, neues Passwort eingeben |
| x-center-Weboberfläche sperrt die Anmeldung | zu viele Fehlversuche (auch von anderer Software) | warten, bis die Sperre abläuft. Die Integration selbst versucht es bei falschem Passwort nicht erneut. |
| Gerät «Kermi Heizen» oder «Kermi Warmwasser» fehlt | Gerätename im x-center weicht ab | Diagnose herunterladen und als Issue melden |
| Steuer-Entität meldet «Nicht an die Wärmepumpe gesendet» | eine der Schutzregeln (Abschnitt 7.4) greift | Grund in der Meldung lesen, bei «rate limit» 5 Minuten warten |

## 12. Umstieg von kermi-ha-bridge (AppDaemon)

Mit diesem Vorgehen laufen bestehende Dashboards, Helfer und die **Langzeitstatistik**
ohne Unterbruch weiter:

1. **Bestandsaufnahme:** Notiere, welche `sensor.kermi_*`/`binary_sensor.kermi_*` in
   Dashboards, Helfern (Template, Riemann-Integral, Verbrauchszähler, history_stats),
   Automationen und Skripten vorkommen.
2. **Bridge stoppen:** AppDaemon-Add-on stoppen und den Autostart abschalten. Die
   Bridge-Entitäten haben keinen Registry-Eintrag. Nach einem Neustart von Home Assistant
   sind sie weg und ihre IDs frei.
3. **Integration installieren und einrichten** (Abschnitte 3 und 4). Die neuen Entitäten
   heissen zunächst z. B. `sensor.kermi_warmepumpe_vorlauftemperatur_b16`.
4. **Auf die alten IDs umbenennen:** Entität öffnen, ⚙, Feld **Entitäts-ID** auf die
   alte ID setzen (z. B. `sensor.kermi_wp_flow_temp_lc`) und speichern. Die
   Langzeitstatistik läuft weiter, wenn ID, Einheit und `state_class` gleich bleiben. Die
   Einheiten der Integration entsprechen denen der Bridge (kW, °C, L/min, h, K).
5. **Abweichungen anpassen:**
   - «Abtauen» ist jetzt ein Binärsensor mit `on`/`off` statt eines Texts `true`/`false`.
     Prüfungen wie `is_state('sensor.kermi_is_defrosting','true')` werden zu
     `is_state('binary_sensor.kermi_is_defrosting','on')`, wenn du den Binärsensor auf
     `binary_sensor.kermi_is_defrosting` umbenennst.
   - `sensor.kermi_bridge_status` gibt es nicht mehr. Ersatz:
     `states('sensor.kermi_status_code') not in ['unavailable','unknown']`.
   - Der Energiemodus heisst intern `normal`, `eco`, `comfort` usw. Angezeigt wird er
     übersetzt. Vergleiche in Vorlagen auf diese Schlüssel umstellen.
6. **Prüfen:** Unter *Entwicklerwerkzeuge → Statistiken* dürfen bei den `kermi_*`-Einträgen
   keine Einheiten-Warnungen stehen. Die Helfer müssen Werte zeigen.
7. **Aufräumen**, wenn alles läuft:
   - AppDaemon deinstallieren.
   - Den Bridge-Ordner löschen. Die dort abgelegte Katalog-Datei enthält Seriennummern.
   - Das Bridge-Passwort aus `secrets.yaml` entfernen. Die Integration speichert ihr
     Passwort selbst.
   - Statistik-Einträge von Bridge-Sensoren, die es nicht mehr gibt, löschst du unter
     *Entwicklerwerkzeuge → Statistiken* mit «Beheben».

## 13. Deinstallieren

1. *Einstellungen → Geräte & Dienste → Kermi x-center (lokal) → ⋮ → **Löschen***. Die
   Integration meldet sich beim x-center ab. Geräte und Entitäten werden entfernt, die
   Langzeitstatistik bleibt erhalten.
2. Marketplace → «Kermi x-center (lokal)» → ⋮ → **Entfernen**, bei Variante B den Ordner
   `custom_components/kermi_xcenter` löschen.
3. Home Assistant neu starten.
