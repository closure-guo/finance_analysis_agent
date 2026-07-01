# FinGround Verification Node 设计文档

> **注意**: 本文档为设计档案。Agent 类型已按 ADR-0011 更新为 5 层架构（宏观/基本面/技术面/舆情 + Trader + Risk Management + Fund Manager）。下方 "基本面/技术面/估值/风险" 为旧版分类，`agent_type` 枚举需按 ADR-0011 更新。

## 1. 节点定位

### 1.1 架构位置

```
[Sub-Agent: 宏观/基本面/技术面/舆情分析师（ADR-0011 Layer I）]
                ↓ (生成分析文本 a)
        ┌───────────────────┐
        │  FinGround         │
        │  Verification Node │ ← 本文档描述的对象
        │  (Stage 2 原子验证) │
        └───────────────────┘
                ↓ (声明级判决 + 引用标注)
        [Grounded Regeneration Node] (Stage 3)
                ↓
        [修正后的分析文本 + 行内引用]
```

### 1.2 核心职责

1. **分解**：将子 Agent 生成的分析文本拆分为原子声明（atomic claims）
2. **分类**：按金融六类型分类法对每条声明打标
3. **对齐**：将声明与 Stage 1 检索到的证据（文本段落 + 表格单元格）精确对齐
4. **判决**：对每条声明给出 supported / contradicted / unverifiable 判决
5. **输出**：返回结构化验证结果，供下游 Regeneration Node 消费

### 1.3 非职责（由其他节点处理）

- 不处理检索（Stage 1 职责）
- 不执行文本重写（Stage 3 职责）
- 不做跨 Agent 一致性检查（需独立仲裁节点）
- 不做投资逻辑判断（子 Agent 职责）

---

## 2. 输入输出规范

### 2.1 输入数据结构

```python
from typing import List, Optional, Literal
from pydantic import BaseModel

class EvidenceChunk(BaseModel):
    """Stage 1 检索输出的证据块"""
    content: str                          # 文本内容或表格 JSON 表示
    chunk_type: Literal["text", "table"]  # 证据类型
    provenance: tuple[str, str, int, str] # (document, section, page, element_type)
    # 表格特有字段
    table_headers: Optional[List[str]] = None   # 列头
    table_rows: Optional[List[List[str]]] = None # 行数据

class VerificationInput(BaseModel):
    """验证节点输入"""
    query: str                            # 原始用户查询
    answer: str                           # 子 Agent 生成的分析文本
    evidence: List[EvidenceChunk]         # Stage 1 检索到的证据集合 E = {e1, ..., ek}
    agent_type: Literal["fundamental", "technical", "valuation", "risk", "synthesis"]
    metadata: Optional[dict] = None       # 附加元数据（如股票代码、报告期等）
```

### 2.2 输出数据结构

