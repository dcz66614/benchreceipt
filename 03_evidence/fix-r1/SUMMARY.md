# P027 BenchReceipt FIX-R1 — 修复总结（P0-R1-01，fail-closed legacy path）

- 分支：`fix-r1`（自 `b1910e6` 起；仅含复现证据合并，无生产改动）
- 修复时间：2026-11-18 ~03:35–04:10 GMT
- 结论先行：**P0-R1-01 已关闭。** 删掉两个 after 字段的收据在 Python
  验证器与 Node Oracle 下均由 BOUND_PASS 变为 UNBOUND + `MISSING_FIELD`
  （jobs_verified 0，CLI exit 2）；原始 6 项测试与原始 e5/e6 收据的 UNBOUND
  判定不变；全量套件 848 通过；S0 PASS 10/10（52 夹具）。

## 1. 设计（协调员裁决：方案 A）

终审 R1 的 P0-R1-01：`git.head_sha_after` / `git.tree_sha_after`
两个可选字段都缺失时，旧 verifier 退回 dirty/digest 判定，而 clean-tree
HEAD 变化对 dirty/digest 不可见，于是 legacy 形状收据误判 BOUND_PASS。

上一轮工人正确 STOP 的原因（协调员已核对属实）：按原设计，e7（e5 删掉
两个 after 字段）与现有控制夹具 n01 的输入逐字段相同（收据 JSON、
policy.toml、expected.json 全部相同），而 Golden 要求 n01→BOUND_PASS、
e7→UNBOUND；verify 是输入的确定性函数，两者不可能输出不同。50 个夹具
里只有 e5/e6 带 after 字段，其余 48 个（make_receipt 默认不写）都没有。

协调员裁决采用**方案 A**：放弃“其余 50 个夹具 byte-identical”的旧约束，
改为让 builder 给全部现有夹具补上 after 字段。理由：v1.1.0 已让 capture
始终记录 after 字段，合成夹具应模拟当前 capture 的输出；48 个夹具缺
after 字段只是 v1.1.0 修复时没更新 builder 默认值的遗留，不是语义选择。
ADR-005 决策 4 的旧兼容规则正是 R1 否决的规则，ADR-007 明确写明推翻它。

修复规则（SPEC_VERSION 1.1.0 → 1.2.0）：

- 两个 after 字段都缺失 → 该收据无法证明运行中无 clean-tree HEAD 变化，
  不得 BOUND_PASS：状态 UNBOUND，reason code 复用已冻结的 `MISSING_FIELD`
  （UNBOUND 类），该 job jobs_verified 0，CLI exit 2。
- 只出现其一仍按现有规则判 `SOURCE_MUTATED_DURING_RUN`，不动。
- Schema 里两个 after 字段保持 optional（旧格式收据仍可解析，得 UNBOUND
  而非 INVALID），只改 description 文字说明 fail-closed 规则。
- Python 与 Oracle 的 `MISSING_FIELD` 消息模板逐字一致：
  `missing git.head_sha_after and git.tree_sha_after`（冻结于
  `docs/REASON_CODES.md`）。
- 新夹具 e7/e8（S0 50 → 52，legacy 形状不变）；Golden 只追加两条手写
  entry，不改任何已有 Golden 值。

## 2. 改动文件清单

生产代码：

- `02_source/src/benchreceipt/verify.py` — §5.5 fail-closed：两字段皆无时
  加 `MISSING_FIELD` + 对应 report_error、job_ok=False；模块 docstring 与
  注释同步（旧兼容规则描述删除）。
- `02_source/oracle/verify.mjs` — 约 1444–1475 行镜像同一逻辑，消息模板
  与 Python 逐字一致。
- `02_source/src/benchreceipt/schemas/run.v1.json` — 仅 description 文字
  （顶层 + 两个 after 字段）改写 fail-closed 规则；`git.required` 不变，
  after 字段仍为 optional。
- `02_source/docs/REASON_CODES.md` — `MISSING_FIELD` 词条扩展到 after 身份
  缺失情形；消息模板表新增 after 身份一行。

夹具与门禁：

