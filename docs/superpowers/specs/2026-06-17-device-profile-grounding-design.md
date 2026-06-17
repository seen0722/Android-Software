# Design: Device Profile Grounding (L4) for Multi-SKU / Multi-Customer ODM

**Date:** 2026-06-17
**Status:** Draft for review
**Scope:** Android-Software hierarchical skill set
**Author:** brainstormed with the team lead (Qualcomm BSP / Android tablet ODM)

---

## 1. Problem

The skill set routes by AOSP path (Path as Truth) through `L1 → L2 → L3`. It has no
notion of **a specific product/board**. An ODM ships one hardware design as many
**SKUs** that diverge along several orthogonal axes:

- **HW**: panel, modem, touch, sensors.
- **Distribution**: GMS vs CN (whether GMS packages are integrated; decided by branch).
- **Android OS version**: A15, A16 … (different GKI branch, manifest, behavior).
- **Brand customer**: e.g. Datalogic, Trimble — each with its **own** branch-naming
  convention, version numbering, Android system properties, SKU encoding, delivery
  branch, and certification ownership.

Critically, for each **(customer × product × dist × OS version)** combination, the
**GitLab source location, `repo` manifest, branch, and build script can all differ**.
The same logical path (`device/qcom/kalama/`) can live in a different repo / manifest /
branch with different content per SKU. So **a correct path is necessary but not
sufficient** — it is only meaningful inside the confirmed (repo, manifest, branch, sync
state). Before analyzing a problem or proposing a fix, the agent must **confirm the
actual source-control state matches the active SKU**.

