# Zelter5 Raumlog

FastAPI-Anwendung zur Dokumentation gemeinsamer Räume: Werkstatt, Dachterrasse,
Sommerküche, Sauna und Ruheraum. Öffentliche QR-Formulare erfassen Nutzungen und
Anmerkungen. Ein Raum-QR-Code vermittelt eine globale serverseitige Leseberechtigung für
alle Raumlogbücher, Bilder, QR-PDF-Downloads und das Kopieren von Zugangslinks, ohne Bewohnerkonto.
Die Administration verwaltet zusätzlich allgemeine Nachrichten, Soft-Deletes und Raumschlüssel.

Die Einrichtung des Master-Schlüssels, der erste Ausdruck und die Rotation stehen in
[QR_ACCESS.md](QR_ACCESS.md).

## Starten

Python 3.11 oder neuer:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=ein-langes-eigenes-passwort
uvicorn app.main:app --env-file .env --no-proxy-headers --limit-concurrency 32
```

Lokal: <http://localhost:8000>. Für Entwicklung optional `--reload` ergänzen.
Umgebungsvariablen müssen beim Python-Start exportiert sein; die `.env` wird nur
von Docker Compose automatisch und beim obigen lokalen Start ausdrücklich über `--env-file` eingelesen.

Docker:

```bash
mkdir -p data/uploads
docker compose up --build -d
```

Standard: <http://localhost:9000>. `./data:/data` enthält die persistenten Daten.
Der Container läuft ohne Reload und ohne Quellcode-Bind-Mount; nach Codeänderungen
neu bauen. `.env`, Daten, Git-Metadaten und Archive gelangen nicht in den Build-Kontext.
Der Prozess läuft unprivilegiert als `APP_UID:APP_GID` (Standard `1000:1000`),
auch wenn alle Linux-Capabilities entfernt sind. Für einen anderen lokalen Benutzer
vor dem Start `APP_UID` und `APP_GID` passend zum Eigentümer von `data/` setzen:

```bash
APP_UID="$(id -u)" APP_GID="$(id -g)" docker compose up --build -d
```

Die Werte lassen sich auch in `.env` hinterlegen. Das Datenverzeichnis muss für
diese UID beschreibbar sein; SQLite benötigt neben der DB-Datei auch Schreibrechte
im Verzeichnis für WAL-/SHM-Dateien. Vorhandene Daten werden weder automatisch
umgechownt noch durch eine neue Datenbank ersetzt. Bei `attempt to write a readonly
database` zuerst Eigentümer und die konfigurierte UID/GID prüfen; `chmod 777` ist
nicht erforderlich. Bei Rootless-Docker oder User-Namespace-Remapping müssen die
auf dem Host abgebildeten IDs berücksichtigt werden.

Nach Änderungen den laufenden Dienst mit dem neu gebauten Image neu erstellen.

## Navigation und mobile Nutzung

Die Weboberfläche kombiniert **Noto Serif Display** für Seitentitel und Raumnamen
auf Karten mit **Google Sans Flex** für Fließtext, Daten und Bedienung. App-Name
und Verwaltungskopf verwenden ebenfalls Noto Serif Display. Beide Familien werden lokal
ausgeliefert; es entstehen keine Font-Anfragen an Google. QR-PDFs betten weiterhin
unverändert Google Sans Flex ein. Quellen, feste Asset-Versionen, Prüfsummen und
Lizenzen stehen unter [app/static/fonts](app/static/fonts/README.md).

### Typografie

Der Kopfbereich zeigt einmalig „Zelter5 Raumlog“ beziehungsweise „Zelter5 Verwaltung“
in Noto Serif Display Bold (700), mit 24 bis 32 Pixeln und Zeilenhöhe 1,15.
Die Schriftzüge bleiben Links zur jeweiligen Startseite und dürfen umbrechen.

Die Schriftrollen sind zentral in `app/static/styles/typography.css` definiert.
Seitentitel verwenden Noto Serif Display Medium (500), normal breit und aufrecht:
32 bis 40 Pixel (`clamp(2rem, 1.5rem + 1.25vw, 2.5rem)`), Zeilenhöhe 1,15 und
ausgewogene Umbrüche. Raumnamen auf Karten verwenden denselben Schnitt mit 24 Pixeln
und Zeilenhöhe 1,25. Lange Titel bleiben vollständig sichtbar und können umbrechen.
Abschnittsüberschriften stehen in Google Sans Flex 600 mit 20 Pixeln und
Zeilenhöhe 1,35; kleinere Inhaltsüberschriften und FAQ-Fragen behalten ihre Größen.
Formularbeschriftungen und Navigation verwenden 600, Eingaben 400, Hauptaktionen 700.

Fließtext hat Zeilenhöhe 1,6; längere Texte in Hilfe/Datenschutz 1,65 und kompakte
Kartenbeschreibungen weiterhin 1,45. Zwischen Titel und Einführung stehen 12 Pixel,
zwischen Einführung und Inhalt 24 Pixel; Raumkarten behalten 8 Pixel zwischen Name
und Beschreibung. Inhaltsbreiten, Raster und Formularanordnung bleiben erhalten.

Die Latin-Dateien der Serif-Schnitte werden zusätzlich vorgeladen; Latin Extended
lädt bei Bedarf. `font-display: swap` mit Georgia als Serif-Ersatz hält die Seiten
auch bei fehlenden Schriftdateien benutzbar. Gewichte und Farben sind in Hell und
Dunkel identisch definiert; es gibt keine zusätzlichen Kursiv- oder Zierschnitte.

Die drei Hauptseiten heißen **Räume**, **Logbuch** und **Hilfe & Infos**. Sie stehen
auch nach einem QR-Scan als gleich breite Tabs im Header. Im geöffneten Raum heißt
der erste Tab **Alle Räume** und führt zurück zur Übersicht. Der vorhandene Admin-Button
rechts im Header führt direkt nach `/admin`, ohne Aufklappmenü. Ohne gültige Anmeldung
erscheint zuerst die Anmeldeseite. Das Layout der öffentlichen Seiten bleibt unverändert.

Die Verwaltung hat einen eigenen Kopfbereich mit **Verwaltung**, **Zur App**,
Darstellungswechsel und **Abmelden** sowie die Navigation **Einträge · Nachrichten ·
QR-Zugänge**. Die drei Bereiche bündeln ausschließlich die bisherigen Funktionen.
Eintragsdetails und `/admin/logbuch` bleiben erreichbar; **Zur App** öffnet die
öffentliche Raumübersicht.

Unter dem Raumformular stehen die letzten drei nicht gelöschten Buchungen dieses
Raums als kompakte Karten. **Alle Buchungen anzeigen** öffnet das raumgefilterte
Logbuch. Die Vorschau wird separat mit Reader-/Admin-Berechtigung nachgeladen;
das öffentliche Formular enthält keine Buchungsdaten. Bei fehlendem Zugang erscheint
ein QR-Hinweis. Bildaktionen verwenden denselben geschützten Bildbetrachter wie das Logbuch.

Die aktuellen Adressen sind `/logbuch`, `/hilfe` und `/admin/nachrichten`.
Die bisherigen Adressen `/letzte-buchungen`, `/anmerkungen` und `/admin/anmerkungen`
wurden ohne Weiterleitungen oder Alias-Routen entfernt. Neu erzeugte QR-Links
benötigen keinen besonderen Formularmodus; der Header ist einheitlich.

### Bewohneransichten

Aktionsicons stammen aus lokal gebündelten Lucide-SVGs. Herkunft, feste Revision,
Prüfsummen und ISC-/MIT-Lizenz liegen unter `app/static/icons/lucide/`. Ein gemeinsames
Jinja-Makro liefert 22-Pixel-Icons mit einheitlicher Strichstärke; reine Icon-Aktionen
haben 44-Pixel-Bedienflächen ohne sichtbaren Rahmen oder Hintergrund sowie
Hinweise bei Hover oder Tastaturfokus.
Der Darstellungswechsel zeigt die Zielansicht (Mond für dunkel, Sonne für hell).
Nach erfolgreichem Link-Kopieren erscheint für zwei Sekunden ein Häkchen; bei
Clipboard-Fehlern bleibt der manuell kopierbare Link erhalten. Die Icons benötigen
keine zusätzliche JavaScript-Bibliothek und keine externen Netzwerkanfragen.

Raumkarten sind native Links und funktionieren ohne JavaScript. Das Raster zeigt
je nach Breite eine, zwei oder drei Spalten; Raum- und Nachrichtenformulare sind
auf 760 Pixel begrenzt. „Hilfe & Infos“ erklärt Nutzung, globalen QR-Lesezugang,
Datensichtbarkeit, lokale Eingaben und Bildlimits. Der Link `/hilfe#qr-zugang`
öffnet die passende Erklärung direkt.