- `02_source/scripts/build_fixtures.py` — `make_receipt` 默认写
  `head_after=head`、`tree_after=tree`（除非夹具本身植入 after 异常，如
  e5/e6 保持原样）；新增 `omit_after` 参数（唯一能生成无 after 字段收据
  的途径，仅 e7/e8 使用）；新增 e7/e8 定义；docstring 与 argparse 描述
  50 → 52。
- `02_source/fixtures/s0/` — 重生成：75 个收据各增加两个 after 字段
  （见 §3）；新增 `e7-legacy-clean-checkout/`、`e8-legacy-empty-commit/`
  （各 4 个文件）；e5/e6 字节不变。
- `02_source/fixtures/s0/GOLDEN.json` — 只追加 e7/e8 两条手写 entry
  （UNBOUND + `MISSING_FIELD` + 对应 report_error，jobs_verified 0）；
  已有 50 条经脚本断言逐条比对**全部不变**（另 note 中 "50 S0 fixtures"
  改为 52，仅为计数文字）。
- `02_source/scripts/s0_gate.py` — 硬编码 50/34 改为按夹具数推导
  （controls 保持 16/16，faults 36，parity 52/52）；输出 `spec_version`
  1.1.0 → 1.2.0。
- `02_source/fixtures/s0/README.md`、`02_source/src/benchreceipt/schemas/README.md`、
  `02_source/README.md`、`02_source/oracle/README.md`、`02_source/docs/README.md`、
  `02_source/docs/USER_GUIDE.md`、`02_source/docs/LIMITATIONS.md` — 规格
  版本 1.1.0 → 1.2.0、夹具计数 50 → 52、旧兼容规则文字改写。
- `02_source/scripts/verify_release.py` — 仅标签/文案数字 50/50 → 52/52、
  34/34 → 36/36（校验逻辑不变，仍比对 manifest gates 与 S0_GATE.json）。

规格（SPEC_VERSION 1.1.0 → 1.2.0）：

- `01_spec/PROJECT_BOOK.md` — §5.5 删旧兼容句、改写 fail-closed 规则
  （含 n01/e7 不可区分证明与方案 A 说明）；§5.1 bullet 补 v1.2.0 句；
  §8.1 表加 e7–e8 行、合计 50 → 52；§8.3 门槛 34/34 → 36/36、50/50 →
  52/52；新增 §8.6 v1.2.0 修订记录；§12.1 与 §13.3 计数同步。
- `01_spec/IMPLEMENTATION_PLAN.md` — frontmatter 与 §11.5 规则 5 同步
  （MD + DOCX）；§6.2、§0.2 等处计数 50 → 52；新增 §11.2 v1.2.0
  修订记录（照 §11.1 的 v1.1.0 格式）。
- `01_spec/PROJECT_BOOK.docx`、`01_spec/IMPLEMENTATION_PLAN.docx` —
  与 MD 逐项同步（含 §8.6/§11.2 新节与 §8.1 新表行），见
  `03_evidence/fix-r1/docx-update.py`（python-docx 脚本）。
- `00_control/ADR/ADR-007-fix-r1-legacy-after-fail-closed.md` — 新 ADR，
  照 ADR-005 格式；写明推翻 ADR-005 决策 4、n01/e7 不可区分的证明、
  方案 A 的取舍与被否决的替代方案。
- 镜像 `~/workspace/p027-specs/`（4 个文件）已从 `01_spec/` 同步，
  字节一致；已知分歧已收敛：镜像旧 BOOK.md（38148 B / sha f9f4ee53…）
  缺 T014 后编辑的 SECRET_HINTS 行，现与 `01_spec/`（38299 B →
  v1.2.0 后 40942 B / sha de795a33…）一致。
  `~/workspace/p027-specs/SPEC_MANIFEST.json` 已更新为 spec_version
  1.2.0 与 4 个人工件的新 size + SHA-256；`SHA256SUMS.txt` 同步更新。
  新规格 SHA-256：BOOK.md `de795a33…37b692`（40942 B）、BOOK.docx
  `2a9394d3…998ab6b`（62022 B）、PLAN.md `41be8c66…2723ca81afc`
  （33788 B）、PLAN.docx `482badde…2b816d`（56117 B）。

