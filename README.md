# Werkstatt Log MVP

Minimaler Test für Raum-Nutzung per QR-Code.

## Lokal starten

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Dann öffnen:

```text
http://localhost:8000/r/werkstatt
http://localhost:8000/admin
```

## E-Mail-Benachrichtigung

Wenn bei einem neuen Eintrag eine Mail verschickt werden soll, setze diese Umgebungsvariablen:

```bash
export SMTP_HOST=smtp.example.com
export SMTP_PORT=587
export SMTP_FROM=werkstatt@example.com
export SMTP_TO=deine-adresse@example.com
export SMTP_USER=werkstatt@example.com
export SMTP_PASSWORD=dein-passwort
export SMTP_STARTTLS=true
export SMTP_SSL=false
```

Hinweise:

- Die Benachrichtigung ist nur aktiv, wenn `SMTP_HOST`, `SMTP_FROM` und `SMTP_TO` gesetzt sind.
- Für die meisten Provider ist `SMTP_PORT=587` mit `SMTP_STARTTLS=true` richtig.
- Wenn dein Provider direkt SSL verlangt, nutze meist `SMTP_PORT=465`, `SMTP_SSL=true` und `SMTP_STARTTLS=false`.
- Falls der Mailversand fehlschlägt, wird der Eintrag trotzdem gespeichert.

## Mit Docker starten

```bash
docker compose up --build
```

Im Docker-Setup werden Änderungen in `./app` jetzt direkt in den Container gespiegelt. `uvicorn` läuft dabei mit `--reload`, sodass Python-, Template- und CSS-Änderungen automatisch übernommen werden.

Dann öffnen:

```text
http://localhost:8080/r/werkstatt
http://localhost:8080/admin
```

## QR-Code

Der QR-Code zeigt später einfach auf:

```text
https://deine-domain.de/r/werkstatt
```
