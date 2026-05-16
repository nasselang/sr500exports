# Setup på Raspberry Pi (SR500)

Dette dokumentet beskriver det konkrete oppsettet som nå er gjort på `sr500.lan`.

## Maskin / miljø
- host: `SR500`
- bruker: `johnny`
- OS: Debian 13 (trixie)
- arkitektur: `arm64`
- Python: `3.13.5`
- GPS-dongle: `u-blox 7`
- device: `/dev/ttyACM0`

## GPS-verktøy
Verifisert på Pi-en:
- `gpsd`
- `cgps`
- `gpsmon`

GPS-fix ble bekreftet via `gpsd` og Python-script mot lokal GPSD-socket.

## Mappestruktur på Pi-en
```text
/home/johnny/mc-gps/
├── exports/
├── gps.db
├── scripts/
│   ├── export_gps.py
│   ├── gps_logger.py
│   ├── read_gps.py
│   ├── run_sync.sh
│   ├── sync_exports.sh
│   └── trip_builder.py
└── sr500exports/
```

## Database
SQLite-database:

```text
/home/johnny/mc-gps/gps.db
```

### Tabeller
#### `gps_points`
Felter:
- `id`
- `ts`
- `lat`
- `lon`
- `speed_kmh`
- `alt_m`
- `trip_id`
- `synced`

#### `trips`
Felter:
- `trip_id`
- `start_ts`
- `end_ts`
- `points`
- `distance_km`

## Script-roller
### `read_gps.py`
Brukes for enkel verifisering av at `gpsd` leverer gyldig posisjon.

### `gps_logger.py`
Lytter på `gpsd` og skriver gyldige GPS-punkter til SQLite.
Filtrerer bort ugyldige punkter og ignorerer duplikater med samme timestamp.
Setter også `trip_id` løpende.

### `trip_builder.py`
Rebygger turer fra eksisterende punkter og oppdaterer `trips`-tabellen.
Starter ny tur dersom gapet mellom punkter er større enn 5 minutter.

### `export_gps.py`
Genererer:
- `exports/latest.json`
- `exports/trips/trip-*.summary.json`
- `exports/trips/trip-*.geojson`

### `sync_exports.sh`
Kopierer eksportfiler inn i Git-repoet, committer og pusher ved endringer.

### `run_sync.sh`
Wrapper som kjører:
1. `trip_builder.py`
2. `export_gps.py`
3. `sync_exports.sh`

## systemd user units
Plassering:

```text
/home/johnny/.config/systemd/user/
```

### `gps-logger.service`
Kontinuerlig GPS-logging.
Kjører med restart-policy.

### `gps-sync.service`
One-shot jobb for eksport + GitHub-sync.

### `gps-sync.timer`
Kjører `gps-sync.service` automatisk:
- 2 minutter etter boot
- deretter hver 15. minutt

## GitHub
Repo:

```text
https://github.com/nasselang/sr500exports
```

Lokal clone på Pi:

```text
/home/johnny/mc-gps/sr500exports
```

Git-identitet satt på Pi:
- navn: `nasselang`
- epost: `nasselang@gmail.com`

## Driftstips
Sjekk logger-service:
```bash
systemctl --user status gps-logger.service
```

Sjekk sync-timer:
```bash
systemctl --user status gps-sync.timer
systemctl --user list-timers --all | grep gps-sync
```

Kjør sync manuelt:
```bash
systemctl --user start gps-sync.service
```

Se siste commit i repo-klonen:
```bash
cd /home/johnny/mc-gps/sr500exports
git log -1 --stat
```

## Gjenstående arbeid
- GPX-eksport
- mer robust turdeteksjon
- OpenClaw-agent som leser eksportene
- kart-rendering
- Telegram-integrasjon