测试：

- 新增 `02_source/tests/verify/test_legacy_after_missing.py`（11 测试）—
  e7/e8：源码 API、Schema 仍有效、Oracle parity、CLI exit 2、
  e7/e8 收据字节相同（by design）。
- 新增 `02_source/tests/packaging/test_wheel_legacy_after_missing.py`
  （2 测试）— 用离线工具链从当前源码构建 wheel、装进全新 venv：
  删字段后 CLI exit 2 + UNBOUND/MISSING_FIELD；干净 capture 对照仍
  BOUND_PASS。
- 新增 `02_source/tests/capture/test_capture_after_identity.py::test_both_after_fields_missing_fails_closed_with_missing_field`
  （真实 capture，删两字段 → UNBOUND/MISSING_FIELD）。
- 新增 `02_source/oracle/verify.test.mjs` 2 测试（both-missing fail-closed
  与 e7 fixture，evaluate + CLI）— Oracle 自测 24 → 26。
- 更新的既有测试（见 §7）。

## 3. 夹具重生成 diff 摘要

重生成方法：先快照现有夹具（`.tmp/fix-r1-tmp/fixtures-before/`），
用新 builder 生成到暂存目录（`.tmp/fix-r1-tmp/fixtures-regen/`），
逐字段 diff 核对后再写入原位置。diff 全文：
`03_evidence/fix-r1/regen.diff`（603 行）；逐字段核对日志：
`03_evidence/fix-r1/regen-field-check.log`。

核对结果（`BAD: NONE`）：

- 共 77 个收据：75 个各增加一对 after 字段，且值与 before 一致
  （`head_sha_after == head_sha`、`tree_sha_after == tree_sha`）；
  e5/e6 字节不变；除 after 字段外无任何其他 diff（git 其余字段、
  非 git 字段、非收据文件全部相同）。
- `git diff --stat`：75 个收据文件修改（每文件 +2 行 after 字段，
  另 1 行因 sort_keys 顺序移动显示为改动），e7/e8 各新增 4 个文件。
- e7/e8 收据**字节相同**（by design）：无 after 字段时 clean-checkout
  场景与 empty-commit 场景无法区分——这正是两者都必须 fail-closed
  的原因；场景含义只存在于夹具 id 与 Golden 手写 entry 中。
- 手写夹具检查：全部 50 个旧夹具均为 builder 生成（build() 清单与磁盘
  一致），不存在 builder 之外的手写夹具目录；唯一的手写件是
  GOLDEN.json 与 README.md，均已按上述方式处理。

## 4. 复现前后对比表

### 4.1 夹具反例（`repro_fixture_legacy.py`，e5/e6 × Python/Oracle）

修前（冻结 a07dc79 源码，`03_evidence/fix-r1/pre-fix-repro-fixture.log`）：

| 夹具 | 变体 | 实现 | status | reason_codes | jobs_verified | exit |
|---|---|---|---|---|---|---|
| e5 | orig | Python CLI | UNBOUND | SOURCE_MUTATED_DURING_RUN | 0 | 2 |
| e5 | orig | Oracle | UNBOUND | SOURCE_MUTATED_DURING_RUN | 0 | 2 |
| e5 | legacy（删两字段） | Python CLI | **BOUND_PASS** | [] | 1 | 0 |
| e5 | legacy（删两字段） | Oracle | **BOUND_PASS** | [] | 1 | 0 |
| e6 | orig | Python CLI | UNBOUND | SOURCE_MUTATED_DURING_RUN | 0 | 2 |
| e6 | orig | Oracle | UNBOUND | SOURCE_MUTATED_DURING_RUN | 0 | 2 |
| e6 | legacy（删两字段） | Python CLI | **BOUND_PASS** | [] | 1 | 0 |
| e6 | legacy（删两字段） | Oracle | **BOUND_PASS** | [] | 1 | 0 |

修后（修复后工作树，`03_evidence/fix-r1/post_fix_fixture_repro.py`，
日志 `03_evidence/fix-r1/post-fix-fixture-repro/` +
`post-fix-fixture-repro.run.log`）：

