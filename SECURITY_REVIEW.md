# Abschlussbericht: Sicherheitsfixes und Refactoring

Stand: 01.11.2026. Die Nachträge dokumentieren die anschließenden Änderungen am
ursprünglichen Review sowie die tatsächlich ausgeführten Prüfungen und Containerstarts.
Die vorhandenen Archivdateien bleiben unverändert.

## Aktueller Nachtrag: Google Sans Flex

Die zentrale Webschrift ist jetzt Google Sans Flex, einschließlich Formularfeldern
und Schaltflächen. Variable WOFF2-Dateien für Latin und Latin Extended werden lokal
ausgeliefert; die Hauptschrift wird vorgeladen. Es gibt keine Font-Anfragen an Google
im Browser und keine Lockerung der bestehenden CSP. MIME-Typen für WOFF2 und TTF
werden ausdrücklich registriert, damit auch das schlanke Docker-Image die Dateien
korrekt ausliefert. Quellen, Prüfsummen und Lizenz stehen unter `app/static/fonts`.

Auch QR-PDFs betten Google Sans Flex ein. Die bisherigen Inter-Dateien sowie die
Inter-/Helvetica-Auswahl wurden entfernt. Seitengröße, QR-Position und Textgrößen
bleiben erhalten. Das A4-Beispiel mit „Sommerküche“ wurde gerendert und visuell geprüft;
`pdffonts` bestätigt eingebettetes Google Sans Flex Regular und Bold.

Prüfung am 01.11.2026: **34 Tests bestanden in 26,16 Sekunden**, darunter alle
25 Chromium-Tests und die PDF-Tests. Die Handyansichten wurden in beiden Farbschemata
geprüft. Eine zusätzliche Browserprüfung bestätigt tatsächlich gerendertes Google
Sans Flex, vererbte Schrift in Bedienelementen und ausschließlich lokale Font-Anfragen.
Ruff, Formatierung, Python-Kompilierung und Diff-Prüfung waren erfolgreich.
Der Container wurde neu gebaut und lokal aktualisiert; beide Webfonts liefern 200
mit `font/woff2`. Auch am laufenden Dienst wurde die tatsächlich verwendete Schrift
in der 390-Pixel-Ansicht geprüft. Der Container läuft ohne Neustartschleife.

## Nachtrag: Mobile Navigation und Raumvorschau

Die bisher vermischten öffentlichen und administrativen Header-Links sind durch
die drei gleich breiten Haupttabs **Räume**, **Logbuch** und **Hilfe & Infos** ersetzt.
Im Raum heißt der erste Tab „Alle Räume“. Der Header ist auch beim QR-Einstieg
vollständig; das Verwaltungsmenü liegt separat rechts neben der Darstellungsauswahl.
Die aktuellen URLs sind `/logbuch`, `/hilfe` und `/admin/nachrichten`. Die alten
Adressen wurden ohne Redirects oder Alias-Routen entfernt. Formularaktionen,
Erfolgsweiterleitung, Origin-Prüfung, Ratenbegrenzung und Links verwenden die neuen URLs.

Unter dem Nutzungsformular steht eine eigene Gruppe mit den drei letzten aktiven
Buchungen des Raums und „Alle Buchungen anzeigen“. Die geschützte HTML-Vorschau
verwendet die zentrale Reader-Dependency und wird separat nachgeladen. Öffentliche
Formularantworten enthalten keine Buchungsdaten und verlängern keine Reader-Sitzung;
ein erfolgreicher privater Vorschauabruf verlängert sie regulär. Admin-Vorschau und
Bilder verwenden weiterhin den Admin-Schutzbereich. Karten und Bildbetrachter werden
zwischen Vorschau und Logbuch wiederverwendet. Ein Zugangsfragment wird jetzt auch
beim Aufrufen auf dem bereits geöffneten Raum sofort entfernt und verarbeitet.

Name, Haus und Nummer werden auf ausdrücklichen Änderungswunsch standardmäßig schon
beim Ausfüllen auf dem Gerät gemerkt. Ausschalten und Löschen bleiben über Neustarts
erhalten. Hilfe & Infos übernimmt nur den optionalen gespeicherten Namen; eine
anonyme Nachricht verändert das Raumprofil nicht. Texte und Bilder werden nicht im
Browser-Speicher gehalten. Validierungsfehler behalten übermittelte Werte bei;
blockierter Speicher verhindert keine Formularnutzung. Datenschutzhinweise und README
beschreiben das geänderte Verhalten.

