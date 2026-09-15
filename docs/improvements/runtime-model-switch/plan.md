# TUI 运行时模型切换 Plan

## 架构概览

本功能沿用 CodeShell 现有的 Provider、命令注册、Textual TUI 和 Agent 运行时结构，在其上增加一个窄范围的运行时模型切换链路。

- **配置层**：为 `ProviderConfig` 增加可选的 `models` 列表，并在现有 DeepSeek 配置中登记 `deepseek-flash` 和 `deepseek-v4-pro`。原有 `model` 字段继续表示启动时默认模型，未配置 `models` 的旧配置保持兼容。
- **命令层**：新增 `/model` 命令。无参数时打开模型选择列表，有参数时直接请求切换。
- **界面层**：在 TUI 中增加专用模型选择面板，展示两个可选模型并标记当前模型；选择结果与直接参数统一进入同一个切换入口。
- **切换准备层**：基于当前 Provider 创建仅修改 `model` 的运行时副本，初始化候选客户端并解析上下文窗口。在准备成功前不修改现有运行时状态。
- **运行时协调层**：准备成功后，一次性同步主客户端、主 Agent、技能执行器、后续子 Agent Provider 以及界面模型标签。不会重新初始化会话、对话、权限、工具、MCP、记忆、团队或任务组件。
- **持久化边界**：运行时只使用内存中的 Provider 副本，不调用配置保存逻辑；重新启动后仍采用配置中的默认 `model`。

## 核心数据结构

### `ProviderConfig`

在现有数据类上增加：

```python
models: list[str] = field(default_factory=list)
```

并提供：

```python
def get_switchable_models(self) -> tuple[str, ...]: ...
def copy_for_model(self, model: str) -> ProviderConfig: ...
```

规则如下：

- `model` 是启动时默认模型。
- `models` 是允许运行时切换的候选模型。
- `models` 缺失或为空时，`get_switchable_models()` 返回只包含当前 `model` 的元组，保证旧配置兼容。
- 配置校验要求候选项为非空字符串、不得重复，并且默认 `model` 必须包含在候选列表中。
- `copy_for_model()` 创建新对象，保留协议、地址、密钥、thinking、上下文窗口和输出限制，仅替换模型，并清除不能跨模型复用的运行时 context-window 缓存。
- 本次项目配置只登记 `deepseek-flash` 和 `deepseek-v4-pro`；运行时切换模块还会用固定白名单限制范围。

### `PreparedModelSwitch`

```python
@dataclass(frozen=True)
class PreparedModelSwitch:
    provider: ProviderConfig
    client: LLMClient
    context_window: int
```

该对象表示已准备完成但尚未应用的候选运行时。`provider` 和 `client` 不进入用户界面或日志输出，避免暴露密钥或客户端内部信息。

### TUI 模型控制接口

在现有 `UIController` 协议上增加：

```python
def get_available_models(self) -> tuple[str, ...]: ...
def get_current_model(self) -> str: ...
def show_model_selector(
    self,
    models: tuple[str, ...],
    current: str,
) -> None: ...
async def switch_model(self, model: str) -> bool: ...
```

- `get_available_models()` 返回当前 Provider 配置与固定 DeepSeek 白名单的交集。
- `get_current_model()` 返回当前运行时模型 ID。
- `show_model_selector()` 打开专用选择面板。
- `switch_model()` 执行忙碌检查、输入校验、候选准备、原子提交及用户提示；失败返回 `False` 并保持旧状态。

### `/model` 命令接口

```python
async def handle_model(context: CommandContext) -> None: ...
```

- 无参数时调用模型选择面板。
- 有一个参数时直接请求切换。
- 多余参数或无效模型时拒绝执行并显示合法模型。
- 命令不设置通用 `arg_prompt`，因为空参数本身是有效操作。

### 运行时依赖更新接口

为需要同步模型依赖的组件增加显式方法，避免由应用层修改私有字段：

```python
Agent.set_runtime_client(client, protocol, context_window) -> None
SkillExecutor.set_runtime_client(client, protocol) -> None
AgentTool.set_provider_config(provider) -> None
```

这些方法只替换模型相关引用，不重新创建组件或清空其状态。

## 模块设计

### 配置模块

**职责：**

