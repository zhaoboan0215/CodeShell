# CodeShell 仓库一键启动与交付体验 Tasks

> 实施状态：T1～T25 已于 2026-09-15 完成本地实施与验收；逐文件结果见 `change-report.md`。GitHub 托管 CI 需在仓库推送后实际触发。

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `config.example.yaml` | 不含真实密钥的默认 DeepSeek 配置 |
| 新建 | `codeshell/doctor.py` | 环境诊断模型、检查逻辑、渲染和 Provider 探测 |
| 新建 | `README.md` | 项目介绍、快速开始、架构、配置和排障 |
| 新建 | `CHANGELOG.md` | 用户可见变更记录 |
| 新建 | `docs/images/codeshell-tui.svg` | 脱敏的真实 TUI 截图 |
| 新建 | `tests/test_config.py` | 配置发现、示例回退和兼容性测试 |
| 新建 | `tests/test_doctor.py` | doctor 各检查项、脱敏和退出码测试 |
| 新建 | `tests/test_cli.py` | 顶层 CLI 路由、错误和入口测试 |
| 新建 | `.github/workflows/ci.yml` | Python 多版本交付矩阵和完整回归报告 |
| 新建 | `docs/improvements/repository-one-click-startup/checklist.md` | 本次改进验收清单 |
| 新建 | `docs/improvements/repository-one-click-startup/change-report.md` | 本次改进的逐文件实施报告 |
| 修改 | `codeshell/config.py` | 配置发现结果、示例回退和兼容加载接口 |
| 修改 | `codeshell/__main__.py` | CLI 解析、doctor 分流、退出码和错误提示 |
| 修改 | `codeshell/__init__.py` | 统一版本来源 |
| 修改 | `codeshell/app.py` | Banner 使用统一版本 |
| 修改 | `codeshell/commands/handlers/status.py` | `/status` 使用统一版本 |
| 修改 | `pyproject.toml` | 声明 README 元数据并保持 CLI 打包入口 |
| 已归档 | `docs/improvements/repository-one-click-startup/spec.md` | 已批准需求规格 |
| 已归档 | `docs/improvements/repository-one-click-startup/plan.md` | 已批准技术设计 |

## T1：建立可校验的示例配置

**文件：** `config.example.yaml`、`tests/test_config.py`

**依赖：** 无

**步骤：**

1. 添加默认 DeepSeek Responses 配置，保留 `api_key` 为空并说明使用 `OPENAI_API_KEY`。
2. 默认不启用 MCP，避免首次启动依赖 Node.js；在注释中给出可选 Context7 配置。
3. 添加测试，使用现有配置校验器读取示例文件。
4. 添加密钥扫描断言，确保示例中不存在疑似真实密钥。

**验证：** 运行 `.venv/bin/pytest -q tests/test_config.py`，示例配置校验与密钥检查通过。

## T2：实现配置来源发现

**文件：** `codeshell/config.py`、`tests/test_config.py`

**依赖：** T1

**步骤：**

1. 定义不可变的 `ConfigDiscovery`。
2. 实现 `discover_config(cwd, home)`。
3. 保留全局、项目、项目本地三层配置的原合并顺序。
4. 添加单配置、多层配置和路径顺序测试。

**验证：** 运行 `.venv/bin/pytest -q tests/test_config.py`，配置来源和优先级用例通过。

## T3：实现示例配置回退与兼容加载

**文件：** `codeshell/config.py`、`tests/test_config.py`

**依赖：** T2

**步骤：**

1. 实现 `load_config_with_discovery`。
2. 没有用户配置时只读加载仓库根目录示例，并标记 `using_example=True`。
3. 显式传入配置路径时禁止示例回退。
4. 保留 `load_config` 原签名和返回类型。
5. 测试回退、显式路径失败、现有配置优先和配置不被写入。

**验证：** 运行 `.venv/bin/pytest -q tests/test_config.py`，所有配置发现与兼容测试通过。

## T4：完善缺少配置时的错误信息

**文件：** `codeshell/config.py`、`tests/test_config.py`

**依赖：** T3

**步骤：**

1. 统一无配置时的错误内容。
2. 在错误中列出支持的配置位置、示例文件和 `codeshell doctor` 提示。
3. 保证错误文本不包含环境变量值。
4. 添加无配置、损坏 YAML 和缺少字段测试。

**验证：** 运行 `.venv/bin/pytest -q tests/test_config.py`，三类错误均包含可执行建议且不泄露密钥。