| 夹具 | 变体 | 实现 | status | reason_codes | jobs_verified | exit |
|---|---|---|---|---|---|---|
| e5 | orig | Python CLI | UNBOUND | SOURCE_MUTATED_DURING_RUN | 0 | 2 |
| e5 | orig | Oracle | UNBOUND | SOURCE_MUTATED_DURING_RUN | 0 | 2 |
| e5 | legacy（删两字段） | Python CLI | UNBOUND | **MISSING_FIELD** | 0 | 2 |
| e5 | legacy（删两字段） | Oracle | UNBOUND | **MISSING_FIELD** | 0 | 2 |
| e6 | orig | Python CLI | UNBOUND | SOURCE_MUTATED_DURING_RUN | 0 | 2 |
| e6 | orig | Oracle | UNBOUND | SOURCE_MUTATED_DURING_RUN | 0 | 2 |
| e6 | legacy（删两字段） | Python CLI | UNBOUND | **MISSING_FIELD** | 0 | 2 |
| e6 | legacy（删两字段） | Oracle | UNBOUND | **MISSING_FIELD** | 0 | 2 |

4 个 legacy 格全部变为非 BOUND_PASS（UNBOUND + MISSING_FIELD），
4 个 orig 对照格不变。

### 4.2 评审方 wheel 脚本（`independent_p0_wheel_repro.py`）

修前（冻结 dist.zip wheel，`03_evidence/fix-r1/pre-fix-wheel-repro.log`）：

| case | 原始收据 | 删 after 字段后 | jobs_verified |
|---|---|---|---|
| clean_checkout | UNBOUND / SOURCE_MUTATED_DURING_RUN | **BOUND_PASS** / [] | 1 |
| empty_commit | UNBOUND / SOURCE_MUTATED_DURING_RUN | **BOUND_PASS** / [] | 1 |

末行：`2/2 ORIGINAL FIXES PASS; 2/2 LEGACY-SHAPE FALSE PASS PROVEN`。

修后（从修复后源码新构建的 wheel，`03_evidence/fix-r1/post_fix_wheel_repro.py`，
期望已按修复改写，日志 `03_evidence/fix-r1/post-fix-wheel-repro.log`）：

| case | 原始收据 | 删 after 字段后 | jobs_verified |
|---|---|---|---|
| clean_checkout | UNBOUND / SOURCE_MUTATED_DURING_RUN | UNBOUND / **MISSING_FIELD** | 0 |
| empty_commit | UNBOUND / SOURCE_MUTATED_DURING_RUN | UNBOUND / **MISSING_FIELD** | 0 |

末行：`2/2 ORIGINAL FIXES PASS; 2/2 LEGACY-SHAPE FAIL-CLOSED (UNBOUND + MISSING_FIELD)`。
两案删字段后收据仍通过 run schema 校验（字段保持 optional），
与修复设计一致。

## 5. 验收数字（均为亲自跑出）

- 全量 pytest：**848 passed**（40.96s，0 失败），冻结时 830；新增 18 =
  S0 参数化 +4（2 新夹具 × 2）、e7/e8 新测试 11、both-missing 1、
  wheel 2。日志 `03_evidence/fix-r1/pytest-full.log`。
- 原始 6 项测试：全部通过（现为 7 项，含新增 both-missing 1 项）。
  日志 `03_evidence/fix-r1/original-variants.log`。
- S0 门禁：**PASS 10/10**（日志 `03_evidence/fix-r1/s0-gate.log`；
  报告 `03_evidence/s0/S0_GATE.json`、`S0_REPORT.md` 已更新提交）：
  controls 16/16、faults 36/36、false PASS 0、false block 0、
  parity 52/52、100 replays 1 hash、P95 0.09622893100004148s、
  offline network_requests 0、79 receipts 隐私 0 违规、52 夹具清点。
- repeat-100（独立跑 `scripts/repeat_hash.py`）：1 distinct hash，
  `a19054f11949ddd21f922556c07d7d51f0028dde09a18beb9b64e4b2e827d530`
  ——与 v1.1.0 冻结值相同（n02  verdict 未变）。日志
  `03_evidence/fix-r1/repeat-100.log`。
