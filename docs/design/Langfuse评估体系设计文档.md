# Langfuse 评估体系设计文档（LLM-as-a-Judge + Dataset/Experiments）

> 项目：finance_analysis_agent
> 前置：P8 已完成 Tracing + Prompt 管理 + citation_pass 上报（ADR-0015/0016）
> 本文档目标：将观测体系从「有 tracing」升级为「有评估闭环」，可直接作为 P10 实施依据。

---

## 1. 背景与问题

当前质量保障现状：

| 能力 | 现状 | 缺口 |
|---|---|---|
| 引用正确性 | ✅ citation.py 确定性校验 + `citation_pass` score | — |
| 主观质量（辩论质量、决策依据、一致性） | ❌ 无任何评估手段 | 需 LLM-as-a-Judge |
| Prompt/代码变更的回归验证 | ❌ 手动跑单只股票肉眼检查 | 需 Dataset + Experiments |
| 上线后质量漂移监控 | ❌ 无 | 托管 Evaluator 采样评估 |

核心原则：**能用代码查的用代码（零成本、确定），查不了的才用 Judge（贵、需校准）。** 已有的 `citation_pass` 是前者，本文档补后者。

---

## 2. 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                     质量信号三层分工                        │
├──────────────┬──────────────────┬───────────────────────┤
│ 确定性评估     │ LLM-as-a-Judge   │ 人工 Annotation        │
│ (代码/零成本) │ (rubric 打分)     │ (金标准/抽检校准)        │
├──────────────┼──────────────────┼───────────────────────┤
│ citation_pass│ debate_quality   │ 抽检 judge 准确性        │
│ section_cov. │ decision_ground. │ 处理 judge 存疑 case     │
│ 勾稽校验      │ report_relevance │ 校准后更新 rubric        │
└──────────────┴──────────────────┴───────────────────────┘
         │              │                    │
         └──────────────┼────────────────────┘
                        ▼
        ┌───────────────────────────────┐
        │   Dataset + Experiments        │
        │   线下：prompt 变更回归测试      │──→ CI 质量门控（可选 P2）
        └───────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │   托管 Evaluator（线上）         │
        │   同一套 rubric，10-20% 采样    │──→ Monitors 告警（可选 P2）
        └───────────────────────────────┘
```

**标准一致性**：线下 Experiment 和线上托管 Evaluator 使用**同一套 rubric**，保证「上线前测的」和「上线后看的」是同一把尺子。

---

## 3. Score 设计

### 3.1 Score 清单

| Score 名 | 类型 | 来源 | 评估对象 | 说明 |
|---|---|---|---|---|
| `citation_pass` | BOOLEAN | 代码（已有） | 全报告 | 引用校验通过与否 |
| `section_coverage` | NUMERIC (0-1) | 代码 | 报告结构 | 必备章节覆盖率 |
| `report_relevance` | NUMERIC (1-5) | Judge | 最终报告 | 是否回答用户实际查询 |
| `debate_quality` | NUMERIC (1-5) | Judge | 辩论记录 | 多空是否实质交锋、引用证据 |
| `decision_grounding` | NUMERIC (1-5) | Judge | 交易决策 | 决策是否有前文分析支撑 |
| `consistency` | NUMERIC (1-5) | Judge | 跨层结论 | Fund Manager 与 Risk Judge 一致性 |

控制数量：Judge 类 score 不超过 4 个，每个都有明确 rubric，避免"为评而评"。

### 3.2 Judge 模型选型

- 裁判模型：**deepseek-chat**（快速模型），不用 v4-pro。裁判任务比生成任务简单，成本降一个量级。
- 裁判调用必须出现在 trace 中（环境标记 `langfuse-llm-as-a-judge` 或自定义 environment），成本单独核算。

---

## 4. Rubric 定义

### 4.1 report_relevance（1-5 分）

```
你是投资分析报告评审专家。

【用户查询】{{query}}
【分析报告】{{report}}

评估报告是否切实回答了用户的查询意图：
5 = 完全切题，针对用户查询的标的和关注点展开
4 = 基本切题，少量无关内容
3 = 部分切题，有明显答非所问的章节
2 = 大部分内容偏离查询意图
1 = 完全答非所问（如用户问个股，输出行业综述）

只输出 JSON：{"score": <1-5>, "reason": "<一句话理由>"}
不以报告长度论优劣。
```

### 4.2 debate_quality（1-5 分）

```
你是投资研究评审专家。

【多空辩论记录】{{debate_history}}

评估辩论质量：
5 = 双方针对对方具体论点逐条交锋，均引用具体数据/指标佐证
4 = 有交锋，但部分论点未回应或证据不足
3 = 有交锋形式，但多为各说各话
2 = 几乎无交锋，仅陈述各自观点
1 = 单方输出或内容空洞

只输出 JSON：{"score": <1-5>, "reason": "<一句话理由>"}
```

### 4.3 decision_grounding（1-5 分）

```
你是投资决策评审专家。

【分析师结论】{{analyst_reports}}
【辩论结论】{{research_manager_decision}}
【交易决策】{{trade_decision}}