Im Raumformular steht der Datenschutzhinweis direkt über „Nutzung speichern“.
Die Speicheroption für Name, Haus und Nummer, das Entfernen gespeicherter Angaben
und der Feedbackhinweis stehen im Footer der Raumseiten. Nach erfolgreichem
Speichern ist „Zur Raumübersicht“ die Hauptaktion; die Raum-Checkliste bleibt
erhalten. Verwaltungsfilter umbrechen unter 1024 Pixeln auf mehrere Zeilen.

Das Logbuch unterstützt kombinierbare GET-Filter: `raum` (aktiver Raumslug),
`zustand` (einer der drei angebotenen Zustände), `q` (wörtliche Teilstringsuche,
maximal 100 Zeichen) und `seite` (1 bis 1000000, Standard 1). Gesucht wird in Name,
Haus, Bemerkung und Raumname. Pro Seite erscheinen 20 nicht gelöschte Einträge,
sortiert nach Zeitpunkt und ID absteigend. „Neuere“/„Ältere“ behalten die Filter;
Raum- und Suchänderungen beginnen auf Seite 1. Ungültige Filter liefern eine
HTML-Antwort mit Status 400. Bei gleichzeitigen neuen Einträgen kann sich die
Zuordnung zu den nummerierten Seiten verschieben.