```python
class ClaimVerdict(BaseModel):
    """单条原子声明的验证结果"""
    # 声明身份
    claim_id: str                         # 声明唯一标识 (如 "C001")
    claim_text: str                       # 声明原文
    claim_type: Literal["numerical", "temporal", "entity_attribute", 
                        "comparative", "regulatory", "computational"]
    
    # 证据对齐
    aligned_evidence: List[dict]          # 对齐到的证据块 [{chunk_index, relevance_score, matched_span}]
    alignment_confidence: float           # 对齐置信度 (0-1)
    
    # 判决结果
    verdict: Literal["supported", "contradicted", "unverifiable"]
    verdict_confidence: float             # 判决置信度 (0-1)
    
    # 计算类特有
    formula_reconstructed: Optional[str] = None      # 重建的公式
    recomputed_value: Optional[float] = None         # 重计算结果
    original_value: Optional[float] = None           # 声明中的原始值
    tolerance_applied: Optional[float] = None        # 使用的容差 (默认 0.5%)
    
    # 引用标注
    citations: List[str]                  # 行内引用 ["Doc: AAPL_10K, §Item 7, p.23"] 
                                          # 或 ["Doc: AAPL_10K, Table 4, Row: Revenue, Col: FY2024"]
    
    # 解释
    explanation: Optional[str] = None     # 判决解释（用于调试和分析师审核）

class VerificationOutput(BaseModel):
    """验证节点完整输出"""
    input_query: str
    input_answer: str
    agent_type: str
    
    # 声明分解结果
    total_claims: int
    claims: List[ClaimVerdict]
    
    # 统计摘要
    summary: dict = {
        "supported_count": int,           # 支撑声明数
        "contradicted_count": int,        # 矛盾声明数（幻觉）
        "unverifiable_count": int,        # 无法验证声明数
        "hal_rate": float,                # 幻觉率 = (contradicted + unverifiable) / total
        "by_type": {                      # 按类型统计
            "numerical": {"supported": 0, "contradicted": 0, "unverifiable": 0},
            "computational": {"supported": 0, "contradicted": 0, "unverifiable": 0},
            # ...
        }
    }
    
    # 处理元数据
    processing_metadata: dict = {
        "latency_ms": int,                # 处理延迟
        "model_version": str,             # 使用的模型版本
        "distillation_applied": bool,     # 是否使用蒸馏模型
    }
    
    # 下游消费标志
    requires_regeneration: bool           # 是否有 contradicted/unverifiable 声明需要 Stage 3 处理
    requires_full_regeneration: bool      # contradicted/unverifiable >= 3 时触发全量重写
```

---

## 3. 内部子流程设计

### 3.1 流程总览

```
┌─────────────────────────────────────────────────────────────┐
│                    Verification Node                         │
│                                                              │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────┐   │
│  │ 3.2 Claim   │ → │ 3.3 Claim   │ → │ 3.4 Verdict     │   │
│  │    Decomp.  │   │    Align.   │   │    Classify     │   │
│  │             │   │             │   │                 │   │
│  │ LLM 拆分     │   │ Cross-Enc.  │   │ Distilled 8B    │   │
│  │ + Taxonomy  │   │ + NLI       │   │ + Formula Recon │   │
│  │ 分类        │   │ 对齐        │   │ 计算验证        │   │
│  └─────────────┘   └─────────────┘   └─────────────────┘   │
│         ↑                                    ↑               │
│         └──────────────┬─────────────────────┘               │
│                        │                                     │
│                   ┌────┴────┐                                │
│                   │ 输入    │                                │
│                   │ (q, a, E)│                               │
│                   └─────────┘                                │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 子流程一：声明分解与分类（Claim Decomposition & Typing）

**目标**：将 Agent 生成的长文本 `a` 拆分为原子声明集合 `C = {c1, ..., cn}`，并为每条声明标注类型。

#### 3.2.1 分解策略

采用 **FActScore 分解模式** 的金融域适配版本：

- 每条原子声明必须是一个**可独立验证**的单一事实
- 复合句必须拆分为多个声明
- 模糊表述（"approximately", "roughly"）保留原样，后续由判决层处理

**分解示例**：

```
输入文本:
"Apple FY2024 营收 3910 亿美元，同比增长 2%，毛利率 45.6% 较去年同期 44.1% 有所提升。"

分解结果:
C1 [numerical]:       "Apple FY2024 营收为 3910 亿美元"
C2 [computational]:   "Apple FY2024 营收同比增长 2%"
C3 [numerical]:       "Apple FY2024 毛利率为 45.6%"
C4 [comparative]:     "Apple FY2024 毛利率 45.6% 高于去年同期 44.1%"
C5 [temporal]:        "去年同期指 FY2023"
```

#### 3.2.2 六类型分类法（Financial Claim Taxonomy）

| 类型 | 定义 | 典型示例 | 验证策略 |
|------|------|---------|---------|
| **numerical** | 具体数值声明 | "营收 1000 亿" | 结构化提取 → 精确匹配表格单元格 |
| **temporal** | 时间范围声明 | "FY2024 Q3"、"截至 2024 年 9 月" | 时间范围比对 |
| **entity_attribute** | 实体属性声明 | "Apple 总部位于 Cupertino" | 实体-属性匹配 |
| **comparative** | 跨实体/时期比较 | "同比增长 5%"、"高于行业均值" | 双值提取 + 关系验证 |
| **regulatory** | 合规/法规引用 | "根据 SOX 法案第 302 条" | 法规库引用验证 |
| **computational** | 派生计算量 | "毛利率 45.6%"、"PE 为 20x" | **公式重建 + 重计算** |

**分类实现**：

```python
# 使用蒸馏后的 8B 模型做分类
# 输入: 原子声明文本
# 输出: 类型标签 + 置信度

