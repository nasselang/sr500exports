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
Bare prosjektets operative struktur er tatt med her.
Hemmeligheter, credential-filer og øvrige systemfiler er utelatt med vilje.

```text
/home/johnny/mc-gps/
├── config/
│   └── trip-config.env
├── exports/
│   ├── latest.json
│   └── trips/
│       ├── trip-*.summary.json
│       ├── trip-*.geojson
│       └── trip-*.gpx
├── gps.db
├── scripts/
│   ├── export_gps.py
│   ├── gps_logger.py
│   ├── prune_gps_db.py
│   ├── read_gps.py
│   ├── run_sync.sh
│   ├── sync_exports.sh
│   └── trip_builder.py
└── sr500exports/

/home/johnny/.config/systemd/user/
├── gps-logger.service
├── gps-sync.service
└── gps-sync.timer
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
Dersom sykkelen har lite bevegelse i 15 minutter, legges nye punkter midlertidig uten `trip_id` til bevegelse faktisk starter igjen.

### `trip_builder.py`
Rebygger turer fra eksisterende punkter og oppdaterer `trips`-tabellen.
Starter ny tur dersom gapet mellom punkter er større enn 5 minutter.
Avslutter også tur dersom sykkelen holder seg innenfor liten radius i 15 minutter, og neste reelle bevegelse starter en ny tur.
Filtrerer også bort støy-turer som ser ut som GPS-drift / parkert wobble.

Standard støyfilter:
- `distance_km < 1.0`
- `duration >= 600 sek`
- `average_speed < 2.0 km/t`

### `export_gps.py`
Genererer:
- `exports/latest.json`
- `exports/trips/trip-*.summary.json`
- `exports/trips/trip-*.geojson`
- `exports/trips/trip-*.gpx`

Eksportscriptet rydder også bort gamle eksportfiler som ikke lenger finnes i `trips`-tabellen før nye filer skrives.

### `sync_exports.sh`
Kopierer eksportfiler inn i Git-repoet, committer og pusher ved endringer.

### `run_sync.sh`
Wrapper som kjører:
1. `trip_builder.py`
2. `export_gps.py`
3. `render_trip_html.py`
4. `render_maps_index.py`
5. `sync_exports.sh`
6. `sync_maps.sh`

## Konfigurerbare terskler
Konfigfil:

```text
/home/johnny/mc-gps/config/trip-config.env
```

Standardverdier:
- `TRIP_GAP_SECONDS=300`
- `TRIP_IDLE_SECONDS=900`
- `TRIP_IDLE_RADIUS_METERS=30`
- `TRIP_RESUME_MOVE_METERS=50`
- `MIN_REAL_TRIP_DISTANCE_KM=1.0`
- `MIN_REAL_TRIP_AVG_SPEED_KMH=2.0`
- `MIN_REAL_TRIP_DURATION_SECONDS=600`

Konfigfila inneholder også anbefalte profiler for:
- konservativ
- normal / anbefalt
- aggressiv

Både `gps_logger.py` og `trip_builder.py` leser disse verdiene.
`gps-logger.service` laster dem via `EnvironmentFile`, og `run_sync.sh` sourcer samme fil før rebuild/export/sync.

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

### `gps-prune.timer`
Kjører `gps-prune.service` automatisk for databasevedlikehold:
- 10 minutter etter boot som første mulige catch-up
- deretter månedlig (`OnCalendar=monthly`)
- bruker `prune_gps_db.py --days 90 --apply --vacuum --analyze`

## GitHub
Datarepo:

```text
https://github.com/nasselang/sr500exports
```

Lokal clone på Pi:

```text
/home/johnny/mc-gps/sr500exports
```

Kartpublisering:

```text
https://github.com/nasselang/sr500maps
https://nasselang.github.io/sr500maps/
```

Lokal clone på Pi:

```text
/home/johnny/mc-gps/sr500maps
```

Git-identitet satt på Pi:
- navn: `nasselang`
- epost: `nasselang@gmail.com`

## Databasevedlikehold
For å holde `gps.db` nede i størrelse uten å miste historiske turer, brukes:

```text
/home/johnny/mc-gps/scripts/prune_gps_db.py
```

Scriptet sletter bare råpunkt-rader i `gps_points` for avsluttede turer eldre enn valgt retention-vindu. `trips`-tabellen og eksportfilene beholdes.

Anbefalt standard:
- retention: `90` dager
- første kjøring som dry-run
- ekte kjøring med `--apply --vacuum --analyze`
- periodisk automatikk via `gps-prune.timer` månedlig på Pi-en

Eksempler:

```bash
# dry-run
python3 /home/johnny/mc-gps/scripts/prune_gps_db.py --days 90 --verbose

# faktisk sletting
python3 /home/johnny/mc-gps/scripts/prune_gps_db.py --days 90 --apply --vacuum --analyze
```

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

Kjør database-prune manuelt:
```bash
python3 /home/johnny/mc-gps/scripts/prune_gps_db.py --days 90 --verbose
```

Se siste commit i repo-klonen:
```bash
cd /home/johnny/mc-gps/sr500exports
git log -1 --stat
```

## Gjenstående arbeid
- ytterligere finjustering av turdeteksjon og støyfiltrering ved behov
- forbedret deling av kart ut til chatflater som bilde og/eller lenke
- direkte GPX-utlevering fra agent ved behov
- eventuell Telegram-integrasjon rundt dette
