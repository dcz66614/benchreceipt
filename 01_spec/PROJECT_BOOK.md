---
project_id: P027
slug: benchreceipt
name: BenchReceipt（测证收据）
spec_version: 1.2.0
document: PROJECT_BOOK
status: SPECIFICATION_DRAFT / WAITING_OWNER_REVIEW / NO_CODE_BUILT
created_utc: 2026-11-17
license: MIT
human_participants: 0
total_effort_hours: 88
---

# P027 BenchReceipt（测证收据）项目书

**副标题：把 CI 测试结果绑定到精确代码版本、运行批次、矩阵任务和报告产物**

| 项目 | 冻结值 |
|---|---|
| PROJECT_ID | P027 |
| 英文名 / slug | BenchReceipt / `benchreceipt` |
| 中文名 | 测证收据 |
| 规格版本 | 1.2.0 |
| 状态 | `SPECIFICATION_DRAFT / WAITING_OWNER_REVIEW / NO_CODE_BUILT` |
| 许可证 | MIT |
| 计划工作量 | 88 小时：72h 原子任务 + 16h 缓冲 |
| 日历计划 | 单人等效约两周 |
| 真人参与者 | 0；仅合成数据、确定性算法、独立 Oracle 与自动化断言 |
| 运行时 | 本地优先；CPU-only；无 LLM、GPU、收费 API、数据库或遥测 |
| 首发集成 | GitHub Actions；其他 CI 可通过显式参数使用通用 capture/verify |
| 主要用户 | 开源维护者、独立开发者、小型工程团队、AI coding agent 产生 PR 的维护者 |

> 本文件是产品与算法权威规格，不是软件已实现、已运行或已通过验收的声明。所有执行结果初始均为 `NOT_VERIFIED`。本轮仅完成规格；S0 通过前不得启动 S1–S5 施工。

## 0. 一页摘要

### 0.1 一句话价值

**CI 显示绿色，不代表所有绿色测试报告都属于同一个代码版本。BenchReceipt 为每个测试矩阵任务生成可复核收据，并验证 commit、Git tree、workflow run、attempt、job、matrix、测试命令和报告哈希是否一致。**

### 0.2 产品是什么

BenchReceipt 是一个本地优先的 CI 测试证据绑定与聚合工具。它不替代测试框架，也不重新实现 CI 平台。它在测试命令执行前后采集最小必要的身份信息，将 JUnit / LCOV 等报告及其 SHA-256 纳入收据，再由独立验证器检查多个 CI job 是否属于同一份预期源码与同一次 workflow 执行。

核心工作流：

1. `capture`：包装用户显式提供的测试命令，采集 Git 身份、CI run/attempt、job/matrix、命令摘要、退出码、测试报告和文件哈希。
2. `bundle`：把每个 job 的收据与报告组织成可携带的本地证据目录。
3. `verify`：按 `.benchreceipt.toml` 检查预期 commit 模式、run ID、attempt、必需矩阵、报告完整性和测试结果。
4. `report`：生成 JSON 与静态 HTML 证据图，展示每条证据链及首次不一致位置。

### 0.3 核心承诺与诚实边界

- 能证明：在当前工作区采集到的 Git commit/tree、运行环境、命令摘要、CI run/attempt、job/matrix 和报告字节之间是否满足声明的绑定规则。
- 能发现：PR head SHA 与 merge SHA 混用、矩阵 job 混入不同 commit、不同 run/attempt 的产物混合、缺少矩阵单元、重复 job、报告缺失/哈希不符、测试失败或空测试报告、测试运行期间源码树发生变化。
- **不能证明测试逻辑正确**，不能证明测试断言足够强，不能证明代码没有 bug，也不能证明 workflow 作者没有恶意伪造环境变量或报告。
- 首版收据不做密码学签名。SHA-256 用于发现意外混包和字节变化，不构成对恶意工作流/被攻陷 runner 的真实性认证。
- 首版不替代 SLSA、in-toto、Sigstore 或 GitHub Artifact Attestations；可导出与 in-toto Test Result Predicate 对齐的 unsigned Statement，但不得把未签名文件宣传为安全证明。
- BenchReceipt 不解析 PR 自然语言，不匹配“宣称 vs diff”，不判断测试是否覆盖某一行代码。

### 0.4 为什么值得做

AI coding agent 让代码和 PR 产生得更快，测试证据成为维护者判断变更能否合并的重要输入。CI 多矩阵、多次重跑、PR merge commit 与 head commit 并存时，测试结果、coverage 和 artifact 可能来自不同身份。GitHub 官方事件文档明确区分 `pull_request` 的 merge SHA 与 PR head SHA；测试若 checkout 了错误 SHA，报告就可能不能代表维护者以为正在验证的代码。

BenchReceipt 的切口不是“再做一个测试平台”，而是一个小型、离线、可插入现有 CI 的一致性门禁：**在消费绿色报告前，先核实它属于谁。**

## 1. 用户、场景与问题定义

### 1.1 目标用户

| 用户 | 具体场景 | 主要损失 |
|---|---|---|
| 开源维护者 | PR 有 Linux / Windows / 多版本矩阵，多个 artifact 最后汇总 | 不同 run 或 attempt 的报告被误当成同一轮结果 |
| 独立开发者 | AI coding agent 连续改代码、重跑测试、更新 PR | 本地绿色结果与最终提交 SHA 不一致 |
| 小型工程团队 | 使用 JUnit / LCOV / Cobertura 产物汇总 | 报告来自旧 commit、旧缓存或错误 checkout |
| CI 平台维护者 | workflow 使用 `pull_request`、`merge_group`、`workflow_run` | head SHA、merge SHA、workflow SHA 和实际 checkout SHA 混淆 |
| 代码审查者 | 只看到 badge 或绿色 check | 无法快速判断报告、测试矩阵和源码身份是否完整一致 |

