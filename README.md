# F4bst3r-YTDL

Lokaler Video- und Audio-Downloader mit Weboberfläche, gebaut auf **yt-dlp** (der gepflegte Nachfolger von youtube-dl) und **ffmpeg**.

> **Hinweis:** Dieses Projekt ist zu 100 % mit Claude (Anthropic) vibe-gecodet. Der gesamte Code wurde von der KI geschrieben und nicht manuell geprüft. Nutzung auf eigene Verantwortung.
>
> **Note:** This project is 100% vibe-coded with Claude (Anthropic). All code was written by the AI and has not been manually reviewed. Use at your own risk.

## Starten

| System | Befehl |
| --- | --- |
| Windows | Doppelklick auf `start.bat` |
| macOS | Doppelklick auf `start.command` |
| Linux | `./start.sh` |

Beim ersten Start richtet das Skript alles selbst ein und lädt dafür einmalig etwa 200 MB. Danach öffnet sich der Browser.
Du kannst auch `index.html` per Doppelklick öffnen, solange das Startfenster läuft. Der Server muss laufen, weil ein Browser allein weder yt-dlp noch ffmpeg ausführen kann.

## Was automatisch eingerichtet wird

| Programm | Wie |
| --- | --- |
| Python | Windows: per `winget`. Linux: über apt, dnf oder pacman (fragt ggf. nach dem Passwort). Mac: über Homebrew, falls vorhanden. |
| yt-dlp | in eine eigene Umgebung im Ordner `.venv` |
| ffmpeg und ffprobe | in den Ordner `bin` (ohne Admin-Rechte, nichts wird im System verändert) |
| Deno (für YouTube) | in den Ordner `bin`, wenn weder Deno noch Node.js vorhanden ist |

Schon vorhandene Programme werden erkannt und nicht doppelt geladen. Zum Aufräumen genügt es, den Ordner zu löschen.
Nicht automatisch geht es, wenn auf dem Windows-PC `winget` fehlt (dann Python von python.org installieren) oder wenn auf dem Mac weder Python noch Homebrew vorhanden sind (dann beim ersten `python3`-Aufruf die Entwicklertools bestätigen).

## Funktionen

- **Qualität:** „Automatisch – höchste“ nimmt immer die beste verfügbare Auflösung (bis 8K). Alternativ feste Stufen von 144p bis 4320p.
- **Video:** MP4, MKV oder WebM. Optional „Kompatibel (H.264)“ für Geräte, die VP9/AV1 nicht abspielen.
- **Nur Audio:** MP3, M4A, Opus, FLAC, WAV oder das unveränderte Original. Bei MP3, M4A und Opus wählbar von 128 bis 320 kbit/s.
- Playlists, Cover und Metadaten einbetten, mehrere Downloads gleichzeitig, Abbrechen.
- Dateien landen standardmäßig in `Downloads/F4bst3r-YTDL`, im Browser lassen sie sich zusätzlich direkt speichern.

## Optionen

```
python server.py --dir D:\Videos --port 9000 --parallel 3
python server.py --cookies-from-browser firefox     # für altersbeschränkte Videos
```

## Anmeldung bei YouTube

Verlangt YouTube eine Anmeldung („Sign in to confirm you're not a bot“ oder Altersabfrage), probiert die App automatisch die Cookies deiner Browser (Firefox, Chrome, Edge, Brave) durch. Dafür musst du in einem davon bei YouTube angemeldet sein. Der Browser, der funktioniert hat, wird bis zum Beenden der App weiterverwendet. Die Cookies werden nur lokal von yt-dlp gelesen und nirgends gespeichert oder gesendet.
Firefox klappt am zuverlässigsten, bei Chrome, Edge und Brave blockiert Windows den Zugriff oft. Mit `--no-auto-cookies` schaltest du das Verhalten ab, mit `--cookies-from-browser firefox` legst du den Browser fest.

## Wenn es nicht mehr klappt

YouTube ändert oft etwas. Dann hilft fast immer ein Update: `start.bat update` bzw. `./start.sh update`.

## Sicherheit

Der Server hört nur auf `127.0.0.1` und verlangt ein Token, das in `config.js` steht. Fremde Webseiten können damit nichts auslösen. Gib `config.js` nicht weiter.

Lade nur Inhalte herunter, für die du die Rechte hast oder deren Nutzung erlaubt ist. Die Nutzungsbedingungen der Plattformen und das Urheberrecht gelten weiterhin.
