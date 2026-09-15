# CodeShell 仓库一键启动与交付体验 Checklist

> 本地可验证条目已于 2026-09-15 全部完成；详细证据见 `change-report.md`。GitHub 托管的 Python 3.11～3.13 实际运行需在仓库推送后确认。

## 一键安装与 CLI

- [x] 正式启动命令能够从干净仓库自动创建或复用隔离环境、严格使用 `uv.lock` 并启动 TUI。（验证：在临时干净副本运行 `uv run --locked --no-editable codeshell`，观察依赖同步完成并出现输入框；覆盖 AC1）
- [x] 正式启动不要求执行 `source .venv/bin/activate`。（验证：在未激活虚拟环境的终端运行正式启动命令；覆盖 F1）
- [x] 非 editable 安装后的 `codeshell --help` 不出现 `ModuleNotFoundError`。（验证：构建 wheel，在临时虚拟环境安装后运行 `codeshell --help`；覆盖 AC2）
- [x] 模块入口和安装后的命令入口提供一致的帮助、版本及运行参数。（验证：分别运行 `python -m codeshell --help` 与 `codeshell --help` 并对比关键选项；覆盖 F2）
- [x] 现有 `-p`、`--output-format`、`--remote`、`--mode` 和 teammate worker 参数仍可解析。（验证：运行 `tests/test_cli.py` 的旧参数兼容用例；覆盖 N4）
- [x] `codeshell --version`、TUI Banner 和 `/status` 显示同一个项目版本。（验证：自动化版本一致性测试通过，并实际观察 Banner；覆盖 F2）

## 配置发现与首次启动

- [x] `config.example.yaml` 能通过项目配置校验器读取。（验证：运行 `.venv/bin/pytest -q tests/test_config.py`；覆盖 AC5）
- [x] 示例配置不包含真实密钥或疑似密钥字符串。（验证：运行配置测试中的敏感信息扫描，并人工检查示例；覆盖 AC5、N1）
- [x] 没有用户配置时，加载器只读使用仓库示例并报告 `using_example=True`。（验证：在临时目录运行配置回退测试，并比较运行前后文件列表和内容；覆盖 F1、F3、N2）
- [x] 存在用户配置时，优先级仍为全局配置、项目配置、项目本地配置，仓库示例不参与覆盖。（验证：运行多层配置合并测试；覆盖 N4）
- [x] 显式指定不存在的配置路径时返回配置错误，不静默使用示例。（验证：运行显式路径失败测试；覆盖 F3）
- [x] 完全缺少配置时，错误信息包含支持的配置位置、必填字段、示例文件和 doctor 命令，不输出 traceback。（验证：在不含任何配置和示例的临时目录执行入口并检查 stderr；覆盖 AC3）
- [x] 缺少 API Key 时只显示配置方法，不输出内部异常堆栈或任何已有 Key。（验证：清除对应环境变量并启动，检查终端输出；覆盖 AC3、N1）

## Doctor 环境诊断

- [x] `codeshell doctor --offline` 逐项显示 Python、项目文件、配置来源、API Key 和 MCP 状态。（验证：使用有效本地配置运行命令，观察每项都有 PASS、WARN 或 FAIL；覆盖 AC4）
- [x] Python 低于 3.11 时诊断为关键失败并返回退出码 `1`。（验证：注入低版本信息运行单元测试；覆盖 F4）
- [x] 缺少 `pyproject.toml` 或 `uv.lock` 时能够指出具体缺失项和修复建议。（验证：分别在缺少对应文件的临时目录运行诊断测试；覆盖 F4）
- [x] 配置损坏时停止依赖配置的检查，不产生级联 traceback。（验证：使用损坏 YAML 运行 doctor 测试；覆盖 N3）
- [x] API Key 检查只显示“已配置/未配置”，报告中不存在 Key 原文。（验证：使用特征明显的假 Key 运行 doctor 并断言输出不含该字符串；覆盖 AC4、N1）
- [x] 在线 doctor 通过只读模型接口区分认证失败、网络失败、模型不存在和服务端错误。（验证：运行替代 Provider 探针的分支测试；覆盖 F4、N3）
- [x] 在线 doctor 对当前有效 Provider 和模型返回成功，且不发送对话、不产生推理 token。（验证：经许可运行 `codeshell doctor`，观察模型检查通过；检查实现只调用模型查询接口；覆盖 AC4）
- [x] `--offline` 不创建网络客户端，并将 Provider 网络检查标记为警告。（验证：注入一旦调用即失败的探针运行离线测试；覆盖 N3）
- [x] 配置 stdio MCP 时检查其命令；配置 `npx` 时同时检查 Node.js 和 npx。（验证：使用注入命令查找器运行存在与缺失测试；覆盖 F4）
- [x] 未配置 MCP 和配置 HTTP MCP 时不会错误要求 Node.js。（验证：运行无 MCP 与 HTTP MCP 测试；覆盖 F4）
- [x] 重复运行 doctor 不创建、覆盖或修改配置与虚拟环境文件。（验证：连续运行两次并比较目标文件的哈希和修改时间；覆盖 N2）
- [x] 关键检查失败返回非零状态，仅有警告时返回 `0`。（验证：运行 `DoctorReport.exit_code` 和完整流程测试；覆盖 AC4）