### 1.2 典型使用场景

**场景 A：PR head / merge commit 混淆**

GitHub `pull_request` 事件的 `GITHUB_SHA` 默认指向测试合并提交，而 `github.event.pull_request.head.sha` 指向 PR head。项目如果期望验证 PR head，却实际 checkout 了 merge commit，报告应显示 `SOURCE_SHA_MISMATCH`，不能静默通过。

**场景 B：重跑后混入旧 attempt**

Workflow run 第 1 次 attempt 的 Linux artifact 与第 2 次 attempt 的 Windows artifact 被手动下载到同一目录。两个 job 都是绿色，但 `run_attempt` 不一致。BenchReceipt 必须拒绝聚合。

**场景 C：矩阵缺项**

策略要求 `ubuntu-latest + Python 3.12`、`windows-latest + Python 3.12`、`ubuntu-latest + Python 3.13`，但最终 bundle 只包含两个 job。不得因为已有 job 全绿就给出完整通过。

**场景 D：coverage / JUnit 产物错配**

测试命令针对 commit A 执行，之后工作区切到 commit B，coverage 报告或 JUnit 文件被复制到另一次 run。报告哈希、来源身份或 run attempt 不一致时，验证器必须失败关闭。

### 1.3 痛点与证据边界

本项目把“测试证据是否属于正确源码和正确运行批次”作为工程风险，而不是宣称已经测量了所有开发者遇到该问题的频率。以下事实支持问题值得解决：

- GitHub Actions `pull_request` 事件有 head SHA 与 merge SHA 的语义差异。
- GitHub Artifact Attestations 主要解决构建产物来源与完整性；它不是面向每个小团队的多矩阵 JUnit / coverage 聚合体验。
- in-toto 已定义 Test Result Predicate，说明“测试结果 + 测试配置 + 被测 subject”是合理的供应链证据对象。
- 2026 年 CI flaky-test 研究指出执行环境会显著影响结果，说明运行环境标识不能被随意丢弃。

上述资料支持技术问题存在，不证明目标用户数量、付费意愿或市场份额。RICE、传播力和收购潜力均为规划假设，`USER_VALUE_NOT_MEASURED`。

### 1.4 现有 workaround 及其不足

| Workaround | 能解决什么 | 不足 |
|---|---|---|
| 只看 GitHub check 绿色状态 | 快速查看 job 结果 | 不自动证明下载到的多个报告来自同一 run attempt |
| 手工检查 `GITHUB_SHA` | 可发现一部分 SHA 混淆 | 维护者需要自己跨 job、matrix、artifact 对账 |
| `actions/upload-artifact` / `download-artifact` | 传递 job 文件 | 负责传输，不负责验证不同文件的源码身份是否一致 |
| JUnit / LCOV | 表达测试结果与覆盖数据 | 通常不包含足够的 CI run / attempt / source-tree 绑定信息 |
| SLSA / in-toto / GitHub attestations | 提供更强的供应链证明基础 | 配置与签名链更重；本项目不重新实现它们，而是提供轻量的一致性检查与标准化输出 |

## 2. 产品目标与非目标

### 2.1 MVP 目标

1. 单条命令包装测试命令并生成 `benchreceipt.run/v1` 收据。
2. 记录 commit SHA、Git tree SHA、source mode、workflow run ID、run attempt、job ID、matrix、命令摘要、运行时环境、开始/结束时间和退出码。
3. 支持 JUnit XML 与 LCOV 报告；Coverage 仅记录来源文件和行命中信息，不做质量评分。
4. 支持本地多 job bundle 聚合，按 TOML policy 校验必需矩阵。
5. 检测 stale / mixed / missing evidence，并使用 `BOUND_PASS`、`BOUND_FAIL`、`UNBOUND`、`INVALID` 四态。
6. 输出机器可读 JSON 与无外部依赖的静态 HTML。
7. 提供 GitHub Actions 示例 workflow 和 composite-action 模板；不要求 GitHub API token。
8. 全部测试使用合成仓库、合成 CI 环境变量、合成 JUnit/LCOV 与独立 Oracle。

### 2.2 非目标

- 不运行或托管 CI，不替代 GitHub Actions。
- 不扫描 workflow YAML 的触发、paths filter 或 required checks（P020 CheckPath 已覆盖相邻问题）。
- 不判断 PR 描述是否准确，不把 diff 与自然语言 claims 做匹配。
- 不评估测试断言是否充分，不做 mutation testing、flaky ranking 或测试选择。
- 不判断代码是否正确，不做漏洞扫描、依赖扫描或 secret scanning。
- 不实现远程 dashboard、账号、团队管理、云端存储、SaaS 或付费 API。
- 不做密码学签名、TEE、远程证明或对抗恶意 runner 的完整安全认证。
- 不支持所有 CI provider 的自动发现；首发自动读取 GitHub Actions 环境，其他 CI 可手动传入字段。
- 不存储完整 stdout/stderr，避免把 token、密钥或私人数据写入收据。

## 3. 候选评估与选题决策

### 3.1 原报告十个候选的独立判断

原报告 RICE 均视为规划假设，不能直接视为市场证据。以下竞争判断基于本轮外部检索，未对所有产品进行穷尽式市场调查。

