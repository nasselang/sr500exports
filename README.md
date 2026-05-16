# sr500exports

Eksportrepo for motorsykkel/GPS-prosjektet på Raspberry Pi `SR500`.

Dette repoet mottar batch-oppdaterte eksportfiler fra Pi-en:
- `latest.json` for siste kjente posisjon
- `trips/trip-*.summary.json` for enkel turmetadata
- `trips/trip-*.geojson` for rute + punkter

Målet er å holde repoet enkelt nok til at en OpenClaw-agent senere kan lese siste posisjon og siste tur uten å koble seg direkte til Pi-en.

## Nåværende status
Følgende er implementert på Pi-en:

1. GPS-dongle (`u-blox 7`) leses via `gpsd`
2. gyldige GPS-punkter lagres i SQLite (`gps.db`)
3. punktene grupperes til turer med `trip_id`
4. tur avsluttes ved mer enn 5 minutters datagap eller ved lite bevegelse over 15 minutter
5. ny tur opprettes når reell bevegelse starter igjen
6. siste tur eksporteres til JSON/GeoJSON
7. eksportene synkes automatisk til dette repoet hvert 15. minutt

## Arkitektur
På Raspberry Pi-en kjører følgende komponenter:

- `read_gps.py`
  - enkel testleser mot `gpsd`
- `gps_logger.py`
  - kontinuerlig logger GPS-punkter til SQLite
- `trip_builder.py`
  - bygger turer fra `gps_points`
  - avslutter tur ved >5 min datagap eller 15 min lite bevegelse
  - oppretter ny tur når faktisk bevegelse starter igjen
- `export_gps.py`
  - eksporterer `latest.json`, `summary.json` og `geojson`
- `sync_exports.sh`
  - kopierer eksportene inn i repoet, commit’er og pusher
- `run_sync.sh`
  - kjører rebuild + eksport + sync i én jobb

## Filer i repoet

### `latest.json`
Siste kjente posisjon.

Eksempel:

```json
{
  "ts": "2026-05-16T12:02:28.000Z",
  "lat": 59.900360648,
  "lon": 10.833089228,
  "speed_kmh": 3.56,
  "alt_m": 105.6554,
  "trip_id": "2026-05-16T11-56-51Z"
}
```

### `trips/trip-*.summary.json`
Metadata om en tur:
- `trip_id`
- `start_ts`
- `end_ts`
- `points`
- `distance_km`

### `trips/trip-*.geojson`
GeoJSON `FeatureCollection` med:
- en `LineString` for hele ruta
- `Point`-features for hvert punkt

## Operativ filstruktur på SR500
Bare prosjektets relevante struktur er dokumentert her.
Secrets, Git-credentials og øvrige systemfiler er bevisst utelatt.

```text
/home/johnny/mc-gps/
├── exports/
│   ├── latest.json
│   └── trips/
│       ├── trip-*.summary.json
│       └── trip-*.geojson
├── gps.db
├── scripts/
│   ├── read_gps.py
│   ├── gps_logger.py
│   ├── trip_builder.py
│   ├── export_gps.py
│   ├── sync_exports.sh
│   └── run_sync.sh
└── sr500exports/

/home/johnny/.config/systemd/user/
├── gps-logger.service
├── gps-sync.service
└── gps-sync.timer
```

## Hvor dette kjører på Pi-en
Basemappe:

```text
/home/johnny/mc-gps/
```

## Systemd-oppsett
Det brukes `systemd --user` på Pi-en.

### Vedvarende GPS-logging
- `gps-logger.service`
- restartes automatisk ved feil

### Periodisk eksport + GitHub-sync
- `gps-sync.service`
- `gps-sync.timer`

Timeren kjører:
- 2 minutter etter boot
- deretter hver 15. minutt

## GitHub-sync
Repoet klones lokalt på Pi-en til:

```text
/home/johnny/mc-gps/sr500exports
```

Sync-flyten er:
1. rebuild turer
2. eksportér filer
3. kopier eksportene til repoet
4. `git add`
5. `git commit`
6. `git push`

Det pushes bare når det faktisk finnes endringer.

## Nåværende begrensninger
- turdeteksjon er forbedret med 15 min lite-bevegelse-regel, men er fortsatt heuristisk
- eksportstruktur bruker foreløpig flat `trips/`-mappe
- GPX er ikke implementert ennå
- OpenClaw-agent-lesing, kart og Telegram gjenstår

## Naturlige neste steg
1. la agenten lese `latest.json` og siste turfil
2. generere enkel turoppsummering
3. rendere kart fra GeoJSON
4. sende resultat via Telegram
