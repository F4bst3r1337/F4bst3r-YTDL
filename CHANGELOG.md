# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier festgehalten.

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
