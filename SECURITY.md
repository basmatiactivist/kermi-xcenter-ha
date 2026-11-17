# Sicherheit / Security

## Schwachstelle melden / Reporting a vulnerability

Bitte Sicherheitslücken **nicht** als öffentliches Issue melden, sondern vertraulich über
GitHub: *Security → Report a vulnerability* in diesem Repository.

Please do **not** open a public issue for security problems. Report them privately via
GitHub: *Security → Report a vulnerability* in this repository.

Eine Rückmeldung erfolgt nach bestem Bemühen; es ist ein privates Freizeitprojekt ohne
Supportzusage.

## Unterstützte Versionen / Supported versions

Nur der aktuelle Stand des Branches `main` wird gepflegt.

## Sicherheitsmodell / Security model

- Standardmässig nur lesend; der einzige Schreibweg ist `KermiClient.write_value` und
  standardmässig gesperrt (siehe README).
- Das x-center bietet nur unverschlüsseltes HTTP. Das Passwort und das Session-Cookie
  gehen daher im Klartext über das lokale Netz. Die Integration sollte nur in einem
  vertrauenswürdigen Netz (idealerweise eigenes VLAN für Haustechnik) betrieben werden;
  das x-center gehört nicht ins Internet.
- Die Integration folgt keinen HTTP-Weiterleitungen, akzeptiert nur Hostnamen/IP-Adressen
  (keine URLs mit Zugangsdaten), begrenzt Antwortgrössen und Zeitüberschreitungen und
  schwärzt Passwort, Host, Seriennummern und Geräte-IDs in Diagnosedaten.
- Keine Fremdabhängigkeiten ausser denen von Home Assistant selbst.
