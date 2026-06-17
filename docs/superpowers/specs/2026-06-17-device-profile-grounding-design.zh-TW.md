# 設計：Device Profile Grounding（L4）——多 SKU／多客戶 ODM

**日期：** 2026-06-17
**狀態：** 草案待 review
**範圍：** Android-Software 階層式 skill set
**作者：** 與團隊主管腦力激盪（Qualcomm BSP／Android 平板 ODM）

> 本文為英文版 `2026-06-17-device-profile-grounding-design.md` 的繁體中文對照版本，內容一致。技術術語、程式碼、路徑保留原文。

---

## 1. 問題

目前 skill set 以 AOSP 路徑路由（Path as Truth），走 `L1 → L2 → L3`，但**完全沒有「特定產品／板子」的概念**。ODM 把同一套硬體設計出貨成許多 **SKU**，沿多個正交軸分歧：

- **HW**：面板（panel）、modem、觸控（touch）、sensor。
- **Distribution**：GMS vs CN（是否整合 GMS packages；由 branch 決定）。
- **Android OS version**：A15、A16…（不同的 GKI branch、manifest、行為）。
- **品牌客戶（Brand customer）**：例如 Datalogic、Trimble——各自有**自己的** branch 命名慣例、版本號規則、Android system property、SKU 編碼、交付分支、認證歸屬。

關鍵在於：對每個 **(客戶 × 產品 × dist × OS version)** 組合，**GitLab source 存放位置、`repo` manifest、branch、build script 都可能不同**。同一條邏輯 path（`device/qcom/kalama/`）在不同 SKU 下可能位於不同的 repo／manifest／branch、內容也不同。所以**路徑正確是「必要但不充分」**——它只有在「**正確的 repo + manifest + branch + 已確認的 sync 狀態**」之內才有意義。在分析問題或提解法之前，agent 必須**先確認實際 source-control 狀態與 active SKU 一致**。

我們要讓 agent 能夠：(a) **回答 device 事實查詢**（「產品 X 的 SKU Y 用哪顆 SoC／面板／branch／manifest？」）；(b) **用 active 板子的真實事實與已確認的 source 狀態 grounding 子系統回答**——把防幻覺的使命從「正確的路徑」延伸到「這塊實際板子、這個 SKU、這個客戶、在已確認的 source 狀態下」。

## 2. 決策摘要

1. **facts 以 DATA 形式存在**，不是 skill：新增 top-level `devices/` 事實庫，採**分層組合**（`base` + `os` + `hw` + `dist` + `customer` fragment），讓 N×M×K 的 SKU 矩陣不重複共用事實（DRY）。
2. **method 放在唯一一個通用 skill**：新增 `L4-device-grounding-expert`（product/customer-agnostic、on-demand paging）。它解析有效 profile、套用 active 客戶的治理規則、強制隔離與紅線 Forbidden Actions，並**以 source-state 驗證為前提閘門**。**絕不做 per-product 或 per-customer**——divergence 由資料驅動，method 維持通用。
3. **解析是腳本**：`resolve_device.py` 把分層合併成有效 profile（含 **source coordinates**：manifest repo/檔/revision、working branch、build script），且是**慣例驅動**——用 active 客戶宣告的 pattern 解析 branch/SKU/version。預設宣告式 pattern，另有可選的 per-customer `resolver_hook` 逃生口。
4. **Source State as Truth（硬前提）**：路徑正確是必要但不充分。在任何分析或提解法之前，agent 必須確認實際 synced source（repo／manifest／branch／HEAD）與解析出的座標一致，且 path 確實存在於**那棵樹**裡。不一致或不確定 → 停下來回報，絕不臆測。見 §7。
5. **層級梯度**：`L1（always-on）→ L4（device grounding + source 驗證，on-demand）→ L2/L3（subsystem，on-demand）`。純查詢在 L4 終止；grounded 子系統任務 page L4 + 子系統 expert。

### 考慮過的方案（以及為何 C/L4 勝出）

