# Google Sans Flex

Die Anwendung liefert die Schriftdateien lokal aus. Zur Laufzeit werden keine
Google-Fonts-Server aufgerufen. Die Lizenz und Markenhinweise liegen neben den Dateien.

## Web

`google-sans-flex-latin.woff2` und `google-sans-flex-latin-ext.woff2` sind die
unveränderten Google-Fonts-Webdateien für die variablen Achsen `opsz` und `wght`
(Schriftgewichte 100 bis 1000). Die Unicode-Bereiche stehen in `styles/base.css`.
Die normale Latin-Datei wird vorgeladen; Latin Extended wird bei Bedarf geladen.

Quelle, abgerufen am 01.11.2026:
https://fonts.googleapis.com/css2?family=Google+Sans+Flex:opsz,wght@6..144,100..1000&display=swap

SHA-256:

- Latin: `9ec7b22b710ffd078fc5d89b6677d8eef8d06e33b33b7dffcf24668b689eb45c`
- Latin Extended: `a3bd9664466147666a1e6d36344135eb8e47c4d4fecc7da6b02226648d9e980b`

## PDF

Die TTF-Dateien sind vollständig instanzierte Schnitte mit Gewichten 400, 600 und
700; alle anderen Achsen stehen auf ihrem jeweiligen Standardwert. Sie wurden
einmalig mit FontTools erzeugt und werden von ReportLab eingebettet. Eine Erzeugung
oder ein Download zur Laufzeit ist nicht erforderlich.

Quelle: https://github.com/google/fonts/tree/main/ofl/googlesansflex

Quelldatei: `GoogleSansFlex[ROND,opsz,slnt,wdth,wght].ttf`

Git-Blob-SHA-1 der geprüften Quelldatei:
`1d8d8ae5a7c6d0e48312d2a0a478bad92caee73a`

Die Schrift steht unter der SIL Open Font License 1.1, siehe `OFL-GoogleSansFlex.txt`.
