# Globaler QR-Lesezugang und dauerhafte Reader-Sitzungen

Ein beliebiger gültiger Raum-QR-Code erteilt dieselbe **globale Leseberechtigung**.
Der QR-Link öffnet weiterhin das Formular seines Raums. Danach kann der Browser alle
Raumlogbücher und zugehörigen Bilder lesen, alle aktiven Raum-QR-PDFs nachdrucken und
Zugangslinks kopieren. Weitere Räume benötigen keinen erneuten Scan. Öffentliche
Formulare und das Eintragen einer Nutzung bleiben ohne Reader-Zugang verfügbar.

## Reader und Admin

| Funktion | Öffentlich | Reader | Admin |
| --- | --- | --- | --- |
| Räume/Formulare öffnen, Nutzung oder Anmerkung einsenden | ja | ja | ja |
| Raumlogbücher und zugehörige nicht gelöschte Bilder lesen | nein | alle Räume | alle Räume |
| QR-PDFs und Zugangslinks ausgeben | nein | alle aktiven Räume | alle aktiven Räume |
| Allgemeine Anmerkungen lesen, Einträge verwalten/löschen | nein | nein | ja |
| Alle QR-Zugänge und Reader-Sitzungen widerrufen | nein | nein | ja, mit CSRF-Schutz |

`require_reader` ist die zentrale Dependency geschützter Reader-Endpunkte. Eine
fehlende, abgelaufene oder widerrufene Reader-Berechtigung ergibt **403 ohne
WWW-Authenticate**. Es erscheint kein Browser-Anmeldedialog. Die Verwaltung verwendet
eine eigene Formularanmeldung mit einer serverseitigen Admin-Sitzung; HTTP Basic wird
nicht mehr akzeptiert. Reader-Cookies erteilen keine Admin-Rechte.

Die Admin-Oberfläche verwendet für ihre Bilder, PDFs und Kopieraktionen `/admin/...`-
Adressen. Diese prüfen dieselbe Admin-Sitzung wie die übrige Verwaltung. Es wird
keine zusätzliche Reader-Sitzung angelegt und kein neues Kontensystem eingeführt.
Die konfigurierten Admin-Zugangsdaten bleiben unverändert. Das Admin-Cookie ist
unabhängig vom QR-Lesezugang, gilt höchstens acht Stunden und wird beim Abmelden
serverseitig widerrufen. Anmeldung, Cookieattribute und Migration sind im README dokumentiert.

Die Hauptnavigation trennt Räume, Logbuch (`/logbuch`) und Hilfe & Infos (`/hilfe`).
Das öffentliche Nachrichtenformular unter Hilfe & Infos gibt keine eingegangenen
Nachrichten aus; diese stehen ausschließlich unter `/admin/nachrichten` bereit.
Die früheren öffentlichen Logbuch-/Anmerkungsadressen und `/admin/anmerkungen`
wurden ohne Kompatibilitätsrouten entfernt.

Im geöffneten Raum lädt die separate Gruppe „Letzte Buchungen“ höchstens drei
nicht gelöschte Einträge dieses Raums nach. `/r/{slug}/recent-bookings` verwendet
dieselbe zentrale Reader-Dependency wie das Logbuch. Die Administration verwendet
`/admin/rooms/{id}/recent-bookings` mit derselben Admin-Sitzung wie die übrige Verwaltung. Karten und Bilder bleiben geschützt; der
öffentliche HTML-Formularabruf enthält keine Buchungsdaten.

## Erster Ausdruck und lokaler Betrieb

Unter `/admin/raumzugaenge` kann die Administration die ersten PDFs ausdrucken oder
Zugangslinks kopieren. Nach einem Scan erscheinen diese Aktionen im geöffneten Raum
als kleine QR-Code- und Link-Icons rechts neben dem Raumnamen. Der Kopier-Button
fordert den geheimen Link erst nach einem bewussten
Klick per geschütztem Same-Origin-POST an; der Token steht nicht vorab im HTML.
Ist die Zwischenablage nicht verfügbar, wird nach diesem Klick ein auswählbares
Linkfeld angeboten. Die Anwendung speichert weder Reader-Kennungen noch QR-Tokens
in localStorage oder sessionStorage.

