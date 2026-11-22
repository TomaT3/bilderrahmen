# bilderrahmen

Kleiner Dienst für das Synology-NAS: Er liefert jedem E-Ink-Rahmen **einmal am Tag ein zufälliges Foto** aus „seinem“
Album in Synology Photos. Gebaut für den **OpenPaper L** (13,3", E Ink Spectra 6, 1200×1600) mit der
[Offline-Firmware von paperlesspaper](https://github.com/paperlesspaper/paperlesspaper-firmware-offline). Es braucht keine
eigene Firmware und keine Hersteller-Cloud.

```
Synology Photos (Album je Rahmen)
        │  Photos-API, Nur-Lese-Benutzer
        ▼
bilderrahmen (Container)  :8080 /frame/<id>/image.bmp, /frame/<id>/settings.json  ─► cloudflared ─► Internet
                          :8081 /status, /preview/<id>.png, /healthz               (nur LAN)
        ▲
        │ 1× täglich HTTPS + Basic Auth
OpenPaper L im WLAN der Großeltern
```

## Was der Dienst macht
- **Auswahl:** Pro Rahmen gibt es eine Shuffle-Bag. Jedes Foto kommt einmal, bevor sich eines wiederholt. Neue Fotos im Album
  kommen in der nächsten Runde dran, gelöschte fallen heraus. Innerhalb eines Tages bleibt das Bild gleich.
- **Aufbereitung:**
  - EXIF-Drehung;
  - Zuschnitt auf das Rahmenformat; Fotos in der anderen Ausrichtung werden mit weißem Rand eingepasst;
  - etwas mehr Sättigung und Kontrast;
  - Floyd-Steinberg-Dithering gegen die gemessenen Panelfarben;
  - Ausgabe als 4-Bit-BMP.
  - HEIC-Fotos vom iPhone gehen auch.
- **Aufwachzeit:** Der Header `X-OpenPaper-Sleep-Seconds` schickt den Rahmen bis zur nächsten eingestellten Uhrzeit schlafen
  (Standard 06:00). Sommer- und Winterzeit sind berücksichtigt.
- **ETag:** Ruft der Rahmen am selben Tag noch einmal ab (Taste, Wiederholung), antwortet der Dienst mit 304, und der Rahmen
  zeichnet nicht neu.
- **Status:** Batteriespannung, WLAN-Signal und letzter Abruf (aus den `X-OpenPaper-*`-Headern) stehen unter `/status` und
  als JSON-Log (`event: frame_request`) auf stdout.

## Konfiguration
`/config/devices.yaml`, Vorlage: [devices.example.yaml](devices.example.yaml).

| Variable | Bedeutung |
|---|---|
| `SYNO_URL` | z. B. `https://<nas>:5001` |
| `SYNO_USER`, `SYNO_PASSWORD` | eigener DSM-Benutzer nur für Synology Photos, ohne 2FA |
| `SYNO_VERIFY_TLS` | `false`, wenn das NAS ein selbstsigniertes Zertifikat hat (Standard `true`) |
| `FRAME_PASSWORD_<ID>` | Basic-Auth-Passwort je Rahmen, mindestens 16 Zeichen (`openssl rand -hex 24`); Benutzername = Geräte-ID |
| `PUBLIC_URL` | öffentliche Basis-URL, z. B. `https://rahmen.example.de` (für `settings.json`) |
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
   Der Spike legt `spike.bmp` und `spike_preview.png` im aktuellen Ordner ab; beide sind in `.gitignore`.
4. **NAS:** Stack `nas/bilderrahmen/` aus `agent-home-repo` in Arcane anlegen, siehe dort.
5. **Cloudflare-Tunnel:** Public Hostname `rahmen.<domain>` → `http://<nas>:<Rahmen-Port>`. **Nur** auf den Rahmen-Port
   zeigen lassen, nie auf den Status-Port.
6. **Rahmen:**
   - Offline-Firmware per Web-Flasher oder `pio run -e epd13 -t upload` aufspielen. Den Flash **nicht** komplett löschen,
     sonst gehen die Zertifikate der Cloud-Firmware verloren.
   - Reset-Taste drücken; der Rahmen ist dann 30 s per Bluetooth erreichbar. In der Web-UI (Chrome/Edge, Web Bluetooth;
     iOS geht nicht) einstellen:
     - WLAN der Großeltern;
     - `downloadUrl` = `https://rahmen.<domain>/frame/<id>/image.bmp`;
     - Basic Auth: Benutzer `<id>`, Passwort aus `FRAME_PASSWORD_<ID>`;
     - optional die Settings-URL `https://rahmen.<domain>/frame/<id>/settings.json`. Damit lassen sich URL und Passwort
       später aus der Ferne ändern.
   - Steht das Bild auf dem Kopf, dreh den Rahmen um 180°.

## Zuerst am echten Gerät prüfen
- **Palette des BMP:** Die Indizes entsprechen den Farbcodes des Spectra-6-Controllers (0 Schwarz, 1 Weiß, 2 Gelb, 3 Rot,
  5 Blau, 6 Grün), und die Farbtabelle enthält die passenden reinen RGB-Werte. Mit dem „BMP herunterladen“ der Web-UI
  vergleichen. Falls es nicht passt: Palette in [render.py](src/bilderrahmen/render.py) anpassen.
- **Panelfarben:** Die Werte in `PALETTE` (Spalte „measured“) sind Startwerte. Unter `/preview/<id>.png` (LAN-Port) siehst
  du, wie das Bild ungefähr wirkt.
- **Batterie:** Laut Firmware-README werden Updates unter 4,0 V ohne USB übersprungen. Die Warnschwelle für den Alarm
  danach festlegen.

## Sicherheit
- Der Rahmen-Port verlangt Basic Auth pro Gerät; die Prüfung läuft in konstanter Zeit. `/status` und `/preview` antworten
  nur auf dem Status-Port.
- Die Firmware prüft das HTTPS-Zertifikat nicht. Wer den Verkehr mitschneiden kann, sieht also das Rahmen-Passwort. Es öffnet
  nur das Tagesbild dieses Rahmens; bei Verdacht wechselst du es.

## Entwicklung
```sh
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest -q
```
Release: `git tag v0.1.0 && git push --tags` startet CI, die `ghcr.io/tomat3/bilderrahmen:0.1.0` (amd64 und arm64) baut
und pusht.