Tatsächlich ausgeführte Prüfung am 01.11.2026:

- `RUN_DOCKER_TESTS=1 python -m pytest -q -W error`: **191 Tests bestanden in 47,57 Sekunden**, einschließlich **25 Chromium- und vier Docker-Tests**, ohne übersprungene Tests oder Warnungen.
- Die Browserprüfung deckt beide Farbschemata bei **320, 390, 430 und 1280 Pixeln** ab: gleiche Tabbreiten, mindestens 44 Pixel hohe Haupttabs, Verwaltungsmenü mit Escape/Außenklick, Vorschau, Logbuch-Navigation und Bilder. Die Screenshots wurden zusätzlich visuell geprüft.
- Speicherung beim Tippen, Raumwechsel und wiederhergestelltem Browser, dauerhaftes Ausschalten/Löschen, anonyme Nachrichten, Validierungsfehler und gesperrter Speicher wurden geprüft. Die bestehende strikte CSP bleibt aktiv; Browser-Warteprädikate verwenden Funktionen statt wiederholter String-Auswertung.
- Ruff, Formatprüfung, JavaScript-Syntax, Python-Kompilierung, Compose-Konfiguration und `git diff --check` waren erfolgreich. Es kamen keine Abhängigkeiten oder Datenbankmigrationen hinzu.
- Image neu gebaut und lokalen Container aktualisiert: `http://localhost:9000`, Nutzer `1000:1000`, laufend ohne Neustartschleife. Neue öffentliche Seiten lieferten 200, Reader-Adressen anonym 403 ohne Basic-Challenge, Admin-Nachrichten/Logbuch/Vorschau mit Anmeldung 200 und entfernte URLs 404.
- Vor dem Update konsistentes Backup unter `data/backups/before-mobile-navigation-20261101T160427Z.db`. Danach alle Werte in **5 Räumen, 23 Nutzungen, 18 Bildreferenzen und 6 Nachrichten** sowie alle **18 Uploaddateien** per Hash unverändert nachgewiesen. `.env`, Schema und globale Widerrufsversion blieben ebenfalls unverändert; SQLite-Integrität und Fremdschlüssel sind korrekt.

Die Bildschirmgrößen wurden in Chromium simuliert; ein Test auf einem physischen
Handy oder mit Safari war nicht Bestandteil dieses Laufs. Die folgenden Abschnitte
halten die früheren Änderungen und damaligen Ergebnisse fest.

## Nachtrag: Globale Reader und Sliding Expiration

Ein gültiger Raum-QR-Code erteilt jetzt globale Leserechte für alle Raumlogbücher,
zugehörigen Bilder und Raum-QR-PDFs sowie das bewusste Kopieren von Zugangslinks.
Der QR-Link öffnet weiterhin sein Raumformular. Eine zentrale Reader-Dependency
ersetzt die früheren Raumfreigaben; fehlender Zugang liefert 403 ohne Basic-Challenge.
Reader erhalten keine administrativen Rechte. Die vorhandene Admin-Authentifizierung
bleibt für Verwaltung, Bilder, PDFs und Kopieraktionen nutzbar.

Sitzungen laufen standardmäßig 365 Tage. Jeder erfolgreiche geschützte Reader-Zugriff
verlängert SQLite-Ablauf und persistentes HttpOnly-Cookie gemeinsam, ohne Schwelle.
Öffentliche/fehlgeschlagene Anfragen verlängern nicht; abgelaufene oder widerrufene
Sitzungen werden nicht reaktiviert. Der globale Widerruf erhöht alle Raumtoken-Versionen
und die globale Berechtigungsversion atomar, da jeder Reader sämtliche Raumcodes
kennen kann. Die frühere einzelne Raumrotation wurde entfernt.

Der vollständige Lauf mit `RUN_DOCKER_TESTS=1 python -m pytest -q -W error` bestand
mit **164 Tests in 50,68 Sekunden**, darunter **14 Chromium- und vier Docker-Tests**,
ohne übersprungene Tests oder Warnungen. Ruff, Formatprüfung, JavaScript-Syntax,
Python-Kompilierung, Compose-Konfiguration und Git-Diff-Prüfung waren erfolgreich.