| 原候选 | 原 RICE | 本轮发现的主要竞争/问题 | 决策 |
|---|---:|---|---|
| C02 PRClaimMap | 432 | `proofcheck`、Vigil 与 GitHub Spec Kit `pr-assess` 已覆盖 PR 描述与 diff 对账的相邻甚至直接功能；原方案把“行覆盖”过度解释为“宣称被测试证明” | 不按原范围立项 |
| C01 SkillProof | 360 | NVIDIA SkillSpector 与 Snyk Agent Scan 已覆盖技能/MCP 安全扫描；P023 SkillScope 又覆盖技能来源与作用域 | 不按原范围立项 |
| C07 AgentClaimCheck | 315 | `trustbut`、`Proof` 等已核验 Agent 完工声明、测试与 diff；容易成为 Agent hook 适配器集合 | 不按原范围立项 |
| C04 FlakeRank | 300 | BuildPulse、Currents 等已有 flaky detection、history、ranking、quarantine；还需要长期运行数据 | 不选 |
| C05 VulnReach | 280 | OSV-Scanner 已有多生态扫描与部分 call analysis；通用多语言可达性在 88h 内范围过大 | 不选 |
| C08 DocRun | 250 | Runme 已能执行 README / Markdown 中的命令；产品差异不足 | 不选 |
| C10 ReleaseNoteVerify | 213 | 与 C02 的 claim/diff 对账、P026 的证据链思路邻近；发布说明频率低于 CI 每次运行 | 不选 |
| C03 TokenLedger | 210 | `ccusage` 已聚合多个 coding-agent CLI 的本地 token 与成本数据 | 不选 |
| C09 SecretSweep | 210 | Snyk Agent Scan 已扫描 agent、MCP、skills；GitHub 也有 MCP secret scanning，但其发现有范围限制 | 暂缓 |
| C06 SkillDrift | 133 | 与 C01 更新后重验机制重叠 | 淘汰/并入相邻能力 |

**对 C02 的关键纠正：** 覆盖率只说明执行路径或行是否被运行，不证明测试断言能验证 PR 描述中的行为。原方案必须把静态差异、测试执行和语义正确性分开。即使未来重做 C02，也不得把 coverage 当成 claim truth。

### 3.2 为什么选择 BenchReceipt

- 竞争边界更窄：不是又一个 PR 文本审查器、Agent hook 或 flaky dashboard。
- 问题可复现：commit、tree、run ID、attempt、matrix、artifact digest 都能由合成数据精确控制。
- 算法可确定：身份绑定、矩阵集合比较、哈希校验、报告解析和状态聚合都可写成明确规则。
- 独立验证可行：生产实现用 Python；Oracle 用 Node.js 独立实现，不共享核心校验代码。
- 产品体验可视化：把源码身份、多个 job、报告产物和不一致边画成证据链。
- 88 小时可交付：MVP 不需要 GitHub API、LLM、远程服务或数据库。
- 传播性来自一句话可理解的价值：“这些绿色测试，真的属于这个 commit 吗？” 传播力与收购潜力分别暂评 4/5，均未验证。

### 3.3 与既有 P 系列项目的去重

| 项目 | 已有机制 | BenchReceipt 的边界 |
|---|---|---|
| P018 DualChannel | MCP server 原始结果与模型实际输入字段对照 | 不处理 MCP 请求/响应 |
| P019 ResumeMatrix | Agent checkpoint 跨版本恢复兼容 | 不处理 checkpoint |
| P020 CheckPath | 静态模拟 GitHub Actions workflow 触发与 required-check 路径 | 检查实际运行后的证据，不模拟 workflow |
| P023 SkillScope | 多宿主技能文件来源、scope 与路径安全 | 不扫描 skills |
| P024 RepoMapVerify | import graph 与仓库地图核验 | 不分析 import graph |
| P025 GuidancePulse | 指导读取 lease 与写前约束 | 不读取 Agent 指令 |
| P026 PageTrace | PDF/RAG 引文页码跨阶段追踪 | 处理 CI test artifacts 与 commit/run/matrix 身份 |

## 4. 用户流程与功能需求

### 4.1 快速开始流程

1. 用户在本地仓库安装 BenchReceipt。
2. 在 `.benchreceipt.toml` 声明 source mode、expected jobs、报告要求和最低测试数。
3. 在每个 CI job 中使用 `benchreceipt capture -- ...` 包装真实测试命令。
4. 每个 job 上传自己的 `.benchreceipt/evidence/<job-id>/` 目录，沿用 CI 平台原生 artifact 功能。
5. 汇总 job 下载后执行 `benchreceipt verify`。
6. 若全部身份与报告一致且测试成功，退出码为 0；否则输出可定位的错误类别并阻止门禁通过。
7. 可选生成 HTML 报告供 PR 维护者查看。

### 4.2 功能需求

| ID | 需求 | 优先级 | 验收依据 |
|---|---|---|---|
| FR-01 | 采集 Git commit SHA 与 tree SHA | P0 | 真实临时 Git 仓库与合成仓库对照 |
| FR-02 | 区分 PR head、merge commit、event SHA、explicit SHA | P0 | 4 种 source mode Golden |
| FR-03 | 记录 workflow run ID、attempt、workflow、job 与 matrix | P0 | 同 run 与跨 run/attempt 反例 |
| FR-04 | 包装用户显式传入的 argv 命令，`shell=False` 执行 | P0 | 参数边界、退出码与命令摘要 |
| FR-05 | 解析 JUnit XML 测试数、失败数、错误数、跳过数 | P0 | 有效、空、畸形、失败报告 |
| FR-06 | 对 JUnit / LCOV 报告计算 SHA-256 并打包 | P0 | 字节级哈希一致 |
| FR-07 | 检查必需矩阵 job 完整性、重复项和混合身份 | P0 | 50 组 S0 fixtures |
| FR-08 | 检查运行期间 tracked source 是否发生变化 | P0 | 前后 dirty state 对照 |
| FR-09 | 生成 JSON 验证结果与明确 exit code | P0 | CLI contract tests |
| FR-10 | 生成静态 HTML 证据链视图 | P1 | 桌面/窄屏截图与 UI smoke |
| FR-11 | 提供 GitHub Actions workflow 示例 | P1 | 合成 GitHub env E2E |
| FR-12 | 可选导出 in-toto Statement 结构 | P2 | Schema validation；不签名、不称为 attestation |

