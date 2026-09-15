# TUI 运行时模型切换 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 修改 | `codeshell/validator.py` | 校验并清洗 Provider 的 `models` 配置 |
| 修改 | `codeshell/config.py` | 扩展 `ProviderConfig`、加载模型列表、复制运行时 Provider |
| 新建 | `codeshell/model_switching.py` | 模型白名单、`PreparedModelSwitch` 和候选准备逻辑 |
| 修改 | `codeshell/commands/registry.py` | 扩展 `UIController` 的模型控制接口 |
| 新建 | `codeshell/commands/handlers/model.py` | 定义并处理 `/model` 命令 |
| 修改 | `codeshell/commands/handlers/__init__.py` | 注册 `MODEL_COMMAND` |
| 修改 | `codeshell/app.py` | 模型选择面板、运行状态检查、原子提交和界面同步 |
| 修改 | `codeshell/styles.tcss` | 模型选择面板布局和可见状态样式 |
| 修改 | `codeshell/agent.py` | 增加主 Agent 的运行时客户端更新接口 |
| 修改 | `codeshell/skills/executor.py` | 增加技能执行器的运行时客户端更新接口 |
| 修改 | `codeshell/tools/agent_tool.py` | 增加后续子 Agent Provider 更新接口 |
| 修改 | `tests/test_config.py` | 配置默认、合法和非法模型列表测试 |
| 修改 | `tests/test_commands.py` | 命令注册、帮助、列表和直接参数测试 |
| 新建 | `tests/test_model_switching.py` | 准备、同步、回滚、TUI 和端到端切换测试 |
| 修改 | `config.yaml` | 为示例 DeepSeek Provider 登记两个候选模型 |
| 修改 | `.codeshell/config.yaml` | 为当前本地 Provider 登记两个候选模型，保留其他配置 |
| 修改 | `README.md` | 说明 `models` 配置与 `/model` 两种用法 |
| 新建 | `docs/improvements/runtime-model-switch/task.md` | 记录本任务拆解 |

## T1：扩展 Provider 配置校验

**文件：** `codeshell/validator.py`  
**依赖：** 无

**步骤：**

1. 在 `validate_providers()` 中读取可选的 `models` 字段。
2. 缺失或配置为空列表时，将清洗结果规范化为 `[model]`。
3. 拒绝非列表、非字符串、空字符串和重复候选项。
4. 拒绝默认 `model` 不在显式候选列表中的配置。
5. 将清洗后的 `models` 写入 Provider 校验结果，保持其他字段行为不变。

**验证：** 运行 `.venv/bin/python -m py_compile codeshell/validator.py`，期望退出码为 0。

## T2：扩展 ProviderConfig 和配置加载

**文件：** `codeshell/config.py`  
**依赖：** T1

**步骤：**

1. 为 `ProviderConfig` 增加默认空列表的 `models` 字段。
2. 实现 `get_switchable_models()`，在列表为空时回退为当前模型。
3. 实现 `copy_for_model()`，只替换模型并将 `_fetched_context_window` 重置为 0。
4. 修改配置加载过程，将校验后的 `models` 传入 `ProviderConfig`。
5. 保证复制对象保留协议、地址、API Key、thinking、上下文窗口和输出限制。

**验证：** 运行一个只构造并复制 `ProviderConfig` 的 Python 断言脚本，期望候选列表正确、原对象不变、新对象模型已替换且运行时窗口缓存为 0。

## T3：补齐配置行为测试

**文件：** `tests/test_config.py`  
**依赖：** T1、T2

**步骤：**

1. 增加旧配置未提供 `models` 时自动回退到默认模型的测试。
2. 增加两个 DeepSeek 模型均能被读取且顺序不变的测试。
3. 增加空列表回退、重复项、空字符串、错误类型和默认模型缺失的测试。
4. 增加 `copy_for_model()` 不修改源对象且不泄漏旧模型缓存的测试。

**验证：** 运行 `.venv/bin/python -m pytest -q tests/test_config.py`，期望全部通过。

## T4：实现模型切换准备模块

**文件：** `codeshell/model_switching.py`  
**依赖：** T2

**步骤：**

1. 定义有序白名单 `SUPPORTED_DEEPSEEK_MODELS`，只包含 `deepseek-flash` 和 `deepseek-v4-pro`。
2. 定义不可变的 `PreparedModelSwitch`，并让 Provider 和客户端字段不参与 repr。
3. 实现 `prepare_model_switch()`，同时校验配置候选列表和固定白名单。
4. 使用 `copy_for_model()` 创建候选 Provider，再通过注入的客户端工厂创建客户端。
5. 从候选 Provider 解析 context window，并在任一步骤失败时向调用方返回异常，不修改源 Provider。

**验证：** 运行 `.venv/bin/python -m py_compile codeshell/model_switching.py`，期望退出码为 0。

