# Device Grounding Model

`Path as Truth` → `Source State as Truth`: a correct path is necessary but not
sufficient; it is only meaningful inside a confirmed (repo, manifest, branch, sync state).

- **Layered composition:** `effective = deep_merge(base, os, hw…, dist, customer)`.
  Divergence (HW, GMS/CN, customer conventions, source location) lives in DATA; this skill
  is the generic method.
- **Resolution priority:** explicit sku → branch/build_option → product default (state it)
  → ambiguous = ask.
- **Verification gate:** never reason on an unconfirmed tree; when wrong/missing, emit the
  per-SKU fetch hint so the user can sync the correct code.
- **Isolation:** `isolation_group` is the NDA boundary; never cross customers.