Migration 4 ist lokal aktiviert. Der neu gebaute Container läuft unter
`http://localhost:9000` als `1000:1000` ohne Neustartschleife. Öffentliche Formulare,
Reader-Ablehnung ohne Basic-Challenge und angemeldete Admin-Logbuch-/PDF-Antworten
wurden zusätzlich am laufenden Dienst geprüft. Nach konsistentem Backup unter
`data/backups/before-global-readers-20261101T123958Z.db` wurden alle ursprünglichen
Werte in 5 Räumen, 23 Nutzungen, 18 Bildreferenzen und 6 Anmerkungen sowie alle
18 Uploaddateien unverändert nachgewiesen. Master und Raumtoken-Versionen bleiben
erhalten; keine globale Rotation wurde im Betriebsbestand ausgelöst. Alte Sitzungen
benötigen einmalig einen erneuten Scan; vorhandene Ausdrucke bleiben gültig.

Modell, Konfiguration, Widerrufsfolgen und Prüfgrenzen stehen in
[QR_ACCESS.md](QR_ACCESS.md). Die folgenden Abschnitte sind historische Berichte;
ihre früheren Raumfreigaben und ausschließlichen Admin-Lesezugriffe sind durch das
hier beschriebene globale Reader-Modell ersetzt.

## Historischer Nachtrag: Raumbezogener QR-Zugang

Der anschließende Änderungsauftrag ergänzt Leserechte über einen regulären Raum-QR-Code
und den selbstständigen PDF-Nachdruck ohne Bewohnerkonto. Die bisher öffentlich
abrufbaren QR-PDFs sind nun auf Raum-Lesesitzungen und Admins beschränkt. Logbuch und
Bilder verwenden dieselbe serverseitige Raumfreigabe. Die Admin-Verwaltung der
Schlüssel liegt unter `/admin/raumzugaenge`; öffentliche Meldeformulare bleiben erhalten.

Die vollständige Beschreibung, Einrichtung/Sicherung des Master-Schlüssels, Grenzen
und ausgeführten Prüfungen stehen in [QR_ACCESS.md](QR_ACCESS.md). Neu hinzugekommen
sind 33 Testfälle; der damalige vollständige Lauf mit Docker und Warnungen als Fehler
besteht mit **138 Tests**, darunter zehn echte Browser- und vier Docker-Tests.
Die Migration 3 ist lokal aktiviert; bestehende Nutzungsdaten und 18 Uploads wurden
unverändert nachgewiesen. Der einmalige Master-Schlüssel wird geschützt über die lokale
`.env` bereitgestellt. Auf ausdrücklichen Wunsch bleibt es vorerst beim lokalen Test
unter `http://localhost:9000`. Frühere Aussagen in den folgenden historischen
Review-Abschnitten zur ausschließlichen Admin-Leseberechtigung werden durch diesen
Nachtrag ersetzt.

## Nachtrag: Docker-Schreibrechte korrigiert

Die Kombination aus einem als Root gestarteten Container und `cap_drop: ALL` war
mit dem eingebundenen Datenverzeichnis inkompatibel: Verzeichnis und DB gehören
UID/GID `1000:1000` und erlauben nur diesem Eigentümer das Schreiben. Ohne
DAC-Override-Capability konnte auch Container-Root dort nicht schreiben.
Das wurde direkt am bestehenden Bind-Mount ohne Schreiboperation reproduziert:
UID 0 hatte keine Schreibrechte, UID 1000 dagegen schon.

Korrektur:

- `Dockerfile` setzt `USER 1000:1000` und bereitet `/data` im Image für diesen Nutzer vor.
- `docker-compose.yml` verwendet konfigurierbare `APP_UID`/`APP_GID`, standardmäßig `1000:1000`. `cap_drop: ALL` und `no-new-privileges` bleiben aktiv.
- Bestehende Dateirechte und Eigentümer wurden nicht pauschal geändert. Die README beschreibt das vorherige Anlegen des Bind-Verzeichnisses und abweichende Host-IDs.
- Vier neue echte Docker-Tests in `tests/test_docker.py` prüfen UID-Konfiguration, das leere Image-Datenverzeichnis sowie Speichern, Bild-Upload, Zugriffsschutz und Neustart mit neuen und bestehenden Host-Daten. Sie arbeiten ausschließlich mit temporären Verzeichnissen. Ein eigener CI-Job baut und prüft das Image.

