# Onboarding a Real Product Line into `devices/`

The data under `devices/` is currently **example/placeholder** (`tab-atlas`, fake
`gitlab.example.com` URLs, Datalogic/Trimble stubs). This guide walks you through adding
**one real product line** by copying the working example and replacing its values.

> **NDA note:** real GitLab URLs, delivery branches, SKU codes, and customer naming are
> internal. Fill them **locally** — do not paste them into agent chats. Keep this repo
> **private**. `validate_device_profile.py` rejects committed secrets, but it cannot judge
> what is NDA-sensitive — that is on you.

---

## Step 1 — Copy the working example as your starting point

```bash
cd Android-Software
cp -r devices/tab-atlas devices/<your-product-id>      # e.g. devices/halo-tab
```

`tab-atlas` already validates clean, so you are editing from a known-good shape.

## Step 2 — Replace values, file by file

Everything below currently holds example values. Replace each with your real value.
"RED LINE" marks fields that touch your hard-stop areas (delivery branches, certification).

### `devices/<product>/base.yaml` — shared facts
| Field | Replace with |
|---|---|
| `product` | your product id (match the directory name) |
| `soc.vendor` / `soc.codename` / `soc.model` | real SoC (e.g. `qualcomm` / `pineapple` / `SM8650`). The codename must exist in `SOC_GKI_TABLE` — see Step 6 |
| `kernel.gki_branch` / `kernel.page_size` | real GKI branch (e.g. `android15-6.6`), `4k` or `16k` |
| `android_version` | real OS version |
| `board_paths.device_config` / `vendor_root` | real paths (e.g. `device/qcom/<target>/`, `vendor/qcom/`) |
| `partitions` | real scheme/layout (`ab`/`virtual_ab`, `gpt`) |
| `components.wifi` / `.modem` | shared HW parts (override per-SKU in `hw/`) |
| `source.manifest_repo` / `.manifest_file` / `.build_script` | **default** GitLab manifest + build entry (per-customer override below) |
| `freshness` | today's date, `status: fresh` |

### `devices/<product>/os/*.yaml` — OS-version axis
One file per OS version you ship. Set `android_version`, `kernel.gki_branch`, and any
`source.manifest_file` that differs by OS. Rename files to your versions (`a15.yaml`, …).

### `devices/<product>/hw/*.yaml` — hardware axis
One fragment per swappable part. Put only the delta in `components`
(e.g. `panel: <real part no>`, `touch: ...`, `modem: ...`). Rename files to your parts.

### `devices/<product>/dist/{gms,cn}.yaml` — distribution axis
- `gms.integrated` (`true`/`false`), `gms.level`, `gms.package_config` (real partner GMS path)
- `certification.programs` (`[cts, gts, vts]` for GMS; drop `gts` for CN), `certification.status`

### `devices/<product>/customer/<name>.yaml` — **the sensitive ones** (one per brand)
Rename `datalogic.yaml` / `trimble.yaml` to your real customers and fill:
| Field | Replace with |
|---|---|
| `customer` / `isolation_group` | the customer key (isolation boundary — keep distinct per customer) |
| `conventions.branch_pattern` | the customer's **real** branch naming, e.g. `DL_{product}_{androidver}_{sku}` |
| `conventions.sku_encoding` / `version_scheme` | the customer's real SKU code + version scheme |
| `source.manifest_repo` / `gitlab_location` | the customer's **real GitLab** repo + group (NDA) |
| `source.fetch.init` / `.sync` / `.workspace_hint` | real fetch commands — **commands only, never tokens** |
| `source.build_script` | the customer's build entry |
| `properties` | the customer's `ro.*` system properties |
| `governance.delivery_branch` | **RED LINE** — the customer delivery/release branch (pattern ok) |
| `governance.cert_owner` | `odm` or `customer` — **RED LINE** if `customer` |
| `governance.approval_gate` | your sign-off gate |

### `devices/<product>/skus/*.yaml` — one recipe per shipped SKU
```yaml
sku: <your-sku-id>                 # per the customer's sku_encoding
layers: [base, os/<ver>, hw/<panel>, hw/<modem?>, dist/<gms|cn>, customer/<name>]
resolves_from:
  branch: "<REAL delivery/working branch>"        # how the agent resolves this SKU
  build_option: "TARGET_PRODUCT=<real>"
freshness: { last_verified: "<date>", status: fresh }
```
Name each file after its `sku`. Delete the example SKU files you don't use.

## Step 3 — Register the product in the index

Edit `devices/index.json` and add your product (keep or remove `tab-atlas`):
```json
{ "id": "<your-product-id>", "name": "<display name>",
  "default_sku": "<one of your sku ids>", "skus": ["<sku-a>", "<sku-b>"] }
```

## Step 4 — Validate (must be clean before use)

```bash
python3 scripts/validate_device_profile.py
```
Fix every reported error: missing layer files, missing `source` coords, a `resolves_from.branch`
that doesn't match the customer's `branch_pattern`, `codename`↔`gki_branch` mismatch, or any
detected secret.

## Step 5 — Smoke-test resolution

```bash
python3 scripts/resolve_device.py --branch "<a real branch you declared>"
python3 scripts/resolve_device.py --sku "<one of your sku ids>"
```
Confirm the merged profile shows the right SoC / panel / dist / customer.

## Step 6 — Add your SoC to the codename table (if needed)

If your `soc.codename` is not in `SOC_GKI_TABLE`, add it in
`scripts/validate_device_profile.py` so the `codename`↔`gki_branch` check works:
```python
SOC_GKI_TABLE = {
    ...,
    "<your-codename>": "<expected gki_branch>",
}
```

## Step 7 — (optional) Verify against a real synced tree

```bash
python3 scripts/verify_source_state.py /path/to/your/synced/tree \
    --profile <(python3 scripts/resolve_device.py --sku "<sku id>")
```
`VERIFIED` only when the tree's current branch equals the SKU's resolved branch; otherwise
`UNVERIFIED`/`MISMATCH` with a fetch hint. This is the `Source State as Truth` gate.

---

## Done when

- `validate_device_profile.py` is clean for your real product.
- `resolve_device.py` returns the correct profile for your real branches/SKUs.
- The example `tab-atlas` (and `gitlab.example.com` values) are removed or clearly marked as
  samples, so no fake data ships to real use.