Mit Leseberechtigung lädt die Raumübersicht über `/rooms/latest-status` die
letzte nicht gelöschte Meldung je aktivem Raum nach. Die JSON-Liste enthält nur
`slug`, `condition` und `started_at`; ohne Eintrag sind die letzten beiden Werte
`null`. Der öffentliche HTML-Inhalt enthält keine Meldungsdaten. Der geschützte
Abruf verlängert eine gültige Reader-Sitzung, der Abruf der öffentlichen Übersicht
allein nicht. Die Admin-Variante `/admin/rooms/latest-status` verwendet ausschließlich
die bestehende Admin-Authentifizierung. Zustand und Zeitpunkt beschreiben eine
frühere Meldung, keine aktuelle Belegung oder verbindliche Freigabe des Raums.

Normale Browseraufrufe der Bewohnerseiten erhalten bei fehlendem Zugang oder
Übertragungs-/Dienstfehlern eine gestaltete Fehlerseite mit Navigation und dem
ursprünglichen HTTP-Status. Daten-, PDF- und Bildendpunkte behalten ihre bisherigen
Antwortformate. Sitzungswiderruf unmittelbar vor der Auslieferung wird weiterhin
vor der Ausgabe privater Inhalte geprüft.

Formulare zeigen feldbezogene Fehler mit fokussierter Zusammenfassung und erhalten
übermittelte Textwerte bei Validierungsfehlern. Bilder müssen danach erneut gewählt
werden. Die optionale Browserprüfung von Bildanzahl und Dateigröße ersetzt keine
serverseitige Prüfung. Während einer Übermittlung verhindert die Oberfläche weitere
Absendeversuche; dies ist keine serverseitige Idempotenzgarantie. Nach erfolgreichem
Speichern folgt weiterhin eine 303-Weiterleitung. Die Nutzungsdaten bleiben unverändert.

## Zugriffsmodell

| Route | Zugriff und Zweck |
| --- | --- |
| `/` | öffentliche Raumübersicht |
| `/r/{raum}` | öffentliches Meldeformular |
| `/r/{raum}/submit` | öffentliches POST, begrenzt und validiert |
| `/r/{raum}/qr.pdf` | QR-PDF mit globaler Reader-Sitzung oder Admin-Anmeldung |
| `/r/{raum}/access-link` | bewusster POST zum Kopieren eines Zugangslinks, nur Reader/Admin |
| `/r/{raum}/access` | Same-Origin-JSON-POST: Raumtoken gegen globale Reader-Sitzung eintauschen |
| `/r/{raum}/recent-bookings` | geschütztes HTML-Fragment mit höchstens drei Buchungen des Raums |
| `/admin/rooms/{id}/recent-bookings` | dieselbe Vorschau unter Admin-Authentifizierung |
| `/thanks` | öffentliche Bestätigung ohne gespeicherte Personendaten |
| `/hilfe` | Hilfe & Infos mit öffentlichem Nachrichtenformular, keine eingegangenen Nachrichten |
| `/admin/nachrichten` | eingereichte Nachrichten, nur Admin |
| `/logbuch` | globale Reader-Ansicht aller nicht gelöschten Nutzungen |
| `/rooms/latest-status` | geschützte JSON-Liste der letzten Zustandsmeldungen aktiver Räume |
| `/admin/rooms/latest-status` | dieselben minimalen Zustandsdaten unter Admin-Authentifizierung |
| `/admin` | gefilterte Verwaltungsübersicht, nur Admin |
| `/admin/anmelden` | GET Anmeldeformular, POST Anmeldung mit CSRF und Same-Origin-Schutz |
| `/admin/abmelden` | POST widerruft die aktuelle Admin-Sitzung mit CSRF-Schutz |
| `/admin/session/{id}` | aktive Nutzung mit Bildern, nur Admin |
| `/admin/session/{id}/delete` | POST mit Admin-Anmeldung und CSRF-Token |
| `/uploads/{filename}` | globale Reader-Sitzung oder Admin, nur DB-Referenzen nicht gelöschter Nutzungen |
| `/admin/raumzugaenge` | Admin: QR-PDFs, Link-Kopieren und globaler Widerruf |
| `/admin/reader-access/rotate` | Admin-POST mit CSRF: alle QR-Zugänge und Reader-Sitzungen erneuern |
| `/datenschutz` | öffentliche Hinweise zum tatsächlichen Verhalten |

Die Formularanmeldung verwendet weiterhin `ADMIN_USERNAME` und `ADMIN_PASSWORD`.
Fehlen diese, bleiben Admin-Routen gesperrt (503); globale Reader-Sitzungen sind
unabhängig davon möglich. HTTP Basic wird vollständig ignoriert und löst keinen
Browserdialog aus. Bei einem nicht angemeldeten HTML-Aufruf einer Verwaltungsseite
folgt eine 303-Weiterleitung zur Anmeldung; Daten-, Bild-, PDF- und nicht angemeldete
POST-Anfragen liefern 401. Vorhandene Integrationen müssen Basic-Header durch die
Formularanmeldung und Sitzungscookies ersetzen. Interne Verwaltungsziele einschließlich
Query-Filter bleiben nach dem Login erhalten; externe Ziele sind ausgeschlossen.