Tatsächlich verifiziert:

- Image erfolgreich gebaut, Betriebscontainer neu erstellt und gestartet, `Application startup complete` bestätigt.
- Prozess läuft als `1000:1000`, Container läuft ohne Neustartschleife (`RestartCount=0`).
- HTTP 200 für Startseite, Raumformular und Anmerkungsformular; HTTP 401 für anonyme geschützte Seiten; angemeldete Admin-Ansicht HTTP 200 mit `no-store`.
- Vor Start konsistentes SQLite-Backup unter `data/backups/before-container-user-20261031T154036Z.db` angelegt. Alle ursprünglichen Spalten/Werte in 5 Räumen, 23 Nutzungen, 18 Bildreferenzen und 6 Anmerkungen danach per Hash verglichen: unverändert. Alle 18 vorhandenen Uploaddateien ebenfalls per SHA-256 unverändert; DB-Integrität und Fremdschlüssel korrekt.
- Vollständiger Lauf mit `RUN_DOCKER_TESTS=1 python -m pytest -q -W error`: **105 Tests bestanden in 22,62 Sekunden**, einschließlich der vier Docker- und sechs Chromium-Tests; keine übersprungenen Tests oder Warnungen.
- Ruff, Formatierung, Compose-Konfiguration und `git diff --check` erfolgreich.

Die folgenden Abschnitte halten den Umfang und die ursprünglichen Prüfergebnisse
des Sicherheitsreviews fest.

## Vorher und nachher

| Auftrag | Vorher | Jetzt |
| --- | --- | --- |
| 1: Personenbezogene Ansichten | Nutzungen, Nachrichten und Bildreferenzen waren öffentlich. | Zentrale Admin-Dependency für Buchungen, Verwaltung und Bilder. Öffentliches Anmerkungsformular getrennt von `/admin/anmerkungen`. Dynamische Antworten mit `private, no-store`; Datenschutzhinweise angepasst. |
| 2: Soft-Delete | Bilder gelöschter Einträge blieben über bekannte URLs erreichbar. | Bildabfrage verknüpft Nutzung und Bild und schließt gelöschte Einträge aus. Auch Details liefern nach Löschung 404. Dateien bleiben physisch bestehen. Gleichzeitige Löschversuche verändern den Löschzeitpunkt nicht wiederholt. |
| 3: CSRF | Browser konnten Basic-Auth-Zugangsdaten für fremd ausgelöste POSTs mitsenden. | Routerweite Prüfung signierter Double-Submit-Tokens mit Host-only-Cookie, Ablaufzeit und Passwortwechsel-Widerruf. Fehlende, manipulierte und abgelaufene Tokens scheitern geschlossen. |
| 4: Bilder | Nur `verify()`, Originalbytes mit Metadaten, uneinheitliche Decoderfehler. | Strukturprüfung und vollständiges `load()`, Format-/Datei-/Dimensions-/Pixelgrenzen, Bomb-Schutz, Neucodierung ohne Metadaten und mit EXIF-Orientierung. Animationen werden konservativ abgelehnt. Kontrollierte 400-Formularfehler. |
| 5: Missbrauch und Ressourcen | Keine dauerhaften Raten-, Request- oder Speichergrenzen. | Byte-/Zeitlimit vor Multipart, persistente atomare Client- und globale Ratenlimits mit 429/Retry-After, gemeinsame Speicherquote. Proxy-Header nur von expliziten Gegenstellen. |
| 6: SQLite-Verbindungen | `with sqlite3.connect()` schloss Verbindungen nicht explizit. | Contextmanager garantiert Close und Commit/Rollback; Busy-Timeout pro Verbindung, WAL zentral beim Start. Fehlerantworten ohne SQL-Inhalte. |
| 7: Initialisierung | Neustarts überschrieben Raumkonfigurationen. | Additive idempotente Migration mit Versionsmarkern; Standardräume nur bei erstmalig leerer Konfiguration. Keine nachträgliche Wiederherstellung gelöschter Räume. |
| 8: Event-Loop und SMTP | SQLite, Dateisystem, Pillow und SMTP blockierten den Async-Handler. | Synchroner Verarbeitungsschritt im Threadpool; SMTP erst nach der Antwort als BackgroundTask. Fehler ändern den erfolgreich gespeicherten Datensatz nicht. TLS-Zertifikatsprüfung explizit. |
| 9: Lifecycle | Veralteter Startup-Decorator. | Lifespan initialisiert Verzeichnisse und Datenbank im Threadpool. Es bleiben keine dauerhaften DB-Verbindungen für den Shutdown offen. |
| 10: Hausnummern | Unicode-Ziffern wurden akzeptiert; HTML-Limit passte nicht zur kombinierten Hausangabe. | ASCII-RegEx und abgestimmtes Längenlimit, standardmäßig acht Nummernziffern plus Hausgruppe. |
| 11: Browser-Datenschutz | Persönliche Angaben wurden ungefragt dauerhaft gespeichert. | Ausdrückliches Opt-in, Widerruf und Entfernen; alte Angaben ohne Opt-in werden beim nächsten Seitenaufruf entfernt. Gesperrter Browser-Speicher unterbricht die UI nicht. |
| 12: Raumtexte | PDF und E-Mail sprachen immer von der Werkstatt. | Tatsächlicher Raumname in PDF und E-Mail; QR-Link und A4-Layout erhalten. |
| 13: Bedienbarkeit | Unvollständige Fokusführung und Object-URL-Freigabe. | Dialog mit Tastatursteuerung, Fokusbegrenzung und -rückgabe, inertem Hintergrund, Live-Status; Freigabe von Vorschau-URLs auch bei Fehlern. Radio-Inputs verursachen keinen mobilen Überlauf mehr. |
| 14: Testinfrastruktur | Keine Tests vorhanden. | Pytest/TestClient mit temporären Daten; zusätzliche echte Chromium-Tests. Sämtliche SMTP-Tests verwenden lokale Mocks. |
| 15: Qualität | Ungeschützte Host-/QR-Basis, veraltete/floating Abhängigkeiten, Build-Kontext mit unnötigen Dateien. | Host-Allowlist, geprüfte QR-Basis, Sicherheitsheader, Nonce-CSP für App-Seiten, Inhalts-Hashes für Assets, sinnvolle DB-Indizes, festgelegte direkte Abhängigkeiten, isolierte Entwicklungsabhängigkeiten, Dockerignore und CI. |
| 16: Verifikation | Keine reproduzierbaren Regressionsergebnisse. | Vollständige Tests, Lint/Format/Syntax, Compose-Validierung, Schwachstellenabgleich, Datenbankkopie und visuelle PDF-/Browserkontrolle. Details unten. |