class ClaimClassifier:
    """声明分类器（基于 Llama-3-8B 微调）"""
    
    def classify(self, claim_text: str) -> tuple[str, float]:
        prompt = f"""将以下金融声明分类为六种类型之一。
        
声明: "{claim_text}"

类型选项:
- numerical: 具体数值（营收、利润、股价等具体数字）
- temporal: 时间相关（财年、季度、日期）
- entity_attribute: 实体属性（公司特征、业务描述）
- comparative: 比较关系（同比、环比、高于/低于）
- regulatory: 法规引用（合规、监管、法律条款）
- computational: 计算派生（比率、增长率、估值指标）

仅输出类型名称:"""
        
        response = self.llm.generate(prompt)
        claim_type = self._parse_type(response)
        confidence = self._calibrate_confidence(claim_type)
        return claim_type, confidence
```

**分类验证依据**：论文附录 A 中验证 6-type 优于 3-type（+4.3 F1），10-type 无显著增益（p=0.23），6 类是最佳粒度。

---

### 3.3 子流程二：声明-证据对齐（Claim-Evidence Alignment）

**目标**：为每条声明 `ci` 在证据集合 `E` 中找到最相关的支撑证据。

#### 3.3.1 对齐流水线

```
声明 ci
    ↓
[检索候选证据]  ← 基于 BM25 + Dense Embedding 召回 top-k chunks
    ↓
[Cross-Encoder 精排]  ← 金融 NLI 微调模型，输出相关性分数
    ↓
[阈值判断]
    ├── 分数 >= threshold → 对齐成功，进入判决
    └── 分数 < threshold  → 标记 unverifiable（检索失败）
```

#### 3.3.2 Cross-Encoder 模型

```python
class EvidenceAligner:
    """声明-证据对齐器"""
    
    def __init__(self):
        # 基于金融 NLI 数据微调的 Cross-Encoder
        # 训练数据: 8,400 条来自 TAT-QA 和 FinQA 的金融 NLI 样本
        self.cross_encoder = CrossEncoder("finground-aligner-v1")  # 论文 87.2% F1
        self.threshold = 0.65  # 对齐阈值（可配置）
    
    def align(self, claim: str, evidence_chunks: List[EvidenceChunk]) -> List[dict]:
        # 构建 (claim, evidence) 对
        pairs = [(claim, chunk.content) for chunk in evidence_chunks]
        
        # Cross-Encoder 打分
        scores = self.cross_encoder.predict(pairs)
        
        # 取超过阈值的证据
        aligned = []
        for idx, score in enumerate(scores):
            if score >= self.threshold:
                aligned.append({
                    "chunk_index": idx,
                    "relevance_score": float(score),
                    "matched_span": self._extract_matched_span(claim, evidence_chunks[idx])
                })
        
        # 按相关性降序排列
        aligned.sort(key=lambda x: x["relevance_score"], reverse=True)
        return aligned
```

#### 3.3.3 数值型声明的特殊处理

对于 **numerical** 和 **computational** 类型声明，在 Cross-Encoder 粗排后增加**结构化精确匹配**：

```python
def structured_value_match(claim: str, evidence: EvidenceChunk) -> Optional[dict]:
    """
    从声明中提取数值、单位、时间期、实体
    与表格单元格做精确匹配
    """
    # 提取声明中的数值四元组
    claim_value = extract_value_quad(claim)  # (value, unit, period, entity)
    
    if evidence.chunk_type == "table":
        # 遍历表格单元格
        for row_idx, row in enumerate(evidence.table_rows):
            for col_idx, cell in enumerate(row):
                cell_value = parse_cell(cell)
                if values_equal(claim_value, cell_value, tolerance=0.005):
                    return {
                        "match_type": "exact_cell",
                        "cell_location": (row_idx, col_idx),
                        "cell_header": evidence.table_headers[col_idx] if evidence.table_headers else None,
                        "matched_value": cell_value
                    }
    return None