- **A — 純資料庫，grounding 折進 L1。** paging 最省，但會養肥永遠在線的 router；對客戶**治理**與 source 驗證推理而言是不夠好的家。
- **B — 每產品一個 L3 skill。** 複用既有機制，但造成矩陣爆炸、破壞 L3「單一 L2 parent」不變式（device 是跨子系統的）、且雙重 paging。
- **C / L4 — 資料 + 一個通用 L4 method skill（採用）。** 客戶軸帶來治理推理（交付分支、認證歸屬、NDA 隔離）、慣例 schema、與 source-state 驗證——這是 skill 形狀的東西，塞進 L1 一小段太重。單一通用 L4 讓 L1 維持精簡、facts 維持 DRY，且契合 L2→L3→L4 的特化梯度。

## 3. 架構

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

- **純 device 查詢** → 在 L4 用解析出的 profile/registry 回答；終止。
- **grounded 子系統任務** → L4 解析 + 驗證 source 狀態 + grounding，再交給唯一相關的 L2/L3。

## 3.1 Runtime flow（執行順序 ≠ 特化程度）

**關鍵——層級編號與執行順序是兩回事：**

- **特化梯度（命名）：** `L1 → L2 → L3 → L4`，越來越具體（router → 子系統 → vendor → 產品/SKU）。
- **執行順序（runtime）：** `L1 → L4 → L2 → L3`。L4 編號最大卻執行得早，因為 grounding 必須在子系統推理之前完成。

```
                          USER TASK
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │ L1  aosp-root-router        (ALWAYS loaded)  │
        │  • 解析意圖                                   │
        │  • Device Context Detection（偵測 device 線索）│
        │  • 子系統意圖 → AOSP path                      │
        └───────┬───────────────────────────┬──────────┘
         device │ 有                          │ 無 device 線索
          線索? ▼                             │
        ┌──────────────────────────────┐     │
        │ L4  device-grounding-expert   │     │
        │  1) resolve_device.py         │     │
        │     合併 base+os+hw+dist+cust │     │
        │  2) VERIFY source state ──────┼──► MISMATCH / UNVERIFIED
        │     repo/manifest/branch/HEAD │       └─► STOP，回報／問使用者
        │  3) 套客戶治理                 │           （絕不在錯誤 source 上推理）
        │     + 隔離 / 紅線              │     │
        │  4) emit [Profile][Source][State]   │
        └───────┬───────────────────────┘     │
         純查詢? │ 是 ─► ANSWER（終止，不進 L2/L3）
         grounded▼                             │
        ┌─────────────────────────────────────▼────────┐
        │ 子系統路由（priority order）                   │
        │ Security>Build>HAL>Framework>Init>...>Kernel  │
        └───────┬───────────────────────────────────────┘
                ▼
        ┌──────────────────────┐  escalate (parent_skill) ┌──────────────────────┐
        │ L2 subsystem expert  │ ───────────────────────► │ L3 vendor expert      │
        │  (kernel-gki …)      │ ◄──────── hand back ──────│  (qualcomm-kernel)    │
        └───────┬──────────────┘                          └──────────┬────────────┘
                │  兩者都吃 L4 注入的 [Profile]/[State] 標頭          │
                └───────────────────────┬─────────────────────────────┘
                                         ▼
                                      ANSWER
```

**跨 layer 處理：**