Die vorhandene lokale Basis bleibt auf Wunsch `http://localhost:9000`.
Für andere Geräte muss `PUBLIC_BASE_URL` eine erreichbare HTTPS-Adresse enthalten.
HTTP ist ausschließlich für Loopback-Entwicklung zugelassen. `ALLOWED_HOSTS`,
`TRUSTED_PROXIES` und Uvicorns `--no-proxy-headers` weiterhin passend konfigurieren.
Die QR-Basis wird ausdrücklich konfiguriert und niemals aus dem Host-Header abgeleitet.

## Master-Schlüssel und reproduzierbare Raumtokens

`QR_MASTER_KEY` ist ein pro Installation einmalig kryptografisch zufällig erzeugter
256-Bit-Schlüssel: genau 32 Bytes als 64 Hex-Zeichen. Sichere Erzeugung zum Beispiel:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Die Ausgabe ausschließlich in der geschützten Umgebung bzw. lokalen `.env` hinterlegen,
nicht in Git, Tickets oder geteilten Terminalmitschnitten. Die bereits eingerichtete
`.env` ist auf Modus 0600 beschränkt. Den Schlüssel zusätzlich im Passwortmanager oder
in einem verschlüsselten Backup sichern; SQLite-Backups enthalten ihn nicht. Alle
Worker derselben Installation brauchen denselben Schlüssel und dieselbe Datenbank.

```dotenv
QR_MASTER_KEY=<64-zufaellige-hex-zeichen>
READER_SESSION_DAYS=365
PUBLIC_BASE_URL=https://raumlog.example.org
ALLOWED_HOSTS=raumlog.example.org
```

Es wird kein Schlüssel beim App-Start neu erzeugt und kein unsicherer Default genutzt.
Ein fehlender Schlüssel sperrt den QR-Tausch und die PDF-Erzeugung; öffentliche Formulare
und die Admin-Verwaltung bleiben verfügbar. Ein gesetzter, falsch formatierter Schlüssel
verhindert den Start mit einer generischen Meldung ohne den geheimen Wert.

Die bestehende Ableitung bleibt unverändert:

```text
base64url_without_padding(
  HMAC-SHA256(master, b"zelter5/room-access/v1\0" + ASCII(room_id + ":" + key_version))
)
```

Raum-ID und `qr_key_version` erzeugen weiterhin unterschiedliche Codes je Raum.
Jeder dieser gültigen Codes erteilt aber dieselbe globale Reader-Rolle. Ein Raumtoken
ist weder die Reader-Sitzungskennung noch der Master. Tokenprüfung erfolgt mit
`secrets.compare_digest`; die Master-Erkennung in Sitzungen nutzt die eigene Domain
`zelter5/reader-master-id/v1\0`. Solange Raumversion, ID und Master gleich bleiben,
enthalten wiederholte Downloads denselben QR-Token. Erstellungszeiten im PDF können
variieren; das bestehende A4-Layout bleibt unverändert.

## Sitzungsablauf und Sliding Expiration

Nach dem Scan liest das früh geladene Script `#access=...`, entfernt das Fragment
sofort per `history.replaceState` und tauscht den Token ausschließlich im JSON-Body
eines Same-Origin-POSTs gegen die Sitzung ein. Weder QR-Token noch Sitzungskennung
stehen in HTTP-URLs, Zugriffslogs oder Analytics. Proxies dürfen Bodies und Cookies
nicht protokollieren. Fehlermeldungen geben keine geheimen Eingaben wieder.

