# Zelter5 Raumlog

Mehrraum-Log für die gemeinsamen Bereiche von Zelter5.
Die Anwendung ermöglicht es Nutzerinnen und Nutzern, per QR-Code einen Raum aufzurufen und dessen Nutzung kurz zu dokumentieren.

## Funktionen

* Raumübersicht für mehrere gemeinsame Bereiche
* QR-Code-fähige Direktlinks pro Raum
* Formular pro Raum mit Name, Haus, Zustand, Bemerkung und optionalen Bildern
* Speicherung der Einträge in SQLite
* Upload von Bildern pro Nutzungseintrag
* Übersicht der letzten Buchungen
* allgemeine Anmerkungen
* einfache Admin-Ansicht mit Detailansicht und Soft-Delete
* optionale E-Mail-Benachrichtigung bei neuen Einträgen
* Docker-Setup für einfachen Betrieb auf einem Server

## Aktuell eingerichtete Räume

* Werkstatt
* Dachterrasse
* Sommerküche
* Sauna
* Ruheraum

Die Raumkonfiguration befindet sich aktuell im Code in `app/main.py` in `ROOM_DEFINITIONS`.

## Tech Stack

* Python
* FastAPI
* Uvicorn
* Jinja2 Templates
* SQLite
* Docker / Docker Compose

## Projektstruktur

Beispielhafte Struktur:

