# bilderrahmen

Ein E-Ink-Rahmen zeigt **einmal am Tag ein zufälliges Foto** aus „seinem“ Album in Synology Photos. Das Repo enthält
zwei Teile:

- den **Dienst** für das Synology-NAS (Python/FastAPI): Er wählt das Foto aus und bereitet es fertig für das Panel auf;
- die **Firmware** für den Rahmen ([firmware/](firmware/), ESP-IDF): Sie holt das Bild ab, zeigt es an und schläft dann
  bis zum nächsten Morgen.

Hardware ist der [Waveshare ESP32-S3-PhotoPainter](https://www.waveshare.com/esp32-s3-photopainter.htm):
- 7,3" E Ink Spectra 6 mit 800×480 Pixeln;
- Holzrahmen mit Aufsteller und Aufhänger;
- LiPo-Akku (3,7 V, 1500 mAh, als Option mitbestellen), Ladung über USB-C;
- rund 85–95 € inklusive Akku.

Eine Hersteller-Cloud braucht es nicht.

```
Synology Photos (Album je Rahmen)
        │  Photos-API, Nur-Lese-Benutzer
        ▼
bilderrahmen (Container)  :8080 /frame/<id>/image.bin            ─► cloudflared ─► Internet
                          :8081 /status, /preview/<id>.png, /healthz   (nur LAN)
        ▲
        │ 1× täglich HTTPS + Basic Auth
PhotoPainter im WLAN der Großeltern (firmware/)
```

## Was der Dienst macht
- **Auswahl:**
  - Pro Rahmen gibt es eine Shuffle-Bag: Jedes Foto kommt einmal, bevor sich eines wiederholt.
  - Neue Fotos im Album kommen in der nächsten Runde dran, gelöschte fallen heraus.
  - Innerhalb eines Tages bleibt das Bild gleich.
- **Aufbereitung:**
  - EXIF-Drehung;
  - Zuschnitt auf 800×480; Fotos in der anderen Ausrichtung werden mit weißem Rand eingepasst;
  - etwas mehr Sättigung und Kontrast;
  - Floyd-Steinberg-Dithering gegen die gemessenen Panelfarben;
  - HEIC-Fotos vom iPhone gehen auch.
- **Ausgabe:** `image.bin` ist der rohe Panelpuffer mit genau 192 000 Bytes:
  - 4 Bit pro Pixel, das hohe Nibble ist das linke Pixel;
  - Zeilen von oben nach unten;
  - Werte sind die Farbcodes des Controllers (0 Schwarz, 1 Weiß, 2 Gelb, 3 Rot, 5 Blau, 6 Grün).
  - Die Firmware schickt den Puffer unverändert ans Panel und muss nichts dekodieren.
- **Aufwachzeit:** Der Header `X-Sleep-Seconds` schickt den Rahmen bis zur nächsten eingestellten Uhrzeit schlafen
  (Standard 06:00). Sommer- und Winterzeit sind berücksichtigt. Der interne Takt des ESP32 driftet über 24 h etwas,
  das wird aber jeden Morgen neu ausgeglichen.
- **ETag:** Ruft der Rahmen am selben Tag noch einmal ab (KEY-Taste), antwortet der Dienst mit 304, und der Rahmen
  zeichnet nicht neu.
- **Status:** Akkuspannung, WLAN-Signal, Weckgrund, Firmware-Version und letzter Abruf (aus den `X-Frame-*`-Headern)
  stehen unter `/status` und als JSON-Log (`event: frame_request`) auf stdout.

## Was die Firmware macht
Bei jedem Aufwachen, also durch den Timer oder die KEY-Taste:
1. PMIC wecken und die Akkuspannung messen.
2. Im WLAN anmelden (20 s Timeout).
3. `image.bin` mit Basic Auth und `If-None-Match` abrufen.
4. Bei einem neuen Bild das WLAN abschalten und das Panel neu zeichnen (ca. 25 s).
5. Panel und PMIC schlafen legen, dann Deep Sleep für `X-Sleep-Seconds`.

Bei einem Fehler behält der Rahmen das alte Bild und versucht es nach 1 h erneut, ab dem dritten Fehler in Folge
nach 6 h. Hängt etwas, zieht ein Zeitlimit von 3 Minuten den Rahmen trotzdem in den Schlaf.

Woher Pins, Panel-Init und PMIC-Register stammen, steht in den Kommentaren von [board.h](firmware/main/board.h),
[epd.c](firmware/main/epd.c) und [pmic.c](firmware/main/pmic.c). Quelle ist die Waveshare-Demo
[wurongmin/ESP32-S3-PhotoPainter](https://github.com/wurongmin/ESP32-S3-PhotoPainter).

## Konfiguration des Dienstes
`/config/devices.yaml`, Vorlage: [devices.example.yaml](devices.example.yaml).

| Variable | Bedeutung |
|---|---|
| `SYNO_URL` | z. B. `https://<nas>:5001` |
| `SYNO_USER`, `SYNO_PASSWORD` | eigener DSM-Benutzer nur für Synology Photos, ohne 2FA |
| `SYNO_VERIFY_TLS` | `false`, wenn das NAS ein selbstsigniertes Zertifikat hat (Standard `true`) |
| `FRAME_PASSWORD_<ID>` | Basic-Auth-Passwort je Rahmen, mindestens 16 Zeichen (`openssl rand -hex 24`); Benutzername = Geräte-ID |
| `FRAME_PORT`, `STATUS_PORT` | Standard 8080 / 8081 |

Der Zustand (Shuffle-Bag, Status) liegt in `/data/state.json`, das fertige Tagesbild in `/data/cache/`.

## Einrichtung
1. **DSM:** Benutzer `bilderrahmen` anlegen. Er darf nur Synology Photos nutzen und bekommt kein 2FA.
2. **Synology Photos:** Pro Rahmen ein Album anlegen und mit `bilderrahmen` teilen (nur ansehen). Bilder fügst du einfach
   am Handy zum Album hinzu.
3. **Spike:** Zugriff prüfen, bevor der Rahmen dran ist:
   ```sh
   pip install -e .
   SYNO_URL=https://nas:5001 SYNO_USER=bilderrahmen SYNO_PASSWORD=… python -m bilderrahmen.spike "Rahmen Oma+Opa"
   ```
   Der Spike legt `spike_panel.bin` und `spike_preview.png` im aktuellen Ordner ab; beide sind in `.gitignore`.
4. **NAS:** Stack `nas/bilderrahmen/` aus `agent-home-repo` in Arcane anlegen, siehe dort.
5. **Cloudflare-Tunnel:** Public Hostname `rahmen.<domain>` → `http://<nas>:<Rahmen-Port>`. **Nur** auf den Rahmen-Port
   zeigen lassen, nie auf den Status-Port.
6. **Firmware:**
   - `firmware/main/secrets.example.h` nach `secrets.h` kopieren und ausfüllen: WLAN der Großeltern, `FRAME_ID`,
     `FRAME_PASSWORD` (aus `FRAME_PASSWORD_<ID>`) und `FRAME_BASE_URL` (`https://rahmen.<domain>`).
   - Bauen und flashen, z. B. mit Docker, ohne lokale ESP-IDF:
     ```sh
     docker run --rm -v "$PWD/firmware:/project" -w /project espressif/idf:v5.5.2 idf.py build
     # Flashen vom Host (USB-C, Port anpassen):
     cd firmware/build && python -m esptool --chip esp32s3 -p COM5 write_flash @flash_args
     ```
     Mit einer lokalen ESP-IDF 5.5.2 geht auch `idf.py -p COM5 flash monitor` im Ordner `firmware/`.
   - Ändert sich das WLAN der Großeltern, musst du den Rahmen per USB neu flashen.
7. **Rahmen:** Er holt das erste Bild gleich nach dem Flashen. Steht es auf dem Kopf, dreh den Rahmen um 180°. Hängt
   er hochkant, stell in `devices.yaml` `orientation: portrait` ein.

## Zuerst am echten Gerät prüfen
- **Panel:** Pins und Init-Sequenz stammen aus der Waveshare-Demo, getestet ist die Firmware aber nur durch den Build.
  Den ersten Lauf mit `idf.py monitor` mitlesen.
- **Akkulaufzeit:** Waveshare gibt einen Schlafstrom von ≤ 1 mA an. Mit 1500 mAh wären das grob 6–8 Wochen pro Ladung.
  Die Firmware schaltet wie Waveshares Stromtest alle PMIC-Schienen außer der des ESP32 ab. Ob der Rahmen damit
  deutlich länger hält, zeigt nur eine Messung oder der Verlauf von `battery_mv` in OpenObserve.
- **Akkuwarnung:** Startwert unter 3500 mV. Die Schwelle legst du nach den ersten Wochen anhand des Verlaufs fest.
- **Panelfarben:** Die Werte in `PALETTE` (Spalte „measured“) sind Startwerte. Unter `/preview/<id>.png` (LAN-Port)
  siehst du, wie das Bild ungefähr wirkt; vergleich das mit dem echten Panel.

## Sicherheit
- Der Rahmen-Port verlangt Basic Auth pro Gerät; die Prüfung läuft in konstanter Zeit. `/status` und `/preview` antworten
  nur auf dem Status-Port.
- Die Firmware prüft das HTTPS-Zertifikat gegen das CA-Bundle von ESP-IDF. Das Rahmen-Passwort steht im Flash des
  Rahmens und öffnet nur das Tagesbild dieses Rahmens. Geht der Rahmen verloren, wechselst du das Passwort.

## Entwicklung
```sh
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest -q
```
CI testet den Dienst und baut die Firmware; das Firmware-Binary liegt als Artefakt am Lauf.

Release des Dienstes: `git tag v0.1.0 && git push --tags` startet CI. Die baut und pusht
`ghcr.io/tomat3/bilderrahmen:0.1.0` (amd64 und arm64).
