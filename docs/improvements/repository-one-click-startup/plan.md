# CodeShell 仓库一键启动与交付体验 Plan

## 架构概览

本轮改造保持现有 Agent、TUI、Provider 和 MCP 运行链路不变，在它们之前增加一个轻量的“交付入口层”。入口层负责解析命令、发现配置、输出可操作的启动错误，并在用户选择诊断命令时执行独立的环境检查。

正式的一键启动命令确定为：

```bash
uv run --locked --no-editable codeshell
```

`uv` 负责依据锁文件创建或复用虚拟环境、同步依赖，并以非 editable 方式安装当前项目后调用既有 `codeshell` 入口。选择 `--no-editable` 是为了避开部分 macOS/Python 3.13 环境中隐藏 `.pth` 文件被忽略而导致的 `ModuleNotFoundError`，不在项目代码里注入 `sys.path` 补丁。

仓库根目录提供一份可直接校验的 `config.example.yaml`。当用户没有全局或项目配置时，配置加载器将它作为只读仓库默认配置使用；示例默认连接 DeepSeek，密钥从 `OPENAI_API_KEY` 环境变量读取。用户已有的 `~/.codeshell/config.yaml`、项目 `.codeshell/config.yaml` 和 `.codeshell/config.local.yaml` 仍保持原优先级，不发生迁移。

诊断能力使用顶层命令 `codeshell doctor`，在启动 TUI 之前运行，因此即使配置缺失或损坏也能给出诊断。诊断默认执行只读网络探测，`--offline` 可跳过 Provider 网络访问。

```text
正式启动命令
    │
    ▼
uv：锁定依赖同步 + 非 editable 安装
    │
    ▼
CLI 参数路由 ────────────────┐
    │                        │ doctor
    │ 默认 / -p / --remote   ▼
    ▼                   环境诊断器
配置发现与合并              ├─ Python/项目环境
    │                       ├─ 配置/API Key
    ▼                       ├─ Provider/模型
现有 TUI / Prompt / Remote  └─ MCP/Node.js
```

## 核心数据结构与接口

### 配置发现结果

在 `codeshell.config` 中增加不可变的数据结构：

```python
@dataclass(frozen=True)
class ConfigDiscovery:
    paths: tuple[Path, ...]
    using_example: bool = False
```

- `paths`：按实际合并顺序排列的配置文件。
- `using_example`：是否因没有用户配置而回退到仓库示例。

新增接口：

```python
def discover_config(
    cwd: Path | None = None,
    home: Path | None = None,
) -> ConfigDiscovery

def load_config_with_discovery(
    path: Path | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
) -> tuple[AppConfig, ConfigDiscovery]
```

现有 `load_config(path=None) -> AppConfig` 保留并委托给新接口，避免修改已有调用方。显式传入不存在的配置路径时仍然报错，不使用示例回退。

### 诊断状态

在新模块 `codeshell.doctor` 中定义：

```python
class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"

@dataclass(frozen=True)
class DiagnosticResult:
    name: str
    status: CheckStatus
    detail: str
    remediation: str = ""
    critical: bool = False

@dataclass(frozen=True)
class DoctorReport:
    results: tuple[DiagnosticResult, ...]

    @property
    def exit_code(self) -> int: ...

    def render(self) -> str: ...
```

`DoctorReport.exit_code` 在任一关键检查失败时返回 `1`，否则返回 `0`。可选 MCP 依赖缺失记为警告，不阻止核心 TUI 启动；Python、配置、API Key 或在线 Provider 检查失败属于关键失败。

诊断入口及可替换依赖：

```python
ProviderProbe = Callable[[ProviderConfig], Awaitable[DiagnosticResult]]
CommandLookup = Callable[[str], str | None]

async def run_doctor(
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    online: bool = True,
    provider_probe: ProviderProbe | None = None,
    command_lookup: CommandLookup = shutil.which,
) -> DoctorReport
```

网络探测和可执行文件查找可在测试中替换，单元测试不访问真实 API、不依赖本机 Node.js，也不输出密钥。

### CLI 入口

在 `codeshell.__main__` 中抽出：

```python
def build_parser() -> argparse.ArgumentParser: ...
def run_cli(argv: list[str] | None = None) -> int: ...
def main() -> None: ...
```

- `build_parser` 同时定义现有选项和可选的 `doctor` 命令。
- `run_cli` 返回退出码，便于测试；`main` 只负责将退出码交给进程。
- teammate worker 参数仍在常规参数解析之前处理。
- `doctor` 分支先于正常配置加载执行。
- 正常启动的配置错误和认证错误统一转成简洁提示，日志保留诊断细节，终端不打印内部堆栈。