Dateipublikation verwendet exklusiv angelegte temporäre Dateien und einen atomaren
Hardlink im selben Upload-Verzeichnis. Vorhandene zufällige Dateinamen werden nicht
überschrieben. Nach fehlgeschlagenem DB-Commit oder Dateischreiben werden neue Dateien
entfernt und die Transaktion zurückgerollt; das Aufräumen läuft auch bei unerwarteten
Exceptions. Ein Datei-/Lesefehler ergibt eine generische 503-Antwort.

## Geänderte Dateien

| Bereich | Dateien und wichtigste Änderung |
| --- | --- |
| Berechtigungen/Requests | `app/auth.py`, neues `app/middleware.py`, `app/routes/public.py`, `app/routes/admin.py`: gemeinsame Authentifizierung, CSRF, Request-/Ratenlimits und Bildberechtigungen. |
| Datenbank/Start | `app/db.py`, `app/main.py`, `app/config.py`, `app/constants.py`: Transaktionen und Close, Migration/Seed, Lifespan, Limits und Navigation. |
| Services | `app/services/uploads.py`, `notifications.py`, `pdf.py`: Decodierung, sichere Speicherung, entkoppelter SMTP-Versand, dynamische Raumtexte und geschlossene Font-Ressourcen. |
| Darstellung | `app/static/theme.js`, `app/static/styles/forms.css`, `app/templating.py`, `app/utils.py`: Opt-in, Fokus/Viewer, Vorschau-Cleanup, Cache-Versionierung, validierte Basis-URL und korrekte Weiterleitung bei eigenen Raum-Slugs. |
| Templates | `base.html`, `notes.html`, neues `admin_notes.html`, `privacy.html`, `recent_bookings.html`, `room_form.html`, `session_detail.html`, `admin.html`: geschützte Daten, CSRF-Feld, Einwilligung und Live-Status. |
| Betrieb | `requirements.txt`, neue `requirements-dev.txt` und `requirements-browser.txt`, `Dockerfile`, `docker-compose.yml`, neue `.dockerignore`, `.gitignore`: Versionen, Proxy-Trust, sichere Defaults, kein Reload/Source-Mount im Betriebscontainer und keine Daten/Secrets im Build-Kontext. |
| Qualität/Dokumentation | Neue `tests/`, `pyproject.toml`, `.github/workflows/tests.yml`, aktualisierte `README.md` und dieser Bericht. |

