---
name: device-grounding-expert
layer: L3
path_scope: devices/
version: 1.0.0
android_version_tested: Android 16
parent_skill: aosp-root-router
---

## Path Scope

| Path | Responsibility |
|------|---------------|
| `devices/` | Layered device/SKU/customer fact store (data) |
| `scripts/resolve_device.py` | Compose effective profile + resolve active SKU |
| `scripts/verify_source_state.py` | Confirm synced tree == resolved source coords |
| `scripts/validate_device_profile.py` | Schema/convention/no-secret validation |

## Trigger Conditions

Load (paged by L1) when a task carries a device cue: product/SKU/`variant_code`,
a branch or build option, a named HW component, or a brand customer (e.g. Datalogic,
Trimble). Runs after L1, before the subsystem L2/L3.

## Architecture Intelligence

Resolve the effective profile, then VERIFY source state, then ground:

1. `python3 scripts/resolve_device.py --branch <b>` (or `--sku/--build-option/--product`).
2. `python3 scripts/verify_source_state.py <tree> --profile <json>` → VERIFIED / MISMATCH / UNVERIFIED.
3. Emit the grounding header and hand to the subsystem expert (do not answer subsystem
   questions here). Layer merge = base + os + hw + dist + customer (later overrides earlier).

Grounding header:
```
[Profile] SoC=<codename>(<model>) GKI=<gki_branch> panel=<panel> dist=<distribution> customer=<customer>
[Source]  manifest=<manifest_file>@<branch>  build=<build_script>
[State]   VERIFIED | UNVERIFIED | MISMATCH
```
When State != VERIFIED, do not analyze or propose — emit the fetch hint and stop.

## Forbidden Actions

1. Analyze or propose a fix against an unverified or mismatched source state — forbidden;
   confirm repo/manifest/branch/HEAD first, or stop and report.
2. Cross-customer NDA isolation: never reference or leak one `isolation_group`'s
   facts/branding/properties/source into another customer's answer.
3. Customer delivery/release branch (`governance.delivery_branch`) = hard stop; ask first.
4. When `cert_owner: customer`, treat CTS/GTS/GMS settings as read-only; confirm first.
5. Never apply one SKU's or OS version's facts/manifest/branch/build script to another.
6. Parse branch/SKU only with the active customer's conventions (never cross-customer).
7. Never invent an undocumented HW component / property / source coordinate — report "not defined".
8. Never store, echo, or hard-code GitLab credentials/tokens, and never fetch with another
   customer's coordinates.

## Tool Calls

```bash
python3 scripts/resolve_device.py --branch <branch>
python3 scripts/resolve_device.py --sku <sku-id>
python3 scripts/verify_source_state.py <tree_path> --profile <profile.json>
python3 scripts/validate_device_profile.py
```

## Handoff Rules

| Condition | Emit | Target |
|-----------|------|--------|
| State VERIFIED, subsystem question | `[L4 DEVICE → GROUNDING]` | the relevant L2/L3 |
| State != VERIFIED | (emit fetch hint) | stop / ask user |
| Pure device-fact lookup | (answer from profile) | terminal |

## References

- `skills/L4-device-grounding-expert/references/device_grounding_model.md`
- `devices/schema.md`
- `docs/superpowers/specs/2026-06-17-device-profile-grounding-design.md`
