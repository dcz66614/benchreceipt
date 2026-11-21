# P027 BenchReceipt FIX-R1 复现证据 — P0-R1-01（fail-first，只复现，不改生产代码）

- 分支：`fix-r1-repro`（从 `196fa7c` 切出）
- 复现时间：2026-11-18 ~03:27–03:35 GMT
- 冻结身份：`05_release/source.zip` SHA-256
  `2b06fcd38e6207f3c3bfa2058b68443e693b7c1b719e04b69dbdccd34f09caac`（解压前已核对，与 R1 提交值一致）；
  `05_release/dist.zip` SHA-256
  `77b08aacfd2c93a14bce670608e03f6b3ca77116e9f344c72521ac327539f1df`（与 R1 提交值一致）。
  解压位置：`.tmp/fix-r1-repro-scratch/`（`.tmp/` 已 gitignore，未提交解压产物）。
- 环境：本地 Python 3.12.3（仓库 `.venv`）、Node v24.22.1；pytest 的 TMPDIR 指到持久磁盘
  `~/workspace/p027-benchreceipt/.tmp/repro-tmp`。
- 结论先行：**反例复现成功。删掉 `git.head_sha_after` 与 `git.tree_sha_after` 两个字段后，
  e5 与 e6 的收据在 Python 验证器与 Node Oracle 下均由 UNBOUND 变为 BOUND_PASS。**
  原始路径（带 after 字段）仍有效：6 项原始测试全部通过。

## 1. 评审方脚本复现（优先采用评审方自己的脚本）

脚本：`03_evidence/r1-repro/independent_p0_wheel_repro.py`（已先通读源码再运行）。
它只用已发布 wheel 的公开 API（`benchreceipt.capture` + `benchreceipt.verify.evaluate`），
在临时仓库里真实跑一次 capture、途中切换 HEAD（`clean_checkout`）或建空提交（`empty_commit`），
先验证原始收据，再删掉两个 after 字段后重新 `evaluate`，并对收据做 schema 校验。

运行方式：先把冻结 `dist.zip` 里的 `benchreceipt-0.1.0-py3-none-any.whl`
以 `--no-index --no-deps` 装进全新 venv（`.tmp/fix-r1-repro/wheel-venv/`），再跑脚本。
原始日志：`independent_p0_wheel_repro.my-run.log`。

我亲自跑出的结果（与脚本内断言一致，脚本 exit 0）：

| case | 原始收据 | 原始 reason_codes | 删 after 字段后 | 删后 reason_codes | jobs_verified |
|---|---|---|---|---|---|
| clean_checkout | UNBOUND | `["SOURCE_MUTATED_DURING_RUN"]` | **BOUND_PASS** | `[]` | 1 |
| empty_commit | UNBOUND | `["SOURCE_MUTATED_DURING_RUN"]` | **BOUND_PASS** | `[]` | 1 |

两案的 `was_mutated_during_run` 均为 `true`，`legacy_shape_schema_valid` 均为 `true`
（删字段后的收据仍通过 `run` schema 校验），脚本末行：
`INDEPENDENT_R1_WHEEL_REPRO: 2/2 ORIGINAL FIXES PASS; 2/2 LEGACY-SHAPE FALSE PASS PROVEN`。
（注：各案的 commit SHA 与 receipt SHA-256 与评审方日志不同是正常的——脚本每次新建临时仓库，
commit 时间不同导致 SHA 不同；状态与 reason_codes 完全一致。）

## 2. 冻结夹具删除字段反例（我按 R1 文字描述独立重建的第二路复现）

驱动脚本：`repro_fixture_legacy.py`（本目录）。夹具取自解压后的冻结源码：
`fixtures/s0/e5-clean-tree-head-change/evidence/unit-linux-py312/receipt.json` 与
`fixtures/s0/e6-empty-commit-mid-run/evidence/unit-linux-py312/receipt.json`；
`expected_source_sha` 取夹具 `expected.json` 的 `aaaa…（40 个 a）`。
删除操作只删 `git.head_sha_after` 与 `git.tree_sha_after`，其余字段原样
（删掉的值见 `e5-….removed-fields.json` / `e6-….removed-fields.json`；
e5 删 `head_sha_after=bbbb…`、`tree_sha_after=eeee…`；
e6 删 `head_sha_after=cccc…`、`tree_sha_after=dddd…`——即与 `tree_sha` 相同的值）。