评估交易决策是否有前文分析支撑：
5 = 决策的每个关键论据都能在前文分析/辩论中找到出处
4 = 大部分论据有出处，个别结论跳跃
3 = 决策方向合理但论据链不完整
2 = 决策与前文分析关联薄弱
1 = 决策与前文矛盾或无中生有

只输出 JSON：{"score": <1-5>, "reason": "<一句话理由>"}
```

### 4.4 consistency（1-5 分）

```
评估最终报告各层结论的一致性：
- Fund Manager 结论是否与 Risk Judge 裁决一致
- 报告结论章节是否与分析师章节一致（无静默推翻）

5 = 完全一致；1 = 明显自相矛盾
只输出 JSON：{"score": <1-5>, "reason": "<一句话理由>"}
```

> 所有 rubric 显式声明「不以长度论优劣」，抑制 LLM judge 的冗长偏置。

---

## 5. Dataset 设计

### 5.1 建库策略

**首选：从历史 trace 捞取。** 在 Langfuse UI 浏览已有运行记录，把有代表性的 trace「Add to Dataset」。也可用 API 批量建。

**覆盖矩阵**（三模式 × 典型/边界）：

| 类别 | 用例数 | 示例 |
|---|---|---|
| deep-典型 | 5-6 | "300750"、"分析茅台"、"宁德时代值得买吗" |
| deep-边界 | 2-3 | 模糊名称（"平安"→ 多义）、ST 股、新上市股 |
| quick | 3-4 | "茅台最近有什么新闻"、"央行降准影响" |
| follow_up | 2-3 | 基于已有报告的追问 |
| 意图澄清（P9） | 1-2 | "分析一下这家公司"（无上下文，应触发反问） |

首版规模 **15-20 条**，够用即可，后续随 bad case 持续补充。

### 5.2 Item Schema

```python
{
  "input": {
    "query": "分析茅台",
    "mode": "deep",               # deep / quick / follow_up
    "session_id": "xxx"           # follow_up 模式需要
  },
  "expected_output": {
    "ticker": "600519",           # 自然语言解析正确性断言
    "must_cover": [               # deep 模式必备章节
      "偿债能力", "盈利能力", "技术面", "风险提示"
    ],
    "should_clarify": False       # 意图澄清断言
  },
  "metadata": {"category": "deep-典型", "source": "trace-20260701"}
}
```

`expected_output` 按需填写，只断言能确定性验证的字段；主观质量交给 Judge。

---

## 6. 代码实现

新增目录 `evals/`（与 src 平级，不侵入业务代码）：

```
evals/
├── conftest.py / env.py    # Langfuse 客户端初始化
├── dataset_seed.py         # 建库脚本（可重复执行，幂等）
├── task.py                 # run_analysis_task：封装 graph 入口
├── evaluators.py           # 确定性 + Judge evaluators
└── run.py                  # 跑实验入口（CLI 参数：实验名、prompt label）
```

### 6.1 task.py

```python
def run_analysis_task(*, item, **kwargs):
    """task 接收 dataset item 的 input，返回系统输出。"""
    result = run_graph(
        query=item.input["query"],
        mode=item.input["mode"],
        session_id=item.input.get("session_id"),
    )
    return {
        "report": result["final_report"],
        "ticker": result["ticker"],
        "citation_pass": result["citation_pass"],
        "debate_history": result.get("debate_history", []),
        "trade_decision": result.get("trade_decision", {}),
    }
```

### 6.2 evaluators.py

```python
# ── 确定性（零 token）──

def section_coverage_evaluator(*, input, output, expected_output, **kwargs):
    must = (expected_output or {}).get("must_cover", [])
    if not must:
        return None
    missing = [s for s in must if s not in output["report"]]
    return {"name": "section_coverage",
            "value": 1.0 - len(missing) / len(must),
            "comment": f"missing: {missing}" if missing else None}

def ticker_match_evaluator(*, input, output, expected_output, **kwargs):
    exp = (expected_output or {}).get("ticker")
    if not exp:
        return None
    return {"name": "ticker_match",
            "value": 1.0 if output["ticker"] == exp else 0.0}

# ── LLM-as-a-Judge ──

JUDGE_MODEL = "deepseek/deepseek-chat"

def _judge(rubric_prompt: str, name: str) -> dict:
    resp = call_judge_llm(model=JUDGE_MODEL, prompt=rubric_prompt)  # litellm
    parsed = parse_json_response(resp)  # 复用 nodes/_llm_utils.py
    return {"name": name, "value": parsed["score"], "comment": parsed["reason"]}

def debate_quality_evaluator(*, input, output, **kwargs):
    prompt = DEBATE_QUALITY_RUBRIC.replace(
        "{{debate_history}}", json.dumps(output["debate_history"], ensure_ascii=False))
    return _judge(prompt, "debate_quality")

def decision_grounding_evaluator(*, input, output, **kwargs):
    ...

def report_relevance_evaluator(*, input, output, **kwargs):
    ...