1. **L1 → L4（偵測即 page）：** 只有偵測到 device 線索（產品/SKU/branch/build-option/HW/客戶）才 page L4；否則跳過（`L1 → L2 → L3`），一般 AOSP 任務不付 grounding 成本。
2. **L4 閘門：** 先 `resolve_device.py` 再 `verify_source_state.py`。`State` 非 VERIFIED 即 STOP（回報／問）——`Source State as Truth`。
3. **注入標頭、不重新 page：** L4 把 `[Profile]/[Source]/[State]` 寫進決策標頭，下游 L2/L3 只「讀」它（不重新 page L4）。device 任務最多 page **L4 + 一個子系統 expert**（不會三頁）。
4. **L2 → L3（單一 parent 升級）：** 子系統路由先到 L2；遇 vendor 特化（如 `codename=kalama`、qcom 路徑/符號）依 `parent_skill` 升級到 L3，出 vendor 範圍再交回。一個 L3 只 extends 一個 L2 parent。
5. **handoff marker：** `[L1 ROUTING DECISION]` → `[L4 DEVICE → GROUNDING]` → `[L2 <x> → HANDOFF]` → `[L3 → HANDOFF]`。
6. **跨層優先序 + 紅線：** 多子系統衝突用既有 priority order；L4 的隔離／紅線（NDA、交付分支、認證）先於任何子系統動作。

## 4. 目錄結構

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

`devices/` 是新的 top-level 目錄；repo 的 `.gitignore` 採白名單模式，因此要加 `!devices/`（若這份 spec 也要追蹤，再加 `!docs/`）。

## 5. 資料模型——分層組合

`effective_profile = deep_merge(base, os_fragment, hw_fragments…, dist_fragment, customer_fragment)`，依 recipe 順序套用。map 深層合併；scalar 由後面的 layer 覆蓋；顯式刪除用 `null`。SKU recipe 很薄。**source coordinates** 可出現在任一 layer 並如常合併（例如 base 預設 → os 覆蓋 → customer 覆蓋）。

### base.yaml（共用事實 + 預設 source coords）

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

### os/a16.yaml（OS 版本軸——可覆蓋 source/branch）

```yaml
layer: os/a16
android_version: "16"
kernel: { gki_branch: android14-6.1 }
source: { manifest_file: "atlas_a16.xml" }   # A16 uses a different manifest
```

### customer/datalogic.yaml（慣例 + source + 治理 + 屬性）

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

### skus/<sku-id>.yaml（recipe + branch 對映）

```yaml
sku: atlas-lte-ofilm-cn-dl
layers: [base, os/a16, hw/panel-ofilm, hw/modem-x75, dist/cn, customer/datalogic]
resolves_from:
  branch: "DL_atlas_A16_lte-ofilm-cn"                  # also the manifest revision
  build_option: "TARGET_PRODUCT=atlas_lte_cn_dl"
freshness: { last_verified: "2026-06-12", status: fresh }
```

新增一個客戶（Trimble）、OS 版本、或 HW/dist 選項，只是**一個新 fragment**，不是一整組新的 SKU 檔——矩陣維持 DRY。

## 6. 解析——`resolve_device.py`（慣例驅動、通用）

active SKU 選定優先序（複用 L1 Path Discipline——絕不臆測）：

1. 任務點名 SKU id／`variant_code` → 直接用。
2. 任務點名 branch 或 build option → 用 **active 客戶的** `branch_pattern`／`sku_encoding` 解析出 (product, os, hw, dist, customer)。
3. 只點名產品線 → 用 `index.json` 的 `default_sku`，並明確聲明此假設。
4. 歧義 → 問使用者。

resolver 本身通用；per-customer 行為來自宣告的 `conventions`。輸出：合併後的 effective-profile JSON——含解析出的 **source coordinates**（`manifest_repo`、`manifest_file`、`manifest_revision`/`working_branch`、`build_script`）——供 source-state 驗證、L4、與下游 expert 使用。

## 7. Source State Verification（硬前提）

**路徑正確是必要但「不充分」。** 同一條 path 在不同 SKU 下可能位於不同 repo／manifest／branch、內容不同。在做**任何**問題分析或提解法之前，L4 必須驗證 source 狀態：

