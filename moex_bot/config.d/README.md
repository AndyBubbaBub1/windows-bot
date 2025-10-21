# Fragmented configuration

Drop YAML files in this directory to override or extend the default
`config.yaml`.  Files are merged in alphabetical order.  Example
fragments:

- `strategies.yaml` — strategy bundle definitions.
- `schedule.yaml` — APScheduler jobs for automatic runs.
- `secrets.yaml` — placeholders for tokens/keys (do not commit real secrets).

All fragments included with the repository are safe defaults that
mirror the monolithic `config.yaml` so the application behaves exactly
the same when fragments are loaded.
