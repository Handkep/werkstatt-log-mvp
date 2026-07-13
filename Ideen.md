# Ideen für das Zelter5 Raumlog

Kleine, offene Brainstorming-Liste für mögliche Erweiterungen. Die Reihenfolge ist noch keine feste Roadmap.

## Reservierung und Kalender

- Räume direkt in der Webapp reservieren.
- Freie und belegte Zeiten in einer einfachen Tages- oder Wochenansicht zeigen.
- Reservierungen ändern oder stornieren können.
- Bestätigung und Erinnerung per E-Mail.
- Termin als `.ics`-Datei für den eigenen Kalender herunterladen.
- Später optional einen Kalender pro Raum abonnierbar machen.
- Eine direkte Google-/Microsoft-/CalDAV-Synchronisation nur ergänzen, wenn sie wirklich benötigt wird.

Mögliche Regeln je Raum:

- **Werkstatt:** längere Zeitblöcke, eventuell mehrere Personen gleichzeitig.
- **Sauna:** feste Zeitfenster, maximale Dauer und Aufheizpuffer.
- **Ruheraum:** einzeln oder gemeinsam mit der Sauna reservierbar.
- **Sommerküche:** Gruppengröße, Ruhezeiten und Reinigungspuffer.
- **Dachterrasse:** Gruppengröße, Ruhezeiten und eventuell Wetterhinweis.
- **Keller:** erst klären, ob einzelne Kellerbereiche getrennte Ressourcen sind.

## Kabellose Zugangskontrolle

Die Türen liegen räumlich getrennt. Eine Verkabelung von Tür zu Tür ist nicht realistisch. Bevorzugt werden daher eigenständige, kabellose Lösungen.

Mögliche Varianten:

- Batteriebetriebene elektronische Schließzylinder oder Türbeschläge mit NFC-Karten.
- Kommerzielle Offline-Schlösser, deren Berechtigungen per Smartphone, Karte oder Funk-Gateway aktualisiert werden.
- WLAN-Leser an Türen, an denen WLAN-Abdeckung und eine lokale Stromversorgung vorhanden sind.
- Funk-Gateway pro Gebäudeabschnitt statt einer Kabelverbindung zwischen allen Türen.
- Lokaler Stromanschluss je Tür, falls ein elektrischer Türöffner verwendet wird.

Wichtige Anforderungen:

- Türen müssen auch bei Internet- oder Serverausfall funktionieren.
- Verlorene NFC-Karten müssen einzeln sperrbar sein.
- Keine Freigabe nur anhand einer leicht kopierbaren Karten-ID.
- Möglichst fertige kommerzielle Türhardware verwenden; die Webapp verwaltet nur Personen, Rechte und Ereignisse.
- Batteriestand, Offlinezustand und Störungen sollten im Adminbereich sichtbar sein.
- Mechanischer Schlüssel bleibt als unabhängiger Notfallzugang erhalten.

### NFC-Karten

- Karten sind günstig, einfach auszugeben und ohne Smartphone nutzbar.
- Rechte könnten je Raum und Zeitraum vergeben werden.
- Ausgabe, Verlust, Ersatz und Rückgabe einer Karte müssen verwaltbar sein.
- Eine Reservierung könnte später automatisch ein zeitlich begrenztes Zutrittsrecht erzeugen.

### Notfall-Zahlenpad

- Zahlenpad als Fallback, wenn NFC-Karte oder Smartphone fehlen.
- Keine dauerhaft gemeinsame Haus-PIN verwenden.
- Besser: individuelle, einmalige oder zeitlich begrenzte Codes.
- Fehlversuche begrenzen und bei vielen Versuchen eine Meldung auslösen.
- Zahlenpad und Schloss sollten auch ohne Verbindung zur Webapp arbeiten.

### Sinnvoller Testaufbau

1. Zwei oder drei kabellose Systeme beziehungsweise Schließzylinder vergleichen.
2. NFC und PIN zunächst ohne echte Türöffnung testen.
3. Batterielaufzeit, Funkreichweite, Sperrung verlorener Karten und Offlinebetrieb prüfen.
4. Danach eine einzelne, unkritische Tür als Pilot ausstatten.
5. Erst nach einigen Monaten über weitere Türen entscheiden.

## Automatisierung und Logging

- NFC-Karte kann Name und Haus automatisch in das Nutzungsformular übernehmen.
- Ein Türzutritt kann einen vorbereiteten Logeintrag erzeugen, den die Person nur noch bestätigt.
- Bei der Sauna könnte der NFC-Zutritt die manuelle Nummerneingabe ersetzen.
- Check-in und Check-out per NFC könnten Nutzungsdauer und Belegung erfassen.
- Türkontakt könnte melden, wenn eine Tür ungewöhnlich lange offensteht.
- Sauna-Reservierung könnte später Aufheizzeiten berücksichtigen.
- Eine Steuerung der Saunatechnik nur mit geeigneter professioneller Hardware umsetzen; Sicherheitsfunktionen müssen unabhängig von der Webapp bleiben.

## Weitere Produktideen

- Aktuellen Raumstatus anzeigen: frei, reserviert, belegt, gesperrt oder in Wartung.
- Werkzeuge oder Geräte per QR-Code/NFC ausleihen und zurückgeben.
- Einweisungen für bestimmte Maschinen hinterlegen.
- Reinigungs- und Übergabechecklisten je Raum.
- Verantwortliche Person für einen Defekt oder eine Wartung festlegen.
- Kleine Statistik: Nutzung pro Raum, häufige Defekte und beliebte Zeiten.
- Installierbare Webapp/PWA für schnelleren Zugriff auf dem Smartphone.

## Technische Verbesserungen

- Automatische Backups von Datenbank und Bildern einrichten und Wiederherstellung testen.
- Tests für Formulare, Uploads, Datenbank und Adminfunktionen ergänzen.
- Datenbankänderungen mit einem Migrationswerkzeug verwalten.
- Separates Docker-Setup für Entwicklung und Produktivbetrieb.
- Uploadgrenzen vereinheitlichen; aktuell unterscheiden sich App- und Docker-Standardwerte.
- Individuelle Adminzugänge und Rollen statt eines gemeinsamen Passworts.
- Bei größerer Nutzung später Wechsel von SQLite zu PostgreSQL prüfen.

## Offene Fragen

- Welche Türen sollen zuerst ausgestattet werden?
- Gibt es an jeder Tür Strom, WLAN oder nur Batteriebetrieb?
- Wie weit sind die Türen vom nächsten möglichen Funk-Gateway entfernt?
- Werden elektronische Schließzylinder, Türbeschläge oder elektrische Türöffner bevorzugt?
- Welche Türen sind Flucht- oder Brandschutztüren?
- Wie lange soll ein Schloss ohne Verbindung weiterarbeiten können?
- Wer darf Zutrittsrechte vergeben und verlorene Karten sperren?
- Welche Räume benötigen Reservierungen und welche nur ein Nutzungslog?
- Welche Informationen dürfen für andere Bewohner sichtbar sein?
- Wie lange sollen Nutzungs-, Reservierungs- und Zutrittsdaten gespeichert werden?
- Welches Budget steht pro Tür und für laufende Lizenzen zur Verfügung?
