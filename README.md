# sr500exports

Eksportrepo for motorsykkel/GPS-prosjektet på Raspberry Pi `SR500`.

Dette repoet mottar batch-oppdaterte eksportfiler fra Pi-en:
- `latest.json` for siste kjente posisjon
- `trips/trip-*.summary.json` for enkel turmetadata
- `trips/trip-*.geojson` for rute + punkter
- `trips/trip-*.gpx` for standard GPS-sporformat

Målet er å holde repoet enkelt nok til at en OpenClaw-agent kan lese siste posisjon og siste tur uten å koble seg direkte til Pi-en.

## Nåværende status
Følgende er implementert på Pi-en:

1. GPS-dongle (`u-blox 7`) leses via `gpsd`
2. gyldige GPS-punkter lagres i SQLite (`gps.db`)
3. punktene grupperes til turer med `trip_id`
4. tur avsluttes ved mer enn 5 minutters datagap eller ved lite bevegelse over 15 minutter
5. ny tur opprettes når reell bevegelse starter igjen
6. alle gyldige turer eksporteres til JSON/GeoJSON/GPX
7. støy-turer filtreres bort ved rebuild når de ser ut som GPS-drift (lav distanse + lang varighet + lav snittfart)
8. stale eksportfiler ryddes bort før ny eksport skrives
9. eksportene synkes automatisk til dette repoet hvert 15. minutt

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
  - filtrerer bort støy-turer som ligner GPS-drift / parkert wobble
- `export_gps.py`
  - eksporterer `latest.json`, `summary.json`, `geojson` og `gpx` for alle gyldige turer
  - rydder bort gamle eksportfiler som ikke lenger finnes i `trips`-tabellen
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

### `trips/trip-*.gpx`
GPX 1.1-sporfil for samme tur.
Kan brukes i eksterne GPS-/kartverktøy som støtter GPX-import.

## Operativ filstruktur på SR500
Bare prosjektets relevante struktur er dokumentert her.
Secrets, Git-credentials og øvrige systemfiler er bevisst utelatt.

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
│   ├── read_gps.py
│   ├── gps_logger.py
│   ├── trip_builder.py
│   ├── export_gps.py
│   ├── prune_gps_db.py
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

## Konfigurerbare terskler
Trip-logikken leser nå terskler fra:

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

Filen inneholder også anbefalte profiler for:
- konservativ
- normal / anbefalt
- aggressiv

Dette gjør at trip-deling kan finjusteres uten å redigere Python-koden.

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

## Databasevedlikehold
For å hindre at SQLite-databasen vokser unødvendig, finnes det nå et eget ryddeverktøy:

- `scripts/prune_gps_db.py`

Dette scriptet:
- sletter gamle rader i `gps_points`
- rydder bare punkter for **avsluttede turer** eldre enn valgt retention-vindu
- **beholder** `trips`-tabellen
- **beholder** eksportfiler (`summary.json`, `geojson`, `gpx`, `latest.json`)
- støtter dry-run som standard
- kan kjøre `VACUUM` og `ANALYZE` etter sletting

Anbefalt policy akkurat nå:
- behold råpunkter siste `90` dager
- bruk eksportfilene som langtidsarkiv
- kjør første gang som dry-run
- periodisk vedlikehold kjøres nå månedlig på Pi-en via `gps-prune.timer`

Eksempler:

```bash
# se hva som ville blitt slettet
python3 /home/johnny/mc-gps/scripts/prune_gps_db.py --days 90 --verbose

# faktisk sletting + databasevedlikehold
python3 /home/johnny/mc-gps/scripts/prune_gps_db.py --days 90 --apply --vacuum --analyze
```

## Nåværende begrensninger
- turdeteksjon er forbedret med 15 min lite-bevegelse-regel og enkel støyfiltrering, men er fortsatt heuristisk
- eksportstruktur bruker foreløpig flat `trips/`-mappe
- GPX er lagt til som eksportformat, men er foreløpig et enkelt sporformat uten ekstra waypoints/segmentmetadata
- interaktiv HTML-kartvisning publiseres nå via `sr500maps` på GitHub Pages
- publisert kartflate: `https://nasselang.github.io/sr500maps/`
- Telegram-/chat-flater er fortsatt best med bilde eller lenke, ikke rå lokal HTML-fil

## Naturlige neste steg
1. la agenten kunne dele både bilde og lenke til publisert interaktivt kart fra `sr500maps`
2. generere enkel turoppsummering der det er nyttig
3. vurdere direkte GPX-utlevering fra agent ved forespørsel
4. eventuelt legge til Telegram-flyt rundt dette
