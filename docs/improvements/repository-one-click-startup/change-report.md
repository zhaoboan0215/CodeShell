# CodeShell 仓库一键启动与交付体验 Change Report

## 交付结论

本次改进已在 2026-09-15 完成本地实施与验收。克隆仓库后，在已安装 `uv`、Python 3.11～3.13 且设置 Provider API Key 的前提下，正式启动命令为：

```bash
uv run --locked --no-editable codeshell
```

在不含 `.venv`、项目本地配置和构建产物的临时干净副本中，命令已实际完成虚拟环境创建、项目构建、53 个包安装并打开 TUI。界面显示 `CodeShell v0.2.0`、`deepseek-flash` 和输入框；再次执行能够复用环境并正常启动。

## 逐文件变更

| 文件 | 修改前问题 | 具体修改 | 用户可见影响 | 验证证据 |
|---|---|---|---|---|
| `config.example.yaml` | 仓库没有安全、可直接用于首次启动的公开配置 | 新增无密钥 DeepSeek Responses 配置；默认关闭 MCP；用注释提供可选 Context7 配置 | 只设置 `OPENAI_API_KEY` 即可首次启动，不强制安装 Node.js | 配置校验、敏感信息测试及干净副本启动通过 |
| `codeshell/config.py` | 配置加载只接受用户/项目文件，无法说明实际来源；错误信息缺少操作指引 | 新增不可变 `ConfigDiscovery`、`discover_config`、`load_config_with_discovery`；保留原三层优先级和 `load_config` 兼容入口；仅在三层均不存在时只读回退示例；为缺失、不可读、YAML 损坏和字段错误附加路径与修复提示 | 新克隆可以直接使用安全示例；已有配置行为不变；配置错误更容易自行排查 | `tests/test_config.py` 与完整回归相关用例通过 |
| `codeshell/doctor.py` | 没有统一的环境自检命令 | 新增 PASS/WARN/FAIL 结果模型、退出码、Python/仓库/配置/API Key/MCP 检查、在线和离线 Provider 探测；输出不包含 Key；OpenAI-compatible 模型列表按 SDK 页对象的 `data` 字段读取，并兼容直接 iterable 的测试替身 | 可用 `codeshell doctor [--offline]` 快速定位安装、配置、网络、模型与 MCP 问题 | 19 项 doctor 单测通过；当前 DeepSeek 在线检查 8 PASS、0 WARN、0 FAIL |
| `codeshell/__main__.py` | CLI 解析与执行耦合；没有 doctor/version；启动错误可能暴露内部堆栈 | 抽取 `build_parser()` 与返回退出码的 `run_cli()`；增加 `--version`、`doctor --offline`；doctor 在普通配置加载前分流；保留 teammate 前置分流和原有参数；配置及非交互认证错误改为简洁提示 | 命令更易诊断和自动化；原交互、Prompt、Remote 参数继续可用 | CLI 测试通过；安装后 `--help`、`--version`、doctor 均为退出码 0 |
| `codeshell/__init__.py` | 版本号散落且互相不一致 | 从安装包元数据读取 `__version__`，源码环境回退为 `0.2.0` | CLI、界面和状态信息使用同一版本 | 版本回退与一致性测试通过 |
| `codeshell/app.py` | TUI Banner 硬编码旧版本 `0.1.0` | Banner 改为引用统一的 `__version__` | 启动界面正确显示 `CodeShell v0.2.0` | 真实 TUI 启动和截图均已观察 |
| `codeshell/commands/handlers/status.py` | `/status` 硬编码另一版本 `0.9.0` | 状态命令引用统一的 `__version__` | `/status` 与 CLI、Banner 版本一致 | 版本一致性测试通过 |
| `pyproject.toml` | 包元数据没有声明 README | 新增 `readme = "README.md"`，保留 `codeshell = "codeshell.__main__:main"` | wheel 元数据完整，安装后命令入口可用 | `uv build` 成功；隔离环境安装 wheel 后三个入口通过 |
| `README.md` | 缺少项目级介绍、可靠启动说明、架构和排障材料 | 新增中文项目介绍、真实截图、唯一正式启动命令、环境要求、配置优先级、4 类 Provider 示例、MCP、交互/Prompt/Remote 用法、Doctor、Mermaid 架构、安全边界、测试和故障排查 | 新用户可以按文档从克隆直接启动；可直接用于简历项目展示和面试讲解 | 4 个 Provider YAML 片段通过配置校验；命令与实际 `--help` 核对 |
| `docs/images/codeshell-tui.svg` | README 没有真实运行效果图 | 使用 Textual 的实际应用测试运行生成 SVG，并把演示路径替换为 `/workspace/demo-project` | README 可直观看到真实 TUI，而非设计稿 | SVG 包含 Banner、模型、输入框；敏感词扫描无真实用户名、主目录或 Key |
| `.github/workflows/ci.yml` | 没有仓库级交付自动化 | 新增 Python 3.11/3.12/3.13 交付矩阵：锁定非 editable 安装、交付测试、构建、安装入口与离线 doctor；另设不筛选测试的非阻塞完整回归任务 | 推送到 GitHub 后可自动发现多版本安装/入口问题，并透明保留已知 Hook 失败 | YAML 解析和矩阵/命令静态检查通过；Python 3.13 核心流程本地复现通过 |
| `CHANGELOG.md` | 没有用户可见变更记录 | 新增 Unreleased 的 Added/Changed/Fixed/Known issues，并明确 Hook 边界 | 后续发布和简历复盘有清晰变更依据 | 已逐项与实际实现核对 |
| `tests/test_config.py` | 缺少配置发现、示例回退和错误可操作性覆盖 | 新增示例安全、优先级、只读回退、显式路径、损坏 YAML、缺少字段等测试 | 防止一键启动配置路径回归 | 包含在 37 项交付测试中并通过 |
| `tests/test_doctor.py` | 没有诊断能力测试 | 新增报告/退出码、环境、配置脱敏、离线、Provider 错误分类、OpenAI SDK 页响应、MCP 和幂等性测试 | Doctor 行为可稳定回归 | 单文件 19 passed |
| `tests/test_cli.py` | 顶层入口缺少可注入的路由测试 | 新增旧参数、help/version、doctor、teammate、错误处理、Banner 与 status 版本测试 | 防止新命令破坏原入口 | 包含在 37 项交付测试中并通过 |
| `docs/improvements/repository-one-click-startup/spec.md` | 改进范围和验收边界未归档 | 保存已批准需求、非功能要求、范围外事项及 AC1～AC10 | 审阅时可追溯“为什么改”和“不改什么” | 与最终实现逐项核对 |
| `docs/improvements/repository-one-click-startup/plan.md` | 技术方案、接口和取舍未归档 | 保存配置发现、Doctor、CLI、文档、截图、CI、测试策略和正式命令设计 | 面试时可说明技术决策与替代方案 | 已批准后实施 |
| `docs/improvements/repository-one-click-startup/task.md` | 实施步骤和依赖关系未归档 | 保存 T1～T25 的文件级任务、依赖、验证方式和执行顺序 | 后续可复盘或继续迭代 | T1～T25 均已实施 |
| `docs/improvements/repository-one-click-startup/checklist.md` | 缺少可观察的验收清单 | 建立 CLI、配置、Doctor、文档、构建、兼容性、归档和 6 个端到端场景的逐项检查 | 验收证据集中、结果透明 | 已按本报告证据更新状态 |
| `docs/improvements/repository-one-click-startup/change-report.md` | 没有实施后的逐文件说明 | 新增本报告，记录修改、影响、命令、结果和限制 | 用户能明确看到每一次改进具体改了什么 | 文件清单与工作区逐项核对 |