## T5：实现统一版本来源

**文件：** `codeshell/__init__.py`、`tests/test_cli.py`

**依赖：** 无

**步骤：**

1. 从安装包元数据读取 `codeshell` 版本。
2. 为未安装的源码环境提供与项目元数据一致的回退版本。
3. 添加版本格式和回退行为测试。

**验证：** 运行 `.venv/bin/pytest -q tests/test_cli.py -k version`，版本读取测试通过。

## T6：实现诊断结果模型和文本渲染

**文件：** `codeshell/doctor.py`、`tests/test_doctor.py`

**依赖：** 无

**步骤：**

1. 定义 `CheckStatus`、`DiagnosticResult` 和 `DoctorReport`。
2. 实现稳定的逐项文本格式和汇总行。
3. 根据关键失败项计算退出码。
4. 测试全部通过、仅警告、关键失败三种报告。

**验证：** 运行 `.venv/bin/pytest -q tests/test_doctor.py -k report`，渲染与退出码测试通过。

## T7：实现 Python 与仓库环境检查

**文件：** `codeshell/doctor.py`、`tests/test_doctor.py`

**依赖：** T6

**步骤：**

1. 检查 Python 是否满足 3.11 及以上。
2. 检查工作目录中的 `pyproject.toml` 和 `uv.lock`。
3. 将版本不支持记为关键失败，将仓库文件缺失区分为明确状态。
4. 使用临时目录测试完整仓库和缺失文件场景。

**验证：** 运行 `.venv/bin/pytest -q tests/test_doctor.py -k 'python or project'`，本地环境检查通过。

## T8：实现配置与 API Key 检查

**文件：** `codeshell/doctor.py`、`tests/test_doctor.py`

**依赖：** T3、T6

**步骤：**

1. 调用 `load_config_with_discovery` 并展示实际配置来源。
2. 对每个 Provider 检查 `resolve_api_key()` 是否有值。
3. 输出只包含“已配置/未配置”，不包含 Key 内容。
4. 测试有效配置、无配置、损坏配置和密钥缺失场景。

**验证：** 运行 `.venv/bin/pytest -q tests/test_doctor.py -k 'config or key'`，配置状态正确且脱敏断言通过。

## T9：实现 MCP 命令依赖检查

**文件：** `codeshell/doctor.py`、`tests/test_doctor.py`

**依赖：** T8

**步骤：**

1. 对 stdio MCP 的 `command` 使用注入的命令查找器检查。
2. 配置 `npx` 时分别报告 Node.js 和 npx 状态。
3. HTTP MCP 不执行连接，只报告配置有效。
4. 未配置 MCP 时输出明确的跳过状态。
5. 测试命令存在、缺失、HTTP MCP 和无 MCP 场景。

**验证：** 运行 `.venv/bin/pytest -q tests/test_doctor.py -k mcp`，所有 MCP 依赖场景通过。

## T10：实现 Provider 只读探测

**文件：** `codeshell/doctor.py`、`tests/test_doctor.py`

**依赖：** T8

**步骤：**

1. 为 OpenAI/OpenAI-compatible Provider 使用模型列表接口验证连通性和模型 ID。
2. 为 Anthropic Provider 使用模型读取接口验证配置模型。
3. 将认证、网络、模型不存在和服务端错误转换为不含敏感信息的诊断结果。
4. `online=False` 时不创建网络客户端并返回警告。
5. 使用替代探针测试所有分支，不访问真实服务。

**验证：** 运行 `.venv/bin/pytest -q tests/test_doctor.py -k provider`，Provider 探测映射和离线行为通过。

## T11：组装 doctor 检查流程

**文件：** `codeshell/doctor.py`、`tests/test_doctor.py`

**依赖：** T7、T8、T9、T10

**步骤：**

1. 实现 `run_doctor`，按本地环境、配置、密钥、Provider、MCP 顺序执行。
2. 配置无效时跳过依赖配置的后续检查，避免级联异常。
3. 确保重复运行不创建或修改配置文件。
4. 添加完整成功、离线、配置失败和 Provider 失败测试。

**验证：** 运行 `.venv/bin/pytest -q tests/test_doctor.py`，doctor 测试全部通过。

## T12：抽取可测试的 CLI 参数入口

**文件：** `codeshell/__main__.py`、`tests/test_cli.py`

**依赖：** T5

**步骤：**