Das Host-only-Cookie `raumlog_admin` enthält eine zufällige 256-Bit-Kennung:
`HttpOnly; SameSite=Strict; Path=/`, unter HTTPS zusätzlich `Secure`. Es hat kein
persistentes Browser-Ablaufdatum. Die serverseitige, absolute Laufzeit beträgt acht
Stunden und wird beim Lesen nicht verlängert. Browser können Sitzungscookies bei der
Wiederherstellung dennoch behalten; maßgeblich bleiben serverseitiger Ablauf und Logout.
Migration 5 legt dafür nur `admin_sessions` mit SHA-256-Hash, einer an die konfigurierten
Zugangsdaten gebundenen HMAC-Kennung und Ablaufzeit an. Nutzungsdaten werden nicht verändert.
Neue Logins rotieren die Kennung des aktuellen Browsers; abgelaufene Zeilen werden beim
Login entfernt. Die Sitzung überlebt einen Serverneustart innerhalb ihrer Laufzeit und
ist workerübergreifend verfügbar. Änderungen an Benutzername oder Passwort widerrufen
bestehende Admin-Sitzungen.

**Abmelden** löscht die aktuelle Sitzungszeile und beide Admin-/CSRF-Cookies. Eine
wiederverwendete alte Kennung gewährt keinen Zugang. Andere Browseranmeldungen,
Reader-Cookies, gespeicherte Formularangaben und Darstellung bleiben unabhängig erhalten.
Loginversuche verwenden einen eigenen Rate-Limit-Bereich mit den vorhandenen
`RATE_LIMIT_*`-Grenzen; öffentliche Formularbudgets werden dadurch nicht verbraucht.
Die Anmeldeseite speichert Passwörter weder im HTML noch in Protokollen. Benutzername
und Passwort sind auf 256 beziehungsweise 4096 Zeichen begrenzt.

Ohne gültigen Reader-Zugang: 403 ohne `WWW-Authenticate`, unabhängig davon, ob eine
Bilddatei existiert. Mit Lesefreigabe oder Admin-Anmeldung: einheitlich 404 für fehlende,
gelöschte oder anderweitig nicht zugängliche Bilder/Einträge. Alle dynamischen
Antworten einschließlich Validierungsfehlern tragen `Cache-Control: private, no-store`.
Bereits früher heruntergeladene Dateien oder alte Browser-/Proxy-Caches können damit
nicht rückwirkend entfernt werden; vorhandene Proxy-Caches beim Umstieg leeren.
Uploads niemals separat als statisches Verzeichnis im Proxy freigeben.

Zustandsändernde Admin-Routen prüfen routerweit ein signiertes, höchstens eine
Stunde gültiges, an die jeweilige Admin-Sitzung gebundenes Double-Submit-Token im Formular und Host-only-Cookie. Vor der Anmeldung gilt ein getrennt signiertes Login-Token. Cookies sind
HttpOnly, SameSite=Strict und unter HTTPS Secure. Der Signaturschlüssel wird aus den
Admin-Zugangsdaten abgeleitet und ist workerübergreifend gleich; ein Passwortwechsel
widerruft Tokens. Lange, geheime Zugangsdaten und HTTPS sind erforderlich.

## Konfiguration

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `DATA_DIR` | `./data` im Repository | DB und Uploads; im Container `/data` |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | leer | bestehende Zugangsdaten für die Verwaltungsanmeldung |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | erlaubte Hostnamen/IPs, kommasepariert, ohne Port |
| `PUBLIC_BASE_URL` | leer; Compose `http://localhost:9000` | explizite vertrauenswürdige Basis für QR-Links; kein Host-Header-Fallback |
| `QR_MASTER_KEY` | leer | einmalig kryptografisch zufällig erzeugter 256-Bit-Schlüssel als 64 Hex-Zeichen |
| `READER_SESSION_DAYS` | `365` | Sliding Expiration: erneute Laufzeit ab jedem erfolgreichen geschützten Reader-Zugriff |
| `TRUSTED_PROXIES` | leer | explizit vertraute Proxy-IP-Adressen/CIDR-Netze |
| `APP_UID`, `APP_GID` | `1000`, `1000` | Container-UID/GID; passend zum Eigentümer des Datenverzeichnisses setzen |
| `HOST_PORT` | `9000` | veröffentlichter Docker-Port |
| `HOST_BIND` | `0.0.0.0` | Docker-Bind-Adresse; bei lokalem Proxy `127.0.0.1` setzen |
| `MAX_UPLOAD_IMAGES` | `5` | Bilder je Nutzung |
| `MAX_UPLOAD_SIZE_MB` | `5` | maximale Eingabe- UND neu codierte Größe je Bild, MiB |
| `MAX_REQUEST_SIZE_MB` | `26` | gesamte HTTP-Anfrage, inklusive Multipart-Overhead; Python-Default Bilderanzahl × Bildlimit + 1 |
| `MAX_UPLOAD_STORAGE_MB` | `1024` | Größe aller Dateien im Upload-Verzeichnis, auch alte/verwaiste Dateien |
| `MAX_IMAGE_DIMENSION` | `10000` | längste Bildseite, Pixel |
| `MAX_IMAGE_PIXELS` | `20000000` | maximale decodierte Pixelzahl |
| `REQUEST_BODY_TIMEOUT_SECONDS` | `30` | Gesamtdauer zum Einlesen einer mutierenden Anfrage |
| `RATE_LIMIT_COUNT` | `10` | öffentliche Formular-/Raumzugang-Versuche je Client und Zeitfenster |
| `RATE_LIMIT_GLOBAL_COUNT` | `100` | Übermittlungsversuche aller Clients zusammen je Zeitfenster |
| `RATE_LIMIT_WINDOW_SECONDS` | `600` | Dauer eines festen Fensters ab erstem Versuch |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | Wartezeit bei DB-Sperren |
| `MAX_NAME_LENGTH` | `100` | Namen |
| `MAX_HOUSE_LENGTH` | `10` | gesamte Hausangabe, einschließlich zweistelliger Gruppe |
| `MAX_COMMENT_LENGTH` | `2000` | Bemerkungen und Zusatzfelder |
| `MAX_GENERAL_NOTE_LENGTH` | `4000` | Anmerkungen |