```text
.
├── app/
│   ├── main.py
│   ├── static/
│   └── templates/
├── data/
│   ├── app.db
│   └── uploads/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

`data/` enthält persistente Daten und sollte im Produktivbetrieb nicht versehentlich gelöscht werden.

## Lokal starten

### Voraussetzungen

* Python 3.11 oder neuer empfohlen
* `pip`
* optional: `venv`

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Entwicklung starten

```bash
uvicorn app.main:app --reload
```

Danach öffnen:

```text
http://localhost:8000/
http://localhost:8000/admin
```

## Mit Docker starten

```bash
docker compose up --build
```

Danach öffnen:

```text
http://localhost:8000/
http://localhost:8000/admin
```

Im Docker-Setup werden Änderungen in `./app` direkt in den Container gespiegelt. `uvicorn` läuft mit `--reload`, sodass Änderungen an Python-Dateien, Templates und CSS automatisch übernommen werden.

## Persistente Daten

Standardmäßig verwendet die Anwendung:

```text
data/app.db
data/uploads/
```

Über die Umgebungsvariable `DATA_DIR` kann ein anderer Speicherort gesetzt werden:

```bash
export DATA_DIR=/pfad/zum/datenverzeichnis
```

Im Docker-Betrieb sollte `DATA_DIR` auf ein Volume zeigen, damit Datenbank und Uploads Container-Neustarts überleben.

## Konfiguration per Umgebungsvariablen

| Variable        | Pflicht | Standard                  | Beschreibung                                 |
| --------------- | ------: | ------------------------- | -------------------------------------------- |
| `DATA_DIR`      |    nein | `../data` relativ zur App | Speicherort für SQLite-Datenbank und Uploads |
| `SMTP_HOST`     |    nein | -                         | SMTP-Server für E-Mail-Benachrichtigungen    |
| `SMTP_PORT`     |    nein | `587`                     | SMTP-Port                                    |
| `SMTP_FROM`     |    nein | -                         | Absenderadresse                              |
| `SMTP_TO`       |    nein | -                         | Empfängeradresse                             |
| `SMTP_USER`     |    nein | leer                      | SMTP-Benutzername                            |
| `SMTP_PASSWORD` |    nein | leer                      | SMTP-Passwort                                |
| `SMTP_STARTTLS` |    nein | `true`                    | STARTTLS verwenden                           |
| `SMTP_SSL`      |    nein | `false`                   | direkte SSL-Verbindung verwenden             |

Die E-Mail-Benachrichtigung ist nur aktiv, wenn mindestens diese Variablen gesetzt sind:

```text
SMTP_HOST
SMTP_FROM
SMTP_TO
```

## E-Mail-Benachrichtigung einrichten

Beispiel für SMTP mit STARTTLS:

```bash
export SMTP_HOST=smtp.example.com
export SMTP_PORT=587
export SMTP_FROM=raumlog@example.com
export SMTP_TO=deine-adresse@example.com
export SMTP_USER=raumlog@example.com
export SMTP_PASSWORD=dein-passwort
export SMTP_STARTTLS=true
export SMTP_SSL=false
```

Für Anbieter mit direktem SSL ist häufig diese Variante passend:

```bash
export SMTP_PORT=465
export SMTP_SSL=true
export SMTP_STARTTLS=false
```

Falls der Mailversand fehlschlägt, wird der Nutzungseintrag trotzdem gespeichert. Der Fehler wird nur geloggt.

## QR-Code-Links

Die QR-Codes sollten jeweils direkt auf den passenden Raum zeigen:

```text
https://deine-domain.de/r/werkstatt
https://deine-domain.de/r/dachterrasse
https://deine-domain.de/r/sommerkueche
https://deine-domain.de/r/sauna
https://deine-domain.de/r/ruheraum
```

Für lokale Tests entsprechend:

```text
http://localhost:8000/r/werkstatt
http://localhost:8000/r/dachterrasse
http://localhost:8000/r/sommerkueche
http://localhost:8000/r/sauna
http://localhost:8000/r/ruheraum
```

## Wichtige Routen

| Route                 | Beschreibung                               |
| --------------------- | ------------------------------------------ |
| `/`                   | Raumübersicht                              |
| `/r/{raum}`           | Formular für einen bestimmten Raum         |
| `/letzte-buchungen`   | öffentliche Übersicht der letzten Einträge |
| `/anmerkungen`        | allgemeine Anmerkungen                     |
| `/admin`              | Admin-Übersicht                            |
| `/admin/session/{id}` | Detailansicht eines Eintrags               |
| `/datenschutz`        | Datenschutzseite                           |
| `/uploads/{filename}` | ausgelieferte Upload-Dateien               |

## Admin-Bereich

Der Admin-Bereich ist aktuell funktional einfach gehalten:

* Übersicht der letzten Einträge
* Filterung nach Raum
* Detailansicht einzelner Einträge
* Soft-Delete von Einträgen

Beim Soft-Delete wird ein Eintrag nicht physisch gelöscht, sondern mit `deleted_at` markiert und anschließend in den Listen ausgeblendet.

## Sicherheitshinweise

Wichtig für den Betrieb außerhalb des lokalen Netzwerks:

* `/admin` ist aktuell nicht durch Login oder Passwort geschützt.
* Uploads werden nur grob anhand von Content-Type und Dateiendung geprüft.
* Für den Produktivbetrieb sollte die Anwendung hinter HTTPS laufen.
* Admin-Zugriff sollte per Reverse Proxy, Basic Auth, VPN oder echter Login-Funktion geschützt werden.
* Regelmäßige Backups von `data/app.db` und `data/uploads/` sind empfehlenswert.

Beispiel: Schutz des Admin-Bereichs über Caddy, Traefik, Nginx oder Authelia.

## Backup

Für ein einfaches Backup sollten mindestens diese Daten gesichert werden:

```text
data/app.db
data/uploads/
```

Beispiel:

```bash
tar -czf zelter5-raumlog-backup.tar.gz data/
```

## Entwicklungshinweise

Die Datenbank wird beim Start automatisch initialisiert. Fehlende Spalten werden einfach ergänzt. Für dieses kleine Projekt ist das praktisch; bei größeren Änderungen wäre ein echtes Migrationswerkzeug wie Alembic sauberer.

Die Räume werden beim Start aus `ROOM_DEFINITIONS` in die Datenbank geschrieben oder aktualisiert. Bestehende Nutzungseinträge bleiben dabei erhalten.

## Typische Probleme

### Seite startet, aber Uploads fehlen nach Neustart

Prüfe, ob `data/` im Docker-Setup als Volume eingebunden ist.

### E-Mails werden nicht verschickt

Prüfe:

* Sind `SMTP_HOST`, `SMTP_FROM` und `SMTP_TO` gesetzt?
* Stimmen Port und TLS/SSL-Einstellungen?
* Erlaubt der Mailanbieter SMTP-Login mit Passwort oder ist ein App-Passwort nötig?
* Gibt es Fehlermeldungen im Container-Log?

```bash
docker compose logs -f
```

### Datenbank wird nicht gefunden

Prüfe den Wert von `DATA_DIR` und ob der Prozess Schreibrechte auf dieses Verzeichnis hat.

## Offene Punkte für Produktivbetrieb

* Admin-Authentifizierung ergänzen
* Upload-Prüfung robuster machen
* maximale Upload-Größe begrenzen
* Datenschutztext final prüfen
* Backup-Konzept festlegen
* Domain und Reverse Proxy konfigurieren
* QR-Codes final mit Produktivdomain erzeugen