## 文档与展示材料

- [x] README 首屏清楚说明项目定位、核心能力、环境要求和一键启动命令。（验证：人工审阅 README；覆盖 AC6）
- [x] README 包含 DeepSeek、OpenAI、Anthropic 和 OpenAI-compatible 配置说明，并解释密钥环境变量。（验证：逐项复制 YAML 片段运行配置校验；覆盖 F5、AC6）
- [x] README 包含交互、非交互、Remote、doctor、测试和常见故障排查命令。（验证：逐条与 `codeshell --help` 和代码入口核对；覆盖 F5、AC6）
- [x] README 的 Mermaid 架构图与实际 CLI、配置、TUI、Agent、MCP 模块关系一致。（验证：对照 `plan.md` 和对应模块人工审阅；覆盖 F5）
- [x] README 明确说明权限模式、沙箱边界、MCP 外部进程和 API 调用费用风险。（验证：人工审阅安全章节；覆盖 F5）
- [x] README 如实披露当前危险命令 Hook 测试状态，不宣称完整回归全部通过。（验证：对比完整 pytest 实际输出；覆盖 AC9）
- [x] README 嵌入真实运行的 TUI SVG，而不是设计稿或生成式示意图。（验证：使用真实 Textual 应用重新生成并对比主要界面元素；覆盖 F5）
- [x] TUI 截图不包含 API Key、真实用户名、主目录、会话内容或个人信息。（验证：人工查看并对 SVG 文本进行敏感词扫描；覆盖 N1）
- [x] README 明确主要支持 macOS 和 Linux，不承诺 Windows 原生一键启动。（验证：人工审阅兼容性章节；覆盖 N6）

## 构建与自动化测试

- [x] `pyproject.toml` 引用存在的 README，并能成功构建 wheel。（验证：运行 `uv build`，检查构建退出码和产物元数据；覆盖 F2）
- [x] wheel 包含 `codeshell` 代码、CLI 入口和运行所需资源。（验证：列出 wheel 内容并在隔离环境启动；覆盖 F2）
- [x] 配置、doctor 和 CLI 新增测试全部通过。（验证：运行 `.venv/bin/pytest -q tests/test_config.py tests/test_doctor.py tests/test_cli.py`；覆盖 N5）
- [x] CI 定义 Python 3.11、3.12、3.13 三个交付矩阵版本。（验证：解析 `.github/workflows/ci.yml` 并检查矩阵值；覆盖 AC7）
- [x] 每个 CI 版本都执行锁定安装、wheel 构建、非 editable 入口、配置和 doctor 冒烟验证。（验证：检查 workflow 日志或逐版本本地复现；覆盖 AC2、AC7）
- [x] CI 冒烟过程使用假 Key 与离线诊断，不调用付费推理接口。（验证：检查 workflow 环境变量与命令；覆盖 N1）
- [x] 完整回归任务执行未经筛选的 `pytest -q`，保留当前已知 Hook 失败的日志。（验证：确认命令没有 `--ignore` 或 `-k`，查看运行输出；覆盖 AC9、N5）
- [x] 本轮改造没有引入新的回归失败。（验证：完整回归为 `738 passed, 1 skipped, 1 failed`，相对基线仅增加 37 个通过项；覆盖 AC9）

## 集成与兼容性