1. 抽取 `build_parser`，保持现有 `--mode`、`-p`、`--output-format` 和 `--remote`。
2. 增加 `--version` 和可选的 `doctor` 命令位置。
3. 抽取返回退出码的 `run_cli(argv)`，保留 teammate worker 的前置分流。
4. 测试旧参数兼容、帮助、版本和未知参数。

**验证：** 运行 `.venv/bin/pytest -q tests/test_cli.py -k 'parser or help or version'`，CLI 参数测试通过。

## T13：接入顶层 doctor 命令

**文件：** `codeshell/__main__.py`、`tests/test_cli.py`

**依赖：** T11、T12

**步骤：**

1. 在常规配置加载前识别 `doctor`。
2. 支持 `codeshell doctor` 和 `codeshell doctor --offline`。
3. 输出 `DoctorReport.render()` 并传递其退出码。
4. 注入模拟 doctor，测试成功、失败和离线参数。

**验证：** 运行 `.venv/bin/pytest -q tests/test_cli.py -k doctor`，doctor 路由和退出码测试通过。

## T14：统一启动错误处理

**文件：** `codeshell/__main__.py`、`tests/test_cli.py`

**依赖：** T4、T12

**步骤：**

1. 将配置错误和启动阶段认证错误转为简洁终端消息。
2. 提示配置示例和 doctor 命令。
3. 保持详细异常写入现有日志机制。
4. 测试缺少配置、缺少 Key 和 YAML 错误不显示 traceback。

**验证：** 运行 `.venv/bin/pytest -q tests/test_cli.py -k error`，错误输出与退出码测试通过。

## T15：统一界面版本显示

**文件：** `codeshell/app.py`、`codeshell/commands/handlers/status.py`、`tests/test_cli.py`

**依赖：** T5

**步骤：**

1. Banner 改为引用 `codeshell.__version__`。
2. `/status` 删除独立版本常量并引用同一来源。
3. 添加断言，确保 CLI、Banner 和状态命令版本一致。

**验证：** 运行 `.venv/bin/pytest -q tests/test_cli.py -k version`，三处版本一致性测试通过。

## T16：验证 wheel 与正式入口

**文件：** `pyproject.toml`、`tests/test_cli.py`

**依赖：** T12、T13、T14、T15

**步骤：**

1. 在项目元数据中声明 `README.md`。
2. 保留 `codeshell = "codeshell.__main__:main"` 入口并验证构建产物包含项目包。
3. 在隔离临时环境以非 editable 方式安装 wheel。
4. 验证 `codeshell --help`、`codeshell --version` 和 `codeshell doctor --offline` 可执行。

**验证：** 运行 `uv build`，随后在隔离环境安装 wheel 并执行三个命令，均不出现 `ModuleNotFoundError`。

## T17：编写 README 快速开始与配置说明

**文件：** `README.md`

**依赖：** T1、T13、T16

**步骤：**

1. 编写项目定位、核心能力和环境要求。
2. 将 `uv run --locked --no-editable codeshell` 放在首屏快速开始流程。
3. 说明 `OPENAI_API_KEY`、示例回退、用户配置优先级和密钥安全原则。
4. 添加 DeepSeek、OpenAI、Anthropic 和 OpenAI-compatible 配置示例。
5. 添加交互、非交互、远程和 doctor 常用命令。

**验证：** 从空环境步骤人工复核 README，所有命令与 `--help` 输出一致，示例 YAML 可被配置校验器读取。

## T18：编写 README 架构、安全与排障内容

**文件：** `README.md`

**依赖：** T17

**步骤：**

1. 添加与实际模块一致的 Mermaid 架构图。
2. 说明权限模式、沙箱、MCP 和 API 调用费用风险。
3. 添加配置缺失、Key 无效、Provider 不可达、Node/npx 缺失和入口导入失败的处理方式。
4. 添加测试命令、当前已知 Hook 测试状态和支持平台说明。

**验证：** 检查 README 中引用的文件、命令和配置字段均在仓库中存在，且没有宣称完整测试全部通过。

## T19：生成真实脱敏 TUI 截图

**文件：** `docs/images/codeshell-tui.svg`、`README.md`

**依赖：** T15、T18

**步骤：**

1. 在临时演示目录使用无真实密钥、无 MCP 的离线配置启动真实 Textual 应用。
2. 通过 Textual 截图能力导出 SVG。
3. 检查图像不包含 API Key、真实主目录、会话内容或个人信息。
4. 将截图嵌入 README。