1. **解析**：從有效 profile 取得 source coordinates（§6）。
2. **確認實際狀態**：取得真實 synced 狀態——`repo manifest -r`、manifest 的 project/revision、以及 `git -C <path> rev-parse --abbrev-ref HEAD`／commit——由 agent 執行指令，或在 agent 無法存取 GitLab 樹時請使用者提供。**絕不假設 sync 狀態。**
3. **比對**：synced 的 manifest／branch／HEAD 必須等於解析出的座標。
4. **path-in-tree**：path 必須存在於**那棵 synced 樹**裡（`read_file`），而不只是「看起來像」有效 AOSP path。
5. **不一致或不確定 → 停下來回報落差。** 不可在未驗證或不一致的 source 狀態上分析或提解法。
6. **讓「停」變成可行動**：當樹不存在或不對時，L4 直接給出**這個 SKU 的 fetch/sync 指令**（由 `source.fetch` + `gitlab_location` 算出），讓使用者能取得正確的樹。「問、不要假設」升級成「這是 fetch 正確 code 的方法」。fetch 座標因客戶而異——絕不拿某客戶的座標去 fetch 另一客戶的樹，也絕不內嵌 credentials/token（驗證由工程師環境負責）。

這就是疊在 `Path as Truth` 之上的 `Source State as Truth`。驗證結果（VERIFIED／UNVERIFIED／MISMATCH）會帶進 grounding 標頭（§8），讓下游子系統 expert 絕不在未確認的樹上推理。

## 8. 路由整合

L1 新增一個 **Device Context Detection** 步驟（在子系統路由之前），以及增修版決策區塊：

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

`Device`／`Profile`／`Source`／`State` 各行是 grounding 標頭，供子系統 expert 取用。當 `State` 不是 VERIFIED 時，子系統 expert 必須拒絕繼續。

## 9. `L4-device-grounding-expert` 職責 + Forbidden Actions

職責：解析有效 profile（透過腳本）、**驗證 source 狀態**（§7）、套用 active 客戶的慣例／治理、為查詢提供 device 事實、發出 grounding 標頭／handoff 給子系統 expert。

Forbidden Actions（≥5；由 `skill_lint.py` 強制）：

1. **在未驗證/不一致的 source 狀態上分析或提解法：** 禁止。path-correct 不等於 source-correct——先確認 repo/manifest/branch/HEAD，否則停下來回報。
2. **跨客戶 NDA 隔離（最強）：** 絕不把某 `isolation_group` 的事實／branding／屬性／source 引用或滲漏到另一客戶的回答。
3. **客戶交付/release branch = 硬停：** 偵測到 `governance.delivery_branch` 時，動任何更動前先停下來問（使用者紅線）。
4. **認證歸屬：** 當 `cert_owner: customer`，CTS/GTS/GMS 設定視為唯讀；更動前先確認（使用者紅線）。
5. **不可跨 SKU／跨 OS 污染：** 絕不把某 SKU 或某 OS 版本的事實／manifest／branch／build script 套到另一個。
6. **只用 active 客戶的慣例解析：** 絕不拿 Datalogic 的 pattern 去解析 Trimble 的 branch（反之亦然）。
7. **不可臆測未記載的 HW component／屬性／source 座標：** profile 沒寫就回報「未定義」，不要編。
8. **`status: dirty` 的 profile 非權威：** 作答前先標記該 SKU profile 為待驗證。
9. **絕不儲存、輸出或寫死 GitLab credentials/token：** `source.fetch` 只放位置與指令；驗證由工程師環境負責。絕不拿另一客戶的座標 fetch（跨客戶 fetch = 隔離破口）。

## 10. Freshness（新鮮度）

每個 `base`/fragment/SKU 帶 `freshness: { last_verified, status, reason? }`。device profile 變髒的**觸發點**與 skill 不同（HW respin、重新 source、換 branch／manifest vs Android 版本跳版），所以它與 `memory/dirty_pages.json` **分離**，由 `validate_device_profile.py` 檢查。L4 不可把 `dirty` 事實當權威（Forbidden Action 8）。

## 11. 驗證與測試