```

#### 3.3.4 检索失败处理

当所有证据的对齐分数均低于阈值时：

- 将该声明标记为 **unverifiable**
- **不默认标记为 supported**（监管场景禁止将"证据缺失"等同于"证据一致"）
- 路由到 Stage 3 进行**针对性重新检索**和再生
- 记录检索失败日志用于持续优化

---

### 3.4 子流程三：判决分类（Verdict Classification）

**目标**：基于对齐的证据，对每条声明判决 supported / contradicted / unverifiable。

#### 3.4.1 标准 NLI 判决（适用于前 5 种类型）

```python
def nli_verdict(claim: str, evidence: str, claim_type: str) -> tuple[str, float]:
    """
    使用金融 NLI 模型做蕴涵判断
    输出: entailment(→supported) / contradiction(→contradicted) / neutral(→unverifiable)
    """
    prompt = f"""基于以下证据，判断声明的真伪。

证据: "{evidence}"
声明: "{claim}"

判断选项:
- supported: 证据直接支持声明
- contradicted: 证据与声明矛盾
- unverifiable: 证据不足以判断

解释你的推理然后给出判断:"""
    
    response = distilled_8b_model.generate(prompt)
    verdict, confidence = parse_verdict(response)
    return verdict, confidence
```

#### 3.4.2 计算类声明的公式重建验证（核心亮点）

对于 **computational** 类型，标准 NLI 不足——需要**算术重验证**：

```python
class ComputationalVerifier:
    """计算类声明验证器 - FinGround 核心差异化能力"""
    
    # 47 个金融公式模板库
    FORMULA_TEMPLATES = {
        "gross_margin": {
            "pattern": r"毛利率.*?([\d.]+)%",
            "formula": lambda revenue, cogs: (revenue - cogs) / revenue * 100,
            "operands": ["revenue", "cost_of_goods_sold"],
            "tolerance": 0.5  # ±0.5% 容差
        },
        "yoy_growth": {
            "pattern": r"同比.*?增长.*?([\d.]+)%",
            "formula": lambda current, previous: (current - previous) / previous * 100,
            "operands": ["current_period_value", "previous_period_value"],
            "tolerance": 0.5
        },
        "pe_ratio": {
            "pattern": r"PE.*?([\d.]+)x",
            "formula": lambda price, eps: price / eps,
            "operands": ["stock_price", "earnings_per_share"],
            "tolerance": 0.5
        },
        "roe": {
            "pattern": r"ROE.*?([\d.]+)%",
            "formula": lambda net_income, equity: net_income / equity * 100,
            "operands": ["net_income", "shareholders_equity"],
            "tolerance": 0.5
        },
        # ... 共 47 个模板
    }
    
    def verify(self, claim: str, evidence_chunks: List[EvidenceChunk]) -> dict:
        """
        计算类声明验证流程:
        1. 识别 implied formula（匹配模板库）
        2. 从表格单元格提取操作数（operand）
        3. 重计算派生值
        4. 与声明值比对（±0.5% 容差）
        """
        # Step 1: 公式识别
        formula_name, formula_template = self._identify_formula(claim)
        if not formula_name:
            return {"verdict": "unverifiable", "reason": "无法识别计算公式"}
        
        # Step 2: 操作数提取（从表格单元格中精确提取）
        operands = {}
        for operand_name in formula_template["operands"]:
            value = self._extract_operand_from_evidence(
                operand_name, evidence_chunks
            )
            if value is None:
                return {"verdict": "unverifiable", "reason": f"无法提取操作数: {operand_name}"}
            operands[operand_name] = value
        
        # Step 3: 重计算
        recomputed = formula_template["formula"](**operands)
        
        # Step 4: 声明值提取
        claimed_value = self._extract_claimed_value(claim, formula_template["pattern"])
        
        # Step 5: 比对（含四舍五入容差）
        tolerance = formula_template["tolerance"]
        if claimed_value is None:
            verdict = "unverifiable"
        elif abs(recomputed - claimed_value) <= tolerance:
            verdict = "supported"
        else:
            verdict = "contradicted"
        
        return {
            "verdict": verdict,
            "formula_reconstructed": f"{formula_name}({', '.join(formula_template['operands'])})",
            "operands": operands,
            "recomputed_value": round(recomputed, 4),
            "original_value": claimed_value,
            "tolerance_applied": tolerance,
            "deviation_pct": round((recomputed - claimed_value) / claimed_value * 100, 2) if claimed_value else None
        }
    
    def _identify_formula(self, claim: str) -> tuple[str, dict]:
        """匹配声明到公式模板"""
        for name, template in self.FORMULA_TEMPLATES.items():
            if re.search(template["pattern"], claim):
                return name, template
        return None, None
    
    def _extract_operand_from_evidence(self, operand_name: str, 
                                       evidence_chunks: List[EvidenceChunk]) -> Optional[float]:
        """从证据表格中提取操作数值"""
        # 使用列头感知匹配 + 行关键词匹配
        for chunk in evidence_chunks:
            if chunk.chunk_type == "table":
                value = self._table_cell_lookup(operand_name, chunk)
                if value is not None:
                    return value
        return None
