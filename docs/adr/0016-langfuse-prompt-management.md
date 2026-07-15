# ADR 0016: Prompt Management 迁移到 Langfuse（P-2 混合+兜底）

**Status**: Accepted
**Date**: 2026-07-14

## Context

现状 prompt 管理完全本地化：[prompts/loader.py](../../src/finance_agent/prompts/loader.py) 用 `lru_cache` 读盘 `src/finance_agent/prompts/*.md`（15 个文件，其中 2 个 ADR-0011 标记废弃），模板语法 `{{key}}` 字符串替换。另有 2 个 system prompt 内联在 [agent_factory.py:26](../../src/finance_agent/agent_factory.py)（`QUICK_MODE_PROMPT` / `DEEP_MODE_PROMPT`），不走 loader，改动需改代码 + 重新部署。

痛点：
1. **改 prompt 要重新部署**。调一个分析师 prompt 的措辞，要走改代码->commit->构建->部署全流程。
2. **无版本与 trace 关联**。ADR-0010 第 124 行要求"幻觉率成为可监控指标"，但无法回答"这份报告是哪版 prompt 产出的"--prompt 在代码里，trace 里没记录版本。
3. **无 A/B 实验能力**。prompt 改版无法在上线前对比新旧版效果。
4. **内联 prompt 不可见**。2 个 system prompt 藏在代码里，非开发者改不了。

Langfuse Prompt Management 提供：`production` label 控版本、运行时 `get_prompt` 拉取、`prompt.compile()` 渲染、Generation 自动记录 `prompt_name`+`prompt_version`、UI 内编辑无需部署。

Langfuse 在本项目可选（[.env.example:32](../../.env.example) 标注），本地开发与离线场景不应被云依赖卡死。

## Decision

### 1. P-2 混合+兜底模式

15 个 prompt 全部迁入 Langfuse（13 活跃 + 2 废弃标记 + 2 内联 system prompt）。本地 `.md` 文件保留并继续 commit，作为兜底基线。

**Loader 语义**：`load_prompt(name)` 改为：
1. 若配置了 Langfuse key，`langfuse.get_prompt(name)` 拉取 `production` label 版本，`prompt.compile(**vars)` 渲染
2. 拉取异常或未配置时，回退本地 `.md` + 现有 `{{key}}` 替换
3. 回退时打 `logger.warning("prompt %s 回退本地，可能版本漂移", name)`

Langfuse 是权威源（启用时），本地文件是安全网。

### 2. 全部 `type="text"`

所有 prompt 创建为 `type="text"`（单段文本，非多轮 chat 结构）。type 不可逆，选错要重建 prompt。当前无多轮 chat 结构 prompt，chat 类型留待未来。

### 3. 模板语法不变

保持 `{{var}}`，与 Langfuse 的 `{{var}}` 语法一致，零迁移成本。`prompt.compile(**vars)` 渲染。

### 4. 版本控制与上线

改 prompt 流程：在 Langfuse UI 编辑 -> 新版本打 `production` label -> 即时上线，无需重新部署。旧版保留可回滚。Generation 观测自动附带 `prompt_name` + `prompt_version`，使"这份报告由哪版 prompt 产出"在 trace 里可追溯。

### 5. 缓存

沿用 `lru_cache`（prompt 改动频率低）。Langfuse SDK 端有秒级缓存。换版本靠改 `production` label + 重启进程（本地 `lru_cache` 不主动失效）。可接受的代价：改 prompt 后需重启才全量生效。

## Alternatives Considered

- **P-1 全量迁移，本地退役**：硬依赖 Langfuse，本地开发和离线场景被云依赖卡死。违背 Langfuse 在本项目可选的定位。否决。
- **P-3 选择性迁移**（仅分析师/辩论者进 Langfuse，其余留本地）：13 个活跃 prompt 不算多，挑挑拣拣产生两套心智模型，维护更累。否决。
- **P-4 不迁移**：落空 ADR-0010 的 prompt 版本+trace 关联目标，内联 prompt 仍不可见。否决。
- **启动时强校验本地 vs Langfuse 一致**（C 方案）：Langfuse 挂了连本地都跑不了，抵消兜底价值。改为运行时回退+WARN（B 方案）。

## Consequences

- **正**：prompt 改动无需重新部署；trace 可追溯 prompt 版本（支撑 ADR-0010 幻觉率监控）；内联 prompt 也可见可改；为 ADR-0010 的 L2 Experiment（prompt 改版 A/B 对比）铺路。
- **权衡（必须明示）**：启用 Langfuse 后，**git 不再反映"线上真实 prompt"**。改 prompt 在 Langfuse UI 里改 + 打 label，本地 `.md` 会滞后。审计链路从 git 转移到 Langfuse（靠 trace 上的 prompt name+version 记录）。这是金融项目的真实权衡：git 可审计性（commit+review）vs 运行时灵活性（不部署即改）。P-2 的本地兜底基线缓解了这点--Langfuse 数据丢失时 git 里有 fallback，但"线上跑的哪版"的真相只在 Langfuse。
- **漂移可见但不阻断**：本地文件与 Langfuse production 版本不一致时仅 WARN，不报错不阻断运行。需运维关注 WARN 日志。
- **type 不可逆**：未来若需多轮 chat prompt，需新建 prompt 而非转换。

## References

- [Langfuse Prompt Management - get started](https://langfuse.com/docs/prompt-management/get-started)
- [Langfuse Prompt Management - data model (text vs chat, type 不可逆)](https://langfuse.com/docs/prompt-management/data-model)
- [ADR-0010](0010-tool-use-refactor.md) - 第 124 行"失败 claim 进 Langfuse score"、prompt 版本+trace 关联目标
- [ADR-0011](0011-five-layer-architecture.md) - 废弃 FA/IA Agent，2 个 prompt 标记废弃
- [prompts/loader.py](../../src/finance_agent/prompts/loader.py) - 待改造的 loader
- [agent_factory.py:26](../../src/finance_agent/agent_factory.py) - 待迁移的 2 个内联 system prompt
- [.env.example:32](../../.env.example) - Langfuse 可选标注
- CONTEXT.md "Langfuse Prompt" 条目
