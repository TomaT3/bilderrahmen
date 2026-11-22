// Vorlage: als secrets.h daneben kopieren und ausfüllen. secrets.h steht in .gitignore und wird nie committet.
#pragma once

#define WIFI_SSID "WLAN-der-Grosseltern"
#define WIFI_PASSWORD "wlan-passwort"

// Geräte-ID aus devices.yaml und das Passwort aus FRAME_PASSWORD_<ID> auf dem NAS
#define FRAME_ID "oma-opa"
#define FRAME_PASSWORD "mindestens-16-zeichen-langes-passwort"

// Öffentliche Adresse über cloudflared (mit gültigem Zertifikat), ohne Schrägstrich am Ende
#define FRAME_BASE_URL "https://rahmen.example.de"