- 读取可选的 `models` 字段。
- 兼容仅含 `model` 的旧配置。
- 验证默认模型、候选模型列表、数据类型和重复项。
- 创建目标模型的内存 Provider 副本。

**对外接口：** `ProviderConfig.get_switchable_models()`、`ProviderConfig.copy_for_model()`。

**依赖：** YAML 配置加载器和现有配置校验模块。

### 模型切换模块

**职责：**

- 定义 `SUPPORTED_DEEPSEEK_MODELS = ("deepseek-flash", "deepseek-v4-pro")`。
- 验证目标模型既在当前 Provider 候选列表中，也在固定白名单中。
- 基于当前 Provider 创建运行时副本。
- 通过现有客户端工厂创建候选客户端并解析上下文窗口。
- 返回 `PreparedModelSwitch`，不直接修改应用状态。

**对外接口：**

```python
def prepare_model_switch(
    provider: ProviderConfig,
    model: str,
    *,
    client_factory: ClientFactory = create_client,
) -> PreparedModelSwitch: ...
```

`client_factory` 可在测试中注入，测试不连接真实 DeepSeek 服务。

**依赖：** 配置模块和现有 LLM 客户端工厂；不依赖 Textual 或应用对象。

### `/model` 命令模块

**职责：**

- 注册命令、描述和使用方法，使其自动出现在 `/help` 中。
- 区分无参数选择模式和直接参数模式。
- 将交互和切换交给 `UIController`，不直接创建客户端或修改 Agent。

**依赖：** 命令注册表和 `UIController` 协议。

### TUI 模型选择模块

**职责：**

- 展示两个模型并明确标记当前项。
- 处理选择、关闭和取消操作。
- 将选择结果交给统一的 `switch_model()` 入口。
- 在回复生成期间拒绝打开或执行切换。

**依赖：** Textual 的 `OptionList`/容器组件和应用运行时协调逻辑。

### 应用运行时协调模块

**职责：**

- 调用模型切换模块完成候选准备。
- 在提交前保存旧运行时引用。
- 原子更新当前 Provider、应用客户端、主 Agent、技能执行器、后续子 Agent Provider、context window 和界面模型标签。
- 提交步骤出现异常时恢复旧引用并给出失败提示。
- 复用现有会话、对话、权限、工具注册表、MCP、记忆、团队和任务管理器实例。

已经运行的后台子任务保持其原客户端直至结束；切换后的新请求和新子任务使用新模型。

**依赖：** 模型切换模块、Agent、SkillExecutor、AgentTool 和现有 TUI 控件。

### 测试模块

**职责：**

- 验证配置兼容和候选模型校验。
- 验证 `/model` 的列表与直接参数两种调用方式。
- 验证选择面板、当前项标记和忙碌拒绝。
- 验证两个方向的切换、状态保持、失败回滚和配置文件不变。
- 运行全量回归及现有诊断流程。

## 模块交互

```text
用户输入 /model
        │
        ▼
命令分发器 → model 命令处理器
        │
        ├─ 无参数 → 检查生成状态 → 打开模型选择面板
        │                              │
        │                              └─ 用户选择模型
        │
        └─ 有参数 ───────────────────────────────┐
                                                 ▼
                                      switch_model(model)
                                                 │
                          ┌──────────────────────┼──────────────────────┐
                          │                      │                      │
                     正在生成               当前模型相同           模型无效
                          │                      │                      │
                       拒绝切换              提示无需切换       提示合法模型列表

                                                 ▼
                                      prepare_model_switch()
                                                 │
                             复制 Provider、创建客户端、
                             解析上下文窗口并完成校验
                                                 │
                          ┌──────────────────────┴──────────────────────┐
                          │                                             │
                        成功                                          失败
                          │                                             │
                 保存旧运行时引用                               保持旧状态并提示
                          │
                 原子更新所有模型引用
                          │
             更新状态栏并显示切换成功消息
```

切换成功后的请求链：

```text
下一条用户消息
  → 原有 Conversation（历史不变）
  → 原有 Agent（身份、工具和状态不变）
  → 新 LLM Client
  → 目标 DeepSeek 模型
```

状态同步规则：

