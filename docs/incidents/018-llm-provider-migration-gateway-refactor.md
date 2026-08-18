# Incident 018: LLM Provider 迁移连环兼容性故障 - LLM Provider Gateway 根治重构

**日期**: 2026-08-16 ~ 2026-08-17
**环境**: 方舟 (Volces Ark) GLM-5.2 管线 + opencode deepseek-v4-flash judge / Windows 10 / Python 3.14.5 / litellm 1.85.1
**影响**: 评估跑批（evals baseline）连续 6 轮失败/失真；quick/follow_up 长期空输出；90 分钟进程挂死
**状态**: 表层修复全部完成（PR #74）；根治架构落地（delta `add-llm-provider-gateway`，PR #75）

## 事件总览

将分析管线从 DeepSeek 官方切换到方舟 GLM-5.2、judge 切换到 opencode 后，评估跑批暴露
**7 个独立 bug**--系统此前为 DeepSeek 生态量身调校（消息构造、thinking 处理、输出格式假设），
换 provider 把每个假设推翻一次。每修一个、跑一批、暴露下一个，共 6 轮跑批迭代。

## 故障清单（根因 -> 修复 -> PR #74 commit）

| # | 故障 | 根因 | 修复 |
|---|---|---|---|
| 1 | 跑批 90 分钟挂死（CPU 冻结、孤儿 127.0.0.1 监听端口） | litellm 流式 logging 全局 100 线程池，worker 内 `asyncio.run` 新建 ProactorEventLoop，Windows `_fallback_socketpair` 并发竞态卡死 accept；退出 `_python_exit` join 挂死 | `disable_streaming_logging` 双入口 + 守护测试 + 复现脚本（**incident 016**） |
| 2 | 报告截断 / content 全空 | 方舟 GLM 强制 thinking（disabled 被 400 拒）且 reasoning 与正文**共享** max_tokens 配额，4096 不够 | max_tokens 16384 + parse 尾逗号容错（**incident 017**） |
| 3 | 思考完正文零输出（非配额） | GLM 特定 prompt 下「thinking 后即止」，reasoning 正常 content 空 | `call_llm_for_json` 重试收口（强化指令重问一次） |
| 4 | judge 28 项全败（两轮） | (a) JUDGE_* 未显式配置回退 LLM_* 打错网关；(b) `python -m evals.run` import 时序：模块常量在 `load_dotenv` 前固化空值，单测（先 dotenv 后 import）全通形成**假阴性** | judge 配置显式化 + 常量改函数调用时读取 |
| 5 | quick/follow_up 空 report | 方舟拒收 messages 携带 `reasoning_content` 字段（DeepSeek 官方**要求**回传，行为相反）；GLM 自身输出的 `tool_calls.arguments` 为单引号 Python 字面量，回传被方舟严格校验 400 | 按 provider 清洗消息 + arguments 规范化（单引号 -> 合法 JSON） |
| 6 | citation 校验炸整行 | GLM 生成的 `field_ref` 指到 dict/list 容器节点，`float(dict)` 抛 TypeError | 非数值按 FAIL（无法核验）处理 |
| 7 | judge 分数静默失真（debate_quality 全 1 分） | 管线 state 中 `DebateMessage` 为 pydantic 实例（LangGraph reducer 不序列化），`_summarize_debate` 的 `isinstance(dict)` **静默跳过** -> judge 对空辩论打最低分，混入真实分数不可察觉 | 提取兼容 pydantic + **judge 输入非空断言**（`input_missing` 不打分） |

## 排查方法论（值得沉淀）

- **py-spy 三次线程栈取证**定位 #1（100/100 worker 卡 socketpair accept + 主线程 join）
- **failure 证据链**：langfuse trace 时间线还原死锁点；trace input 内容抓「空辩论」静默污染（#7）
- **参数矩阵实测**：单引号/双引号 arguments 各发一次实锤 #5
- **校准抽查发现假绿灯**：跑批全绿但 debate_quality 全 1 -> 深挖 judge 真实输入发现 #7。
  「测试全过 ≠ 行为正确」的实证
- **时序 bug 的假阴性**：#4 单测路径与跑批路径 import 顺序不同导致单测全过

## 根治：LLM Provider Gateway（PR #75）

表层修复稳定后，按 `docs/design/LLM Provider Gateway 设计档案` + 本次实战 3 个档案未覆盖缺口
落地防腐层（delta `add-llm-provider-gateway`，22/23 任务）：

- **能力契约**：`Capability`（含实战新增 `reasoning_forced` / `reasoning_must_echo_on_tool`）取代
  `_is_deepseek` 字符串猜测 -> #2/#5 类问题结构化
- **唯一解析入口** resolver：半套配置显式报错、judge 不静默回退、调用时读环境 -> #4 类
- **adapter 收口**：消息清洗/arguments 规范化/finish_reason 分型/litellm 运行时防护统一 -> #1/#5 类
- **输出合同** contracts：extract->validate->repair->typed error；evals 输入合同 -> #3/#6/#7 类
- **probe 五项探测 + 合同测试门禁**：换 provider 前即可发现「能聊天不能跑 Agent」

## 验证

- 表层：r6 跑批首获完整可信结果（judge_failures=0、四 rubric 有意义分布）
- 根治：989 passed、E2E 跑批正常退出 judge_failures=0；分数波动经证据链（prompt 生产/本地
  identical、quick 空 3/3 复测不可复现）定位为 GLM 随机性，架构零回归

## 遗留

- 5.1 legacy（`call_llm_stream`/`with_tools` 主链路）完整转调 gateway + 门禁最后一道收窄
  （需双路径对拍 + 真实 quick 验证，见 `tests/validation/llm-provider-gateway-validation.md`）
- @live 用例硬编码 DeepSeek 路由在方舟下 404（应改读 resolver）
- 完整设计档案对本次问题的覆盖度评审结论见会话记录（3 缺口已并入 delta spec）