## 验收记录

### 干净副本一键启动

临时副本排除了 `.venv`、`.codeshell`、`dist` 和缓存目录。执行：

```bash
OPENAI_API_KEY=CI_PLACEHOLDER_NOT_A_REAL_KEY \
  uv run --locked --no-editable codeshell
```

实际结果：

- 自动创建 `.venv`。
- 构建并非 editable 安装 `codeshell==0.2.0`。
- 安装 53 个依赖包。
- 启动真实 TUI，显示版本、模型和输入框。
- Ctrl+C 正常退出，退出码为 `0`。
- 第二次运行继续正常启动，`config.example.yaml` 与 `uv.lock` 的 SHA-1 前后不变。

### Doctor

当前项目配置执行在线只读探测：

```text
Summary: 8 passed, 0 warnings, 0 failed
```

确认 DeepSeek 可达，模型列表包含 `deepseek-flash`。实现只调用模型元数据接口，不创建对话或推理请求。

故意配置不存在的 MCP 命令后，离线 Doctor 返回 5 PASS、2 WARN、0 FAIL；TUI 同时显示 MCP warning，但核心界面和输入框继续可用。

### 自动化测试

交付路径：

```bash
.venv/bin/python -m pytest -q \
  tests/test_config.py tests/test_doctor.py tests/test_cli.py
```

结果：`37 passed in 0.79s`。

完整回归：

```bash
.venv/bin/python -m pytest -q
```

结果：`738 passed, 1 skipped, 1 failed, 1 warning in 7.23s`。与实施前相比增加的 37 项交付测试全部通过，失败数量仍为 1，没有新增失败。

唯一失败：

```text
tests/test_hooks.py::TestAgentHookIntegration::test_pre_tool_use_reject_skips_tool
```

### 构建与安装

`uv build` 成功生成：

- `dist/codeshell-0.2.0.tar.gz`
- `dist/codeshell-0.2.0-py3-none-any.whl`

wheel 在新的 Python 3.13 隔离虚拟环境安装成功，以下命令均为退出码 `0`：

- `codeshell --help`
- `codeshell --version`，输出 `codeshell 0.2.0`
- `codeshell doctor --offline`

## 已知限制与未触碰边界

- 按用户明确指示，本轮没有修改危险命令检测器、Hook 条件解析器或 Bash 执行逻辑。上述 Hook 集成测试仍失败，并在 README、CHANGELOG 和 CI 中公开保留。
- 当前交付目录不是 Git 工作区，无法在本机触发 GitHub Actions；workflow 已通过 YAML/矩阵静态检查，Python 3.13 核心流程已本地复现，托管环境中的 Python 3.11/3.12/3.13 运行需要将仓库推送到 GitHub 后确认。
- 正式一键流程面向 macOS/Linux；未承诺 Windows 原生终端兼容。
- 用户仍需预先安装 `uv`、受支持的 Python，并自行提供有效 Provider API Key；这些外部凭据和基础工具不会由仓库自动创建。

## 归档核对

本次改进的五份流程文档均位于当前目录：

- `spec.md`
- `plan.md`
- `task.md`
- `checklist.md`
- `change-report.md`

仓库根目录没有本轮 `spec.md`、`plan.md`、`task.md` 或 `checklist.md` 的重复副本。