```

**论文指标**：端到端计算验证达 **90.2% F1**，这是 FinGround 相比通用幻觉检测器最核心的优势。

#### 3.4.3 判决汇总逻辑

```python
def aggregate_verdict(alignments: List[dict], nli_verdicts: List[dict]) -> tuple[str, float]:
    """
    综合对齐结果和 NLI 结果给出最终判决
    
    优先级:
    1. 如果有 contradicted 证据 → contradicted（一票否决）
    2. 如果有 supported 证据 → supported
    3. 否则 → unverifiable
    """
    contradicted_scores = [v["confidence"] for v in nli_verdicts if v["verdict"] == "contradicted"]
    supported_scores = [v["confidence"] for v in nli_verdicts if v["verdict"] == "supported"]
    
    if contradicted_scores:
        return "contradicted", max(contradicted_scores)
    elif supported_scores:
        return "supported", max(supported_scores)
    else:
        return "unverifiable", 0.0
```

---

## 4. 蒸馏模型部署设计

### 4.1 模型规格

| 属性 | 配置 |
|------|------|
| 基础模型 | Llama-3-8B-Instruct |
| 蒸馏源 | GPT-4o (gpt-4o-2024-05-13) |
| 训练数据 | 3,200 条金融 QA 样本（FinQA + TAT-QA + SEC filings） |
| 训练方法 | Reverse KL Divergence + 多任务目标 |
| 多任务目标 | 声明分解 + 证据对齐 + 判决分类 |
| 服务框架 | vLLM + Continuous Batching |
| 推理精度 | FP16 |
| 显存占用 | 18GB |

### 4.2 性能指标

| 指标 | 数值 |
|------|------|
| 检测 F1 | 91.4%（教师 GPT-4o 的 96.2%）|
| 每声明延迟（p95） | 340ms |
| 全 Pipeline 延迟（p95） | 3.8s |
| 相比教师加速 | 18×（每声明）/ 2.2×（全链路）|
| 每查询成本 | $0.003（教师 $0.047）|
| 并发吞吐（A100, 32 req） | 8.4 queries/s |

### 4.3 部署拓扑

```
┌─────────────────────────────────────┐
│            vLLM 服务                 │
│  ┌─────────────────────────────┐    │
│  │  FinGround-8B (FP16, 18GB)  │    │
│  │  - Claim Decomposition      │    │
│  │  - Claim Typing             │    │
│  │  - Verdict Classification   │    │
│  └─────────────────────────────┘    │
│  Continuous Batching + PagedAttention │
└─────────────────────────────────────┘
           ↑
    REST API (OpenAI-compatible)
           ↑