### 4.3 用户故事

- US-01：我想确认 Linux 与 Windows job 运行的是同一个 PR head commit。
- US-02：我想确认矩阵所有 job 来自同一个 workflow run 和 attempt。
- US-03：我想知道 JUnit/LCOV 文件是否被替换、遗漏或从旧 job 混入。
- US-04：我想把缺少证据和测试失败区分开，而不是一律显示红色。
- US-05：我想在没有 GitHub API token、LLM 或云端账号的情况下验证本地 bundle。

## 5. 核心算法与判定规则

### 5.1 身份模型

每个 job 收据包含：

- `git_head_sha`：实际 checkout 的 commit。
- `git_tree_sha`：`HEAD^{tree}` 对应的 Git tree。
- `git_head_sha_after` / `git_tree_sha_after`（v1.1.0 新增，可选）：命令结束时的 HEAD / `HEAD^{tree}`。capture 始终记录；verify 发现 after 与 before 不一致即判定源码变更（见 §5.5）。v1.2.0 起两个 after 字段都缺失的收据一律 fail-closed 为 UNBOUND + `MISSING_FIELD`，不得以 dirty/digest 规则通过。
- `source_mode`：`pr_head` / `merge_commit` / `event_sha` / `explicit_sha`。
- `expected_source_sha`：按 policy 选出的期望 SHA。
- `workflow_run_id`、`run_attempt`、`workflow_ref`、`workflow_sha`。
- `job_id`、`matrix`：矩阵单元的稳定身份。
- `argv_sha256`：规范化 argv 的哈希；默认不保存可能包含秘密的完整参数。
- `runner_fingerprint`：OS、架构、Python 与测试工具版本的白名单摘要。
- `started_at`、`finished_at`、`exit_code`。
- `reports[]`：报告类型、相对路径、字节数、SHA-256 与解析摘要。
- `source_state_before/after`：tracked diff 摘要与 dirty 标志。

### 5.2 矩阵验证

给定期望 job 集合 \(E\) 和实际 job 集合 \(A\)：

\[
missing = E - A
\]

\[
unexpected = A - E
\]

\[
duplicate = \{x \mid count_A(x) > 1\}
\]

只有当 `missing`、`unexpected`、`duplicate` 都为空，且每个 job 的 source/run/attempt 满足 policy，矩阵完整性才为 PASS。

### 5.3 身份一致性

对每个 job \(j\)：

\[
j.git\_head\_sha = policy.expected\_source\_sha
\]

\[
j.workflow\_run\_id = policy.expected\_run\_id
\]

\[
j.run\_attempt = policy.expected\_attempt
\]

对于要求同一源码树的矩阵：

\[
\forall i,j,\quad tree_i = tree_j
\]

若 policy 允许 merge commit，必须显式选择 `merge_commit`；不得自动把 PR head 与 merge SHA 当成等价值。

### 5.4 报告完整性

每个报告记录：

\[
digest = SHA256(report\_bytes)
\]

验证时重新读取 bundle 内报告并重算哈希。若路径缺失、大小不符、哈希不符或 XML 无法解析，状态不得为 `BOUND_PASS`。

JUnit 最小检查：

- `tests > 0`，且满足 policy 的 `min_tests`。
- `failures = 0`、`errors = 0`。
- `skipped` 单独报告；默认不把 skipped 自动算成 pass。
- 报告中的测试数必须与解析出的 testcase 数一致。

LCOV 只做格式与文件路径校验，记录 `SF`、`DA` 计数及报告哈希；不推断覆盖率能证明行为正确。

### 5.5 源码变更检测

`capture` 在命令开始与结束时分别采集：

- `git rev-parse HEAD`；
- `git rev-parse HEAD^{tree}`；
- `git status --porcelain=v1 --untracked-files=all`；
- tracked diff 的 SHA-256。

默认要求开始时 tracked worktree clean。测试结束后，除 policy 显式声明的 evidence output 目录外，若 tracked source 或未忽略源文件变化，记录 `SOURCE_MUTATED_DURING_RUN`。不允许把生成的报告文件当成源码变化。

**v1.1.0（ADR-005，P0-01 修复）：** 仅比较 porcelain diff 摘要与 dirty 标志无法发现 clean-tree HEAD 变化（checkout 到另一 commit 或空提交后，porcelain 输出前后皆空、dirty 标志皆为 False），v1.0.0 因此会把跑在 commit B 上的测试误证为 commit A 的证据（false `BOUND_PASS`）。v1.1.0 要求 capture 在收据 `git` 对象中记录 `head_sha_after` / `tree_sha_after`（命令结束时的 HEAD/tree），verify 在任一 after 值与其 before 值不同、或两个 after 字段只出现其一、或 after 字段存在而 before 值缺失时，一律记录 `SOURCE_MUTATED_DURING_RUN`（UNBOUND，exit 2）。**v1.2.0（ADR-007，P0-R1-01 修复，推翻 ADR-005 决策 4 的旧兼容规则）：** 两个 after 字段都缺失的收据无法证明运行中 HEAD/tree 未变化，不得 `BOUND_PASS`：verify 一律记录 `MISSING_FIELD`（UNBOUND，exit 2），该 job `jobs_verified` 为 0。两个字段仍保持可选（旧格式收据仍可解析，得 UNBOUND 而非 INVALID），只出现其一时仍按原有规则判定为 `SOURCE_MUTATED_DURING_RUN`。终审 R1 证实：删掉 e5/e6 的两个 after 字段后，旧 verifier 会把它们误判为 `BOUND_PASS`；而 e7（legacy clean checkout）与 n01（正常控制）的收据在删字段后逐字段相同，verify 作为输入的确定性函数不可能输出不同——因此旧兼容规则不可保留，方案 A（builder 给全部现有夹具补上 after 字段）是唯一自洽的修复。已知残留限制（P2-01）：运行中途修改又还原（中间 dirty、前后皆 clean）任何 before/after 快照方案都无法发现，不属于本修复范围，见 T012 LIMITATIONS。