Hausgruppen: TH, GH, PH. Nummern enthalten ausschließlich ASCII-Ziffern; mit dem
Standardlimit sind maximal acht Ziffern möglich, auch im HTML-Formular.
Ungültige/nicht positive numerische Einstellungen verwenden geloggte Defaults.
Bei eigenen Uploadlimits alle drei Grenzen für Dateigröße, Dateianzahl und gesamte
Request-Größe passend konfigurieren. Eine ausgeschöpfte Bildquote verhindert keine
Nutzung ohne Bilder. Für DB, SMTP, Backups und temporäre Multipart-Dateien zusätzlichen
Platz reservieren; die Bildquote ist keine Dateisystemquote.

Beispiel für eine LAN-Installation in `.env` (Adresse anpassen):

```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD=hier-ein-langes-geheimes-passwort
ALLOWED_HOSTS=192.168.2.127,localhost,127.0.0.1
PUBLIC_BASE_URL=http://192.168.2.127:9000
HOST_PORT=9000
```

Für Raumzugänge HTTPS verwenden. Nur für die lokale Entwicklung sind HTTP-Adressen
mit `localhost`, `127.0.0.1` oder `::1` als Basis zugelassen. Das Lesecookie ist unter HTTPS `Secure`; unter lokalem HTTP wird es ohne dieses Flag gesetzt. Es bleibt immer HttpOnly und hostgebunden.
`PUBLIC_BASE_URL` akzeptiert keine fremden Schemen, Zugangsdaten, Querystrings oder
Fragmente und wird beim Start geprüft. Ohne explizite Basis wird kein QR-Code erzeugt;
es gibt keinen Fallback auf den Request-Host. Ohne Master-Schlüssel bleiben die öffentlichen
Formulare und die Admin-Verwaltung verfügbar; der QR-Zugang und die PDF-Erzeugung sind gesperrt.

## Proxy und Ressourcenbegrenzung

Uvicorn **immer mit `--no-proxy-headers`** starten (in Docker bereits eingestellt).
Sonst könnte Uvicorn Header vor der Anwendung auswerten und deren Vertrauensprüfung
umgehen. Die App wertet `X-Forwarded-For` und `X-Forwarded-Proto` ausschließlich aus,
wenn die tatsächliche Gegenstelle in `TRUSTED_PROXIES` liegt. Bei mehreren Proxies
wird die IP-Kette von rechts bis zum ersten nicht vertrauten Hop ausgewertet.
`Forwarded` und `X-Forwarded-Host` werden nicht für Identität oder QR-URLs benutzt.
Keine pauschalen Netze wie `0.0.0.0/0` vertrauen. Vorgeschaltete Proxies müssen eingehende
Forwarding-Header überschreiben. Bei Docker die tatsächlich am Container sichtbare
Proxy-Adresse konfigurieren, nicht pauschal das ganze Docker-Netz.

Die App liest mutierende Requests vollständig und mit Byte-/Zeitlimit ein, bevor
Multipart verarbeitet wird, auch ohne `Content-Length`. Überschreitungen ergeben 413,
Zeitüberschreitungen 408. Ratenüberschreitungen ergeben 429 mit `Retry-After`.
SQLite serialisiert die Prüfung/Zählererhöhung; ein persistenter geheimer Schlüssel
pseudonymisiert IPs. Neustarts und mehrere Worker mit derselben DB setzen die Limits
nicht zurück. Bei DB-Ausfall wird keine öffentliche Übermittlung angenommen (503).
Ungültige Formulare zählen ebenfalls. Ein fester Fensterwechsel kann kurzfristig
zwei volle Kontingente zulassen; ein gemeinsamer NAT-Zugang teilt sich das Clientlimit.

