# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier festgehalten.

## [0.3.2]

### Hinzugefügt
- Jedes Release enthält jetzt automatisch ein ZIP `F4bst3r-YTDL-<Version>.zip` unter Assets (gebaut per GitHub Action).

### Behoben
- Zeilenenden festgelegt (`.gitattributes`): `start.bat` mit CRLF, `start.sh` und `start.command` mit LF.

## [0.3.1]

### Hinzugefügt
- Footer „Made by F4bst3r“ mit Links zu X (Twitter) und YouTube unten in der Weboberfläche.

## [0.3]

### Hinzugefügt
- Automatische Anmeldung: Verlangt YouTube eine Anmeldung, probiert die App die Cookies von Firefox, Chrome, Edge und Brave durch und merkt sich den Browser, der funktioniert hat. Das gilt für die Analyse und für Downloads.
- Option `--no-auto-cookies`, um dieses Verhalten abzuschalten.
- Im Download-Eintrag steht, wenn die Anmeldung aus einem Browser genutzt wurde.

## [0.2.1]

### Geändert
- Bei „HTTP Error 403: Forbidden“ startet der Download automatisch einen zweiten Versuch mit frischen Links.
- Verständlichere Fehlermeldung, falls der zweite Versuch ebenfalls scheitert.

## [0.2]

### Hinzugefügt
- `CHANGELOG.md` mit der Versionshistorie.

## [0.1.1]

### Geändert
- README: Hinweis ergänzt, dass das Projekt zu 100 % mit Claude vibe-gecodet ist.

## [0.1]

### Hinzugefügt
- Erste Version: lokaler Video- und Audio-Downloader mit Weboberfläche auf Basis von yt-dlp und ffmpeg.
- Start per `start.bat` (Windows), `start.command` (macOS) oder `start.sh` (Linux).
- Automatische Einrichtung von Python, yt-dlp, ffmpeg und Deno beim ersten Start.