## T5：验证模型切换准备逻辑

**文件：** `tests/test_model_switching.py`  
**依赖：** T4

**步骤：**

1. 使用假客户端工厂验证两个合法模型都能生成完整的 `PreparedModelSwitch`。
2. 验证 Provider 的地址、协议、密钥和输出参数被保留，源对象不变。
3. 验证配置外模型和白名单外模型均在调用客户端工厂前被拒绝。
4. 验证客户端工厂抛错时异常被保留，且不存在源配置修改。
5. 验证对象 repr 和错误消息中不包含 API Key。

**验证：** 运行 `.venv/bin/python -m pytest -q tests/test_model_switching.py -k prepare`，期望全部通过且不访问网络。

## T6：增加运行时依赖更新接口

**文件：** `codeshell/agent.py`、`codeshell/skills/executor.py`、`codeshell/tools/agent_tool.py`、`tests/test_model_switching.py`  
**依赖：** T2

**步骤：**

1. 为 `Agent` 实现 `set_runtime_client(client, protocol, context_window)`。
2. 为 `SkillExecutor` 实现 `set_runtime_client(client, protocol)`。
3. 为 `AgentTool` 实现 `set_provider_config(provider)`。
4. 确保三个接口只替换模型相关引用，不重建注册表、管理器或任务。
5. 增加测试验证模型引用已替换、非模型状态对象身份保持不变。

**验证：** 运行 `.venv/bin/python -m pytest -q tests/test_model_switching.py -k runtime_dependencies`，期望全部通过。

## T7：注册并实现 /model 命令

**文件：** `codeshell/commands/registry.py`、`codeshell/commands/handlers/model.py`、`codeshell/commands/handlers/__init__.py`、`tests/test_commands.py`  
**依赖：** T4

**步骤：**

1. 在 `UIController` 中声明获取候选模型、当前模型、显示选择面板和异步切换的方法。
2. 新建 `MODEL_COMMAND`，设置描述和 `/model [deepseek-flash|deepseek-v4-pro]` 用法，不设置 `arg_prompt`。
3. 实现无参数时显示选择面板、单参数时直接切换、多参数时拒绝并显示合法用法。
4. 将命令加入 `ALL_COMMANDS`，使 `/help` 和补全列表自动包含它。
5. 扩展 `MockUI` 和命令测试，验证两种正常路径、无效参数、注册表及 `/help model`。

**验证：** 运行 `.venv/bin/python -m pytest -q tests/test_commands.py`，期望全部通过且命令集合包含 `model`。

## T8：增加 TUI 模型选择面板

**文件：** `codeshell/app.py`、`codeshell/styles.tcss`、`tests/test_model_switching.py`  
**依赖：** T7

**步骤：**

1. 在现有 TUI 结构中加入默认隐藏的模型选择容器和独立 `OptionList`。
2. 增加面板样式，使其覆盖在输入区域附近且不影响原 Provider 选择器与补全弹层。
3. 实现 `show_model_selector()`：重建两个选项、标记当前项、显示面板并移动焦点。
4. 扩展 OptionList 选择事件，区分启动 Provider 列表和运行时模型列表。
5. 选择模型后关闭面板、恢复输入焦点，并调度统一的 `switch_model()`。
6. 支持取消面板，取消时不改变模型。
7. 增加 Textual 测试验证选项内容、当前项标记、选择和取消行为。

**验证：** 运行 `.venv/bin/python -m pytest -q tests/test_model_switching.py -k selector`，期望全部通过。

## T9：实现模型状态查询和前置拒绝

**文件：** `codeshell/app.py`、`tests/test_model_switching.py`  
**依赖：** T4、T8

**步骤：**

1. 实现 `get_available_models()`，返回配置候选列表与固定白名单的有序交集。
2. 实现 `get_current_model()`，读取当前运行时 Provider 的模型。
3. 在打开面板和直接切换入口同时检查生成状态。
4. 对正在生成、当前模型重复、模型无效和当前 Provider 不支持切换分别给出明确消息。
5. 确保上述分支均不调用客户端工厂，也不改变任何运行时引用。
6. 增加对应状态测试。

**验证：** 运行 `.venv/bin/python -m pytest -q tests/test_model_switching.py -k "busy or same_model or invalid_model or available_models"`，期望全部通过。

## T10：实现原子运行时切换与回滚

**文件：** `codeshell/app.py`、`tests/test_model_switching.py`  
**依赖：** T5、T6、T9

**步骤：**