Die App begrenzt keine vorgelagerten Verbindungen, Headergrößen oder Proxy-Puffer.
Request-Daten werden begrenzt im RAM gepuffert und Bilder im Worker decodiert. Daher
auch am Proxy Verbindungen/Requests begrenzen und Workerzahl, RAM und Uvicorns
`--limit-concurrency` abstimmen. Eine öffentliche Installation braucht diese Grenzen
zusätzlich zu den Anwendungslimits. Bei getrennten Instanzen ist eine gemeinsame
lokale SQLite-Datei erforderlich; SQLite-WAL nicht über Netzwerkdateisysteme betreiben.

Nginx-Beispiel innerhalb eines bereits eingerichteten HTTPS-Servers (im `http`-Block
`limit_conn_zone $binary_remote_addr zone=raumlog_connections:10m;` definieren):

```nginx
server_name raumlog.example.org;
client_max_body_size 26m;
client_body_timeout 30s;
client_header_timeout 10s;
limit_conn raumlog_connections 10;
location / {
    proxy_pass http://127.0.0.1:9000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_request_buffering on;
    proxy_cache off;
}
```

Für dieses Beispiel `ALLOWED_HOSTS=raumlog.example.org`, `PUBLIC_BASE_URL=https://raumlog.example.org`,
`HOST_BIND=127.0.0.1` und `TRUSTED_PROXIES` passend zur wirklichen Proxy-Gegenstelle setzen.
Proxy-Timeouts messen teils Pausen, während das Anwendungslimit die gesamte Übertragung
begrenzt. HTTPS-Zertifikate und weitere Serverblöcke sind in diesem Ausschnitt nicht enthalten.

## Datenbank und vorhandene Uploads

Beim Start richtet `lifespan` Datenverzeichnisse und DB ein. Jede Verbindung hat
explizites Close, Commit/Rollback und Busy-Timeout; WAL wird zentral initialisiert.
`schema_migrations` protokolliert additive, idempotente Schemaergänzungen, `app_state`
hält Initialisierungsmarker und den persistenten Rate-Limit-Schlüssel. Alle Schema-
und Seed-Änderungen erfolgen in einer Transaktion. Es gibt keine DROP-, DELETE- oder
Rebuild-Migrationen für Nutzungsdaten.

`ROOM_DEFINITIONS` sind **Startwerte für eine neue, leere Raumkonfiguration**.
Vorhandene Räume bleiben einschließlich Namen, Zusatzfeldern, Sortierung und
Deaktivierung unverändert. Eine bereits vorhandene Teilkonfiguration wird nicht
mit Standardräumen aufgefüllt. Nach erstmaligem Seeding werden auch bewusst entfernte
Räume nicht neu angelegt. Künftige Raumänderungen explizit in der DB vornehmen;
Änderungen in `constants.py` verändern bestehende Installationen nicht mehr.

Neue Bilder: JPEG/PNG/WebP, Strukturprüfung plus vollständige Decodierung,
Decompression-Bomb-/Dimensionsgrenzen, keine Animationen, Neucodierung mit korrigierter
EXIF-Orientierung und ohne eingebettete Metadaten. Zufällige Dateinamen, atomare
Publikation ohne Überschreiben und DB-Transaktion verhindern partielle Einträge bei
behandelbaren Datei-/DB-Fehlern. Auch unerwartete Exceptions lösen Dateiaufräumen aus.
Vorhandene Uploads werden nicht neu codiert und nicht gelöscht. Bei Prozessabsturz
zwischen Dateipublikation und DB-Commit können unreferenzierte Dateien verbleiben;
Dateisystem und SQLite sind keine gemeinsame atomare Transaktion.

Soft-Delete erhält Daten und Dateien intern, sperrt jedoch Listen, Details und Bilder.
Es gibt noch keine automatische endgültige Löschung. Die Strategie zur späteren
Bereinigung einschließlich Dry-Run, Schonfrist und Backup-Behandlung steht in
[SECURITY_REVIEW.md](SECURITY_REVIEW.md).

## Globaler QR-Zugang und CSRF

Ein Scan eines beliebigen gültigen Raumcodes erteilt globale Leserechte: alle
Raumlogbücher, Bilder, QR-PDFs und Zugangslinks. Der QR-Link öffnet weiterhin das
konkrete Raumformular. Rechts neben dem Raumnamen stehen kompakte Icons für QR-PDF
und Zugangslink-Kopieren. Der Link zum Raumlogbuch steht im Kopf der Buchungsvorschau;
die Raumkarten zeigen
die kleinen QR-Icons für alle Räume.
Allgemeine Anmerkungen und administrative Änderungen bleiben Admin-Sache.

Die zentrale Dependency `require_reader` prüft die serverseitige Sitzung. Die Middleware
verlängert erst vor einer erfolgreichen geschützten Antwort (`2xx`) sowohl den
SQLite-Ablauf als auch `Max-Age` und `Expires` des Cookies. Vorgabe: 365 Tage ab jetzt,
ohne 90-Tage-Schwelle. Öffentliche Seiten/Formulare, Fehler und Admin-Authentifizierung
allein verlängern keine Reader-Sitzung. Der separate erfolgreiche Abruf der geschützten
Buchungsvorschau zählt als Reader-Zugriff und verlängert die Sitzung. Bei zwischenzeitlichem Ablauf/Widerruf werden
weder private Antwortdaten noch ein verlängertes Cookie ausgegeben.