┌─────────────────────────────────────┐
│       Verification Node              │
│  (Cross-Encoder + Formula Engine    │
│   + Table Cell Lookup)              │
└─────────────────────────────────────┘
```

---

## 5. 错误处理与降级策略

### 5.1 异常场景处理

| 异常场景 | 处理策略 | 输出 |
|---------|---------|------|
| 声明分解失败（LLM 输出格式异常） | 回退到段落级验证（整段作为单条声明） | 低置信度标记 |
| 证据对齐全部低于阈值 | 标记 unverifiable，触发 Stage 3 重新检索 | 需重新检索标记 |
| 计算类公式识别失败 | 降级为标准 NLI 判决 | 无公式重建信息 |
| 操作数提取缺失 | 标记 unverifiable | 明确指出缺失的操作数 |
| 蒸馏模型超时 | 回退到 GPT-4o 教师模型（成本容忍时） | 高延迟标记 |
| 表格解析异常 | 退化为文本级验证 | 无单元格引用 |

### 5.2 置信度校准

```python
CONFIDENCE_THRESHOLDS = {
    "high": 0.85,      # 可直接信任，无需人工审核
    "medium": 0.65,    # 建议标注但自动通过
    "low": 0.50,       # 需标记待审核
    "reject": 0.0      # 低于此值视为系统错误
}

def apply_confidence_policy(claim: ClaimVerdict) -> ClaimVerdict:
    """根据置信度策略标记审核状态"""
    if claim.verdict_confidence >= CONFIDENCE_THRESHOLDS["high"]:
        claim.review_required = False
    elif claim.verdict_confidence >= CONFIDENCE_THRESHOLDS["medium"]:
        claim.review_required = False
        claim.review_flag = "low_confidence"
    else:
        claim.review_required = True
        claim.review_flag = "manual_review_needed"
    return claim
```

---

## 6. 与上下游节点的交互契约

### 6.1 与 Stage 1（检索节点）的契约

**Stage 1 必须提供：**

```python
class Stage1Output(BaseModel):
    evidence_chunks: List[EvidenceChunk]  # 带 provenance 的证据块
    query_complexity: Literal["simple", "moderate", "complex"]  # 查询复杂度
    retrieval_method: str  # 使用的检索方法（BM25/Dense/Iterative）
    coverage_score: Optional[float]  # 检索覆盖度评分（如有）
```

**Verification Node 对 Stage 1 的反馈：**
- 统计每轮验证中 unverifiable 声明的检索失败模式
- 用于动态调整检索策略（如扩展检索窗口、增加表格检索权重）

### 6.2 与 Stage 3（再生节点）的契约

**输出到 Stage 3：**

```python
class RegenerationInput(BaseModel):
    original_answer: str
    verification_results: List[ClaimVerdict]
    # Stage 3 只处理 contradicted 和 unverifiable 的声明
    claims_to_regenerate: List[ClaimVerdict]  # 过滤后需重写的声明
    regeneration_mode: Literal["targeted", "full"]  # targeted=逐条修复, full=全量重写
    
    @property
    def regeneration_mode(self) -> str:
        # 当 contradicted + unverifiable >= 3 时触发全量重写
        bad_count = sum(1 for c in self.claims_to_regenerate 
                       if c.verdict in ["contradicted", "unverifiable"])
        return "full" if bad_count >= 3 else "targeted"
```

### 6.3 与子 Agent 的集成模式

```python
# LangGraph 中的节点注册示例
from langgraph.graph import StateGraph

class AgentState(TypedDict):
    query: str
    agent_type: str
    evidence: List[EvidenceChunk]
    analysis_text: str
    verification_result: Optional[VerificationOutput]
    final_answer: Optional[str]