```

### 6.3 run.py

```python
dataset = langfuse.get_dataset("a-share-analysis-v1")

result = dataset.run_experiment(
    name=sys.argv[1],   # 如 "trader-prompt-v4"，每次改动一个名字
    task=run_analysis_task,
    evaluators=[
        section_coverage_evaluator,
        ticker_match_evaluator,
        debate_quality_evaluator,
        decision_grounding_evaluator,
        report_relevance_evaluator,
    ],
)
print(result.format())
```

**prompt 关联**：跑实验时用 `langfuse.get_prompt("trader", label="production")`，Langfuse 会自动把 prompt 版本记到 trace 上，UI 里可直接回答「哪个 prompt 版本分数高」。

### 6.4 实验工作流

```
改 prompt（或模型/代码）
  → uv run python evals/run.py "<改动名>"
  → UI 对比本次 run vs 基线 run
  → 均分下降 or 单 case 回归 → 回滚或继续调
  → 无回归且目标 score 提升 → 标记该 prompt 版本为 production
```

---

## 7. 线上托管 Evaluator（第二阶段）

在 Langfuse UI 配置，与线下同一套 rubric：

| 配置项 | 值 |
|---|---|
| 裁判模型 | deepseek-chat |
| 变量映射 | `{{query}}`→trace input；`{{report}}`→最终 span output；`{{debate_history}}`→debate 节点 output |
| 过滤器 | `mode=deep`（quick 模式无辩论，只跑 relevance） |
| 采样率 | 10-20%（控制裁判成本），放量后按成本回调 |

---

## 8. Judge 校准流程（必须做）

LLM judge 不是金标准，上线前必须校准：

1. 从实验结果中抽 20-30 条，加入 **Annotation Queue**
2. 人工按同一 rubric 打分（NUMERIC 1-5）
3. 对比 judge 分与人工分：
   - 一致性 ≥ 80% → rubric 可用
   - 系统性偏高/偏低 → 调整 rubric 措辞（常见：judge 对长报告偏宽松）
4. 校准后的 rubric 同步更新到线下 evaluator 和线上托管 evaluator

此后每月抽检一次，防 judge 漂移。

---

## 9. 成本预算

单次 deep 模式分析约 10+ 次 LLM 调用；评估侧增量成本：

| 项目 | 调用次数 | 模型 | 备注 |
|---|---|---|---|
| 线下实验（20 条 × 4 judge） | ~80 次/轮 | deepseek-chat | 每轮实验约 ¥0.5-1 |
| 线上托管（15% 采样 × 2 judge） | 0.3 次/trace | deepseek-chat | 可忽略 |

裁判成本合计 < 主流程成本的 5%，可接受。Judge 调用的 token 计入 `langfuse-llm-as-a-judge` 环境，Dashboard 单独看。

---

## 10. 实施计划

| 阶段 | 内容 | 工期 | 验收标准 |
|---|---|---|---|
| S1 | evals/ 脚手架 + Dataset 建库（15-20 条） | 1 天 | `dataset_seed.py` 跑通，UI 可见 dataset |
| S2 | task 封装 + 确定性 evaluators | 0.5 天 | coverage/ticker_match 出分 |
| S3 | 3 个 Judge evaluators + 首轮实验 | 1 天 | 基线 run 完成，`result.format()` 出表 |
| S4 | 人工校准（20-30 条 Annotation） | 0.5 天 | judge/人工一致性 ≥ 80% |
| S5 | 线上托管 Evaluator 配置 | 0.5 天 | 采样 trace 自动出 judge score |
| S6（可选） | CI 门控（experiment-action，均分阈值） | 0.5 天 | 分数低于阈值 PR 阻塞 |
| S7（可选） | Monitors 告警（judge 均分骤降 → webhook） | 0.5 天 | 收到测试告警 |

**MVP = S1-S4（约 3 天）**，即可形成「改 prompt → 跑回归 → 数据说话」的闭环。

---

## 11. 已知风险与对策

| 风险 | 对策 |
|---|---|
| Judge 冗长偏置/位置偏置 | rubric 显式声明；校准时重点检查 |
| Dataset 过拟合（只调这几条 case） | 随线上 bad case 持续补库；定期换一批 |
| 实验结果不可复现（LLM 温度） | 评估用 temperature=0；记录模型版本到 trace metadata |
| AKShare 数据随时间变化导致 expected_output 失效 | expected 只断言结构性内容（章节、ticker），不断言具体数值 |
| follow_up 模式依赖前置会话状态 | 该模式 case 单独建 session fixture，或首版跳过 |

---

## 12. 附录：术语

- **Score**：附着在 trace/observation 上的评分，NUMERIC / BOOLEAN / CATEGORICAL 三型
- **Rubric**：给裁判 LLM 的评分标准 prompt
- **Dataset**：测试用例集合（input + expected_output）
- **Experiment / Run**：某版本在 Dataset 上的一次完整执行
- **Annotation Queue**：人工标注队列，用于校准 judge
- **托管 Evaluator**：Langfuse 服务端自动运行的 LLM-as-a-Judge，支持采样与过滤
