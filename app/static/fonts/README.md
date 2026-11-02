# Lokale Schriften

## Google Sans Flex

Die Anwendung liefert die Schriftdateien lokal aus. Zur Laufzeit werden keine
Google-Fonts-Server aufgerufen. Die Lizenz und Markenhinweise liegen neben den Dateien.

### Web

`google-sans-flex-latin.woff2` und `google-sans-flex-latin-ext.woff2` sind die
unveränderten Google-Fonts-Webdateien für die variablen Achsen `opsz` und `wght`
(Schriftgewichte 100 bis 1000). Die Unicode-Bereiche stehen in `styles/base.css`.
Die normale Latin-Datei wird vorgeladen; Latin Extended wird bei Bedarf geladen.

Quelle, abgerufen am 01.11.2026:
https://fonts.googleapis.com/css2?family=Google+Sans+Flex:opsz,wght@6..144,100..1000&display=swap

SHA-256:

- Latin: `9ec7b22b710ffd078fc5d89b6677d8eef8d06e33b33b7dffcf24668b689eb45c`
- Latin Extended: `a3bd9664466147666a1e6d36344135eb8e47c4d4fecc7da6b02226648d9e980b`

### PDF

Die TTF-Dateien sind vollständig instanzierte Schnitte mit Gewichten 400, 600 und
700; alle anderen Achsen stehen auf ihrem jeweiligen Standardwert. Sie wurden
einmalig mit FontTools erzeugt und werden von ReportLab eingebettet. Eine Erzeugung
oder ein Download zur Laufzeit ist nicht erforderlich.

Quelle: https://github.com/google/fonts/tree/main/ofl/googlesansflex

Quelldatei: `GoogleSansFlex[ROND,opsz,slnt,wdth,wght].ttf`

Git-Blob-SHA-1 der geprüften Quelldatei:
`1d8d8ae5a7c6d0e48312d2a0a478bad92caee73a`

Die Schrift steht unter der SIL Open Font License 1.1, siehe `OFL-GoogleSansFlex.txt`.

## Noto Serif Display

Noto Serif Display setzt Seitentitel und Raumnamen auf Karten in Medium (500)
sowie den gemeinsamen App-/Verwaltungsschriftzug in Bold (700).
Navigation, Formulare, Fließtexte und kleinere Überschriften verwenden
weiterhin Google Sans Flex. QR-PDFs kombinieren Noto für Marke und Raumname mit
Google Sans Flex für Anleitung und Hinweise. Im Web werden die aufrechten Schnitte Medium (500) und Bold (700)
in normaler Breite (100 %) angefordert, ohne synthetische Fettung oder Kursive.

Die WOFF2-Dateien sind unveränderte Google-Fonts-Webdateien, Release **v29**,
abgerufen am **02.11.2026**. Ihre Unicode-Bereiche entsprechen den offiziellen
Latin-/Latin-Extended-Subsets und stehen in `styles/typography.css`. Latin wird
vorgeladen; Latin Extended lädt der Browser nur bei passenden Zeichen nach.
Die Medium-Latin-Datei ist 14.820 Bytes groß, Medium Latin Extended 57.692 Bytes.
Es gibt weder Schrift-Downloads noch Anfragen an Google zur Laufzeit.

Quelle für Schnitt und Subsets:
https://fonts.googleapis.com/css2?family=Noto+Serif+Display:wght@500&display=swap

Feste Asset-URLs und SHA-256:

- `noto-serif-display-500-latin-ext.woff2`
  - Quelle: https://fonts.gstatic.com/s/notoserifdisplay/v29/buERppa9f8_vkXaZLAgP0G5Wi6QmA1QaeYah2sovLCDq_ZgLyt3idQfktOG-PVpv4ugDYjQNhg.woff2
  - SHA-256: `1d07e10dd221c3b65b8766363cf5217035f4f8e14cabae21ea25f1114527712a`
- `noto-serif-display-500-latin.woff2`
  - Quelle: https://fonts.gstatic.com/s/notoserifdisplay/v29/buERppa9f8_vkXaZLAgP0G5Wi6QmA1QaeYah2sovLCDq_ZgLyt3idQfktOG-PVpv4ugNYjQ.woff2
  - SHA-256: `645040ac0639d21dff154094b146a7ba3b3bcb0545c11b3f2ac34730455578e9`

Lizenz: SIL Open Font License 1.1, lokal in `OFL-NotoSerifDisplay.txt`.

Feste Lizenzquelle:
https://raw.githubusercontent.com/google/fonts/a559a6efcfed22bf50219f52ecefcf20b9522408/ofl/notoserifdisplay/OFL.txt

SHA-256 der Lizenz: `5e0da210fb04058a8c0087985d2d456b931c2579811a49655721d3cf0c36b6d6`.

### Bold (700) für den Kopfbereich

Lokal ergänzter echter Bold-Schnitt, Release v29, abgerufen am 02.11.2026.
Gleiche Lizenz und Unicode-Bereiche wie Medium; keine synthetische Fettung.
Quelle: https://fonts.googleapis.com/css2?family=Noto+Serif+Display:wght@700&display=swap

- `noto-serif-display-700-latin-ext.woff2` (54864 Bytes)
  - Quelle: https://fonts.gstatic.com/s/notoserifdisplay/v29/buERppa9f8_vkXaZLAgP0G5Wi6QmA1QaeYah2sovLCDq_ZgLyt3idQfktOG-PVq65egDYjQNhg.woff2
  - SHA-256: `5c6d92989683752f0e3d371b6f740825737c5abf566a0cf73f294a5636a904a4`
- `noto-serif-display-700-latin.woff2` (14408 Bytes)
  - Quelle: https://fonts.gstatic.com/s/notoserifdisplay/v29/buERppa9f8_vkXaZLAgP0G5Wi6QmA1QaeYah2sovLCDq_ZgLyt3idQfktOG-PVq65egNYjQ.woff2
  - SHA-256: `1d6f07e4d36c336d8676875a1afc2a68f175ee5ce31c1aa3ed5d4e3a36f992ca`

### PDF: statische TTF-Schnitte

`NotoSerifDisplay-Medium.ttf` (500) und `NotoSerifDisplay-Bold.ttf` (700) sind
unveränderte statische TrueType-Dateien aus Google Fonts, Release v29,
abgerufen am 02.11.2026. Beide sind aufrecht, normal breit und enthalten je
2.840 Unicode-Zuordnungen. Sie werden von ReportLab eingebettet; zur Laufzeit
sind weder Downloads noch Font-Konvertierungen erforderlich. Die oben genannte
SIL-OFL-Lizenz gilt ebenfalls für diese Dateien.

- `NotoSerifDisplay-Medium.ttf` (398416 Bytes)
  - Quelle: https://fonts.gstatic.com/s/notoserifdisplay/v29/buERppa9f8_vkXaZLAgP0G5Wi6QmA1QaeYah2sovLCDq_ZgLyt3idQfktOG-PVpv4tgK.ttf
  - SHA-256: `e8837ed1854971c52136aaa97ef213c3c2139b236f93d4e2d7fd0b1b03d47c11`
- `NotoSerifDisplay-Bold.ttf` (397628 Bytes)
  - Quelle: https://fonts.gstatic.com/s/notoserifdisplay/v29/buERppa9f8_vkXaZLAgP0G5Wi6QmA1QaeYah2sovLCDq_ZgLyt3idQfktOG-PVq65dgK.ttf
  - SHA-256: `cd898729b4abd86ba20c468564a6d5f59781c7a1db5b38af4a428430fa4f76c1`