Das persistente Host-only-Cookie `raumlog_reader` hat `HttpOnly; SameSite=Lax; Path=/`
und unter HTTPS zusätzlich `Secure`. Unter lokalem HTTP ist Secure nicht gesetzt.
Es enthält eine kryptografisch zufällige 256-Bit-Kennung. SQLite speichert ausschließlich
deren SHA-256-Hash, Master-Erkennung, globale Berechtigungsversion und Ablaufzeit.
Browserneustarts beenden die Sitzung nicht.

`READER_SESSION_DAYS` steuert die Laufzeit, standardmäßig **365 Tage**. Bei jedem
erfolgreichen geschützten Reader-Zugriff wird sie erneut ab dem aktuellen Zeitpunkt
gesetzt. Es gibt keine 90-Tage-Schwelle. Dazu zählen Logbücher, Bilder, QR-PDFs und
bewusst angeforderte Zugangslinks sowie das geschützte Nachladen der drei letzten
Buchungen im Raum. Die Verlängerung läuft vor Beginn der erfolgreichen
Antwort (`2xx`) in einer SQLite-Transaktion. `expires_at` verwendet UTC-Epochsekunden;
Cookie-Expires (GMT/UTC) und Max-Age werden aus demselben Zeitpunkt berechnet.

Öffentliche Übersichten, Formulare, erfolgreiche öffentliche Übermittlungen,
fehlgeschlagene Anfragen und reine Admin-Authentifizierung verlängern keine Reader-
Sitzung. Auch die optionale Prüfung, ob Aktionen auf einer öffentlichen Seite sichtbar
sein sollen, führt keine Verlängerung aus. Der danach separat ausgeführte erfolgreiche
Abruf der privaten Buchungsvorschau verlängert die Reader-Sitzung dagegen regulär.

Ablauf, Master-Erkennung und globale Version werden serverseitig bei jedem geschützten
Zugriff und vor der Verlängerung erneut geprüft. Zwischenzeitlich widerrufene oder
abgelaufene Sitzungen werden nicht reaktiviert; private Antwortdaten und neue Cookies
werden dann nicht ausgegeben. Bei einem DB-Fehler scheitert die Antwort geschlossen.
Ein bereits vollständig ausgelieferter Download lässt sich nicht nachträglich zurückholen.

Ein erneuter Scan mit einer **gültigen bestehenden Sitzung** verlängert dieselbe
Kennung, ohne weitere parallele Sitzung anzulegen. Nach Ablauf/Widerruf ist ein
bewusster Scan eines aktuell gültigen Codes nötig; er erzeugt eine neue Kennung.
Abgelaufene Zeilen werden beim erfolgreichen Scan bereinigt. Eine Deaktivierung des
ursprünglich gescannten Raums widerruft keine globale Reader-Sitzung.

## Konsistenter globaler Widerruf

Wer einmal Reader ist, kann die Tokens sämtlicher aktiver Räume kennen. Nur einen
Raumcode zu ändern und dessen ursprüngliche Leser sperren zu wollen wäre wirkungslos:
Sie könnten sich mit einem anderen bekannten Raumcode wieder freischalten.

Deshalb gibt es ausschließlich die bewusste Admin-Aktion **„Alle QR-Zugänge erneuern“**
unter `/admin/raumzugaenge`. Der bestätigte POST an `/admin/reader-access/rotate`
verlangt Admin-Authentifizierung und das signierte CSRF-Token. Eine Transaktion:

1. erhöht die persistente globale `reader_access_version`,
2. erhöht die `qr_key_version` aller vorhandenen Räume, auch deaktivierter Räume.

Danach sind alle bisherigen Reader-Sitzungen und **alle bisherigen Raumtokens**
ungültig. Der Besitz eines alten Codes eines anderen Raums hilft nicht mehr. Auch
lange Cookies können keine widerrufene Version verlängern. Die Administration kann
über ihre bestehenden Rechte neue Codes ausgeben; alle Aushänge müssen ersetzt werden.
Ein Fehler bei einer der Änderungen rollt die komplette Rotation zurück.