Ein gültiger erneuter QR-Scan verlängert dieselbe Sitzung. Abgelaufene oder widerrufene
Kennungen werden nicht reaktiviert; ein bewusster neuer Scan eines aktuellen gültigen
Codes erstellt eine neue Kennung. Cookies sind HttpOnly, SameSite=Lax und unter HTTPS
Secure, ohne Domain-Attribut. Sie bleiben über Browserneustarts erhalten.

Da jeder Reader alle Raumcodes kennt, bietet die Admin-Seite ausschließlich einen
**globalen Widerruf** an: alle Raumtoken-Versionen und die globale Berechtigungsversion
werden atomar erhöht. Sämtliche alten Codes und Reader-Sitzungen sind anschließend
ungültig. Eine vermeintlich unabhängige Sperrung nur eines Raumcodes gibt es nicht mehr.

PDF-Layout und Master-Schlüssel bleiben erhalten. Migration 4 ergänzt eine globale
Sitzungsversion. Alte 7-Tage-Sitzungen werden in der Entwicklung bewusst nicht
hochgestuft; einmal neu scannen. Bestehende gedruckte Raumcodes bleiben beim Upgrade
gültig, sofern keine globale Rotation ausgelöst wird. Alte Raumfreigabe-Tabellen bleiben
bei vorhandenen Datenbanken ungenutzt erhalten; neue Datenbanken benötigen sie nicht.

Token-Tausch und öffentliche Formular-POSTs verlangen weiterhin eine passende Origin
oder bestätigte Same-Origin-Fetch-Metadaten; Admin-Änderungen das signierte CSRF-Token.
Der geheime Zugangslink wird nur nach einem bewussten POST ausgegeben, nicht vorab
ins HTML eingebettet. Kein Endpunkt fordert einen Basic-Dialog an.
Admin-Ansichten verwenden für Bilder/PDFs eigene `/admin/...`-Adressen mit derselben
bestehenden Admin-Authentifizierung, ohne eine zusätzliche Reader-Sitzung vorauszusetzen.

Details, Schlüsselsicherung, Widerrufsfolgen und aktuelle Testergebnisse:
[QR_ACCESS.md](QR_ACCESS.md).

## E-Mail

Optional: `SMTP_HOST`, `SMTP_FROM`, `SMTP_TO`. Weitere Einstellungen:
`SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS=true`, `SMTP_SSL=false`.
Für direktes TLS typischerweise Port 465, `SMTP_SSL=true`, `SMTP_STARTTLS=false`.
TLS-Zertifikate werden geprüft. Die Nachricht benennt den tatsächlich gewählten Raum.
Es werden keine Bilder angehängt; Name, Haus und Bemerkung werden an den konfigurierten
Empfänger gesendet. Adressen und Serverantworten werden bei Fehlern nicht protokolliert.

Versand erfolgt nach der HTTP-Antwort als FastAPI-BackgroundTask im Worker-Thread.
SMTP-Fehler berühren gespeicherte Einträge nicht. Es gibt keine persistente Queue,
keine Zustellgarantie und keinen automatischen Wiederholungsversuch; Prozessabstürze
oder Neustarts können Nachrichten verlieren. Für garantierte Zustellung wäre eine
separate persistente Outbox notwendig.

## Browser und Datenschutz

Name, Haus und Nummer werden standardmäßig bereits beim Ausfüllen lokal gespeichert
und zwischen Raumformularen übernommen. Die Speicheroption lässt sich ausschalten;
`usage_remember=no` hält diese Entscheidung über Neustarts hinweg fest.
„Gespeicherte Eingaben entfernen“ löscht die drei Werte und schaltet das Merken aus.
Der optionale Name unter Hilfe & Infos wird vorgefüllt; dortiges Entfernen für eine
anonyme Nachricht oder Ändern beeinflusst das gespeicherte Raumprofil nicht.
Validierungsfehler zeigen die tatsächlich übermittelten Werte; Bemerkungen, Nachrichten,
Zustand und Bilder werden nicht lokal gespeichert. Bei blockiertem localStorage bleiben Formulare, Theme und Viewer
benutzbar. Theme-Einstellung ist unabhängig von Personendaten. Object-URLs für Vorschauen
werden bei Laden, Fehlern, Ersetzen, Entfernen und Verlassen der Seite freigegeben.
Der Viewer unterstützt Tab/Shift+Tab, Pfeiltasten, Escape und Fokuswiederherstellung;
der Seiteninhalt ist währenddessen inert. Asset-Hashes und Revalidierung der importierten
Stylesheets verhindern veraltete Assets. Das bestehende Layout bleibt erhalten.