- Oracle 自测：`node --test oracle/verify.test.mjs` **26 pass / 0 fail**
  （原 24 + 新增 2）。
- 离线检查：`scripts/offline_check.py` **PASS**
 （static=CLEAN，socket_events=0，verify=BOUND_PASS）。
  日志 `03_evidence/fix-r1/offline-check.log` / `offline-check.json`。
- 离线安装：`verify_release.py` 全程（含 offline install 步骤）无
  OFFLINE INSTALL 失败；wheel 测试另从当前源码构建 wheel 并离线安装
  进全新 venv 成功（2 测试通过）。

## 6. verify_release.py / verify_review_pack.py（诚实记录）

- `verify_release.py`：**FAIL，exit 1**，恰好 3 个问题，全部是预期内的
  冻结清单滞后（本次不重冻，清单由协调员重冻时再生）：
  `gates.s0_faults='34/34' != '36/36'`、
  `gates.s0_parity='50/50' != '52/52'`、
  `gates.s0_golden_sha256` 旧值 `65ccd954…0ef7870` != 新值
  `fb8e70a1…60497`。其余检查（source.zip 对冻结树、dist.zip、SHA256SUMS、
  LICENSE、deps==0、bundle clone、离线安装）全部通过。
  日志 `03_evidence/fix-r1/verify-release.log` /
  `verify-release.exit.log`。
- `verify_review_pack.py`：**PASS，exit 0** —
  `commit cfede2711bc54567b918b1f85654c2dd42c30943, 45 index rows,
  37 pack rows, 34 key production files all listed in 6 pack(s),
  all SHA-256 + line counts match`。该脚本校验 T013 审查包自身锚点，
  不受本次改动影响；P1-R1-01（审查包未覆盖新冻结）须由重冻后的新
  审查包解决，不在本修复范围内。
  日志 `03_evidence/fix-r1/verify-review-pack.log`。

## 7. 更新的既有测试清单

逐个核查的结果：**没有任何既有测试断言“无 after 字段收据可
BOUND_PASS”**——所有既有 BOUND_PASS 测试都是夹具型或 capture 型，
重生成后夹具全部带 after 字段、capture 本来就写 after 字段，
故无需按新规则改写断言。以下更新只是 50 → 52 的计数跟随：

| 测试 | 改动 | 原因 |
|---|---|---|
| `tests/s0/test_s0.py::test_inventory_is_50` | 改名 `test_inventory_is_52`；50 → 52、faults 34 → 36；模块 docstring 同步 | 夹具 50 → 52 |
| `tests/bundle/test_bundle.py::test_all_50_s0_fixtures_bundle_without_raising` | 改名 `..._52_...`；50 → 52 | 同上 |
| `tests/privacy/test_privacy_scan.py::test_scan_fixtures_tree_is_clean` | 注释 "50 fixtures" → "52 fixtures"；断言 `scanned > 50` 不变（52 仍成立） | 同上 |
| `tests/verify/test_verify.py`、`tests/reports/test_verify_wiring.py`、`tests/test_oracle_parity_r13b.py` 等 | 未改动 | 均使用夹具/capture（现带 after 字段）或只断言 parity/非 PASS，全量通过 |

## 8. 每步命令与日志路径

（工作目录 `~/workspace/p027-benchreceipt`；pytest 的 TMPDIR 均为
持久磁盘 `~/workspace/p027-benchreceipt/.tmp/fix-r1-tmp`，未用 /tmp；
`.venv/bin/python` 为仓库 Python 3.12.3，Node v24.22.1。）