## Neue Regressionstests

| Datei | Abdeckung |
| --- | --- |
| `tests/conftest.py` | Isoliertes Importverzeichnis, separate temporäre SQLite-Datei und Uploads je Test, lokale Test-Zugangsdaten; SMTP-Umgebung entfernt. |
| `tests/test_security.py` | Öffentliche Formulare; Auth/Autorisierung; keine öffentlichen Nutzungs-/Nachrichtenlecks; HTML-Escaping; erfolgreiche und abgelehnte CSRF-Aktionen; Passwortrotation; Soft-Delete; Cookies/CSP/Host-/Cache-Header; Erhalt der automatisch erzeugten API-Dokumentation. |
| `tests/test_uploads.py` | JPEG/PNG/WebP; Struktur- und Decoderfehler; beschädigtes PNG mit gültiger CRC; abgeschnittene Dateien; unerlaubte Formate; Metadaten und Orientierung; Größen-/Anzahl-/Pixel-/Bomb-/Speicherlimits; Animationen; Bildrechte; verwaiste/fehlende Dateien und Symlinks; Rollback nach Schreib-/DB-/Commitfehler; Cleanup bei unerwarteten Exceptions; Kollisionsschutz; parallele Speicherquote. |
| `tests/test_backend.py` | Formulargrenzen und ASCII-Hausnummern; Zusatzfelder; Raum-Modus; eigene Slugs; DB-Commit/Rollback/Close/WAL; bestehende und historische Schemata; paralleler Start und Soft-Delete; Thread-Auslagerung; SMTP-Fehler nach Commit und dynamischer E-Mail-Text. |
| `tests/test_limits.py` | Größenprüfung vor Parser; Requests ohne Content-Length; Timeout und falsche Längen; persistente gemeinsame Limits; konkurrierende Zähler; globales Limit/Ablauf; Proxy-Vertrauenskette; geschlossene Fehlerbehandlung bei ausgefallener DB. |
| `tests/test_pdf.py` | PDF-Endpunkte, tatsächlicher Raumtext, erlaubte Basis-URLs und URL-Encoding. |
| `tests/test_browser.py` | Fünf echte Chromium-Prüfungen: freiwilliges Merken/Entfernen, blockierter Browser-Speicher, Vorschaufehler/Cleanup, Viewer-Tastatur/Fokus/Status und mobiles Layout sowie Admin-Löschformular mit Bestätigungsdialog und echtem CSRF-Ablauf. |

## Tatsächlich ausgeführte Prüfungen

Die Testumgebung liegt isoliert unter `/tmp/raumlog-review-venv`; die vorhandene
Projekt-`.venv` wurde nicht verändert. Lokale Python-Version: **3.14.8**.

Der finale Lauf wird mit Warnungen als Fehler durchgeführt:

```text
python -m pytest -q -W error
```

**Ergebnis: 100 Tests bestanden in 12,04 Sekunden; keine Warnungen, Fehler oder übersprungenen Tests.**
Davon sind fünf Tests echte Chromium-Browserprüfungen.

Weitere erfolgreich ausgeführte Prüfungen:

- `ruff check app tests`: bestanden.
- `ruff format --check app tests`: alle 25 Python-Dateien formatiert.
- `python -m compileall -q app tests`: bestanden.
- `node --check app/static/theme.js`: bestanden.
- `git diff --check`: bestanden; vollständiger Diff einschließlich neuer Dateien geprüft.
- `docker compose config --quiet`: bestanden, ohne Ausgabe vertraulicher Umgebungswerte.
- `pip check`: keine inkompatiblen installierten Anforderungen.
- `pip-audit -r requirements.txt`: **28 Laufzeitabhängigkeiten, keine bekannten Schwachstellen** im zum Prüfzeitpunkt verwendeten Datenbestand. Das ersetzt keine zukünftigen Updates.
- Fünf raumspezifische QR-PDFs erzeugt; Sauna-PDF als PNG gerendert und visuell geprüft: einseitiges A4, vollständiger QR-Code, korrekter Raumtext, keine Überlappungen.
- Desktop- und Mobilansicht aus den Chromium-Tests visuell geprüft; auf 390 px kein horizontaler Überlauf.