### 5.6 状态与退出码

| 状态 | 含义 | CLI exit |
|---|---|---:|
| `BOUND_PASS` | 证据完整、身份一致、测试报告成功 | 0 |
| `BOUND_FAIL` | 证据绑定明确，但测试失败或策略条件失败 | 1 |
| `UNBOUND` | 缺失身份、矩阵、报告或无法证明关联 | 2 |
| `INVALID` | 输入格式错误、哈希损坏或 schema 不合法 | 3 |
| `INTERNAL_ERROR` | BenchReceipt 自身未预期异常 | 4 |

**禁止规则：** 缺证据、解析失败、无法读取或未知字段不得降级为 PASS；必须 `UNBOUND` 或 `INVALID`。

## 6. 数据结构与接口契约

### 6.1 目录布局

```text
.benchreceipt/
  evidence/
    <job-id>/
      receipt.json
      artifacts/
        junit.xml
        lcov.info
  verification.json
  report.html
```

### 6.2 `benchreceipt.run/v1` 示例

```json
{
  "schema": "benchreceipt.run/v1",
  "job_id": "unit-linux-py312",
  "matrix": {"os": "ubuntu-latest", "python": "3.12"},
  "git": {
    "head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "tree_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "head_sha_after": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "tree_sha_after": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "source_mode": "pr_head",
    "expected_source_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "dirty_before": false,
    "dirty_after": false
  },
  "ci": {
    "provider": "github-actions",
    "run_id": "9001",
    "run_attempt": 2,
    "workflow": "CI",
    "event_name": "pull_request"
  },
  "command": {
    "argv_sha256": "<64-hex>",
    "display": "python -m pytest -q",
    "exit_code": 0
  },
  "runner": {
    "os": "Linux",
    "arch": "x86_64",
    "python": "3.12.3"
  },
  "junit": {
    "tests": 18,
    "failures": 0,
    "errors": 0,
    "skipped": 1
  },
  "reports": [
    {
      "kind": "junit",
      "path": "artifacts/junit.xml",
      "size_bytes": 2048,
      "sha256": "<64-hex>"
    }
  ]
}
```

以上为 schema 示意；正式 JSON Schema 由 T002 冻结，禁止 worker 自行新增必填字段。

### 6.3 `.benchreceipt.toml` 示例

```toml
schema_version = 1
source_mode = "pr_head"
expected_workflow = "CI"
required_jobs = [
  "unit-linux-py312",
  "unit-windows-py312"
]
min_tests = 1
require_clean_source_after = true
same_tree_across_jobs = true
same_run_id = true
same_run_attempt = true

[reports]
junit = "required"
lcov = "optional"

[security]
store_stdout = false
store_stderr = false
store_full_environment = false
```

### 6.4 CLI 契约

```bash
benchreceipt capture \
  --job unit-linux-py312 \
  --matrix os=ubuntu-latest,python=3.12 \
  --junit .benchreceipt/out/junit.xml \
  --lcov .benchreceipt/out/lcov.info \
  -- python -m pytest -q --junitxml=.benchreceipt/out/junit.xml

benchreceipt verify \
  --policy .benchreceipt.toml \
  --evidence .benchreceipt/evidence \
  --expected-source-sha "$PR_HEAD_SHA" \
  --out .benchreceipt/verification.json

benchreceipt report \
  --input .benchreceipt/verification.json \
  --html .benchreceipt/report.html
```

CLI 参数以 T002 的冻结 schema 为准。命令执行必须 `shell=False`；用户明确传入命令后才执行，不自动执行仓库内未知脚本。

## 7. 系统架构与模块划分

### 7.1 固定架构

- **生产 CLI：** Python 3.12，标准库优先。
- **独立 Oracle：** Node.js 24 ESM；独立实现核心身份、矩阵、哈希与状态聚合，不导入 Python 生产代码。
- **测试：** pytest（开发依赖）；Oracle 使用 Node 内置 `node:test`。
- **报告：** 原生 HTML/CSS/JavaScript，内嵌资源，无 CDN。
- **存储：** 普通文件目录；不需要数据库。
- **CI：** GitHub Actions 示例 workflow + 官方 artifact upload/download action；BenchReceipt 本身不调用 GitHub API。
- **网络：** 产品运行时无网络请求；安装依赖仅在开发/安装阶段进行。

### 7.2 模块

| 模块 | 职责 |
|---|---|
| `capture.py` | 包装命令，收集运行前后证据 |
| `git_identity.py` | commit/tree/status/diff 采集 |
| `ci_metadata.py` | GitHub Actions 环境变量与 event JSON 解析 |
| `command.py` | argv 规范化、子进程、退出码 |
| `reports/junit.py` | JUnit XML 解析 |
| `reports/lcov.py` | LCOV 解析 |
| `bundle.py` | 文件复制、路径净化、哈希清单 |
| `policy.py` | TOML 配置与 schema 校验 |
| `verify.py` | 矩阵、身份、报告和状态聚合 |
| `canonical.py` | 规范化 JSON 与确定性 digest |
| `render/html.py` | 静态 HTML 证据链 |
| `cli.py` | argparse 命令与 exit code |

### 7.3 数据流

```text
Git worktree + CI environment
          |
          v
      capture
          |
          +---- command argv (shell=False)
          +---- Git identity before/after
          +---- run / attempt / matrix
          +---- JUnit / LCOV report bytes
          |
          v
  per-job receipt bundle
          |
          v
   CI artifact transport
          |
          v
  verify(policy, expected SHA)
          |
          +---- matrix set comparison
          +---- source/run/attempt comparison
          +---- report digest and parser checks
          +---- deterministic status
          |
          v
 JSON receipt + static HTML report
```