- 主 Agent、技能执行器、后续子 Agent 和记忆侧请求使用新模型。
- Conversation、Session、工具注册表、MCP 连接、权限状态、任务和团队对象保持原实例。
- 准备阶段不修改任何运行时引用。
- 提交阶段出现异常时，按保存的快照恢复旧引用。
- 切换流程不调用配置保存接口，也不重新执行应用初始化流程。

## 文件组织

```text
codeshell-python/
├── codeshell/
│   ├── config.py
│   │   └── 扩展 ProviderConfig、读取 models、复制目标模型配置
│   ├── validator.py
│   │   └── 校验 models 列表、默认模型和兼容规则
│   ├── model_switching.py
│   │   └── 新增 PreparedModelSwitch 和模型切换准备逻辑
│   ├── app.py
│   │   └── 模型选择面板、忙碌检查、原子提交和状态栏更新
│   ├── styles.tcss
│   │   └── 模型选择面板样式
│   ├── agent.py
│   │   └── 增加安全更新运行时客户端的接口
│   ├── skills/
│   │   └── executor.py
│   │       └── 同步技能执行器的客户端和协议
│   ├── tools/
│   │   └── agent_tool.py
│   │       └── 同步后续子 Agent 使用的 Provider
│   └── commands/
│       ├── registry.py
│       │   └── 扩展 TUI 控制接口
│       └── handlers/
│           ├── __init__.py
│           │   └── 注册 /model
│           └── model.py
│               └── 新增 /model 命令定义和处理器
├── tests/
│   ├── test_config.py
│   │   └── 配置兼容与 models 校验测试
│   ├── test_commands.py
│   │   └── 命令注册、列表和直接参数测试
│   └── test_model_switching.py
│       └── 新增运行时切换、状态保持、忙碌拒绝和回滚测试
├── config.yaml
│   └── 为默认 Provider 配置两个 DeepSeek 模型
├── .codeshell/config.yaml
│   └── 同步两个候选模型，不改动现有密钥等其他配置
├── README.md
│   └── 补充 models 配置及 /model 使用说明
└── docs/improvements/runtime-model-switch/
    ├── spec.md
    ├── plan.md
    ├── task.md
    └── checklist.md
```

不移动或重命名现有源码文件；只新增模型切换模块、命令处理器和对应测试，其余均为局部修改。

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 模型配置方式 | 在同一 Provider 中增加 `models` 列表 | 避免重复地址和密钥，并保持 Provider 身份不变 |
| 支持范围 | 固定允许 `deepseek-flash`、`deepseek-v4-pro` | 符合当前范围，拒绝任意模型名 |
| 切换方式 | 先完整准备，再原子提交 | 初始化失败不会污染当前运行状态 |
| 会话处理 | 复用原 Agent、Conversation 和 Session | 保留上下文、工具状态和任务状态 |
| 依赖更新 | 通过明确的运行时更新接口同步客户端 | 避免应用层直接修改各组件私有字段 |
| 无参数交互 | 使用独立模型选择面板 | 可直接执行选择并清楚标记当前模型 |
| 生成中切换 | 直接拒绝 | 避免同一响应跨模型或流式任务状态错乱 |
| 持久化策略 | 仅修改内存中的 Provider 副本 | 不写配置，重启后恢复默认模型 |
| 后台子任务 | 已运行任务继续原模型，新任务使用新模型 | 避免中途替换后台任务依赖导致状态破坏 |
| 测试策略 | 注入模拟客户端工厂 | 不需要真实密钥，不访问 DeepSeek 网络 |

## Spec 覆盖

- **F1–F3**：命令注册、命令处理器和模型选择面板。
- **F4**：原子更新主客户端和状态栏。
- **F5**：复用现有会话及运行时管理器。
- **F6**：只使用内存副本，不调用配置保存。
- **F7–F8**：切换入口的同模型及非法模型分支。
- **F9**：TUI 忙碌状态检查。
- **N1**：准备—提交—回滚机制。
- **N2**：不显示或记录 Provider 配置对象及密钥。
- **N3–N5**：不调用初始化流程，限定 TUI 内同 Provider 切换。
- **N6–N7**：模拟客户端测试和全量回归验证。

未发现 spec 功能需求的架构归属缺口，模块依赖为单向调用，不形成循环依赖。
