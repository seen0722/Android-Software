# Device Profile Schema

A profile is composed from layers via a SKU recipe:
`effective = deep_merge(base, os, hw…, dist, customer)`.

## Fragment keys
- `layer` (fragments only): identity string, e.g. `customer/datalogic`. Stripped on merge.
- `soc`: `{ vendor, codename, model }`. `codename` maps to the L3-qualcomm SoC table.
- `kernel`: `{ gki_branch, page_size }`.
- `components`: `{ panel, touch, modem, wifi, ... }`.
- `board_paths`, `partitions`, `android_version`, `distribution`, `gms`, `certification`, `properties`.
- `source`: `{ manifest_repo, manifest_file, gitlab_location, build_script, fetch }`.
  - `fetch`: `{ method, init, sync, workspace_hint }`. Commands only — NEVER credentials.
- `conventions` (customer): `{ branch_pattern, sku_encoding, version_scheme, resolver_hook? }`.
- `governance` (customer): `{ delivery_branch, cert_owner, approval_gate }`.
- `isolation_group` (customer): NDA isolation boundary.
- `freshness`: `{ last_verified, status: fresh|dirty, reason? }`.

## SKU recipe keys
- `sku`, `layers` (ordered), `resolves_from: { branch, build_option }`, `freshness`.
