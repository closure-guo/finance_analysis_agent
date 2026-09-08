# Design: add-prompt-hot-reload

## Context

ADR-0016 的加载机制 + prompt-deploy-consistency 的单向发布契约存在两个体验缺口：(1) `load_prompt` 用 `@lru_cache`，换 production 版本需重启进程；(2) Langfuse UI 编辑不在 git，`deploy_prompts.py` 每次运行都会从本地 md 创建新版本并抢走 production 标签（用户 deep_mode v2 被 v3 覆盖的事故）。治理模型（本地 git 唯一权威源）因静默漂移事故确立，不可回退——本设计在保留该模型的前提下补齐「UI 热改 → 立即生效 → 自动持久」的闭环。

## Goals / Non-Goals

**Goals:**
- Langfuse production 变更最迟 30s 生效，无需重启（含 docker 容器）
- UI 编辑分钟级自动回流 git（sync_prompts 守护）
- deploy 预检：Langfuse 领先时拒绝盲推
- eval 逐字门禁保留为兜底

**Non-Goals:**
- 不改「本地 git 唯一权威源」治理模型（Langfuse-first 已被事故否决）
- 不做容器内回写（镜像层不持久，守护仅在宿主机）
- 不做 prompt 灰度/分流（production 单标签语义不变）
- 不改 eval 门禁的判定逻辑

## Decisions

**决策 1：TTL 缓存用标准库手写，不引 cachetools。**
`_CACHE: dict[str, tuple[float, PromptInfo]]` + `time.monotonic()`，TTL 常量 `PROMPT_CACHE_TTL = 30.0`（环境变量 `PROMPT_CACHE_TTL` 可覆盖，测试用短 TTL）。备选 cachetools.TTLCache——拒绝，为一个 dict 引依赖不值。`load_prompt` 签名不变，11+ caller 零改动。

**决策 2：兜底结果同样缓存，但 TTL 后重试 Langfuse。**
拉取失败回退本地时也写入 TTL 缓存（避免每请求打 WARN+读盘），TTL 过期后仍会重试 Langfuse——Langfuse 恢复后自动回到 production 跟随。这是与 lru_cache 的关键行为差异，写进测试。

**决策 3：sync_prompts 的比对口径复用 eval 门禁的归一函数。**
`_verify_prompt_sync`（evals/run.py）已有 CRLF/LF 归一比对，抽公共函数（或同语义实现）保证两边口径永远一致，防止「守护认为一致、门禁认为不一致」的分裂。

**决策 4：git 提交范围严格限定 + 冲突保护用 git status 判定。**
收编提交只 `git add` 发生变化的 prompt 文件（`src/finance_agent/prompts/<name>.md`），提交信息模板 `chore(prompts): 收编 Langfuse production 变更 <name> v<version>（UI 编辑回流）`。冲突保护：目标 prompt 文件在 `git status --porcelain` 中有未提交改动（M/?? 于该路径）时不覆盖，列入冲突清单退出非零。备选「三方合并」——拒绝，v1 人工裁决足够。

**决策 5：deploy 预检失败语义 = 拒绝整个发布（非跳过不一致项）。**
与 eval 门禁的全有或全无语义对齐，防止半发布状态。Langfuse 不可达时同样拒绝（保守），错误信息区分「不一致」与「不可达」。

**决策 6：--watch 用简单 sleep 循环，复用 --once 逻辑。**
默认 30s 间隔（`--interval` 可调）。不引入 APScheduler——宿主机单进程脚本，循环足矣，且与后端进程解耦（重启后端不影响守护）。

## Risks / Trade-offs

- [TTL 窗口内新旧 prompt 并存（进行中会话用旧版、新会话用新版）] → 可接受：与重启生效模型相比只会更一致；trace 的 prompt_version 字段如实记录各自版本
- [守护与手工编辑竞态（判定时无改动、写回前用户保存了编辑）] → 写回前二次校验 mtime/content；冲突保护是主防线
- [守护自动 commit 可能与用户正在进行的分支工作流纠缠] → 只暂存 prompt 文件、提交信息带固定前缀可 revert；文档注明建议在专用分支/干净工作区跑
- [30s 内每 prompt 一次 get_prompt 调用] → Langfuse SDK 自带秒级缓存，实际 QPS 极低，无成本问题

## Migration Plan

纯增量：loader 改缓存策略（行为向后兼容，签名不变）、两个脚本改造/新增。部署即生效；回滚 = 还原 lru_cache 装饰器。deep_mode 合并稿作为首个走「收编 → deploy」链路的实例。

## Open Questions

- TTL 默认 30s 是否需要按环境区分（dev 10s / prod 60s）？首版统一 30s，环境变量已留口
- 守护的 Windows 后台运行形态（任务计划/nssm/手动终端）由用户侧决定，脚本不绑定