Die Seite `/datenschutz` fasst Datenarten und Zwecke, Sichtbarkeit und Weitergabe,
Browser-Speicherung, Bilder, Aufbewahrung und Kontakt in offen lesbaren Abschnitten
zusammen. Die angezeigte Reader-Laufzeit stammt aus `READER_SESSION_DAYS`.
Bedienung und praktische Fragen stehen unter `/hilfe`; `/hilfe#qr-zugang`,
`/hilfe#geraet` und `/hilfe#nachricht` führen direkt zum jeweiligen Thema.
Interne technische Einzelheiten bleiben in dieser Dokumentation: Raumtokens werden
gegen eine Reader-Sitzung getauscht und aus der Adresszeile entfernt. Die Datenbank
speichert die Sitzungskennung gehasht, Ablaufzeit und Berechtigungsversion. Geschützte
Ansichten und QR-PDFs erhalten Anweisungen gegen Browser- und Proxy-Caching.
Die IP-abgeleitete Kennung für den Spamschutz wird mit einem geheimen Schlüssel erzeugt;
das Ablaufen und Entfernen der Zähler ersetzt keine Aufbewahrungsregel für Serverprotokolle.

Der Betreiber muss weiterhin
Verantwortlichen, Kontakt, Rechtsgrundlage und konkrete Aufbewahrungsfristen für
App, E-Mail, Backups und gegebenenfalls Serverprotokolle ergänzen.

## Backup und Update

Vor dem Update konsistentes DB-Backup mit SQLite-Backup-API oder im gestoppten Dienst
erstellen und Uploads sichern. Bei WAL-Betrieb ist das Kopieren nur von `app.db` im
laufenden Betrieb kein verlässliches Backup. Backups gegen unberechtigten Zugriff schützen.
Die ursprüngliche DB nicht durch eine leere Datei ersetzen.

1. Datenbank und Uploads sichern.
2. Zugangsdaten, `ALLOWED_HOSTS`, `PUBLIC_BASE_URL`, Proxy-Vertrauen und Limits prüfen.
3. Abhängigkeiten neu installieren bzw. Container neu bauen.
4. Anwendung starten; additive Migration läuft automatisch.
5. Anonymes Melden und angemeldete Verwaltung/Bildauslieferung prüfen.
6. Alte Proxy-Caches und gegebenenfalls Browserdaten bereinigen.

Wichtige Verhaltensänderungen: bisher öffentliche Datenansichten verlangen Reader-
oder Admin-Zugang; allgemeine Anmerkungen und Verwaltung bleiben Admins vorbehalten.
Gelöschte Details liefern 404; direkte Admin-POSTs brauchen ein CSRF-Token; Bilder werden
neu codiert und Animationen abgelehnt; strengere Hosts und kleinere Compose-Uploaddefaults;
kein automatisches Überschreiben der Raumkonfiguration und kein Reload im Container.
Eine vorhandene `.env` überschreibt Compose-Defaults weiterhin.

## Tests und CI

```bash
pip install -r requirements-dev.txt
python -m pytest -q --ignore=tests/test_browser.py --ignore=tests/test_capability_browser.py
ruff check app tests
ruff format --check app tests
```

Für echte Browsertests zusätzlich:

```bash
pip install -r requirements-browser.txt
# OpenSSL muss für die lokalen HTTPS-Browsertests verfügbar sein.
playwright install chromium
python -m pytest -q
```

System-Chromium wird verwendet, wenn vorhanden, sonst Playwright-Chromium. Tests
verwenden ausschließlich temporäre DBs/Uploads, auch beim Import. Sie versenden keine
realen E-Mails. CI prüft Python 3.11/3.13/3.14 sowie Chromium separat.
Zusätzliche Docker-Regressionen (Docker-Daemon erforderlich, separate temporäre Daten):

```bash
docker compose build werkstatt-log
RUN_DOCKER_TESTS=1 python -m pytest -q tests/test_docker.py
```

Die Tests verwenden das Image `werkstatt-log-mvp-werkstatt-log`; bei abweichendem
Image-Namen `RAUMLOG_TEST_IMAGE` setzen. Ein eigener CI-Job baut und prüft das Image.

Die aktuelle lokale Verifikation und verbleibende Einschränkungen stehen im
[Abschlussbericht](SECURITY_REVIEW.md).

Technische Referenzen: [FastAPI Lifespan](https://fastapi.tiangolo.com/advanced/events/),
[FastAPI BackgroundTasks](https://fastapi.tiangolo.com/tutorial/background-tasks/),
[Pillow Bild-API](https://pillow.readthedocs.io/en/stable/reference/Image.html),
[Nginx Request-Grenzen](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size).

### Icons in Navigation und Raumübersicht

Die öffentliche Navigation ergänzt ihre Texte um offene Tür, Notizbuch und
Fragezeichen. Raumkarten zeigen Schraubenschlüssel, Geländer, Kochtopf, Heizkörper
oder Sessel links vom Namen. Die Zuordnung liegt zentral in `ROOM_ICONS`; unbekannte
Raum-Slugs erhalten die offene Tür. Alle Symbole sind dekorative, lokal gelieferte
Lucide-SVGs (22 px, Strichstärke 2), ohne eigene Tabstopps. Texte und QR-Download
bleiben eigenständig bedienbar; die Verwaltungsnavigation bleibt unverändert.