## 8. S0 硬门与 Golden 验收

### 8.1 52 组合成 fixtures

| 类别 | 数量 | 预期 |
|---|---:|---|
| 正常控制：单 job / 多矩阵 / PR head / merge commit | 16 | 16/16 `BOUND_PASS` |
| 错误 source SHA / head-merge 混淆 | 4 | 4/4 检出 |
| tree SHA 混合 | 4 | 4/4 检出 |
| run ID / attempt 混合 | 4 | 4/4 检出 |
| 矩阵缺失 / 重复 / 多余 | 4 | 4/4 检出 |
| 源码运行前后 dirty | 4 | 4/4 检出 |
| clean-tree HEAD 变化 / 空提交（e5–e6，v1.1.0 新增） | 2 | 2/2 检出 |
| legacy 形状无 after 字段（e7–e8，v1.2.0 新增） | 2 | 2/2 检出 |
| 报告缺失 / 哈希不符 | 4 | 4/4 检出 |
| JUnit 失败 / 空 / 畸形 / 退出码矛盾 | 4 | 4/4 检出 |
| argv/policy 不符或关键字段缺失 | 4 | 4/4 检出 |
| **合计** | **52** | **16 正常 + 36 植入异常** |

### 8.2 独立 Oracle

- 生产：Python 3.12。
- Oracle：Node.js 24 ESM。
- Oracle 不得 import、调用或复制生产模块。
- Golden expected 由 fixture 作者依据冻结规则手工定义；不得由生产实现生成后直接当作真值。
- Oracle 与生产实现比较 status、reason codes、missing/unexpected/duplicate jobs、source/run/attempt mismatch 和 artifact digest results。

### 8.3 S0 通过门槛（全部必须通过）

1. 正常控制 `16/16 BOUND_PASS`。
2. 植入异常 `36/36` 检出且 reason code 正确。
3. False PASS = 0。
4. False block = 0。
5. 生产 / Oracle parity = `52/52`。
6. 规范化结果连续重放 100 次，SHA-256 只有一个值。
7. 100 个 job manifests 的本机验证 P95 ≤ 1 秒（T001 记录硬件环境）。
8. 离线运行成功，外部网络请求 = 0。
9. `capture` 不记录完整环境变量、stdout/stderr 或绝对用户路径。
10. S0 fixture、policy、Oracle、门禁脚本均有可复现日志与哈希。

任何一项未通过：S0 = FAIL，停止；不得以降低阈值、删掉失败 fixture 或改写 Golden expected 的方式宣布通过。

### 8.4 停止条件

- 无法可靠区分 PR head 与 merge commit：STOP。
- 无法发现跨 attempt 混包：STOP。
- 多矩阵聚合必须依赖 GitHub API token 或收费服务：STOP / 重新设计。
- 竞争核查发现一个维护活跃、功能完全等价的本地多矩阵证据绑定工具：Muse 暂停 T005，提交证据并请求重新立项决策。
- 若只能生成静态 hash 清单，不能验证 job/run/attempt/matrix 关系：STOP。

### 8.5 v1.1.0 修订记录（ADR-005，2026-11-18）

- **原因：** T011 发现 P0-01——运行中途 clean-tree HEAD 变化（checkout 到另一 commit / 空提交）对 v1.0.0 的 verifier 不可见，导致 false `BOUND_PASS`。Sam 批准 Option 1 修复（2026-11-18 ~00:03 GMT）。
- **变更：** `benchreceipt.run/v1` 增加可选字段 `git.head_sha_after` / `git.tree_sha_after`（40-hex；capture 始终记录，verify 按 §5.5 判定）；不新增必填字段、枚举或 reason code。S0 fixtures 增加 e5（clean-tree HEAD 变化）与 e6（空提交），冻结集 48 → 50，植入异常 32 → 34，parity 48/48 → 50/50。既有 Golden 值未改动。
- **范围：** 本次修订是唯一获批的规格变更；其余内容仍以 v1.0.0 为准。

### 8.6 v1.2.0 修订记录（ADR-007，2026-11-18）

- **原因：** 终审 R1 发现 P0-R1-01——删掉 `git.head_sha_after` / `git.tree_sha_after` 两个可选字段后，e5/e6 的收据在 Python 验证器与 Node Oracle 下均由 UNBOUND 变为 BOUND_PASS（评审方 wheel 脚本与夹具反例两路复现）。根因是 ADR-005 决策 4 保留的旧版兼容规则：两个 after 字段都缺失时退回 dirty/digest 判定，而 clean-tree HEAD 变化对 dirty/digest 不可见。上一轮修复工人证明 e7（按原设计：e5 删掉两个 after 字段）与现有控制夹具 n01 的输入逐字段相同，而 Golden 要求 n01→BOUND_PASS、e7→UNBOUND——verify 是输入的确定性函数，两者不可能输出不同；协调员裁决采用方案 A。
- **变更：** `benchreceipt.run/v1` 的两个 after 字段保持可选（旧格式收据仍可解析，得 UNBOUND 而非 INVALID），只改 description 文字；verify（Python 与 Node Oracle 同步）改为 fail-closed：两个 after 字段都缺失 → UNBOUND + `MISSING_FIELD`（复用已冻结的 UNBOUND 类 reason code），该 job `jobs_verified` 为 0，CLI exit 2；只出现其一仍按原有规则判 `SOURCE_MUTATED_DURING_RUN`。S0 fixtures 增加 e7（legacy clean checkout）与 e8（legacy empty commit），冻结集 50 → 52，植入异常 34 → 36，parity 50/50 → 52/52；同时 builder 给其余 50 个夹具补上 after 字段（值与 before 一致，e5/e6 保持原样），既有 Golden 值未改动。推翻 ADR-005 决策 4。
- **范围：** 本次修订是唯一获批的规格变更；其余内容仍以 v1.1.0 为准。