Python CLI（冻结源码，`PYTHONPATH=.tmp/fix-r1-repro-scratch/src`，
`.venv/bin/python -m benchreceipt verify --policy <夹具 policy.toml> --evidence <dir>
--expected-source-sha aaaa… --out <result.json>`）与
Node Oracle（`node .tmp/fix-r1-repro-scratch/oracle/verify.mjs --policy <policy.toml>
--expected-source-sha aaaa… --evidence <dir>`）逐项结果（逐行原始日志见同名 `.log` 文件，
汇总见 `fixture-legacy.summary.json`，驱动输出见 `fixture-legacy.run.log`）：

| 夹具 | 变体 | 实现 | status | reason_codes | jobs_verified | exit code |
|---|---|---|---|---|---|---|
| e5-clean-tree-head-change | orig（对照） | Python CLI | UNBOUND | `["SOURCE_MUTATED_DURING_RUN"]` | 0 | 2 |
| e5-clean-tree-head-change | orig（对照） | Oracle | UNBOUND | `["SOURCE_MUTATED_DURING_RUN"]` | 0 | 2 |
| e5-clean-tree-head-change | legacy（删两字段） | Python CLI | **BOUND_PASS** | `[]` | 1 | 0 |
| e5-clean-tree-head-change | legacy（删两字段） | Oracle | **BOUND_PASS** | `[]` | 1 | 0 |
| e6-empty-commit-mid-run | orig（对照） | Python CLI | UNBOUND | `["SOURCE_MUTATED_DURING_RUN"]` | 0 | 2 |
| e6-empty-commit-mid-run | orig（对照） | Oracle | UNBOUND | `["SOURCE_MUTATED_DURING_RUN"]` | 0 | 2 |
| e6-empty-commit-mid-run | legacy（删两字段） | Python CLI | **BOUND_PASS** | `[]` | 1 | 0 |
| e6-empty-commit-mid-run | legacy（删两字段） | Oracle | **BOUND_PASS** | `[]` | 1 | 0 |

即 R1 所称的 `{"status":"BOUND_PASS","reason_codes":[],"jobs_verified":1}` 在两夹具 × 两实现上
全部属实，且对照组（不删字段）全部正常为 UNBOUND。Python 与 Oracle 在此反例上行为一致，
不存在实现间分歧可掩盖问题。

## 3. 原始路径回归（6 项测试）

在解压出的冻结源码里跑（`TMPDIR=~/workspace/p027-benchreceipt/.tmp/repro-tmp`，
`PYTHONPATH` 指冻结 `src`，仓库 `.venv` 的 pytest 9.2.0 / Python 3.12.3）：

```
.venv/bin/python -m pytest tests/adversarial/test_source_mutation_evasion.py \
    tests/capture/test_capture_after_identity.py -v
```

结果：**6 passed，exit 0**（原始日志 `original-variants.pytest.log`）。通过项：
`test_head_change_mid_run_is_detected`、`test_empty_commit_mid_run_is_detected`、
`test_dirty_to_clean_flip_is_detected`、`test_clean_capture_emits_after_identity_and_passes`、
`test_half_present_after_pair_fails_closed`、`test_malformed_after_value_is_schema_invalid`。
原始 P0-01 修复（新版 capture 记录 after 身份）在冻结源码上仍有效。

## 4. 评审方日志核对（读 `03_evidence/r1-repro/` 原件，与 R1 正文声称的数字逐项比对）