- [x] 现有 `load_config(path=None)` 的签名和 `AppConfig` 返回类型保持不变。（验证：运行原有配置、MCP、worktree 和团队测试；覆盖 N4）
- [x] 交互 TUI、非交互 Prompt 和 Remote 三条路径仍使用相同的配置合并结果。（验证：用模拟配置运行对应入口测试；覆盖 N4）
- [x] doctor 在正常配置加载之前分流，因此配置损坏时仍能启动诊断。（验证：损坏配置后运行 `codeshell doctor --offline`，观察结构化失败报告；覆盖 F4）
- [x] Provider 网络错误与本地配置错误显示不同的诊断名称和修复建议。（验证：分别注入配置异常与连接异常并比较输出；覆盖 N3）
- [x] 不存在针对 `sys.path` 或用户目录的运行时补丁。（验证：搜索新增代码中的 `sys.path` 修改和硬编码用户路径；覆盖 N2、N6）
- [x] 本轮没有修改危险命令检测器、Hook 条件解析器或 Bash 执行逻辑。（验证：将实际文件差异与 task 文件清单比对；覆盖 AC9）

## 改进文档归档与变更透明度

- [x] 本次改进目录名为稳定、可读的 `repository-one-click-startup`。（验证：检查目录路径；覆盖 N7、AC10）
- [x] `spec.md`、`plan.md`、`task.md`、`checklist.md` 和 `change-report.md` 全部位于本次改进目录。（验证：列出目录文件；覆盖 AC10）
- [x] 仓库根目录不存在本轮四份流程文档的重复副本。（验证：检查根目录的 `spec.md`、`plan.md`、`task.md`、`checklist.md`；覆盖 AC10）
- [x] `change-report.md` 逐文件记录修改前问题、具体修改、用户可见影响和实际验证结果。（验证：与工作区差异和测试日志逐项比对；覆盖 AC8）
- [x] `CHANGELOG.md` 只记录已经实现的用户可见行为，并明确未处理的 Hook 边界。（验证：对照实际文件差异人工审阅；覆盖 F7、AC9）
- [x] 归档文档中的相对文件引用在移动后仍然有效。（验证：提取 Markdown 本地链接并确认目标存在；覆盖 N7）

## 端到端场景

- [x] 场景 1——干净克隆启动：准备 `uv` 和 `OPENAI_API_KEY`，运行唯一正式命令，自动安装后看到 CodeShell Banner、模型名和输入框。（验证：在临时干净副本实际操作；覆盖 AC1）
- [x] 场景 2——首次缺少 Key：不设置 API Key 运行正式命令，看到安全、简洁且可执行的配置指引，不出现 traceback。（验证：在隔离环境实际操作；覆盖 AC3）
- [x] 场景 3——已有用户配置：同时存在示例、全局、项目和本地配置时启动，最终使用原三层规则合并出的 Provider。（验证：使用可区分的测试值运行集成测试；覆盖 N4）
- [x] 场景 4——离线排障：断开 Provider 探针后运行 `codeshell doctor --offline`，本地检查继续执行，网络项显示 WARN，命令不挂起。（验证：使用禁止联网的测试探针运行；覆盖 AC4、N3）
- [x] 场景 5——MCP 依赖缺失：配置 `npx` MCP 但模拟 Node.js/npx 缺失，doctor 给出针对性警告，核心 TUI 仍可启动。（验证：替换命令查找器并运行 TUI 冒烟测试；覆盖 F4）
- [x] 场景 6——重复运行：连续执行两次正式启动和两次 doctor，第二次复用环境且现有配置内容不变。（验证：比较两次运行日志、配置哈希和修改时间；覆盖 N2）

## 验收标准覆盖

| 验收标准 | Checklist 覆盖位置 |
|---|---|
| AC1 | 一键安装第 1 项；端到端场景 1 |
| AC2 | 一键安装第 3～4 项；构建与自动化第 5 项 |
| AC3 | 配置发现第 6～7 项；端到端场景 2 |
| AC4 | Doctor 全节；端到端场景 4 |
| AC5 | 配置发现第 1～2 项 |
| AC6 | 文档与展示第 1～5 项 |
| AC7 | 构建与自动化第 4～6 项 |
| AC8 | 归档与透明度第 4项 |
| AC9 | 文档与展示第 6 项；构建与自动化第 7～8 项；集成第 6 项 |
| AC10 | 归档与透明度第 1～3 项 |