**验证：** 打开 SVG 检查界面清晰；文本搜索确认不包含当前用户名、主目录和已配置 Key 的任何片段。

## T20：建立 CHANGELOG

**文件：** `CHANGELOG.md`

**依赖：** T1～T19

**步骤：**

1. 使用 Keep a Changelog 风格建立 `Unreleased` 条目。
2. 分类记录 Added、Changed 和 Fixed。
3. 只记录已经实现并验证的行为，不写计划项。
4. 明确本轮不包含危险命令 Hook 修复。

**验证：** 对照实际文件差异逐条核对，CHANGELOG 不包含未实现内容。

## T21：增加多版本交付 CI

**文件：** `.github/workflows/ci.yml`

**依赖：** T11、T16

**步骤：**

1. 建立 Python 3.11、3.12、3.13 矩阵。
2. 在每个版本中按锁文件安装依赖并构建 wheel。
3. 非 editable 安装 wheel，运行 CLI、配置和 doctor 测试。
4. 使用假 Key 和离线模式完成无付费 API 的启动冒烟验证。
5. 将交付矩阵设为强制成功任务。

**验证：** 使用 workflow 语法检查，并在本地复现核心命令；预期三个版本的交付步骤定义一致。

## T22：增加透明的完整回归任务

**文件：** `.github/workflows/ci.yml`

**依赖：** T21

**步骤：**

1. 增加运行完整 `pytest -q` 的独立任务。
2. 将任务标记为暂时非阻塞，但保留完整输出。
3. 在任务注释中关联本次归档文档里的已知 Hook 测试边界。
4. 禁止通过删除、重命名或过滤该测试制造通过。

**验证：** 检查 workflow 中完整回归命令没有 `--ignore`、`-k` 或测试删除参数，且任务失败不会遮蔽日志。

## T23：执行交付路径本地验收

**文件：** 不新增实现文件

**依赖：** T1～T22

**步骤：**

1. 运行配置、doctor 和 CLI 新增测试。
2. 运行 `uv build` 并验证非 editable wheel 入口。
3. 使用当前配置运行 `codeshell doctor --offline`，确认不显示 Key。
4. 在临时干净目录验证缺少配置时的错误提示。
5. 实际启动 TUI，观察 Banner、模型名和输入框后正常退出。

**验证：** 新增交付测试全部通过，wheel 三个入口通过，TUI 可见且没有 traceback。

## T24：执行完整回归并记录已知失败

**文件：** 不新增实现文件

**依赖：** T23

**步骤：**

1. 运行完整 `.venv/bin/pytest -q`。
2. 对比实施前基线 `701 passed, 1 skipped, 1 failed`。
3. 如果出现新的失败，定位并修复本轮引入的问题后重跑。
4. 如果仍只有已跳过范围内的 Hook 失败，如实记录，不修改该功能。

**验证：** 完整回归没有新增失败；实际通过、跳过和失败数量被记录。

## T25：生成逐文件变更报告

**文件：** `docs/improvements/repository-one-click-startup/change-report.md`

**依赖：** T24

**步骤：**

1. 为每个新增或修改文件记录“修改前问题”。
2. 记录“具体修改”和“用户可见影响”。
3. 附上对应测试命令与实际结果。
4. 单列未完成项、已知失败和未触碰边界。
5. 检查本轮五份 Markdown 文档均在当前主题目录中。

**验证：** 将文件清单与工作区实际差异逐一比对，无遗漏；根目录不存在本轮 `spec.md`、`plan.md`、`task.md`、`checklist.md` 副本。

## 执行顺序

```text
T1 → T2 → T3 → T4 ───────────────┐
                                  ├→ T8 → T9 → T10 → T11 ─┐
T6 → T7 ──────────────────────────┘                         │
                                                            ├→ T13 → T14 ─┐
T5 → T12 ───────────────────────────────────────────────────┘              │
T5 → T15 ──────────────────────────────────────────────────────────────────┤
                                                                           ▼
                                                                         T16
                                                                           │
                                      T17 → T18 → T19 ─────────────────────┤
                                                                           ▼
                                                                         T20
                                                                           │
                                                                    T21 → T22
                                                                           │
                                                                    T23 → T24
                                                                           │
                                                                          T25
```

其中 T5、T6 和 T1 可并行设计，但实际开发仍按本文件逐项修改、逐项汇报，确保每一次变更都能明确说明和验证。