1. 在 `switch_model()` 中调用 `prepare_model_switch()`，准备成功前不修改应用状态。
2. 保存当前 Provider、应用客户端、Agent、SkillExecutor、AgentTool 和 context window 的旧引用。
3. 通过显式更新接口提交新客户端、协议、Provider 和 context window。
4. 更新状态栏、模型标签以及后续记忆侧请求读取的当前 Provider。
5. 任一准备或提交步骤失败时恢复完整快照，并显示不含敏感信息的失败消息。
6. 成功后显示目标模型，且不调用 `_select_provider()` 或任何 MCP、工具、会话初始化入口。
7. 增加测试验证成功同步、初始化失败、提交失败回滚和敏感信息保护。

**验证：** 运行 `.venv/bin/python -m pytest -q tests/test_model_switching.py -k "switch_success or rollback or initialization_failure"`，期望全部通过。

## T11：验证状态保持和两条端到端路径

**文件：** `tests/test_model_switching.py`  
**依赖：** T10

**步骤：**

1. 记录切换前的 Session、Conversation、权限、工具注册表、MCP、记忆、团队和任务对象身份。
2. 通过 `/model deepseek-v4-pro` 执行直接切换，并验证下一次请求使用候选客户端。
3. 通过 `/model` 打开列表并选择 `deepseek-flash`，验证下一次请求切回对应客户端。
4. 验证两次切换期间会话 ID、历史消息和所有非模型运行时对象身份保持不变。
5. 验证正在运行的后台任务不被重建，后续新子 Agent 读取新 Provider。
6. 在临时目录中比较切换前后配置文件字节，并重新加载配置确认默认模型未被临时选择覆盖。

**验证：** 运行 `.venv/bin/python -m pytest -q tests/test_model_switching.py`，期望全部通过且没有真实网络请求。

## T12：更新项目配置和使用文档

**文件：** `config.yaml`、`.codeshell/config.yaml`、`README.md`  
**依赖：** T2、T7

**步骤：**

1. 在两个现有 DeepSeek Provider 下增加相同的 `models` 列表，顺序为 `deepseek-flash`、`deepseek-v4-pro`。
2. 保留两个文件原有的默认 `model`、地址、协议、密钥引用及其他配置。
3. 在 README 配置示例中说明 `model` 是默认值、`models` 是运行时候选列表。
4. 在 TUI 命令文档中补充 `/model` 列表选择与 `/model <模型>` 直接切换示例。
5. 明确切换仅当前运行有效、生成中拒绝以及只支持两个 DeepSeek 模型。

**验证：** 运行配置加载断言，期望两个配置均能加载、候选模型顺序正确、各自原默认模型保持不变；随后扫描 README，确认两种命令用法均存在。

## T13：运行聚焦集成回归

**文件：** 不新增文件  
**依赖：** T3、T7、T11、T12

**步骤：**

1. 运行配置、命令和模型切换测试组合。
2. 运行 CLI、Remote、非交互和上下文窗口相关测试，确认本轮未扩展的入口行为不变。
3. 检查测试期间没有访问 DeepSeek 网络、没有要求有效 API Key。
4. 如发现失败，只修改本功能清单内的相关文件，并重新运行同一组合。

**验证：** 运行：

```bash
.venv/bin/python -m pytest -q \
  tests/test_config.py \
  tests/test_commands.py \
  tests/test_model_switching.py \
  tests/test_cli.py \
  tests/test_context_window.py
```

期望全部通过。

## T14：执行全量功能验证和构建检查

**文件：** 不新增文件；构建工具会刷新 `dist/` 产物  
**依赖：** T13

**步骤：**

1. 运行完整 pytest 回归，确认新增测试通过且不新增失败。
2. 运行 CodeShell 离线 doctor，确认环境、配置、Provider 和 MCP 本地检查保持既有基线。
3. 构建 sdist 和 wheel，确认新增 Python 模块、命令处理器、样式及文档被正确打包。
4. 使用构建出的 wheel 做隔离安装检查，运行 `codeshell --help` 和离线 doctor。
5. 对照实施前基线，要求至少保持 `738 passed, 1 skipped`，并保留已知 Hook 失败基线而不增加新失败。

**验证：** 依次运行：

```bash
.venv/bin/python -m pytest -q
.venv/bin/codeshell doctor --offline
uv build
```

然后用新 wheel 的隔离环境运行 `codeshell --help` 和 `codeshell doctor --offline`；期望命令可启动、诊断结果不退化、构建产物完整。

## 执行顺序

```text
T1 → T2 → T3 ──────────────────────────────┐
      │                                    │
      ├→ T4 → T5 ───────────────┐          │
      │                         │          │
      └→ T6 ────────────────────┼→ T10     │
                                │    │      │
T4 → T7 → T8 → T9 ─────────────┘    ▼      │
                                    T11    │
T2 + T7 → T12 ──────────────────────┼──────┘
                                    ▼
                                   T13
                                    ▼
                                   T14
```

该依赖图无循环；T3、T5、T6 和 T7 的部分工作在依赖满足后可以独立推进，但实现阶段仍按编号顺序执行，便于逐项留存验证证据。