### 版本信息

`codeshell.__init__` 暴露唯一的 `__version__`，优先从已安装包元数据读取，源码环境提供安全回退值。TUI Banner、`/status` 和 CLI `--version` 统一引用该值，消除当前 `v0.1.0`、`v0.2.0`、`v0.9.0` 并存的问题。

## 模块设计

### CLI 路由模块

**职责：** 解析顶层参数，选择诊断、交互、非交互或远程运行路径，并统一处理启动错误。

**对外接口：** `build_parser`、`run_cli`、`main`。

**依赖：** 配置模块、诊断模块及现有 TUI/Prompt/Remote 入口。

**覆盖需求：** F1、F2、F3、F4。

### 配置发现模块

**职责：** 保留原有三层配置合并规则；没有用户配置时发现仓库示例；向诊断器暴露实际配置来源；生成不含敏感值的错误提示。

**对外接口：** `discover_config`、`load_config_with_discovery`、兼容的 `load_config`。

**依赖：** 现有配置校验器和 YAML 解析器。

**覆盖需求：** F1、F3、F4。

### 环境诊断模块

**职责：** 顺序执行并汇总以下检查：

1. Python 是否满足 `>=3.11`。
2. 当前目录是否包含 `pyproject.toml` 和 `uv.lock`。
3. 配置文件是否存在且结构合法，并显示实际来源。
4. 每个 Provider 对应的 API Key 是否已设置，只报告状态。
5. 在线模式下通过官方 SDK 的只读模型接口验证服务连通性和模型可用性。
6. 对 stdio MCP 检查配置的命令是否存在；使用 `npx` 时同时检查 Node.js 与 npx。
7. 输出汇总、修复建议和进程退出码。

**对外接口：** `run_doctor`、`DoctorReport.render`。

**依赖：** 配置模块、Anthropic/OpenAI SDK、标准库环境与命令查找能力。

**覆盖需求：** F4，N1、N2、N3。

### 项目文档与示例配置

**职责：** 用一份根目录 README 完成从项目理解到启动排障的闭环；用配置示例提供默认 DeepSeek 启动路径及其他 Provider 的改写方法；用真实 TUI 截图展示最终效果。

截图通过真实应用的离线演示配置生成，画面不包含 API Key、用户主目录或其他私密信息。

**覆盖需求：** F1、F3、F5、F7，N1、N6。

### 自动化交付验证

**职责：** 在 Python 3.11、3.12 和 3.13 矩阵中构建 wheel，安装非 editable 包，执行 CLI、配置和 doctor 测试，并进行无需真实 API 的启动冒烟验证。

由于用户已明确跳过危险命令 Hook 修复，完整回归测试作为单独的非阻塞任务运行并如实展示当前已知失败；交付路径任务不得忽略、删除或伪造该测试。后续若单独批准安全修复，再将完整回归任务提升为强制通过。

**覆盖需求：** F2、F3、F4、F6，N5。

### 变更记录

**职责：** 在 `CHANGELOG.md` 中建立本轮版本条目，并在本次改进目录的 `change-report.md` 中逐文件说明修改前问题、修改内容、用户可见影响和验证证据。每个后续改进使用独立的主题目录保存自己的流程文档和变更报告。

**覆盖需求：** F7、F8。

## 模块交互

### 正常启动

```text
uv run --locked --no-editable codeshell
  → uv 依据 uv.lock 安装项目
  → main → run_cli
  → load_config_with_discovery
      → 有用户配置：按 全局 → 项目 → 本地 顺序合并
      → 无用户配置：只读加载 config.example.yaml
  → 已有交互 / 非交互 / Remote 入口
```

### 配置失败

```text
run_cli
  → load_config_with_discovery
  → ConfigError / AuthenticationError
  → 输出错误摘要 + 配置位置 + 示例命令 + doctor 提示
  → 返回非零退出码
```

### 环境诊断

```text
codeshell doctor [--offline]
  → run_cli 在常规启动前分流
  → run_doctor
      → 本地环境检查
      → 配置发现与校验
      → API Key 状态检查
      → Provider 只读探测（非 offline）
      → MCP 可执行文件检查
  → DoctorReport.render
  → 根据关键失败项返回 0 或 1
```

## 文件组织