Eine getrennte, vermeintlich unabhängige Raumrotation wird nicht mehr angeboten.
Der frühere Endpunkt `/admin/rooms/{id}/rotate-key` wurde entfernt; alte Clients
müssen auf die ausdrücklich globale Aktion wechseln. Der Master bleibt dabei erhalten.
Ein bewusster Master-Wechsel widerruft ebenfalls alle Codes und Sitzungen und erfordert
neue Ausdrucke.

## Datenbank und Umstieg

Migration 4 ergänzt `reader_sessions.access_version` und die persistente globale
Version in `app_state`. Es werden keine Nutzungsdaten oder Uploaddateien gelöscht.
Die Raumdaten und bestehenden Raumtoken-Versionen bleiben beim Upgrade erhalten.
Ohne ausdrücklich ausgelöste globale Rotation bleiben bestehende QR-Ausdrucke gültig.

Alte 7-Tage-Sitzungen werden in der Entwicklungsphase nicht automatisch zu globalen
365-Tage-Sitzungen hochgestuft. Ihr alter Cookie-Name wird nicht als Berechtigung
akzeptiert; neue globale Sessions haben die aktuelle Version. Einmal erneut scannen.
Eine vorhandene Legacy-Tabelle `reader_room_grants` bleibt ungenutzt erhalten, neue
Datenbanken legen sie nicht mehr an. Reader-Abfragen setzen keinerlei Raumfreigaben voraus.

Ein Restore kann alte Versionsstände und Sitzungen wiederherstellen. Nach einem
Restore verlorene Widerrufe berücksichtigen und gegebenenfalls global rotieren oder
einen neuen Master konfigurieren. Reader sind nicht personengebunden; ein einzelner
Nutzer lässt sich ohne Konten nicht unabhängig sperren. Bei weitergegebenen/gestohlenen
Codes oder Sitzungen ist ein globaler Widerruf erforderlich.

## Grenzen

- Ein geteilter Zugangslink oder QR-Code erlaubt das Lesen **aller** Raumlogbücher und Bilder. Nur an berechtigte Personen weitergeben.
- Nach 365 Tagen ohne erfolgreichen geschützten Zugriff ist ein neuer Scan erforderlich; bei regelmäßiger Nutzung bleibt die Sitzung durch Sliding Expiration bestehen.
- Wer Cookies löscht oder einen anderen Browser benutzt, muss neu scannen. Reader-Kennungen werden ausschließlich im Cookie gehalten.
- Alle geschützten HTML-, Bild-, JSON- und PDF-Antworten haben `Cache-Control: private, no-store`. Bewusst heruntergeladene oder ausgedruckte Codes bleiben im Besitz des Empfängers.
- Soft-Delete und der Schutz gelöschter Bilder bleiben erhalten. Allgemeine Anmerkungen, Löschen und administrative Funktionen bleiben Admins vorbehalten.
- Die globale SQLite-Version und derselbe Master müssen allen Workern zur Verfügung stehen. Regelmäßige Reader-Zugriffe schreiben die Ablaufzeit bewusst jedes Mal; es wird keine Verlängerungsschwelle eingeführt.

## Ausgeführte Verifikation

Stand: 01.11.2026. Der vollständige lokale Lauf mit
`RUN_DOCKER_TESTS=1 python -m pytest -q -W error` bestand mit **164 Tests in
50,68 Sekunden**, einschließlich **14 Chromium- und vier Docker-Tests**. Es gab
keine übersprungenen Tests oder Warnungen. Die Tests verwenden temporäre Datenbanken
und Uploads sowie eine kontrollierbare Uhr für Ablauf und Verlängerung.

Geprüft wurden insbesondere:

- Ein Werkstatt-Scan erlaubt mit derselben Sitzung andere Raumlogbücher, Bilder, PDFs und Zugangslinks sowie später angelegte Räume. Reader erhalten keine Admin-Rechte.
- Standardlaufzeit von 365 Tagen, konfigurierbare Laufzeit, Verlängerung bei jedem erfolgreichen geschützten Zugriff und konsistente SQLite-/Cookie-Zeitstempel. Öffentliche und fehlgeschlagene Anfragen verlängern nicht.
- Persistente Cookies nach Browser-/Serverneustart, Wiederverwendung einer gültigen Sitzung beim erneuten Scan, abgelaufene/alte Sitzungen, fehlende Basic-Challenge sowie HTTPS- und lokale HTTP-Cookieattribute.
- Globaler Widerruf aller bekannten Raumtokens und Sitzungen, Transaktions-Rollback sowie Widerruf zwischen Berechtigungsprüfung und Antwortbeginn. Bei Widerruf oder DB-Fehler werden keine privaten Antwortdaten ausgeliefert.
- Bewusstes Link-Kopieren, vollständiger Admin-Zugriff ohne zusätzliche Reader-Sitzung, unveränderte öffentliche Übermittlung, CSRF-Schutz und das Fehlen von Sitzungstokens im Browser-Speicher.

Ruff, Formatprüfung, JavaScript-Syntaxprüfung, Python-Kompilierung,
Compose-Konfiguration und `git diff --check` waren erfolgreich. Das PDF-Zeichenlayout
wurde nicht verändert; PDF-Downloads wurden automatisiert geprüft. Eine erneute
visuelle PDF-Prüfung und ein Scan gedruckter Codes mit einem externen Gerät waren
nicht Teil dieses lokalen Laufs.

Das Image wurde neu gebaut und der lokale Dienst unter `http://localhost:9000`
gestartet. Der Container läuft als `1000:1000` ohne Neustartschleife. Öffentliche
Formulare lieferten 200, geschützte Reader-Adressen ohne Zugang 403 ohne
`WWW-Authenticate`, Admin-Logbuch und Admin-PDF mit Anmeldung 200.

Vor Migration 4 wurde ein konsistentes SQLite-Backup unter
`data/backups/before-global-readers-20261101T123958Z.db` angelegt. Nach dem Start
stimmten alle ursprünglichen Spalten/Werte in **5 Räumen, 23 Nutzungen,
18 Bildreferenzen und 6 Anmerkungen** sowie die SHA-256-Hashes aller **18 Uploaddateien**
überein. Master-Schlüssel und Raumtoken-Versionen blieben erhalten; eine globale
Rotation wurde im Betriebsbestand nicht ausgelöst. Bestehende Ausdrucke bleiben
gültig, alte Reader-Sitzungen benötigen einmalig einen erneuten Scan.

Die anschließende UI-Anpassung ersetzt die beiden breiten Aktionen im Raumformular
durch Icons neben der Überschrift. Danach bestanden die 59 zugehörigen Tests aus
`tests/test_capabilities.py` und `tests/test_capability_browser.py` in 14,73 Sekunden.
Die Darstellung wurde zusätzlich im Browser bei 1280, 390 und 320 Pixeln Breite
geprüft, einschließlich des manuellen Kopierfelds bei nicht verfügbarer Zwischenablage.

Nach der anschließenden mobilen Navigation mit `/logbuch`, `/hilfe` und
`/admin/nachrichten` sowie der geschützten Dreier-Vorschau bestand der vollständige
Lauf mit **191 Tests in 47,57 Sekunden**, einschließlich 25 Chromium- und vier
Docker-Tests, ohne Warnungen oder übersprungene Tests. Die UI wurde in beiden
Farbschemata bei 320, 390, 430 und 1280 Pixeln geprüft. Der lokale Container wurde
aktualisiert; Daten, Bilder, `.env` und Widerrufsversion blieben unverändert.
Der aktuelle Abschluss steht in [SECURITY_REVIEW.md](SECURITY_REVIEW.md).