def verification_node(state: AgentState) -> AgentState:
    """LangGraph 节点包装器"""
    verifier = FinGroundVerifier(model="finground-8b")
    
    input_data = VerificationInput(
        query=state["query"],
        answer=state["analysis_text"],
        evidence=state["evidence"],
        agent_type=state["agent_type"]
    )
    
    result = verifier.verify(input_data)
    state["verification_result"] = result
    
    # 如果有需要重生的声明，设置标志
    state["requires_regeneration"] = result.requires_regeneration
    state["regeneration_mode"] = "full" if result.requires_full_regeneration else "targeted"
    
    return state

# 构建子 Agent 图
sub_agent_graph = StateGraph(AgentState)
sub_agent_graph.add_node("analyze", analysis_node)      # 子 Agent 分析
sub_agent_graph.add_node("verify", verification_node)    # FinGround 验证
sub_agent_graph.add_node("regenerate", regeneration_node) # Stage 3 重写

sub_agent_graph.add_edge("analyze", "verify")
sub_agent_graph.add_conditional_edges(
    "verify",
    lambda state: "regenerate" if state["requires_regeneration"] else END,
    {"regenerate": "regenerate", END: END}
)
```

---

## 7. 配置参数汇总

```yaml
# verification_node_config.yaml

model:
  base_model: "meta-llama/Llama-3.1-8B-Instruct"
  checkpoint: "finground-verifier-v1"
  precision: "fp16"
  device: "cuda"
  
serving:
  framework: "vllm"
  max_num_seqs: 32
  tensor_parallel_size: 1
  gpu_memory_utilization: 0.85

evidence_alignment:
  cross_encoder: "finground-cross-encoder-v1"
  top_k_candidates: 10
  relevance_threshold: 0.65
  
claim_classification:
  taxonomy_types: 6  # numerical, temporal, entity_attribute, comparative, regulatory, computational
  min_confidence: 0.7

computational_verification:
  formula_library_path: "./formula_templates.json"  # 47 个金融公式模板
  tolerance_pct: 0.5  # ±0.5% 容差
  max_operand_search_depth: 3  # 表格查找最大深度

verdict:
  aggregation_strategy: "conservative"  # conservative: 一票否决; optimistic: 多数投票
  min_verdict_confidence: 0.6

performance:
  max_latency_ms: 5000  # p95 超时阈值
  fallback_to_teacher: true  # 超时是否回退 GPT-4o
  batch_claims: true  # 是否批量推理声明
  batch_size: 16

monitoring:
  log_all_claims: true
  track_latency_by_type: true
  alert_on_high_hal_rate: 0.15  # HalRate > 15% 触发告警
```

---

## 8. 关键设计决策记录（Design Decisions）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 声明类型粒度 | 6-type（非 3-type 或 10-type）| 论文验证: 6-type 比 3-type +4.3 F1，10-type 无显著增益 |
| unverifiable 默认判决 | 标记为 unverifiable（非 supported）| 监管场景禁止将"证据缺失"等同于"证据一致" |
| 计算验证容差 | ±0.5% | 覆盖四舍五入惯例，论文验证此容差下 90.2% F1 |
| 全量重写阈值 | >=3 个声明需重写 | 防止增量修复的错误累积（论文 4.1% 每声明错误引入率）|
| 蒸馏 vs 教师 | 默认 8B，超时时回退 GPT-4o | 成本 $0.003 vs $0.047，F1 保留 96.2% |
| Cross-Encoder 训练数据 | TAT-QA + FinQA 共 8,400 条 | 金融 NLI 数据，87.2% 对齐 F1 |

---

## 9. 待办 / 后续优化

- [ ] 47 个金融公式模板的中文版适配（A 股报表科目差异）
- [ ] 跨 Agent 一致性仲裁节点的独立设计
- [ ] 分析师审核反馈的在线学习闭环
- [ ] 表格单元格引用的前端渲染组件
- [ ] 计算类声明的复杂公式链式验证（如 DCF 多步推导）

---

*文档版本: v1.0*
*基于 FinGround 论文 (arXiv:2604.23588) Stage 2 设计*
*设计日期: 2026-07-01*