```text
codeshell-python/
├── README.md                         — 项目主页、快速开始、架构与排障
├── CHANGELOG.md                      — 按版本记录明确的用户可见变更
├── config.example.yaml               — 无真实密钥的可运行默认配置
├── pyproject.toml                    — README 元数据和既有 CLI 入口声明
├── docs/
│   ├── improvements/
│   │   └── repository-one-click-startup/
│   │       ├── spec.md               — 本次改进的已批准需求
│   │       ├── plan.md               — 本次改进的已批准技术设计
│   │       ├── task.md               — 本次改进的执行任务
│   │       ├── checklist.md          — 本次改进的验收清单
│   │       └── change-report.md      — 本次改进的逐文件变更报告
│   └── images/
│       └── codeshell-tui.svg           — 脱敏的真实运行界面截图
├── codeshell/
│   ├── __init__.py                   — 唯一版本来源
│   ├── __main__.py                   — CLI 参数构建、doctor 分流和错误处理
│   ├── config.py                     — 配置发现、示例回退和兼容加载接口
│   ├── doctor.py                     — 诊断模型、检查器、渲染与退出码
│   ├── app.py                        — Banner 改用统一版本
│   └── commands/handlers/status.py   — /status 改用统一版本
├── tests/
│   ├── test_cli.py                   — 参数路由、入口一致性、错误提示
│   ├── test_config.py                — 配置发现、示例回退和优先级
│   └── test_doctor.py                — 诊断状态、脱敏、退出码和依赖注入
└── .github/
    └── workflows/
        └── ci.yml                    — 多 Python 版本交付矩阵与回归报告
```

现有同名测试文件若已经承担对应职责，则在其中追加用例，不重复创建模块。例如配置测试将优先并入现有配置相关测试文件。

## Spec 覆盖关系

| Spec 需求 | 技术归属 |
|---|---|
| F1 一键启动 | uv 锁定非 editable 启动命令、示例配置回退、README |
| F2 CLI 稳定 | CLI 路由重构、wheel 安装矩阵、入口一致性测试 |
| F3 配置体验 | 配置发现模块、示例配置、统一错误输出 |
| F4 环境诊断 | `codeshell.doctor`、顶层 doctor 命令、诊断测试 |
| F5 项目文档 | README、架构图、真实脱敏截图 |
| F6 自动化验证 | CI Python 3.11～3.13 交付矩阵 |
| F7 修改透明 | CHANGELOG、逐文件最终交付报告 |
| F8 分主题归档 | `docs/improvements/<topic>/` 独立文档目录 |

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 一键启动工具 | `uv run --locked --no-editable codeshell` | 同时完成锁定依赖同步和启动；非 editable 安装避开已观察到的隐藏 `.pth` 导入问题 |
| 配置示例位置 | 仓库根目录 `config.example.yaml` | 不受当前 `.codeshell/` 整目录忽略规则影响，公开仓库中可直接看见 |
| 无配置时行为 | 只读使用仓库示例，不自动复制或覆盖 | 满足克隆后启动，同时保持幂等且不制造包含密钥的新文件 |
| 默认 Provider | DeepSeek Responses 配置，密钥来自 `OPENAI_API_KEY` | 与当前项目实际配置一致，且示例不保存密钥 |
| doctor 位置 | 顶层 `codeshell doctor` | 配置损坏时仍可运行，不依赖 TUI 已成功初始化 |
| Provider 检查 | SDK 只读模型接口，支持 `--offline` | 验证 Key、网络和模型而不产生推理 token 费用；离线环境可跳过 |
| 诊断测试 | 注入网络探针和命令查找器 | 测试稳定，不访问真实服务或依赖本机工具 |
| 版本来源 | 安装包元数据的单一版本值 | 消除多个界面版本号不一致 |
| CI 范围 | 强制交付冒烟矩阵 + 非阻塞完整回归 | 不掩盖已知 Hook 失败，也不越权实现用户跳过的安全改造 |
| 截图格式 | Textual 生成的 SVG | 保留真实界面与清晰文本，便于版本控制且无需二进制编辑 |
| 改进文档归档 | `docs/improvements/<topic>/` | 每次改进独立存放五份 Markdown 文档，便于简历展示、复盘和后续追踪 |

## 兼容性与风险控制

- 保留 `load_config` 原签名，现有 TUI、非交互、Remote、子 Agent 和测试调用方无需迁移。
- 用户配置始终优先于示例配置，示例不会覆盖 `.codeshell/config.local.yaml`。
- Provider 探测不发送对话，不产生推理 token；错误信息不得包含请求头或完整密钥。
- `doctor --offline` 将网络项标记为警告而不是伪造通过。
- CI 不静默排除现有失败测试；强制任务只约束本轮交付路径，完整回归结果单独展示。
- 不修改危险命令检测器、Hook 条件解析器或 Bash 工具执行逻辑。