- **`validate_device_profile.py`：** 必填欄位齊全；recipe 的 layer 都對應到真實 fragment 檔；無孤兒 override；`branch_pattern`／`sku_encoding` 格式正確；每個 `skus/*.yaml` 的 `resolves_from.branch` 真的能被該客戶 pattern 解析；每個可解析的 SKU 都有完整 **source coordinates**（`manifest_repo`、`manifest_file`、`manifest_revision`/`working_branch`、`build_script`，以及 **fetch 座標** `gitlab_location`、`source.fetch.method`/`init`/`sync`）；任何 profile 都不含 credentials/token；`codename` ↔ `gki_branch` 與 L3-qualcomm SoC 表一致。
- **`verify_source_state.py`：** 給定一棵 synced 樹，比對 `repo`/`git` 的 manifest、branch、HEAD 與解析出的座標；輸出 VERIFIED／UNVERIFIED／MISMATCH。在工程師環境執行；agent 呼叫它或請使用者執行。
- **`resolve_device.py` 單元測試：** 分層合併正確性；override/null 移除；依客戶慣例做 branch/build-option → SKU 解析；歧義 → 不臆測。
- **Routing eval 整合：** 在 `tests/routing_accuracy` 增加 device-context 案例（例如「on Atlas LTE CN Datalogic the panel driver…」→ 解析 SKU + 驗證狀態 + grounding + 路由到正確 L2/L3）。與既有 `grading.py`／`llm_runner.py` Layer-A harness 組合；之後的 Layer-B eval 可評分 grounding 事實正確性、source-state 閘門、與跨客戶隔離（洩漏 = 硬失敗）。
- **`skill_lint.py`：** 套用於 `L4-device-grounding-expert/SKILL.md`（frontmatter、必備章節、≥5 Forbidden Actions）。

## 12. 與既有 skill 的組合

- `soc.codename` → 既有 `L3-qualcomm-kernel-expert` 的 SoC 表（kalama → SM8650 → android14-6.1）。L4 說「這台是 kalama」；L3-qualcomm 提供 kernel know-how。
- Android system property 問題 → 用客戶的 `properties` grounding，交 `L2-init-boot-sequence-expert`（property_service）。
- 版本號／相容性／OS migration → `L2-version-migration-expert`。
- build script／manifest／Soong 問題 → `L2-build-system-expert`。
- SKU/branch 編碼 + source 座標 → resolver + 驗證。

## 13. 分階段

1. **資料 + resolver：** `devices/` schema（含 `os/` + `source` 座標）、一個真實產品含跨 2 客戶的 2 個 SKU、`resolve_device.py`、`validate_device_profile.py`。無需 LLM 即可驗證。
2. **Source 驗證：** `verify_source_state.py` + §7 閘門。
3. **L4 skill：** `L4-device-grounding-expert/SKILL.md` + Forbidden Actions；通過 `skill_lint`。
4. **L1 整合：** Device Context Detection + 增修版決策區塊（含 Source/State）。
5. **Eval：** 在 `tests/routing_accuracy` 增加 device-context 路由 + source-gating 案例；之後做 Layer-B grounding + 隔離 eval。

## 14. 風險與待解問題

- **agent 無法直接存取 GitLab：** 驗證就得靠在本地跑 `repo`/`git` 或詢問使用者；閘門必須退化成「問，不要假設」，絕不退化成「跳過」。
- **resolver 規則性（假設）：** 宣告式 pattern + 可選 `resolver_hook`。若某真實客戶的 scheme 不規則，由 hook 吸收；若 hook 增生過多則重新檢討。
- **L1 變大：** Device Context Detection 加到永遠在線的 router；維持精簡偵測 + 無 device 線索時短路。
- **grounded 任務兩頁：** L4 + 子系統 expert。接受；由客戶軸的治理 + source 驗證份量正當化。
- **NDA 隔離正確性：** 跨客戶洩漏是最高嚴重度的失敗；必須是硬失敗的 eval 案例，而非只在 prose 裡的 Forbidden Action。
- **spec/資料漂移：** 資料裡的慣例描述器與 source 座標必須與真實 GitLab layout 同步；`validate_device_profile.py` + `verify_source_state.py` 是守門員。