| R1 声称 | 日志原件 | 核对结果 |
|---|---|---|
| S0 10/10 | `independent_s0.stdout.log` | **一致**。`S0 gate: PASS (10/10 thresholds)`；正常控制 16/16、植入故障 34/34、parity 50/50、false PASS 0、false block 0、100 次重放 1 个 SHA-256（`a19054f11949ddd21f922556c07d7d51f0028dde09a18beb9b64e4b2e827d530`）、100 manifests P95 = 0.04074712199997066s、离线网络请求 0、77 receipts 0 违规。 |
| Oracle 24/24 | `independent_oracle_node22.log` | **一致**。TAP 输出 24 个子测试全部 `ok`，尾部 `# pass 24 / # fail 0`，Node 22 环境。 |
| pytest 827 passed + 3 errors | `full_pytest_final_attempt.log` | **一致**。尾行 `827 passed, 3 errors in 109.97s`；3 个 errors 全部是 `tests/packaging/test_wheel_contents.py` 三项测试在 setup 阶段的失败（`test_wheel_contains_every_loaded_schema`、`test_wheel_without_package_data_contains_no_schemas`、`test_schemas_dir_resolves_in_packaged_layout`），原因均为审查环境缺少离线 wheel 构建工具链（`setuptools, wheel, build, pyproject_hooks, packaging`），错误信息提示先跑 `python scripts/freeze_release.py build` 下载 pinned wheels 到 `.tmp/t014-freeze/`。即 R1 所述“审查环境缺少三项 packaging tests 所需的离线构建 wheelhouse”属实；这 3 项是环境缺失导致的 setup error，不是产品测试失败。 |
| P0 原始变体 6 passed | `independent_p0_original_variants.log` | **一致**。`6 passed in 4.80s`。与本复现 §3 在冻结源码上亲自跑出的 6 passed 相互印证。 |
| P0 反例 2/2 false PASS | `independent_p0_wheel_repro.log` | **一致**。两案均为原始 UNBOUND + `SOURCE_MUTATED_DURING_RUN`、删字段后 BOUND_PASS + `jobs_verified: 1`；末行 `2/2 ORIGINAL FIXES PASS; 2/2 LEGACY-SHAPE FALSE PASS PROVEN`。与本复现 §1 亲自重跑的结果一致（SHA 不同系每次新建临时仓库所致，状态一致）。 |

另读了 `identity_check.py`：它是评审方核对 source.zip 与冻结 Git 树一致性的脚本
（比对 zip 内文件与 `git ls-tree HEAD 02_source` 的文件集与字节内容，打印 missing/extra/
content_mismatch 计数与冻结 commit/tree），本身不含可直接核对的数字断言；R1 正文称
source ZIP 与冻结 Git 树 345/345 字节一致，未在本目录留下该脚本的输出日志，
故该 345/345 不在本复现的核对范围内（本复现只核对了 source.zip / dist.zip 的 SHA-256，
见文首；未重跑 identity_check.py，因其硬编码评审方路径 `/mnt/data/p027_r1_audit`）。

## 5. 文件清单（本目录 `03_evidence/fix-r1-repro/`）

- `SUMMARY.md` — 本文件。
- `repro_fixture_legacy.py` — §2 夹具反例的驱动脚本。
- `fixture-legacy.summary.json` / `fixture-legacy.run.log` — §2 汇总与驱动输出。
- `e5-clean-tree-head-change-{orig,legacy}.python-cli.log` /
  `e5-clean-tree-head-change-{orig,legacy}.python-result.json` /
  `e5-clean-tree-head-change-{orig,legacy}.oracle.log` — e5 的 Python CLI 原始日志、
  `--out` 结果 JSON、Oracle 原始日志（e6 同名 8 个文件）。
- `e5-clean-tree-head-change-legacy.removed-fields.json` /
  `e6-empty-commit-mid-run-legacy.removed-fields.json` — 删掉的两个字段的值。
- `independent_p0_wheel_repro.my-run.log` — §1 评审方脚本在我方重跑的原始输出。
- `original-variants.pytest.log` — §3 六项原始测试的原始输出。

未提交的中间产物（均在 `.tmp/` 下，已 gitignore）：冻结源码解压目录
`.tmp/fix-r1-repro-scratch/`、wheel 解压与 venv `.tmp/fix-r1-repro/`（含 `dist/`、
`wheel-venv/`、各变体 evidence 副本）、pytest TMPDIR `.tmp/repro-tmp/`。
生产代码、规格、测试均未改动（`git status` 仅新增本证据目录；另有复现前已存在的
未跟踪目录 `03_evidence/r1-repro/`，不属于本次提交）。

## 6. 给 FIX 的交接要点

- 缺陷已在两条独立路径上证实：① 评审方 wheel 脚本（真实 capture + `evaluate()` API）；
  ② 冻结 S0 夹具 e5/e6 删字段后经 Python CLI 与 Node Oracle 双实现验证。
  Python 与 Oracle 在此反例上**一致地**误通过，修一边不够，两边（及规格 §5.5 的
  旧版兼容回退规则）须同步改为 fail-closed。
- 修复门槛（按 R1）：缺少 after 身份证据的收据不得返回 BOUND_PASS；
  可保留旧格式解析，但应返回 UNBOUND / MISSING_FIELD 等明确状态。
- 回归锚点：修复后 §2 的 4 个 legacy 格（e5/e6 × Python/Oracle）应全部变为
  非 BOUND_PASS，§3 的 6 项原始测试与 §1 的原始收据 UNBOUND 判定须保持不变。