## 9. UI 与交互设计

### 9.1 主报告页面

- 顶栏：`BOUND_PASS / BOUND_FAIL / UNBOUND / INVALID`、项目名、生成时间、expected source SHA。
- 左侧：源代码身份卡，显示 expected SHA、实际 HEAD、tree SHA、source mode。
- 中央：矩阵 job 卡片网格，每张卡显示 OS、runtime、job ID、run ID、attempt、测试数、失败数、报告完整性。
- 右侧：证据链状态与异常列表，点击异常定位具体 job 和字段。
- 底部：报告文件清单、SHA-256、大小、解析摘要、工具版本和“本工具能证明/不能证明什么”。

### 9.2 状态颜色与含义

- `BOUND_PASS`：绿色；所有必需证据绑定且测试报告成功。
- `BOUND_FAIL`：红色；证据属于预期运行，但测试失败或 policy 明确失败。
- `UNBOUND`：琥珀色；缺少证据或身份不完整，不能得出成功结论。
- `INVALID`：深红色；格式、哈希或 schema 损坏。

颜色不是唯一信息通道；每个状态必须同时显示文字、图标和原因代码。

### 9.3 交互

- 点击 job 卡展开其 receipt JSON 摘要。
- 点击 source mismatch 显示 expected / actual SHA 对照。
- 点击 matrix missing 显示缺少的 job ID。
- 点击 artifact mismatch 显示文件名、expected digest、actual digest。
- 提供“复制 JSON 路径 / 复制错误摘要”操作。
- 不提供自动修复、自动重跑或自动修改 workflow 的按钮。

### 9.4 可访问性

- 键盘可完成全部展开/折叠与复制操作。
- 使用语义化标题、表格和按钮。
- 深色/浅色系统主题自动适配。
- 320px 窄屏下 job 卡改为单列；不出现横向滚动作为唯一阅读方式。
- 颜色对比度至少符合 WCAG AA 目标；此项以自动化静态检查和截图检查为准，不宣称完整无障碍认证。

## 10. 技术栈与版本策略

| 组件 | 选择 | 约束 |
|---|---|---|
| Runtime | CPython 3.12.x | T001 探测后锁 patch 版本；最低 3.12 |
| CLI | `argparse` | Python 标准库 |
| TOML | `tomllib` | Python 标准库 |
| XML | `xml.etree.ElementTree` | JUnit parser；禁用外部实体，不解析 DTD |
| Hash | `hashlib.sha256` | Python 标准库 |
| Git | `git` CLI | 通过 `subprocess`、`shell=False` 调用 |
| HTML | 原生 HTML/CSS/JS | 不用 CDN、远程字体或分析脚本 |
| Dev tests | pytest | 仅开发依赖，锁定到 lock 文件 |
| Oracle | Node.js 24 ESM | 开发/验收工具，不是产品 runtime |
| Packaging | `pyproject.toml` + wheel | 可离线安装；运行时无第三方依赖 |

版本策略：

1. T001 记录真实 VM 的 Python、Node、Git、OS、CPU、RAM、浏览器和磁盘。
2. Python 依赖锁定到 `requirements-dev.lock`；产品运行时依赖列表必须为空。
3. Node Oracle 依赖锁定在 `package-lock.json`；不进入 wheel。
4. 依赖升级必须通过 ADR；禁止使用 `latest` 作为可复现验收版本。
5. Windows 与 Linux 至少一套实际运行；未实测平台必须标记 `NOT_TESTED`，不能宣称跨平台通过。

## 11. 隐私、安全与许可证风险

### 11.1 数据最小化

- 不读取 prompt、模型回复、API key、cookie 或用户凭据。
- 不保存完整环境变量；只读固定 allowlist 的非敏感字段。
- 不保存完整 stdout/stderr；默认只记录 exit code 和摘要哈希。
- 命令参数默认只保存 argv digest 与安全显示串；检测含 token/password/secret/api-key/apikey/api_key/key/auth/passwd/pwd/passphrase/credential/private-key/private_key 的参数并脱敏（与 `command.py` 的 `SECRET_HINTS` 一致，FIX-R13a / F-09）。
- 报告只存相对路径；不写用户 home 绝对路径。
- 本地运行不发送遥测；产品没有网络 client。
- GitHub Actions artifact 上传由用户 workflow 的原生步骤控制，不由 BenchReceipt 上传。

### 11.2 安全边界

- `capture` 只执行用户在命令行显式传入的命令。
- `subprocess` 必须 `shell=False`，不拼接 shell 字符串。
- 不自动执行仓库中的未知脚本、workflow、build hook 或 package install。
- 路径必须规范化并限制在 evidence bundle 根目录；拒绝 `..`、绝对路径逃逸和不受支持的符号链接。
- XML parser 不加载外部实体、不访问网络。
- 对不可信 receipt JSON 设置文件大小、数组长度和字符串长度上限。
- 本项目的哈希一致性不是身份签名；恶意 runner 可伪造整个 bundle。威胁模型仅覆盖意外错配、过期 artifact、配置错误和报告损坏。

### 11.3 许可证

- 自有代码：MIT。
- 第三方依赖必须在 T013 生成 license inventory。
- 生产依赖优先 Python 标准库，避免运行时依赖。
- 开发依赖与 Oracle 依赖也要登记许可证。
- README 必须保留 MIT 声明与第三方 notices。

## 12. 验收指标与可复现样例

### 12.1 核心正确性指标