Die ursprünglichen Sandbox-Testläufe wurden wegen blockierter interner Event-Loop-
Kommunikation beendet. Die erfolgreichen TestClient-/Browserläufe erfolgten mit
freigegebener Ausführung außerhalb dieser Sandbox. Es wurden keine Tests ausgelassen
oder Warnungen unterdrückt. Ein zunächst verwendeter veralteter HTTP-Testtreiber wurde
durch den von der aktuellen Starlette-Version unterstützten `httpx2` ersetzt.

## Kompatibilität vorhandener Daten

Die vorhandene `data/app.db` wurde ausschließlich lesend über die SQLite-Backup-API
in eine temporäre Kopie übernommen. Nur diese Kopie wurde zweimal initialisiert.
Alle ursprünglichen Spalten und Zeilen wurden anschließend vollständig verglichen:

| Tabelle | Unverändert erhaltene Zeilen |
| --- | ---: |
| Räume | 5 |
| Nutzungen | 23 |
| Bildreferenzen | 18 |
| Anmerkungen | 6 |

`PRAGMA integrity_check` ergibt `ok`; `PRAGMA foreign_key_check` ist leer.
Ein separater automatisierter Test migriert zusätzlich ein älteres Minimalschema
mit fehlenden Spalten. Bestehende Uploaddateien werden weder bei Migration noch bei
Soft-Delete umgeschrieben oder entfernt. Die Originaldatenbank wurde nicht migriert.

## Konfiguration und Umstieg

Die vollständige Variablentabelle und ein Proxy-Beispiel stehen in `README.md`.
Vor dem nächsten produktiven Start besonders beachten:

1. `ADMIN_USERNAME` und ein langes, geheimes `ADMIN_PASSWORD` setzen.
2. `ALLOWED_HOSTS` um die tatsächlich verwendete LAN-IP oder Domain ergänzen; der Standard erlaubt nur localhost/Loopback. `PUBLIC_BASE_URL` auf die erreichbare Adresse setzen.
3. Uvicorn mit `--no-proxy-headers` betreiben und ausschließlich echte Proxy-Gegenstellen in `TRUSTED_PROXIES` aufnehmen. In den bereitgestellten Docker-Kommandos ist das bereits umgesetzt.
4. Datei-, Request-, Pixel- und Gesamtquoten gemeinsam prüfen. Neue Compose-Defaults sind fünf Bilder à 5 MiB und 26 MiB pro Request. Eine vorhandene `.env` kann diese Werte weiterhin überschreiben.
5. Daten und konsistente SQLite-Backups sichern; beim laufenden WAL-Betrieb nicht nur die Hauptdatei kopieren.
6. Abhängigkeiten aktualisieren bzw. Container neu bauen; alte Proxy-Caches leeren. Es gibt keinen automatischen Neustart durch diesen Auftrag.

Bewusste Verhaltensänderungen: Datenansichten und Bilder benötigen jetzt Admin-Auth;
`/anmerkungen` zeigt keine Nachrichten; gelöschte Detailseiten liefern 404; Admin-POSTs
brauchen Tokens; Bildbytes werden neu codiert, Metadaten entfernt und Animationen
abgelehnt. Raumdefinitionen im Code wirken nur als anfängliche Startwerte. Der
Betriebscontainer hat keinen automatischen Reload und keinen Source-Bind-Mount mehr.

## Strategie für spätere physische Bereinigung

Es wurde bewusst **kein automatischer Löschlauf aktiviert**, weil keine verbindlichen
Aufbewahrungsfristen oder Freigaberegeln vorgegeben wurden. Eine spätere Umsetzung
sollte diesen Vertrag einhalten:

1. Betreiber legt getrennte Fristen für aktive Daten, Soft-Deletes, Anmerkungen, E-Mails und Backups fest. Bis dahin keine vermuteten Fristen anwenden.
2. Einen separaten Wartungsbefehl standardmäßig als **Dry-Run** ausführen. Kandidaten sind ausschließlich bekannte Bildreferenzen soft-gelöschter/abgelaufener Nutzungen sowie nicht referenzierte Dateien, deren Alter eine explizite Schonfrist überschreitet. Referenzen aller Einträge einschließlich Soft-Deletes berücksichtigen. Temporäre Dateien benötigen ebenfalls eine Schonfrist.
3. Nur Dateien unmittelbar im festgelegten Upload-Verzeichnis berücksichtigen. Pfadgrenzen, Dateinamen, Symlinks und doppelt referenzierte Dateien prüfen; keine rekursiven oder frei zusammengesetzten Löschpfade.
4. Für einen tatsächlichen Lauf expliziten Ausführungsmodus, frisches konsistentes Backup und einen exklusiven Wartungszeitraum verlangen. Schreibzugriffe pausieren bzw. DB-Sperre nutzen und Referenzen unmittelbar vor der Verarbeitung erneut prüfen. So wird kein gerade publizierter, noch nicht committeter Upload als verwaist entfernt.
5. Kandidaten zunächst in ein gesperrtes Quarantäneverzeichnis auf demselben Dateisystem verschieben. Ein Laufjournal muss nach Unterbrechungen Wiederaufnahme und Wiederherstellung ermöglichen. Quarantäne, Datenbank und Dateisystem sind keine gemeinsame Transaktion.
6. Erst nach erfolgreichem, überprüftem Wartungslauf und definierter Quarantänefrist physisch löschen. Fehler dürfen weder aktive Referenzen beschädigen noch stillschweigend einen erfolgreichen Lauf melden.
7. DB-Zeilen, Anmerkungen und gegebenenfalls Nachrichten beim SMTP-Empfänger getrennt nach dem festgelegten Löschkonzept behandeln. Backups durch ihre eigenen Fristen auslaufen lassen; Wiederherstellungen müssen bereits vollzogene Löschungen beachten. Protokolle nur mit Lauf-ID, Zählern und nötigen technischen Referenzen führen.

## Verbleibende Einschränkungen

- Alle Berechtigten teilen derzeit denselben Admin-Zugang. Es gibt keine individuellen Rollen, Anmeldehistorie oder eigene Basic-Auth-Abmeldung.
- BackgroundTasks sind Best-effort: keine persistente Zustellgarantie, automatische Wiederholung oder Wiederherstellung nach Neustarts. E-Mail-Kopien und Backups werden nicht durch Soft-Delete entfernt.
- Bei hartem Prozess-/Systemabbruch zwischen Dateioperation und DB-Commit können verwaiste Dateien entstehen. Bei normalen behandelten Fehlern wird aufgeräumt; endgültige Bereinigung braucht das oben beschriebene Verfahren.
- Vorhandene Bilder können weiterhin alte Metadaten enthalten. Frühere Downloads oder fremde Cache-Kopien lassen sich nicht rückwirkend zurückrufen.
- Die Speicherquote umfasst den Upload-Ordner, nicht die gesamte Festplatte. DB-Größe, Backups, SMTP und temporäre Parser-Dateien benötigen eigenes Monitoring und gegebenenfalls Dateisystemquoten.
- Feste Rate-Fenster erlauben Spitzen am Fensterwechsel; Personen hinter derselben NAT-Adresse teilen das Kontingent. Netzwerk-, Header- und Verbindungsangriffe müssen zusätzlich am Proxy begrenzt werden. Die gemeinsame SQLite-Datei muss auf lokalem, WAL-tauglichem Speicher liegen.
- Die strenge Nonce-CSP gilt für die App-Seiten. FastAPIs automatisch generierte Entwickler-UIs haben eine gesonderte, auf ihre Bibliotheks-CDNs begrenzte Richtlinie, um ihre bestehende Funktion zu erhalten.
- Die GitHub-Actions-Matrix für Python 3.11/3.13/3.14 ist eingerichtet, wurde hier aber nicht auf GitHub ausgeführt. Lokal geprüft wurde Python 3.14.8 mit System-Chromium. Docker-Image-Build und Containerbetrieb wurden im Nachtrag oben zusätzlich geprüft; produktiver HTTPS-Proxy und echter SMTP-Versand bleiben ungeprüft.
- Betreiberangaben, Kontakt, Rechtsgrundlage und verbindliche Aufbewahrungsfristen fehlen weiterhin als fachliche Vorgaben. Die Datenschutzseite benennt diese Ergänzungen und beschreibt die tatsächliche technische Umsetzung.