| 步骤 | 命令 | 日志 |
|---|---|---|
| 分支核对 | `git status` / `git log`（fix-r1 @ b1910e6） | — |
| 提交预修复日志 | `git add 03_evidence/fix-r1/pre-fix-repro-fixture.log && git commit` | commit d2873e3 |
| 修前夹具复现 | `.venv/bin/python 03_evidence/fix-r1-repro/repro_fixture_legacy.py` | `03_evidence/fix-r1/pre-fix-repro-fixture.log`（已提交）；重跑输出与之一致 |
| 修前 wheel 复现 | `.tmp/fix-r1-repro/wheel-venv/bin/python 03_evidence/r1-repro/independent_p0_wheel_repro.py` | `03_evidence/fix-r1/pre-fix-wheel-repro.log` |
| 夹具重生成（暂存） | `PYTHONPATH=02_source/src .venv/bin/python 02_source/scripts/build_fixtures.py --root .tmp/fix-r1-tmp/fixtures-regen` | `03_evidence/fix-r1/regen.diff`、`regen-field-check.log` |
| S0 门禁 | `TMPDIR=.../.tmp/fix-r1-tmp PYTHONPATH=02_source/src .venv/bin/python 02_source/scripts/s0_gate.py` | `03_evidence/fix-r1/s0-gate.log` |
| 新测试（e7/e8 + after-identity + S0） | `../.venv/bin/python -m pytest tests/verify/test_legacy_after_missing.py tests/capture/test_capture_after_identity.py tests/s0/test_s0.py -q` | 125 passed（终端输出） |
| wheel 新测试 | `../.venv/bin/python -m pytest tests/packaging/test_wheel_legacy_after_missing.py -v` | 2 passed（终端输出） |
| Oracle 自测 | `node --test oracle/verify.test.mjs` | 26 pass / 0 fail（终端输出） |
| 全量套件 | `TMPDIR=... ../.venv/bin/python -m pytest -q`（02_source 内） | `03_evidence/fix-r1/pytest-full.log`（848 passed） |
| 原始 6 项测试 | `pytest tests/adversarial/test_source_mutation_evasion.py tests/capture/test_capture_after_identity.py -v` | `03_evidence/fix-r1/original-variants.log`（7 passed） |
| repeat-100 | `../.venv/bin/python scripts/repeat_hash.py` | `03_evidence/fix-r1/repeat-100.log` |
| 离线检查 | `../.venv/bin/python scripts/offline_check.py --out ../03_evidence/fix-r1/offline-check.json` | `03_evidence/fix-r1/offline-check.log` |
| 修后夹具复现 | `.venv/bin/python 03_evidence/fix-r1/post_fix_fixture_repro.py` | `03_evidence/fix-r1/post-fix-fixture-repro/`、`post-fix-fixture-repro.run.log` |
| 修后 wheel 复现 | 构建 wheel（离线工具链）→ 新 venv 安装 → `.tmp/fix-r1-tmp/wheel-venv/bin/python 03_evidence/fix-r1/post_fix_wheel_repro.py` | `03_evidence/fix-r1/post-fix-wheel-repro.log` |
| verify_release | `../.venv/bin/python scripts/verify_release.py --tmp-dir ../.tmp/fix-r1-tmp/verify-release` | `03_evidence/fix-r1/verify-release.log` |
| verify_review_pack | `../.venv/bin/python scripts/verify_review_pack.py` | `03_evidence/fix-r1/verify-review-pack.log` |
| DOCX 更新 | `.venv/bin/python 03_evidence/fix-r1/docx-update.py` | 脚本本身即证据；执行中发现并修复两处脚本 bug（`while old in p.text` 死循环：新文本含旧文本；`insert_paragraph_before` 逆序插入），已从备份恢复重跑并逐项核对 DOCX 文本 |

## 9. 未做事项（按纪律）

- 未提交 R2、未上传 GitHub、未重冻（无新 source.zip/dist.zip/bundle；
  `05_release/` 未动；verify_release 的 3 个 gates 偏差待重冻时消除）。
- 未改任何已有 Golden 值（脚本断言验证）；未动 `00_control/PROJECT_STATE.json`
  与 `00_control/HANDOFF.md`（控制层快照，属协调员）。
- `03_evidence/r1-repro/`（评审方原件，未跟踪）保持原样，未提交。

## 10. 交给协调员的事项

1. 重冻 v1.2.0（新 source.zip/dist.zip/bundle + RELEASE_MANIFEST + SHA256SUMS），
   verify_release 的 3 个 gates 偏差随之消除。
2. P1-R1-01：为新冻结补一份最终版本独立审查包（T013 包锚定 cfede271，
   须另建新包；本修复未动 04_review）。
3. R2 在同一终审对话提交；P0-R1-01 的修复证据即本目录。