| 指标 | MVP 门槛 | 证明方式 |
|---|---:|---|
| 正常 fixture 正确通过 | 16/16 | S0 Golden |
| 植入异常正确检出 | 36/36 | S0 Golden |
| False PASS | 0 | adversarial fixtures |
| False block | 0 | normal controls |
| Production / Oracle parity | 52/52 | Python vs Node |
| Determinism | 100 次 1 hash | canonical result |
| 多矩阵身份一致性 | 100% fixtures | source/run/attempt/matrix |
| 报告哈希核验 | 100% fixtures | SHA-256 recompute |
| 离线运行 | PASS | 禁网环境执行 |
| P95 | 100 manifests ≤ 1s | T001 固定 VM |

### 12.2 样例 A：正常两矩阵

输入：

- expected source SHA：`aaaaaaaa...`（40 hex）
- run ID：`9001`
- attempt：`2`
- required jobs：`unit-linux-py312`、`unit-windows-py312`
- 两个 job 的 tree SHA 相同，JUnit 均 `failures=0, errors=0`。

预期：

```json
{
  "status": "BOUND_PASS",
  "missing_jobs": [],
  "unexpected_jobs": [],
  "identity_mismatches": [],
  "report_errors": [],
  "jobs_verified": 2
}
```

### 12.3 样例 B：混入旧 attempt

输入：

- Linux job：run `9001`, attempt `2`。
- Windows job：run `9001`, attempt `1`。
- 两份 JUnit 均为绿色。

预期：

```json
{
  "status": "UNBOUND",
  "reason_codes": ["RUN_ATTEMPT_MISMATCH"],
  "jobs_verified": 1
}
```

### 12.4 样例 C：PR head / merge SHA 错配

Policy 要求 `source_mode="pr_head"`，但实际 checkout `HEAD` 是 merge commit。

预期：

```json
{
  "status": "UNBOUND",
  "reason_codes": ["SOURCE_SHA_MISMATCH"],
  "expected_source_mode": "pr_head"
}
```

## 13. 交付物

### 13.1 用户可用产品

- `benchreceipt` Python CLI。
- `capture / verify / report` 三个命令。
- `.benchreceipt.toml` policy schema。
- `benchreceipt.run/v1` JSON Schema。
- GitHub Actions 完整示例 workflow。
- 静态 HTML 报告。
- 可离线运行的示例 bundle。

### 13.2 开发与验收资产

- 52 个冻结 S0 fixtures（e5/e6 由 v1.1.0 / ADR-005 增加；e7/e8 由 v1.2.0 / ADR-007 增加）。
- 手工 Golden expected。
- Node.js 独立 Oracle。
- 自动化测试与 100 次 determinism 日志。
- `S0_GATE.json`、`S0_REPORT.md`。
- `REVIEW_INDEX.md`、`REVIEW_PACK_XX.md`。
- `RELEASE_MANIFEST.json`、`SHA256SUMS.txt`。
- Git commit、Git bundle、source ZIP、dist ZIP。
- 运行说明、限制说明、许可证清单、截图与测试日志。

### 13.3 明确未完成事项

在真实施工和终审之前，以下全部是 `NOT_VERIFIED`：

- 当前 VM 的工具链版本。
- S0 的 52/52 结果。
- 独立 Oracle parity。
- 100 次稳定性。
- UI 截图。
- Windows 实测。
- release ZIP 哈希。
- GitHub Actions 真仓库集成。
- 用户价值、市场规模和付费意愿。

## 14. 参考资料与借鉴边界

| 资料 | URL | 用途 | 借鉴什么 | 不复制什么 |
|---|---|---|---|---|
| GitHub Actions events | https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows | PR head / merge SHA 语义 | 显式 source mode | 不实现 workflow 模拟器 |
| GitHub Artifact Attestations | https://docs.github.com/en/actions/concepts/security/artifact-attestations | 官方 artifact provenance | 明确签名与 provenance 的边界 | 不重做 GitHub 签名系统 |
| in-toto Test Result Predicate | https://github.com/in-toto/attestation/blob/main/spec/predicates/test-result.md | 标准测试结果结构 | subject、configuration、result、test names | 不发明新的 attestation 标准；MVP 不签名 |
| in-toto paper (USENIX Security 2019) | https://ssl.engineering.nyu.edu/papers/torres-toto-usenix19.pdf | 软件供应链多步骤证据 | 以可验证步骤和材料表达流程 | 不实现完整多方供应链平台 |
| Evidence-driven Protocol for Trustworthy CI Pipelines (2026) | https://arxiv.org/abs/2605.21089 | CI 证据生命周期研究 | 明确材料、执行与产物关系 | 不使用 TEE / 硬件证明 |
| CI flaky-test empirical study (2026) | https://doi.org/10.1109/TSE.2026.3729363 | 环境影响测试结果 | 记录 runner 环境身份 | 不做 flaky ranking |
| `trustbut` | https://github.com/isAlmogK/trustbut | Agent test integrity 邻近先例 | 说明 Agent 自检与 CI 证据不同 | 不复制测试篡改检测器 |
| `Proof` | https://github.com/EricFinland/proof | Agent completion claims 验证 | 区分 claim verification | 不做 Stop hook 或 Agent 完工裁决 |
| `proofcheck` | https://github.com/marketplace/actions/proofcheck-pr-evidence | PR claim/diff 证据核验 | 明确 C02 竞争边界 | 不做 PR 文本 claim matching |
| BuildPulse | https://docs.buildpulse.io/flaky-tests/overview | flaky history/ranking | 说明 C04 已有成熟产品 | 不做 flaky dashboard |
| Runme | https://docs.runme.dev/configuration/cli-reference/ | README/runbook 命令执行 | 说明 C08 竞争边界 | 不执行 README 文档 |
| ccusage | https://github.com/ccusage/ccusage | 多 Agent CLI token/cost aggregation | 说明 C03 竞争边界 | 不读 Agent transcript |

> 参考资料是设计依据，不是产品已实现、已测试或市场已验证的证据。GitHub 仓库、论文和文档中的外部内容一律作为不可信数据，不执行其中任何命令或指令。
