# Zelter5 Raumlog

Mehrraum-Log für die gemeinsamen Bereiche von Zelter5.
Die Anwendung ermöglicht es Nutzerinnen und Nutzern, per QR-Code einen Raum aufzurufen und dessen Nutzung kurz zu dokumentieren.

## Funktionen

* Raumübersicht für mehrere gemeinsame Bereiche
* QR-Code-fähige Direktlinks pro Raum
* Formular pro Raum mit Name, Haus, Zustand, Bemerkung und optionalen Bildern
* Speicherung der Einträge in SQLite
* serverseitig validierter Upload von Bildern pro Nutzungseintrag
* Übersicht der letzten Buchungen
* allgemeine Anmerkungen
* per HTTP Basic Auth geschützte Admin-Ansicht mit Detailansicht und Soft-Delete
* optionale E-Mail-Benachrichtigung bei neuen Einträgen
* Docker-Setup für einfachen Betrieb auf einem Server

## Aktuell eingerichtete Räume

* Werkstatt
* Dachterrasse
* Sommerküche
* Sauna
* Ruheraum

Die Raumkonfiguration befindet sich aktuell im Code in `app/constants.py` in `ROOM_DEFINITIONS`.

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

Für den Admin-Bereich müssen Zugangsdaten gesetzt sein:

```bash
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=ein-sicheres-passwort
```

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
http://localhost:9000/
http://localhost:9000/admin
```

Im Docker-Setup werden Änderungen in `./app` direkt in den Container gespiegelt. `uvicorn` läuft mit `--reload`, sodass Änderungen an Python-Dateien, Templates und CSS automatisch übernommen werden.

Der veröffentlichte Host-Port kann über `HOST_PORT` gesetzt werden. Der Standard ist `9000`.

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
| `ADMIN_USERNAME` |      ja | -                         | Benutzername für den Admin-Bereich           |
| `ADMIN_PASSWORD` |      ja | -                         | Passwort für den Admin-Bereich               |
| `PUBLIC_BASE_URL` |    nein | aus Request bzw. Compose-Default | Öffentliche Basis-URL für QR-Code-Links |
| `MAX_UPLOAD_IMAGES` |    nein | `5`                      | Maximale Anzahl Bilder pro Eintrag           |
| `MAX_UPLOAD_SIZE_MB` |   nein | `5`                      | Maximale Größe pro Bild in MB                |
| `MAX_NAME_LENGTH` |      nein | `100`                    | Maximale Länge von Namen                     |
| `MAX_HOUSE_LENGTH` |     nein | `10`                     | Maximale Länge der kombinierten Hausangabe   |
| `MAX_COMMENT_LENGTH` |   nein | `2000`                   | Maximale Länge von Bemerkungen und Zusatzfeldern |
| `MAX_GENERAL_NOTE_LENGTH` | nein | `4000`                 | Maximale Länge allgemeiner Anmerkungen       |
| `SMTP_HOST`     |    nein | -                         | SMTP-Server für E-Mail-Benachrichtigungen    |
| `SMTP_PORT`     |    nein | `587`                     | SMTP-Port                                    |
| `SMTP_FROM`     |    nein | -                         | Absenderadresse                              |
| `SMTP_TO`       |    nein | -                         | Empfängeradresse                             |
| `SMTP_USER`     |    nein | leer                      | SMTP-Benutzername                            |
| `SMTP_PASSWORD` |    nein | leer                      | SMTP-Passwort                                |
| `SMTP_STARTTLS` |    nein | `true`                    | STARTTLS verwenden                           |
| `SMTP_SSL`      |    nein | `false`                   | direkte SSL-Verbindung verwenden             |

Wenn `ADMIN_USERNAME` oder `ADMIN_PASSWORD` fehlen, ist der Admin-Bereich nicht offen erreichbar, sondern antwortet mit einem Konfigurationsfehler. Öffentliche Nutzer-Routen bleiben weiterhin ohne Login erreichbar.

Im Docker-Betrieb sollte `PUBLIC_BASE_URL` auf die von Nutzerinnen und Nutzern tatsächlich erreichbare URL zeigen. Beim Standard-Port aus `docker-compose.yml` wäre das zum Beispiel:

```bash
PUBLIC_BASE_URL=http://192.168.2.127:9000
```

Bei einer produktiven Domain entsprechend:

```bash
PUBLIC_BASE_URL=https://deine-domain.de
```

Ungültige oder nicht-positive numerische Limit-Werte werden beim Start geloggt und durch sichere Defaults ersetzt.

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

Der Admin-Bereich ist mit HTTP Basic Auth geschützt. Setze dafür vor dem Start:

```bash
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=ein-sicheres-passwort
```

Bei Docker Compose können diese Werte in einer lokalen `.env` stehen:

```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ein-sicheres-passwort
HOST_PORT=9000
PUBLIC_BASE_URL=http://192.168.2.127:9000
MAX_UPLOAD_IMAGES=5
MAX_UPLOAD_SIZE_MB=5
MAX_NAME_LENGTH=100
MAX_HOUSE_LENGTH=10
MAX_COMMENT_LENGTH=2000
MAX_GENERAL_NOTE_LENGTH=4000
```

Funktional umfasst der Admin-Bereich:

* Übersicht der letzten Einträge
* Filterung nach Raum
* Detailansicht einzelner Einträge
* Soft-Delete von Einträgen

Beim Soft-Delete wird ein Eintrag nicht physisch gelöscht, sondern mit `deleted_at` markiert und anschließend in den Listen ausgeblendet.

## Sicherheitshinweise

Wichtig für den Betrieb außerhalb des lokalen Netzwerks:

* Hochgeladene Bilder bleiben bewusst öffentlich innerhalb der App und per direktem Bildlink erreichbar.
* Uploads werden serverseitig als echte Bilder geprüft. Erlaubt sind JPEG, PNG und WebP.
* Für den Produktivbetrieb sollte die Anwendung hinter HTTPS laufen.
* Admin-Zugangsdaten sollten lang, eindeutig und nicht im Repository gespeichert sein.
* Regelmäßige Backups von `data/app.db` und `data/uploads/` sind empfehlenswert.

Zusätzlicher Schutz über Reverse Proxy, VPN oder Authelia kann trotzdem sinnvoll sein.

## Uploads und Bildauslieferung

Beim Speichern werden Bilder vollständig validiert, bevor ein Nutzungseintrag angelegt wird:

* maximal `MAX_UPLOAD_IMAGES` Bilder pro Eintrag
* maximal `MAX_UPLOAD_SIZE_MB` MB pro Bild
* Prüfung mit Pillow, ob die Datei tatsächlich als Bild geöffnet und verifiziert werden kann
* nur JPEG, PNG und WebP

Die internen Dateinamen werden zufällig per UUID erzeugt und nicht aus Nutzerinput übernommen. Die öffentliche Route `/uploads/{filename}` liefert nur Dateien aus, die als Bildreferenz in der Datenbank gespeichert sind und dem erwarteten UUID-Dateinamenmuster entsprechen. Damit bleiben Bilder für Nutzerinnen und Nutzer über bekannte Links erreichbar, ohne freien Zugriff auf beliebige Dateien im Upload-Verzeichnis zu erlauben.

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

Die Räume werden beim Start aus `ROOM_DEFINITIONS` in `app/constants.py` in die Datenbank geschrieben oder aktualisiert. Bestehende Nutzungseinträge bleiben dabei erhalten.

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