We want the agent to (a) **answer device fact lookups** ("what SoC / panel / branch /
manifest does product X SKU Y use?") and (b) **ground subsystem answers** in the real
facts and the confirmed source state of the active board — extending the anti-
hallucination mission from "the right path" to "this actual board, this SKU, this
customer, in the confirmed source state".

## 2. Decision summary

1. **Facts live as DATA**, not skills: a new top-level `devices/` store using **layered
   composition** (`base` + `os` + `hw` + `dist` + `customer` fragments) so an
   N×M×K SKU matrix does not duplicate shared facts (DRY).
2. **Method lives in ONE generic skill**: a new `L4-device-grounding-expert`
   (product/customer-agnostic, paged on demand). It resolves the effective profile,
   applies the active customer's governance, enforces isolation/red-line Forbidden
   Actions, and **gates on source-state verification**. **Never one skill per product or
   per customer** — divergence is data-driven, the method is generic.
3. **Resolution is a script**: `resolve_device.py` merges layers into an effective
   profile (including **source coordinates**: manifest repo/file/revision, working
   branch, build script) and is **convention-driven** — it parses branch/SKU/version
   using the active customer's declared patterns. Declarative patterns by default, with
   an optional per-customer `resolver_hook` escape hatch for irregular schemes.
4. **Source State as Truth (hard precondition)**: a correct path is necessary but not
   sufficient. Before any analysis or proposed solution, the agent must confirm the
   actual synced source (repo / manifest / branch / HEAD) matches the resolved
   coordinates, and that the path exists *in that tree*. Mismatch or uncertainty → stop
   and report, never guess. See §7.
5. **Layer gradient**: `L1 (always-on) → L4 (device grounding + source verification,
   on-demand) → L2/L3 (subsystem, on-demand)`. Pure lookups terminate at L4; grounded
   subsystem tasks page L4 + the subsystem expert.

### Approaches considered (and why C/L4 won)

- **A — pure data store, grounding folded into L1.** Keeps paging minimal but bloats the
  always-on router; weak home for customer **governance** and source-verification reasoning.
- **B — one L3 skill per product.** Reuses machinery but causes matrix explosion, breaks
  the L3 "single L2 parent" invariant (a device is cross-subsystem), and double-pages.
- **C / L4 — data + one generic L4 method skill (chosen).** The customer axis brings
  governance reasoning (delivery branches, cert ownership, NDA isolation), convention
  schemas, and source-state verification — that is skill-shaped, too heavy for an L1
  section. A single generic L4 keeps L1 lean, keeps facts DRY in data, and fits the
  L2→L3→L4 specificity gradient.

## 3. Architecture

```
L1-aosp-root-router (always loaded)
  · existing intent → path routing
  · NEW: detect device-context cues (product/SKU/variant/branch/build-option/HW/customer)
        → if present, page L4
  │
L4-device-grounding-expert (on demand, generic, single)
  · calls scripts/resolve_device.py → effective profile (base+os+hw+dist+customer merged)
        incl. source coordinates (manifest repo/file/revision, branch, build script)
  · SOURCE STATE VERIFICATION: confirm synced repo/manifest/branch/HEAD == resolved coords
        and that the path exists in that tree; on mismatch → STOP and report
  · applies the ACTIVE customer's conventions + governance (from data)
  · enforces isolation + red-line Forbidden Actions
  · emits a [Profile] + [Source/State] grounding header
  │
L2 / L3 subsystem expert (on demand)
  · answers using the injected effective profile + VERIFIED source state
```

- **Pure device lookup** → answered at L4 from the resolved profile/registry; terminal.
- **Grounded subsystem task** → L4 resolves + verifies source state + grounds, then hands
  to the single relevant L2/L3.

## 3.1 Runtime flow (execution order ≠ specificity)

**IMPORTANT — layer number and execution order are different things:**

- **Specificity gradient (naming):** `L1 → L2 → L3 → L4`, increasingly specific
  (router → subsystem → vendor → product/SKU).
- **Execution order (runtime):** `L1 → L4 → L2 → L3`. L4 has the highest number yet runs
  early, because grounding must precede subsystem reasoning.

```
                          USER TASK
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │ L1  aosp-root-router        (ALWAYS loaded)  │
        │  • parse intent                              │
        │  • Device Context Detection                  │
        │  • subsystem intent → AOSP path              │
        └───────┬───────────────────────────┬──────────┘
         device │ yes                         │ no device cue
           cue? ▼                             │
        ┌──────────────────────────────┐     │
        │ L4  device-grounding-expert   │     │
        │  1) resolve_device.py         │     │
        │     merge base+os+hw+dist+cust│     │
        │  2) VERIFY source state ──────┼──► MISMATCH / UNVERIFIED
        │     repo/manifest/branch/HEAD │       └─► STOP, report / ask user
        │  3) apply customer governance │           (never reason on wrong source)
        │     + isolation / red lines   │     │
        │  4) emit [Profile][Source][State]   │
        └───────┬───────────────────────┘     │
         pure   │ yes ─► ANSWER (terminal, no L2/L3)
         lookup?▼ grounded                     │
        ┌─────────────────────────────────────▼────────┐
        │ Subsystem routing (priority order)            │
        │ Security>Build>HAL>Framework>Init>...>Kernel  │
        └───────┬───────────────────────────────────────┘
                ▼
        ┌──────────────────────┐  escalate (parent_skill) ┌──────────────────────┐
        │ L2 subsystem expert  │ ───────────────────────► │ L3 vendor expert      │
        │  (kernel-gki …)      │ ◄──────── hand back ──────│  (qualcomm-kernel)    │
        └───────┬──────────────┘                          └──────────┬────────────┘
                │  both consume the [Profile]/[State] grounding header│
                └───────────────────────┬─────────────────────────────┘
                                         ▼
                                      ANSWER
```

**Cross-layer handling:**

1. **L1 → L4 (detect-then-page):** L1 pages L4 only when a device cue is present
   (product/SKU/branch/build-option/HW/customer); otherwise it skips L4 (`L1 → L2 → L3`),
   so generic AOSP tasks pay no grounding cost.
2. **L4 gate:** `resolve_device.py` then `verify_source_state.py`. If `State` is not
   VERIFIED, L4 STOPS (report / ask) — `Source State as Truth`.
3. **Grounding header, not re-paging:** L4 writes `[Profile]/[Source]/[State]` into the
   decision header; downstream L2/L3 READ it (they do not re-page L4). A device task pages
   at most **L4 + one subsystem expert** (never three).
4. **L2 → L3 (single-parent escalation):** subsystem routing hits L2 first; on vendor
   specifics (e.g. `codename=kalama`, qcom paths/symbols) L2 escalates to its `parent_skill`
   L3, handing back when out of vendor scope. One L3 extends exactly one L2 parent.
5. **Handoff markers:** `[L1 ROUTING DECISION]` → `[L4 DEVICE → GROUNDING]` →
   `[L2 <x> → HANDOFF]` → `[L3 → HANDOFF]`.
6. **Priority + red lines across layers:** multi-subsystem conflicts use the existing
   priority order; L4 isolation / red lines (NDA, delivery branch, cert) take precedence
   over any subsystem action.

## 4. Directory structure

```
Android-Software/
├── devices/                              # NEW — data (facts), version-controlled
│   ├── index.json                        # registry: products + SKUs + default_sku
│   ├── schema.md                         # field definitions for humans + validator
│   └── <product>/                        # e.g. tab-atlas
│       ├── base.yaml                     # shared product-line facts + default source coords
│       ├── os/                           # Android OS version axis fragments
│       │   ├── a15.yaml
│       │   └── a16.yaml
│       ├── hw/                           # HW axis fragments
│       │   ├── panel-boe.yaml
│       │   ├── panel-ofilm.yaml
│       │   └── modem-x75.yaml
│       ├── dist/                         # distribution axis fragments
│       │   ├── gms.yaml
│       │   └── cn.yaml
│       ├── customer/                     # brand-customer axis fragments (conventions+source+governance)
│       │   ├── datalogic.yaml
│       │   └── trimble.yaml
│       └── skus/                         # thin recipes: which layers + branch mapping
│           └── <sku-id>.yaml
├── scripts/                              # alongside detect_dirty_pages.py etc.
│   ├── resolve_device.py                 # NEW — merge layers → effective profile (+ source coords)
│   ├── validate_device_profile.py        # NEW — schema + convention + source-coord validation
│   └── verify_source_state.py            # NEW — synced tree state vs resolved coords (runs in eng env)
└── skills/
    └── L4-device-grounding-expert/       # NEW — the only new skill (generic)
        ├── SKILL.md
        └── references/
            └── device_grounding_model.md
```

`devices/` is a new top-level directory; the repo `.gitignore` uses a whitelist, so add
`!devices/` (and, if the spec is to be tracked, `!docs/`).

## 5. Data model — layered composition

`effective_profile = deep_merge(base, os_fragment, hw_fragments…, dist_fragment,
customer_fragment)`, applied in recipe order. Maps deep-merge; scalars overridden by
later layers; explicit removal via `null`. SKU recipes are thin. **Source coordinates**
can appear in any layer and merge like everything else (e.g. base default → os override →
customer override).

### base.yaml (shared facts + default source coords)

```yaml
product: tab-atlas
soc: { vendor: qualcomm, codename: kalama, model: SM8650 }  # codename → L3-qualcomm SoC table
kernel: { gki_branch: android14-6.1, page_size: 4k }
android_version: "16"
board_paths: { device_config: device/qcom/kalama/, vendor_root: vendor/qcom/ }
partitions: { scheme: ab, layout: gpt }
components: { wifi: wcn7850, modem: none }
source:                                   # default source-control coordinates
  manifest_repo: "git@gitlab.example.com:atlas/manifest.git"
  manifest_file: "atlas.xml"
  build_script:  "build/atlas.sh"
freshness: { last_verified: "2026-06-17", status: fresh }
```

### os/a16.yaml (OS-version axis — may override source/branch)

```yaml
layer: os/a16
android_version: "16"
kernel: { gki_branch: android14-6.1 }
source: { manifest_file: "atlas_a16.xml" }   # A16 uses a different manifest
```

### customer/datalogic.yaml (conventions + source + governance + properties)

```yaml
layer: customer/datalogic
customer: datalogic
isolation_group: datalogic
conventions:
  branch_pattern: "DL_{product}_{androidver}_{sku}"   # customer branch naming
  sku_encoding:   "DL-{hw}-{dist}"                     # customer SKU encoding
  version_scheme: "{cust_major}.{cust_minor}.{odm_build}"
  # resolver_hook: datalogic_custom                    # optional escape hatch (irregular only)
source:                                                # customer-specific source location + fetch
  manifest_repo:   "git@gitlab.example.com:datalogic/atlas-manifest.git"
  gitlab_location: "gitlab.example.com/datalogic/atlas/*"   # where this customer's repos live
  fetch:                                                 # HOW to fetch (commands only — NO secrets)
    method: repo                                         # repo | git | custom
    init:   "repo init -u {manifest_repo} -b {branch} -m {manifest_file}"
    sync:   "repo sync -j8"
    workspace_hint: "~/work/atlas-dl"
    # fetch_ref: references/fetch/datalogic.md           # optional: irregular procedure doc
  build_script:    "build/dl/atlas_dl.sh"
properties:                                            # customer Android system properties
  ro.product.manufacturer: Datalogic
  ro.product.model:        "{model}"
  ro.datalogic.sku:        "{variant_code}"
governance:
  delivery_branch: "DL_atlas_A16_*"                    # RED LINE (customer delivery branch)
  cert_owner: customer                                 # GTS account owned by customer
  approval_gate: customer-signoff
```

### skus/<sku-id>.yaml (recipe + branch mapping)

```yaml
sku: atlas-lte-ofilm-cn-dl
layers: [base, os/a16, hw/panel-ofilm, hw/modem-x75, dist/cn, customer/datalogic]
resolves_from:
  branch: "DL_atlas_A16_lte-ofilm-cn"                  # also the manifest revision
  build_option: "TARGET_PRODUCT=atlas_lte_cn_dl"
freshness: { last_verified: "2026-06-12", status: fresh }
```

A new customer (Trimble), OS version, or HW/dist option is **one new fragment**, not a
full new SKU file set — the matrix stays DRY.

## 6. Resolution — `resolve_device.py` (convention-driven, generic)

Active-SKU selection priority (reuses L1 Path Discipline — never guess):

1. Task names the SKU id / `variant_code` → use it.
2. Task names a branch or build option → parse it with the **active customer's**
   `branch_pattern` / `sku_encoding` to recover (product, os, hw, dist, customer).
3. Only the product line is named → use `index.json` `default_sku`, and state the
   assumption explicitly.
4. Ambiguous → ask the user.

The resolver is generic; per-customer behavior comes from the declared `conventions`.
Output: a merged effective-profile JSON — including the resolved **source coordinates**
(`manifest_repo`, `manifest_file`, `manifest_revision`/`working_branch`, `build_script`) —
consumed by source-state verification, L4, and downstream experts.

## 7. Source State Verification (hard precondition)

**A correct path is necessary but NOT sufficient.** The same path can exist in different
repos / manifests / branches with different content per SKU. Before *any* problem
analysis or proposed solution, L4 MUST verify the source state:

1. **Resolve** source coordinates from the effective profile (§6).
2. **Confirm actual state**: obtain the real synced state — `repo manifest -r`, the
   manifest project/revision, and `git -C <path> rev-parse --abbrev-ref HEAD` / commit —
   either by running the commands or by asking the user when the agent has no access to
   the GitLab tree. **Never assume the sync state.**
3. **Match**: the synced manifest / branch / HEAD must equal the resolved coordinates.
4. **Path-in-tree**: the path must exist *in that synced tree* (`read_file`), not merely
   "look like" a valid AOSP path.
5. **On mismatch or uncertainty → STOP and report the discrepancy.** Do not analyze or
   propose a fix against an unverified or mismatched source state.
6. **Make the stop actionable**: when the tree is missing or wrong, L4 emits the exact
   **fetch/sync commands for THIS SKU** (rendered from `source.fetch` + `gitlab_location`),
   so the user can obtain the correct tree. "Ask, don't assume" becomes "here is how to
   fetch the right code". Fetch coordinates differ per customer — never fetch one customer's
   tree using another customer's coordinates, and never embed credentials/tokens (auth is
   the engineer's environment).

This is `Source State as Truth` layered on top of `Path as Truth`. The verification
outcome (VERIFIED / UNVERIFIED / MISMATCH) is carried in the grounding header (§8) so the
downstream subsystem expert never reasons on an unconfirmed tree.

## 8. Routing integration

L1 gains a **Device Context Detection** step (before subsystem routing) and an augmented
decision block:

```
[L1 ROUTING DECISION]
Device:  tab-atlas / sku=atlas-lte-ofilm-cn-dl  (resolved via branch DL_atlas_A16_lte-ofilm-cn)
Profile: SoC=kalama(SM8650) GKI=android14-6.1 panel=ofilm dist=cn(GMS=no) customer=datalogic
Source:  manifest=atlas_a16.xml@DL_atlas_A16_lte-ofilm-cn  build=build/dl/atlas_dl.sh
State:   UNVERIFIED → confirm synced repo/branch/HEAD before analysis or solution
Intent:  panel driver crash analysis
Path(s): vendor/qcom/opensource/..., device/qcom/kalama/
L2/L3 Skill: L3-qualcomm-kernel-expert (parent: L2-kernel-gki-expert)
Reason:  profile.codename=kalama → QC kernel L3; panel=ofilm needs this SKU's DT
[END ROUTING → verify source state, then ground + load skill]
```

The `Device` / `Profile` / `Source` / `State` lines are the grounding header consumed by
the subsystem expert. A subsystem expert must refuse to proceed while `State` is not
VERIFIED.

## 9. `L4-device-grounding-expert` responsibilities + Forbidden Actions

Responsibilities: resolve the effective profile (via script), **verify source state**
(§7), apply the active customer's conventions/governance, surface device facts for
lookups, and emit the grounding header / handoff to the subsystem expert.

Forbidden Actions (≥5; `skill_lint.py` enforced):

1. **Analyze or propose against unverified/mismatched source state:** forbidden. Path-correct
   is not source-correct — confirm repo/manifest/branch/HEAD first, or stop and report.
2. **Cross-customer NDA isolation (strongest):** never reference or leak one
   `isolation_group`'s facts/branding/properties/source into another customer's answer.
3. **Customer delivery/release branch = hard stop:** on detecting `governance.delivery_branch`,
   stop and ask before any change (user red line).
4. **Certification ownership:** when `cert_owner: customer`, treat CTS/GTS/GMS settings as
   read-only; confirm before touching (user red line).
5. **No cross-SKU / cross-OS contamination:** never apply one SKU's or OS version's
   facts / manifest / branch / build script to another.
6. **Resolve with the active customer's conventions only:** never parse a Datalogic branch
   with Trimble's pattern (or vice versa).
7. **Never assume an undocumented HW component / property / source coordinate:** if not in
   the profile, report "not defined", do not invent.
8. **`status: dirty` profiles are not authoritative:** flag the SKU profile as
   pending-verification before answering.
9. **Never store, echo, or hard-code GitLab credentials/tokens:** `source.fetch` carries
   locations and commands only; authentication is the engineer's environment. Never fetch
   with another customer's coordinates (cross-customer fetch = isolation breach).

## 10. Freshness

Each `base`/fragment/SKU carries `freshness: { last_verified, status, reason? }`. Device
profiles go stale for **different reasons** than skills (HW respin, re-source, branch /
manifest change vs Android version bump), so this is **separate from**
`memory/dirty_pages.json` and validated by `validate_device_profile.py`. L4 must not treat
`dirty` facts as authoritative (Forbidden Action 8).

## 11. Validation & testing

- **`validate_device_profile.py`**: required fields present; recipe layers resolve to real
  fragment files; no orphan overrides; `branch_pattern`/`sku_encoding` well-formed; each
  `skus/*.yaml` `resolves_from.branch` actually parses under its customer's pattern; every
  resolvable SKU has complete **source coordinates** (`manifest_repo`, `manifest_file`,
  `manifest_revision`/`working_branch`, `build_script`, and **fetch coordinates**
  (`gitlab_location`, `source.fetch.method`/`init`/`sync`); no credentials/tokens present
  in any profile; `codename` ↔ `gki_branch` consistent with the L3-qualcomm SoC table.
- **`verify_source_state.py`**: given a synced tree, compares `repo`/`git` manifest,
  branch, and HEAD against the resolved coordinates; emits VERIFIED / UNVERIFIED /
  MISMATCH. Runs in the engineer's environment; the agent invokes it or asks the user to.
- **`resolve_device.py` unit tests**: layer merge correctness; override/null removal;
  branch/build-option → SKU resolution per customer convention; ambiguity → no guess.
- **Routing eval integration**: extend `tests/routing_accuracy` with device-context cases
  (e.g. "on Atlas LTE CN Datalogic the panel driver…" → resolves SKU + verifies state +
  grounds + routes to the right L2/L3). Composes with the existing `grading.py` /
  `llm_runner.py` Layer-A harness; a later Layer-B eval scores grounding-fact correctness,
  source-state gating, and cross-customer isolation (a leak = hard fail).
- **`skill_lint.py`**: applies to `L4-device-grounding-expert/SKILL.md` (frontmatter,
  required sections, ≥5 Forbidden Actions).

## 12. Composition with existing skills

- `soc.codename` → existing `L3-qualcomm-kernel-expert` SoC table (kalama → SM8650 →
  android14-6.1). L4 says "this board is kalama"; L3-qualcomm supplies the kernel know-how.
- Android system property questions → ground with the customer's `properties`, hand to
  `L2-init-boot-sequence-expert` (property_service).
- Version numbering / compatibility / OS migration → `L2-version-migration-expert`.
- Build script / manifest / Soong questions → `L2-build-system-expert`.
- SKU/branch encoding + source coordinates → resolver + verification.

## 13. Phasing

1. **Data + resolver**: `devices/` schema (incl. `os/` + `source` coords), one real
   product with 2 SKUs across 2 customers, `resolve_device.py`, `validate_device_profile.py`.
   Verifiable without the LLM.
2. **Source verification**: `verify_source_state.py` + the §7 gate.
3. **L4 skill**: `L4-device-grounding-expert/SKILL.md` + Forbidden Actions; pass `skill_lint`.
4. **L1 integration**: Device Context Detection + augmented decision block (incl. Source/State).
5. **Eval**: device-context routing + source-gating cases in `tests/routing_accuracy`;
   later Layer-B grounding + isolation eval.

## 14. Risks & open questions

- **Agent lacks direct GitLab access:** verification then depends on running `repo`/`git`
  locally or asking the user; the gate must degrade to "ask, do not assume", never to
  "skip".
- **Resolver regularity (assumption):** declarative patterns + optional `resolver_hook`.
  If a real customer scheme proves irregular, the hook absorbs it; revisit if hooks
  proliferate.
- **L1 growth:** Device Context Detection adds to the always-on router; kept to a compact
  detection + short-circuit when no device cue is present.
- **Two pages for grounded tasks:** L4 + subsystem expert. Accepted; justified by the
  governance + source-verification weight of the customer axis.
- **NDA isolation correctness:** cross-customer leakage is the highest-severity failure;
  must be a hard-fail eval case, not just a Forbidden Action in prose.
- **Spec/data drift:** convention descriptors and source coordinates in data must stay in
  sync with the real GitLab layout; `validate_device_profile.py` + `verify_source_state.py`
  are the guardrails.
