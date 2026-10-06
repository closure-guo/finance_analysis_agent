# add-prediction-pool-integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 观点池完整性——同 (symbol, 归属日) 建日主视图，同日重复关闭为 `duplicate_of_day`（无读数不计分母），并预登记 IC/ICIR + 敞口对齐蒙特卡洛零模型的结算统计口径。

**Architecture:** 落库层 append-only 不动；判定/统计消费层改造。`judgment.py` 加归属日/日主纯函数 → `job.py` 日批两阶段（superseded 先行、duplicate 关闭、horizon 判定只走日主）→ `metrics.py` marks 聚合排除 duplicate 行 → 新 `significance.py` 纯函数 + 只读 API → 前端状态徽标 + E2E。

**Tech Stack:** Python 3.12 / pytest / FastAPI / pandas；React 18 + TS + Vitest；Playwright（track-record 专属套件）。

**Delta:** `openspec/changes/add-prediction-pool-integrity/`（proposal/design/specs/tasks 已 --strict 通过）

## Global Constraints

- **在 worktree 实施**：`git worktree add .worktrees/prediction-pool-integrity -b add-prediction-pool-integrity`（主检出被并发会话使用，禁直接改）
- 口径预登记（Task 0）先于一切实现代码（AGENTS.md 评估约束：口径先改台账再动代码）；该任务可独立先行提交
- 落库层 `insert_prediction` / append-only / `_FROZEN_FIELDS` 语义不动；`duplicate_of_day` 只出现在判定消费层
- superseded 处理先行于 duplicate 关闭（同日观点变更链保留读数，spec track-record「同日观点变更链保留读数」场景）
- duplicate 关闭行：`status='duplicate_of_day'`、`resolution_rule='duplicate_of_day'`、无 exit_price/raw_return/excess_return/avoidance_status、`resolved_at=None`、不上报任何 Langfuse Score
- neutral 不走 superseded 的既有规则不动；日主判定对 neutral 同样适用（同日中性重申只留日主）
- 后端注释中文；commit 格式 `feat(outcome): ...` / `test(outcome): ...`
- E2E 禁 mock 被测系统；本 delta 涉前端徽标 = 交互类变更 → track-record 三套件门禁全绿 + 人工验证报告
- 存量生产库（data/sessions.db，76 条 open）不做迁移；dry-run 只读核对

---

### Task 0: metrics.md §1.9 口径预登记（docs-only，可独立合并）

**Files:**
- Modify: `docs/evals/metrics.md`（§1.9 outcome 口径节末尾追加）

**Interfaces:**
- Produces: 预登记版本号 `§1.9-v2`（后续 significance 模块与 11 月结算报告引用）

- [ ] **Step 1: 在 §1.9 节末尾追加以下内容**（保持该节既有编号风格，编号顺延）

```markdown
### §1.9-v2 结算显著性与信号一致性口径（预登记 2026-10-06，首批 T+20 结算前冻结）

**样本口径**：全部读数仅消费日主观点（add-prediction-pool-integrity：同 (symbol, 决策归属日)
取 created_at 最晚者；duplicate_of_day 行永不进入任何分子分母）。归属日派生与
settle_entry_price 同源（收盘前→当日；收盘后/非交易日→次一交易日）。

**IC/ICIR**：IC(月) = 当月判定完成的日主 long/short 观点中 resolved_win 占
(resolved_win + resolved_loss) 比例（resolved_neutral/unresolvable 不进；回避类单独成列）。
单期可判定样本 < 10 → 该期「样本不足」，不进 ICIR 序列；序列期数 < 6 → ICIR 不展示
（仅展示逐期 IC 与样本数；按月积攒，预计 2027-04 满足）。

**蒙特卡洛零模型（敞口对齐）**：对任何对外报告的组合区间超额读数，产出具分布定位——
随机化对象 = 同 universe 内随机替换选股；约束 = 每决策归属日每方向（long/short/neutral）
注数与真实组合完全一致；抽取 = 归属日当日起作用的池内均匀随机（无前视）；次数 10,000
（种子显式注入可复现）；报告 = 真实读数在零模型分布中的右尾分位与 p 值（含真实读数本身的
保守 p）。「跑赢/跑输」类结论必须附分位读数，单独出现的点估计 = 口径违规。
日主可判定样本 < 10 → 不产出（沿 settled<10 红线）。

**分母口径切点**：胜率/平均超额/回避正确率/样本量的「全观点 → 日主」切换登记为口径切点
（2026-10-06，切点时无任何已结算读数——纯声明性登记，无历史读数需重算/分段）。净值正式
积累自 2026-10-08 重启，天然无跨切点混算。
```

- [ ] **Step 2: Commit**

```bash
git add docs/evals/metrics.md
git commit -m "docs(eval): §1.9-v2 预登记 IC/ICIR+敞口对齐蒙特卡洛零模型口径 (add-prediction-pool-integrity)"
```

---

### Task 1: judgment.py 归属日 + 日主纯函数

**Files:**
- Modify: `src/finance_agent/outcome/track_record/judgment.py`
- Test: `tests/outcome/test_track_record_judgment.py`（追加）

**Interfaces:**
- Consumes: 既有 `CLOSE_TIME_CUTOFF` 常量（judgment.py:20）
- Produces: `derive_attribution_date(created_at: str, calendar: list[str]) -> str`；`day_master_ids(predictions: list[dict], calendar: list[str]) -> set[str]`

- [ ] **Step 1: 写失败测试**（追加到 `tests/outcome/test_track_record_judgment.py`）

```python
# ---- add-prediction-pool-integrity: 归属日 + 日主视图 ----


class TestDeriveAttributionDate:
    CALENDAR = ["2026-10-09", "2026-10-12", "2026-10-13"]  # 10/10、10/11 为周末

    def test_收盘前产出归属当日交易日(self):
        # 10-09 为交易日，10:00 产出 → 归属 10-09
        assert derive_attribution_date("2026-10-09T10:00:00", self.CALENDAR) == "2026-10-09"

    def test_收盘后产出归属次一交易日(self):
        assert derive_attribution_date("2026-10-09T18:01:00", self.CALENDAR) == "2026-10-12"

    def test_非交易日产出归属其后首个交易日(self):
        # 周六 10-10 产出（无论时点）→ 归属 10-12
        assert derive_attribution_date("2026-10-10T11:00:00", self.CALENDAR) == "2026-10-12"
        assert derive_attribution_date("2026-10-11T20:00:00", self.CALENDAR) == "2026-10-12"

    def test_晚于全部交易日回退产出日本身(self):
        assert derive_attribution_date("2026-10-20T10:00:00", self.CALENDAR) == "2026-10-20"

    def test_空日历回退产出日(self):
        assert derive_attribution_date("2026-10-09T18:00:00", []) == "2026-10-09"


class TestDayMasterIds:
    def _p(self, pid, created, symbol="600519.SH"):
        return {"prediction_id": pid, "symbol": symbol, "created_at": created}

    def test_同日多条取created_at最晚(self):
        preds = [
            self._p("a", "2026-10-09T10:00:00"),
            self._p("b", "2026-10-09T18:01:00"),  # 收盘后 → 归属 10-12，不与上两条同组
            self._p("c", "2026-10-09T11:00:00"),
        ]
        masters = day_master_ids(preds, self.CALENDAR)
        assert masters == {"a", "b"}  # a/c 同日（10-09）取晚的 a；b 归属 10-12 独立成主

    def test_同created_at并列取prediction_id最大(self):
        preds = [self._p("z", "2026-10-09T10:00:00"), self._p("a", "2026-10-09T10:00:00")]
        assert day_master_ids(preds, self.CALENDAR) == {"z"}

    def test_跨标的不合并(self):
        preds = [
            self._p("a", "2026-10-09T10:00:00", symbol="600519.SH"),
            self._p("b", "2026-10-09T10:00:00", symbol="000001.SZ"),
        ]
        assert day_master_ids(preds, self.CALENDAR) == {"a", "b"}
```

（文件头 import 行补 `derive_attribution_date, day_master_ids`。）

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/outcome/test_track_record_judgment.py -k "AttributionDate or DayMaster" -v`
Expected: FAIL（ImportError: cannot import name）

- [ ] **Step 3: 最小实现**（追加到 `judgment.py`，`derive_entry` 之后）

```python
def derive_attribution_date(created_at: str, calendar: list[str]) -> str:
    """决策归属日：收盘前产出→当日（或其后首个交易日）；收盘后/非交易日→次一/首个交易日。

    与 derive_entry 同源（同用 CLOSE_TIME_CUTOFF，口径 §1.9-v2）；calendar 为升序
    交易日字符串列表（日批判定传基准指数交易日）。晚于全部交易日或空日历 → 返回
    产出日本身（降级：同日去重仍按自然日成立）。
    """
    day, _, time_part = str(created_at).partition("T")
    before_close = (time_part or "00:00:00")[:5] < CLOSE_TIME_CUTOFF
    if before_close:
        for d in calendar:
            if d >= day:
                return d
    else:
        for d in calendar:
            if d > day:
                return d
    return day


def day_master_ids(predictions: list[dict], calendar: list[str]) -> set[str]:
    """日主观点 id 集合：同 (symbol, 归属日) 取 created_at 最晚者（§1.9-v2 样本口径）。

    同 created_at 并列时取 prediction_id 最大者（uuid hex，确定性 tiebreak）。
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for p in predictions:
        day = derive_attribution_date(str(p["created_at"]), calendar)
        groups.setdefault((str(p["symbol"]), day), []).append(p)
    masters: set[str] = set()
    for group in groups.values():
        winner = max(group, key=lambda p: (str(p["created_at"]), str(p["prediction_id"])))
        masters.add(str(winner["prediction_id"]))
    return masters
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/outcome/test_track_record_judgment.py -v`
Expected: 全部 PASS（含存量用例）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/judgment.py tests/outcome/test_track_record_judgment.py
git commit -m "feat(outcome): 归属日派生+日主视图纯函数 (add-prediction-pool-integrity)"
```

---

### Task 2: duplicate_of_day 状态注册（model.py）

**Files:**
- Modify: `src/finance_agent/outcome/track_record/model.py`（PREDICTIONS_STATUSES :57、_STATUS_LABELS :860、新 helper）
- Test: `tests/outcome/test_track_record_model.py`（追加）

**Interfaces:**
- Produces: `duplicate_prediction_ids(db_path=None) -> set[str]`（resolution_rule='duplicate_of_day' 的行）；状态枚举含 `duplicate_of_day`

- [ ] **Step 1: 写失败测试**（追加到 `tests/outcome/test_track_record_model.py`）

```python
# ---- add-prediction-pool-integrity: duplicate_of_day 状态与 helper ----


def test_duplicate_of_day_是合法状态且计入总数不计入统计分母(tmp_path):
    db = tmp_path / "t.db"
    init_predictions(db)
    _insert_prediction(db, symbol="600519.SH", direction="neutral")
    update_prediction_status(
        _only_pid(db), {"status": "duplicate_of_day", "resolution_rule": "duplicate_of_day"}, db
    )
    assert "duplicate_of_day" in PREDICTIONS_STATUSES
    stats = prediction_stats(db_path=db)
    assert stats["total"] == 1  # 总数不受限（UI 展示）
    assert stats["settled"] == 0 and stats["win_rate"] is None  # 不进胜率分母


def test_duplicate_prediction_ids_按resolution_rule筛选(tmp_path):
    db = tmp_path / "t.db"
    init_predictions(db)
    _insert_prediction(db, symbol="600519.SH", direction="neutral")
    dup_id = _only_pid(db)
    _insert_prediction(db, symbol="000001.SZ", direction="long")
    update_prediction_status(dup_id, {"status": "duplicate_of_day", "resolution_rule": "duplicate_of_day"}, db)
    assert duplicate_prediction_ids(db_path=db) == {dup_id}
```

（`_insert_prediction`/`_only_pid` 若该测试文件已有同形 helper 则复用；没有则本测试文件内补最小 helper：`insert_prediction({...全字段默认...}, db_path=db)` + `list_predictions(db_path=db)` 取 id。PREDICTIONS_STATUSES/duplicate_prediction_ids 加入 import。）

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/outcome/test_track_record_model.py -k duplicate -v`
Expected: FAIL（duplicate_prediction_ids 不存在 / 断言枚举失败）

- [ ] **Step 3: 最小实现**

model.py :57 状态元组追加（`"unresolvable"` 之后）：

```python
PREDICTIONS_STATUSES = (
    "open",
    "resolved_win",
    "resolved_loss",
    "resolved_neutral",
    # neutral 回避判定的生命周期终态（结果本身在 avoidance_status 列）
    "avoidance",
    "unresolvable",
    # 同日重复观点关闭终态（add-prediction-pool-integrity）：无结算读数、不计统计分母
    "duplicate_of_day",
)
```

_STATUS_LABELS（:860，中文关键词过滤映射）追加一行：

```python
    "同日重复": "duplicate_of_day",
```

模块内新增 helper（avoidance_stats 之后）：

```python
def duplicate_prediction_ids(db_path: str | Path | None = None) -> set[str]:
    """resolution_rule='duplicate_of_day' 的行 id（marks 聚合排除用；§1.9-v2）。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT prediction_id FROM predictions WHERE resolution_rule='duplicate_of_day'"
        ).fetchall()
        return {str(r["prediction_id"]) for r in rows}
    finally:
        conn.close()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/outcome/test_track_record_model.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/model.py tests/outcome/test_track_record_model.py
git commit -m "feat(outcome): duplicate_of_day 状态注册与筛选 helper (add-prediction-pool-integrity)"
```

---

### Task 3: job.py 日批两阶段判定

**Files:**
- Modify: `src/finance_agent/outcome/track_record/job.py`（supersede 循环之后、horizon 判定之前；返回 dict 增键）
- Test: `tests/outcome/test_track_record_job.py`（追加，复用其 `_db`/`_kline`/`_StubClient` 既有 fixture 模式）

**Interfaces:**
- Consumes: Task 1 `day_master_ids`；既有 `settle_open_predictions` 流程
- Produces: 返回 dict 新键 `duplicates_closed: int`

- [ ] **Step 1: 写失败测试**（追加到 `tests/outcome/test_track_record_job.py`，复用文件头既有 `_db`/`_kline`/`_StubClient`/`insert_prediction`）

```python
# ---- add-prediction-pool-integrity: 日主两阶段判定 ----


def _insert_open(db, symbol, created, direction="neutral", **kw):
    return insert_prediction(
        {
            "source_type": "live",
            "symbol": symbol,
            "symbol_name": symbol,
            "direction": direction,
            "entry_price": 10.0,
            "horizon_days": 20,
            "confidence": 0.6,
            "rationale_snapshot": {},
            "langfuse_trace_id": None,
            "timestamp": created,
            "resolution_rule": None,
        },
        db_path=db,
        **kw,
    )


def test_同日重跑仅日主进入horizon判定其余关闭(tmp_path):
    db = _db(tmp_path)
    # 688072 同日 10:00 与 11:00 各一条 neutral（收盘前 → 同归属日）
    _insert_open(db, "688072.SH", "2026-10-09T10:00:00")
    _insert_open(db, "688072.SH", "2026-10-09T11:00:00")
    klines = {"688072": _kline([10.0, 10.5, 11.0], start="2026-10-09")}
    result = settle_open_predictions(
        client=_StubClient(klines, benchmark=_kline([4000, 4010, 4020], start="2026-10-09")),
        db_path=db,
        langfuse=None,
    )
    rows = {r["prediction_id"]: r for r in list_predictions(db_path=db)}
    assert result["duplicates_closed"] == 1
    # 11:00（created_at 晚）为主保持 open 或被判定；10:00 关闭为 duplicate_of_day
    statuses = sorted((r["status"], r["created_at"]) for r in rows.values())
    dup = [s for s, _ in statuses if s == "duplicate_of_day"]
    assert len(dup) == 1
    # duplicate 行无结算读数
    dup_row = next(r for r in rows.values() if r["status"] == "duplicate_of_day")
    assert dup_row["raw_return"] is None and dup_row["resolved_at"] is None
    assert dup_row["resolution_rule"] == "duplicate_of_day"


def test_同日观点变更链superseded先行于duplicate关闭(tmp_path):
    db = _db(tmp_path)
    # 同日先 short 后 long（方向变更 → superseded 保留读数），再补一条 neutral 重跑
    _insert_open(db, "600519.SH", "2026-10-09T10:00:00", direction="short")
    _insert_open(db, "600519.SH", "2026-10-09T11:00:00", direction="long")
    klines = {"600519": _kline([10.0, 10.5, 11.0], start="2026-10-09")}
    result = settle_open_predictions(
        client=_StubClient(klines, benchmark=_kline([4000, 4010, 4020], start="2026-10-09")),
        db_path=db,
        langfuse=None,
    )
    rows = {r["prediction_id"]: r for r in list_predictions(db_path=db)}
    by_status = {}
    for r in rows.values():
        by_status.setdefault(r["status"], []).append(r)
    assert "resolved_loss" in by_status or "resolved_win" in by_status  # short 被结算（读数保留）
    assert all(
        r["status"] != "duplicate_of_day" for r in rows.values() if r["direction"] == "long"
    )


def test_跨日两条各自为日主独立判定(tmp_path):
    db = _db(tmp_path)
    # 两个不同交易日各一条（收盘后 18:01 → 次一交易日归属，仍跨日）
    _insert_open(db, "600519.SH", "2026-10-09T10:00:00")
    _insert_open(db, "600519.SH", "2026-10-10T10:00:00")
    klines = {"600519": _kline([10.0] * 30, start="2026-10-09")}
    result = settle_open_predictions(
        client=_StubClient(klines, benchmark=_kline([4000.0] * 30, start="2026-10-09")),
        db_path=db,
        langfuse=None,
    )
    assert result["duplicates_closed"] == 0
```

（`insert_prediction` 的关键字签名以 model.py:737 实际为准——若不收 `**kw`/`db_path` 位置不同，implementer 按实际签名调整调用而非改语义。）

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/outcome/test_track_record_job.py -k "日主 or superseded先行 or 跨日" -v`
Expected: FAIL（KeyError: 'duplicates_closed'）

- [ ] **Step 3: 实现**（job.py 改两处）

3a. 返回 dict 增键（`result = {...}` 初始块）：

```python
        "duplicates_closed": 0,
```

3b. supersede 循环结束后、`# 剩余 open 观点` 注释之前插入，并把原 `remaining = list_predictions(status="open", db_path=db_path)` 替换为：

```python
    # 日主两阶段·第二阶段（add-prediction-pool-integrity）：superseded 已先行（第一
    # 阶段，观点变更链读数已保留），剩余 open 中同 (symbol, 归属日) 仅 created_at
    # 最晚者进入 horizon 判定，其余关闭为 duplicate_of_day（无读数、不计分母、
    # 不上报 Score；§1.9-v2）。基准行情缺失 → calendar 空 → 归属日退化为自然日，
    # 同日去重仍成立（降级模式，日志 WARN）。
    remaining_open = list_predictions(status="open", db_path=db_path)
    calendar = (
        [str(d) for d in benchmark["日期"]]
        if benchmark is not None and not benchmark.empty
        else []
    )
    if not calendar:
        logger.warning("基准交易日历不可得，日主判定退化为自然日归属")
    masters = day_master_ids(remaining_open, calendar)
    for p in remaining_open:
        if str(p["prediction_id"]) in masters:
            continue
        try:
            update_prediction_status(
                p["prediction_id"],
                {
                    "status": "duplicate_of_day",
                    "resolution_rule": "duplicate_of_day",
                    "resolved_at": None,
                },
                db_path,
            )
            result["duplicates_closed"] += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("同日重复关闭失败 %s: %s", p["prediction_id"], e)
            result["errors"] += 1
    remaining = [p for p in remaining_open if str(p["prediction_id"]) in masters]
```

import 行（job.py 顶部 `from finance_agent.outcome.track_record.judgment import (...)`）补 `day_master_ids`。

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `uv run pytest tests/outcome/test_track_record_job.py tests/outcome/test_track_record_judgment.py -v`
Expected: 全部 PASS（存量用例不红——存量测试若因新阶段对 fixture 数据关闭了原本保持 open 的同日行而失败，属行为变更断言，逐条核对后更新断言并在 commit message 说明）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/job.py tests/outcome/test_track_record_job.py
git commit -m "feat(outcome): 日批两阶段判定——superseded先行+同日重复关闭duplicate_of_day (add-prediction-pool-integrity)"
```

---

### Task 4: marks 聚合排除 duplicate 行（metrics.py + marking 语义核对）

**Files:**
- Modify: `src/finance_agent/outcome/track_record/metrics.py`（`build_equity_curve_points` / `compute_metrics_snapshot` / `recompute_rf_metrics_history` 三处 excl 合并）
- Test: `tests/outcome/test_track_record_metrics.py`（追加）

**Interfaces:**
- Consumes: Task 2 `duplicate_prediction_ids`
- Produces: NAV/指标聚合的 exclude 集合 = neutral ∪ duplicate（既有 `exclude_prediction_ids` 参数复用，签名不变）

**背景**（implementer 必读）：mark_open_predictions 只对 open 行写 marks；duplicate 关闭后不再新增 marks，但部署前已写入的 marks 行会永久留在表里污染 marks 差分聚合——聚合时显式排除是唯一正确位置。superseded 行的 marks **保留**（其读数合法，spec「变更链保留读数」）。

- [ ] **Step 1: 写失败测试**（追加到 `tests/outcome/test_track_record_metrics.py`，复用其 marks 构造既有 helper；无 helper 则按下述自建）

```python
# ---- add-prediction-pool-integrity: duplicate 行 marks 不进组合 ----


def test_duplicate_marks_被排除出组合聚合(tmp_path):
    db = tmp_path / "t.db"
    init_track_record_tables(db)
    master_id, dup_id = "p_master", "p_dup"
    # 两行 marks：master 正常，dup 为部署前残留
    insert_daily_mark({"prediction_id": master_id, "mark_date": "2026-10-09", "cum_return": 0.01, "benchmark_price": 4000}, db_path=db)
    insert_daily_mark({"prediction_id": master_id, "mark_date": "2026-10-10", "cum_return": 0.02, "benchmark_price": 4010}, db_path=db)
    insert_daily_mark({"prediction_id": dup_id, "mark_date": "2026-10-09", "cum_return": 0.50, "benchmark_price": 4000}, db_path=db)
    insert_daily_mark({"prediction_id": dup_id, "mark_date": "2026-10-10", "cum_return": 0.60, "benchmark_price": 4010}, db_path=db)
    pm = compute_metrics_from_marks(
        list_daily_marks(db_path=db),
        exclude_prediction_ids={"p_dup"},
    )
    # dup 的 +50% 暴涨不进首日组合收益（首盯市日本就贡献 0，第二日 master 0.01 vs 混入后 ~0.055+）
    assert abs(pm.nav_points[1]["agent_nav"] - 1.01) < 1e-6


def test_build_equity_curve_points_合并neutral与duplicate排除(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    init_track_record_tables(db)
    # neutral 行 + duplicate 行各写 marks，两者都必须被排除
    insert_daily_mark({"prediction_id": "p_neu", "mark_date": "2026-10-09", "cum_return": 0.3, "benchmark_price": 4000}, db_path=db)
    insert_daily_mark({"prediction_id": "p_dup", "mark_date": "2026-10-09", "cum_return": 0.4, "benchmark_price": 4000}, db_path=db)
    _insert_prediction_row(db, pid="p_dup", resolution_rule="duplicate_of_day", direction="long")
    _insert_prediction_row(db, pid="p_neu", direction="neutral")
    points = build_equity_curve_points(db_path=db)
    # 全部被排除 → 无 marks 可聚合 → 空点列
    assert points == []
```

（`_insert_prediction_row` 为本测试文件内新建 helper：直接 `insert_prediction({... symbol/direction/created_at/timestamp 等最小字段 ...}, db_path=db)` 后 `update_prediction_status(pid, {...}, db)` 置 resolution_rule；`init_track_record_tables`/`insert_daily_mark`/`list_daily_marks` 从 model.py import。`insert_daily_mark` 实际字段名以 model.py:416 为准核对。）

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/outcome/test_track_record_metrics.py -k duplicate -v`
Expected: 第二例 FAIL（duplicate 行未被自动排除）

- [ ] **Step 3: 最小实现**（三处 excl 合并，metrics.py）

`build_equity_curve_points` 内：

```python
    from finance_agent.outcome.track_record.model import (
        duplicate_prediction_ids,
        list_daily_marks,
        prediction_ids_by_direction,
    )

    marks = list_daily_marks(db_path=db_path)
    excl = prediction_ids_by_direction("neutral", db_path=db_path) | duplicate_prediction_ids(db_path=db_path)
```

`compute_metrics_snapshot` 同形合并：

```python
    excl = prediction_ids_by_direction("neutral", db_path=db_path) | duplicate_prediction_ids(db_path=db_path)
```

`recompute_rf_metrics_history` 内同形：

```python
    excl = prediction_ids_by_direction("neutral", db_path=db_path) | duplicate_prediction_ids(db_path=db_path)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/outcome/test_track_record_metrics.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/metrics.py tests/outcome/test_track_record_metrics.py
git commit -m "feat(outcome): NAV/指标聚合排除duplicate行marks (add-prediction-pool-integrity)"
```

---

### Task 5: significance.py 显著性统计纯函数

**Files:**
- Create: `src/finance_agent/outcome/track_record/significance.py`
- Test: `tests/outcome/test_track_record_significance.py`（新建）

**Interfaces:**
- Consumes: 日主口径的已判定行（dict：`resolved_at`/`status`/`direction`）
- Produces:
  - `monthly_ic(rows: list[dict], kind: str = "direction") -> list[dict]`（[{month, wins, losses, sample, ic, insufficient}]，按月升序；kind="direction" 聚 long/short 的 resolved_win/loss，kind="avoidance" 聚 neutral 的 avoidance_win/avoidance_loss——回避类单独成列，不混入方向 IC）
  - `icir(ic_series: list[dict]) -> float | None`
  - `simulate_random_excess(universe, long_counts, short_counts, closes, entry_map, exit_date, benchmark_return, n_sims=10000, seed=20261006) -> list[float]`
  - `excess_quantile(real_excess: float, sim_excess: list[float]) -> dict`（{quantile, p_value, n_sims}）
  - 常量 `IC_MIN_SAMPLE=10` / `ICIR_MIN_PERIODS=6`（口径 §1.9-v2）

- [ ] **Step 1: 写失败测试**（新建文件）

```python
"""add-prediction-pool-integrity Task 5:IC/ICIR/蒙特卡洛零模型纯函数。"""

from finance_agent.outcome.track_record.significance import (
    excess_quantile,
    icir,
    monthly_ic,
    simulate_random_excess,
)


class TestMonthlyIC:
    def test_ic只计long_short三态进二态(self):
        rows = [
            {"resolved_at": "2026-11-03", "status": "resolved_win", "direction": "long"},
            {"resolved_at": "2026-11-04", "status": "resolved_loss", "direction": "short"},
            {"resolved_at": "2026-11-05", "status": "resolved_neutral", "direction": "long"},
            {"resolved_at": "2026-11-06", "status": "avoidance", "direction": "neutral"},
        ]
        series = monthly_ic(rows)
        assert len(series) == 1
        s = series[0]
        assert s["month"] == "2026-11" and s["wins"] == 1 and s["losses"] == 1
        assert s["ic"] == 0.5 and s["sample"] == 2 and s["insufficient"] is True

    def test_跨月分组升序(self):
        rows = [
            {"resolved_at": "2026-12-01", "status": "resolved_win", "direction": "long"},
            {"resolved_at": "2026-11-02", "status": "resolved_loss", "direction": "long"},
        ]
        assert [s["month"] for s in monthly_ic(rows)] == ["2026-11", "2026-12"]

    def test_avoidance单独成列不混入方向ic(self):
        rows = [
            {"resolved_at": "2026-11-05", "status": "avoidance_win", "direction": "neutral"},
            {"resolved_at": "2026-11-06", "status": "avoidance_loss", "direction": "neutral"},
            {"resolved_at": "2026-11-03", "status": "resolved_win", "direction": "long"},
        ]
        assert monthly_ic(rows, kind="direction")[0]["wins"] == 1  # 回避行不进方向 IC
        av = monthly_ic(rows, kind="avoidance")
        assert av[0]["wins"] == 1 and av[0]["losses"] == 1 and av[0]["ic"] == 0.5


class TestICIR:
    def test_期数不足返回None(self):
        series = [{"ic": 0.6, "insufficient": False}] * 5
        assert icir(series) is None

    def test_样本不足期被剔除后不足6期返回None(self):
        series = [{"ic": 0.6, "insufficient": False}] * 5 + [{"ic": 0.9, "insufficient": True}]
        assert icir(series) is None

    def test_6期有效序列计算总体标准差ICIR(self):
        series = [{"ic": 0.5 + 0.01 * i, "insufficient": False} for i in range(6)]
        value = icir(series)
        assert value is not None and value > 0


class TestMonteCarlo:
    UNIVERSE = ["600519", "000001", "600030", "601818", "300750"]

    def _closes(self):
        return {s: {"2026-11-03": 10.0, "2026-12-01": 10.0 + i * 0.1} for i, s in enumerate(self.UNIVERSE)}

    def test_敞口对齐_注数与真实组合一致(self):
        sims = simulate_random_excess(
            universe=self.UNIVERSE,
            long_counts={"2026-11-03": 2},
            short_counts={"2026-11-03": 1},
            closes=self._closes(),
            entry_map={"2026-11-03": "2026-11-03"},
            exit_date="2026-12-01",
            benchmark_return=-0.04,
            n_sims=200,
            seed=42,
        )
        assert len(sims) == 200
        # 复现性：同种子同分布
        sims2 = simulate_random_excess(
            universe=self.UNIVERSE,
            long_counts={"2026-11-03": 2},
            short_counts={"2026-11-03": 1},
            closes=self._closes(),
            entry_map={"2026-11-03": "2026-11-03"},
            exit_date="2026-12-01",
            benchmark_return=-0.04,
            n_sims=200,
            seed=42,
        )
        assert sims == sims2

    def test_quantile_含真实读数保守p值(self):
        q = excess_quantile(0.10, [0.01, 0.02, 0.03])
        assert q["n_sims"] == 3 and q["quantile"] == 1.0 and q["p_value"] == 0.25
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/outcome/test_track_record_significance.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 最小实现**（新建 `significance.py`）

```python
"""结算显著性与信号一致性统计（add-prediction-pool-integrity；口径预登记 metrics.md §1.9-v2）。

纯函数模块：IC 月度序列 / ICIR / 敞口对齐蒙特卡洛零模型。输入方（API/结算报告）负责
只喂日主口径行（duplicate_of_day 永不进入）；本模块按 direction/status 二次防御过滤。
阈值与公式以 §1.9-v2 为准，禁止在调用方另写拷贝。
"""

from __future__ import annotations

import random

IC_MIN_SAMPLE = 10  # 单期可判定样本 < 10 → 该期「样本不足」，不进 ICIR
ICIR_MIN_PERIODS = 6  # 有效期数 < 6 → ICIR 不展示
MC_DEFAULT_N = 10_000  # 零模型抽样次数


def monthly_ic(rows: list[dict], kind: str = "direction") -> list[dict]:
    """按结算月（resolved_at[:7]）聚合月度读数（§1.9-v2）。

    kind="direction"（默认）：long/short 的 resolved_win/resolved_loss；
    kind="avoidance"：neutral 的 avoidance_win/avoidance_loss（回避类单独成列，
    SHALL NOT 混入方向 IC）。其余状态（resolved_neutral/unresolvable）与
    duplicate_of_day 行不进分子分母（防御性再过滤，输入方仍须只喂日主行）。
    返回按月升序：[{month, wins, losses, sample, ic, insufficient}]。
    """
    want_status = ("resolved_win", "resolved_loss") if kind == "direction" else ("avoidance_win", "avoidance_loss")
    want_dirs = ("long", "short") if kind == "direction" else ("neutral",)
    win_status, loss_status = want_status
    agg: dict[str, list[int]] = {}
    for r in rows:
        if r.get("direction") not in want_dirs:
            continue
        if r.get("status") not in want_status:
            continue
        month = str(r["resolved_at"])[:7]
        slot = agg.setdefault(month, [0, 0])
        slot[0 if r["status"] == win_status else 1] += 1
    out: list[dict] = []
    for month in sorted(agg):
        wins, losses = agg[month]
        sample = wins + losses
        out.append(
            {
                "month": month,
                "wins": wins,
                "losses": losses,
                "sample": sample,
                "ic": round(wins / sample, 4) if sample else None,
                "insufficient": sample < IC_MIN_SAMPLE,
            }
        )
    return out


def icir(ic_series: list[dict]) -> float | None:
    """mean(ic)/std(ic, population)；剔除 insufficient 期后期数 < ICIR_MIN_PERIODS → None。"""
    values = [s["ic"] for s in ic_series if not s.get("insufficient") and s.get("ic") is not None]
    if len(values) < ICIR_MIN_PERIODS:
        return None
    n = len(values)
    mu = sum(values) / n
    sd = (sum((v - mu) ** 2 for v in values) / n) ** 0.5
    if sd <= 0:
        return None
    return round(mu / sd, 4)


def simulate_random_excess(
    universe: list[str],
    long_counts: dict[str, int],
    short_counts: dict[str, int],
    closes: dict[str, dict[str, float]],
    entry_map: dict[str, str],
    exit_date: str,
    benchmark_return: float,
    n_sims: int = MC_DEFAULT_N,
    seed: int = 20261006,
) -> list[float]:
    """敞口对齐零模型：同 universe 随机替换选股，保持每归属日每方向注数一致（§1.9-v2）。

    closes: symbol → {date: close}（至少含各 entry 实际交易日与 exit_date 两档）；
    entry_map: 归属日 → 实际入场交易日（与真实组合 settle_entry_price 派生同源）。
    每次模拟：各归属日按注数无放回抽取（RNG 共享、种子注入、复现确定）；每注收益 =
    sign × (exit_close/entry_close − 1)；组合收益 = 全注等权均值；模拟超额 = 组合收益 −
    benchmark_return（与真实读数同基准同窗）。返回长度 n_sims 的模拟超额列表。
    """
    rng = random.Random(seed)
    slots: list[tuple[str, str, float]] = []  # (symbol_slot 由抽样填充; entry_day, sign)
    plans: list[tuple[str, str, float]] = []
    for day, n in long_counts.items():
        plans += [(day, entry_map[day], 1.0)] * int(n)
    for day, n in short_counts.items():
        plans += [(day, entry_map[day], -1.0)] * int(n)
    if not plans:
        return []
    pool = [s for s in universe if s in closes]
    out: list[float] = []
    for _ in range(n_sims):
        picks = [rng.choice(pool) for _ in plans]  # 有放回近似（池≥注数×10 时差异可忽略；§1.9-v2 简化口径）
        rets = []
        for (day, entry, sign), sym in zip(plans, picks):
            entry_close = closes[sym].get(entry)
            exit_close = closes[sym].get(exit_date)
            if not entry_close or not exit_close:
                continue  # 行情缺失注剔除（与真实读数的缺失处理一致）
            rets.append(sign * (exit_close / entry_close - 1.0))
        if not rets:
            continue
        out.append(sum(rets) / len(rets) - benchmark_return)
    return out


def excess_quantile(real_excess: float, sim_excess: list[float]) -> dict:
    """真实读数在零模型分布中的右尾定位；p 值含真实读数本身（保守）。

    quantile = 模拟中 ≤ 真实读数的比例；p_value = (严格大于真实读数的模拟数 + 1)
    / (n_sims + 1)——自身计入分母的保守 p（真实读数打败全部模拟时 p = 1/(n+1) 而非 0）。
    """
    if not sim_excess:
        return {"quantile": None, "p_value": None, "n_sims": 0}
    ranked = sorted(sim_excess)
    less_equal = sum(1 for v in ranked if v <= real_excess)
    greater = len(ranked) - less_equal
    quantile = less_equal / len(ranked)
    p_value = (greater + 1) / (len(ranked) + 1)
    return {
        "quantile": round(quantile, 4),
        "p_value": round(p_value, 4),
        "n_sims": len(ranked),
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/outcome/test_track_record_significance.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/outcome/track_record/significance.py tests/outcome/test_track_record_significance.py
git commit -m "feat(outcome): IC/ICIR+敞口对齐蒙特卡洛零模型纯函数 (add-prediction-pool-integrity)"
```

---

### Task 6: 只读统计端点 /api/track-record/significance

**Files:**
- Modify: `src/finance_agent/api.py`（`track_record_calibration` :2339 附近追加端点）
- Test: `tests/outcome/test_significance_api.py`（新建）

**Interfaces:**
- Consumes: Task 5 四函数；`list_predictions(db_path=...)`
- Produces: `GET /api/track-record/significance` → `{ic_series, icir, monte_carlo}`；`monte_carlo = {available: false, reason: "..."}`（首批结算时由结算报告任务消费 closes 面板产出真读数，端点在此披露状态）——**结论必附分位**由响应形态保证：`excess_point_estimate` 字段与 `quantile/p_value` 字段必须成对出现，端点永不单独返回点估计

- [ ] **Step 1: 写失败测试**（新建；DB 隔离沿用 `SESSIONS_DB_PATH` env + monkeypatch，与 tests/outcome 既有 API 测试同模式）

```python
"""add-prediction-pool-integrity Task 6:significance 只读端点。"""

import pytest
from fastapi.testclient import TestClient

from finance_agent.api import app
from finance_agent.outcome.track_record.model import (
    init_predictions,
    insert_prediction,
    update_prediction_status,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "sig.db"
    init_predictions(db)
    monkeypatch.setenv("SESSIONS_DB_PATH", str(db))
    # api 模块的 db 读取处若为启动期绑定，则用 monkeypatch.setattr 指向同一 tmp 库
    # （implementer 对照 api.py 既有 track-record 端点测试的隔离方式，保持一致）
    with TestClient(app) as c:
        yield c, db


def test_样本不足_端点返回insufficient与null_icir(client):
    c, db = client
    resp = c.get("/api/track-record/significance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["icir"] is None and body["ic_series"] == []
    assert body["monte_carlo"]["available"] is False


def test_duplicate行_不进ic序列(client):
    c, db = client
    # 造 1 条 duplicate 行（即使海量也不应出现在 ic_series）
    insert_prediction(
        {
            "source_type": "live",
            "symbol": "600519.SH",
            "symbol_name": "x",
            "direction": "long",
            "entry_price": 10.0,
            "horizon_days": 20,
            "confidence": 0.6,
            "rationale_snapshot": {},
            "langfuse_trace_id": None,
            "timestamp": "2026-11-01T10:00:00",
            "resolution_rule": None,
        },
        db_path=db,
    )
    rows = __import__("finance_agent.outcome.track_record.model", fromlist=["list_predictions"]).list_predictions(db_path=db)
    update_prediction_status(
        rows[0]["prediction_id"], {"status": "duplicate_of_day", "resolution_rule": "duplicate_of_day"}, db
    )
    body = c.get("/api/track-record/significance").json()
    assert body["ic_series"] == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/outcome/test_significance_api.py -v`
Expected: FAIL（404 Not Found）

- [ ] **Step 3: 最小实现**（api.py，`track_record_calibration` 之后）

```python
@app.get("/api/track-record/significance")
async def track_record_significance() -> dict[str, Any]:
    """结算显著性与信号一致性只读端点（add-prediction-pool-integrity；口径 §1.9-v2）。

    只读、不触发写操作。IC 只消费日主口径的已判定 long/short 行（duplicate_of_day
    防御过滤）；零模型在首批 T+20 结算时由结算报告任务产出（需行情面板），端点披露
    其可用状态——excess 点估计与分位必须成对出现，本端点永不单独返回点估计。
    """
    from finance_agent.outcome.track_record.model import duplicate_prediction_ids, list_predictions
    from finance_agent.outcome.track_record.significance import icir, monthly_ic

    rows = [
        r
        for r in list_predictions(db_path=None)
        if r.get("resolution_rule") != "duplicate_of_day"
    ]
    dup_ids = duplicate_prediction_ids()
    clean = [r for r in rows if r["prediction_id"] not in dup_ids]
    series = monthly_ic(clean, kind="direction")
    avoidance = monthly_ic(clean, kind="avoidance")
    return {
        "ic_series": series,
        "icir": icir(series),
        "avoidance_series": avoidance,
        "monte_carlo": {
            "available": False,
            "reason": "首批 T+20 结算时由结算报告任务产出（需个股行情面板）",
        },
    }
```

（`list_predictions(db_path=None)` 走 `_default_db_path()`——与同文件其他 track-record 端点取数路径一致；若 api.py 现行端点统一走某 helper，implementer 从众。）

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/outcome/test_significance_api.py tests/outcome -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/api.py tests/outcome/test_significance_api.py
git commit -m "feat(outcome): /api/track-record/significance 只读端点 (add-prediction-pool-integrity)"
```

---

### Task 7: 前端 duplicate_of_day 徽标

**Files:**
- Modify: `frontend/src/types.ts`（`PredictionStatus` 联合类型——以 `predictionStatus.ts` import 的实际类型文件为准）
- Modify: `frontend/src/pages/trackRecord/predictionStatus.ts`（两张映射表）
- Test: `frontend/src/pages/trackRecord/predictionStatus.test.ts`（若已有对应测试文件则追加；无则新建，路径从众 `frontend/src/pages/trackRecord/`）

**Interfaces:**
- Consumes: 后端状态 `duplicate_of_day`（Task 2）
- Produces: `PREDICTION_STATUS_LABEL.duplicate_of_day === '同日重复'`

- [ ] **Step 1: 写失败测试**

```typescript
import { PREDICTION_STATUS_CLS, PREDICTION_STATUS_LABEL } from './predictionStatus'

describe('duplicate_of_day 状态映射（add-prediction-pool-integrity）', () => {
  it('标签为「同日重复」', () => {
    expect(PREDICTION_STATUS_LABEL.duplicate_of_day).toBe('同日重复')
  })
  it('配色为三级灰（非成功/错误语义）', () => {
    expect(PREDICTION_STATUS_CLS.duplicate_of_day).toContain('text-tertiary')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/pages/trackRecord/predictionStatus.test.ts`
Expected: FAIL（TS 类型缺 duplicate_of_day / undefined）

- [ ] **Step 3: 最小实现**

`PredictionStatus` 类型（`frontend/src/types.ts` 中定义处）联合类型追加 `| 'duplicate_of_day'`。

`predictionStatus.ts` 两表各追加一行（保持与后端 PREDICTIONS_STATUSES 逐项对齐的既有纪律）：

```typescript
  duplicate_of_day: '同日重复',
```

```typescript
  duplicate_of_day: 'text-[color:var(--text-tertiary)]',
```

- [ ] **Step 4: 跑测试确认通过 + 前端全量**

Run: `cd frontend && npx vitest run`
Expected: 全部 PASS（TS 类型收紧后若有 switch/exhaustive 报错，按编译器指出的遗漏处补齐——只补映射，不加新逻辑）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/pages/trackRecord/predictionStatus.ts frontend/src/pages/trackRecord/predictionStatus.test.ts
git commit -m "feat(frontend): 观点日志duplicate_of_day徽标 (add-prediction-pool-integrity)"
```

---

### Task 8: E2E 用例（track-record 专属套件）+ seed 扩展

**Files:**
- Modify: `src/finance_agent/api.py`（`/api/test/seed` 的 track_record 造数块支持 `predictions` 列表——:698 起的 seed 处理段）
- Create: `tests/e2e/playwright/tests/track-record-duplicates.spec.ts`
- Test: 该 spec 即测试（track-record 套件 glob `track-record-*.spec.ts` 自动纳入专属 config）

**Interfaces:**
- Consumes: seed 端点既有 track_record 造数块（equity_curve/index_closes/metrics_snapshot）
- Produces: seed 块新可选键 `predictions: [{symbol, direction, status, resolution_rule, created_at, ...}]`（逐行 `insert_prediction` + 可选 `update_prediction_status` 置终态）

- [ ] **Step 1: 扩展 seed 端点**（track_record 造数块处理段，equity_curve 等键并列追加）

```python
        # predictions 造数（add-prediction-pool-integrity）：duplicate 徽标 E2E 用
        seed_predictions = track_seed.get("predictions")
        if isinstance(seed_predictions, list):
            from finance_agent.outcome.track_record.model import (
                insert_prediction as _seed_insert_prediction,
                update_prediction_status as _seed_update_status,
            )

            for i, row in enumerate(seed_predictions):
                pid = _seed_insert_prediction(
                    {
                        "source_type": "live",
                        "symbol": row["symbol"],
                        "symbol_name": row.get("symbol_name", row["symbol"]),
                        "direction": row.get("direction", "neutral"),
                        "entry_price": row.get("entry_price", 10.0),
                        "target_price": row.get("target_price"),
                        "horizon_days": row.get("horizon_days", 20),
                        "confidence": row.get("confidence", 0.6),
                        "rationale_snapshot": {},
                        "langfuse_trace_id": None,
                        "timestamp": row["created_at"],
                        "resolution_rule": None,
                    },
                    db_path=db_path,
                )
                if row.get("status") and row["status"] != "open":
                    _seed_update_status(
                        pid,
                        {
                            "status": row["status"],
                            "resolution_rule": row.get("resolution_rule", row["status"]),
                            "resolved_at": row.get("resolved_at"),
                        },
                        db_path=db_path,
                    )
```

（`insert_prediction` 返回值若非 pid 而是行 dict，取其 `["prediction_id"]`——implementer 按 model.py:737 实际返回值调整。）

- [ ] **Step 2: 写 E2E spec**（selector 纪律：data-testid 优先；track-record 套件独立库，造数 spec 不与空态断言 spec 同库冲突——本 spec 在专属套件内自带造数）

```typescript
import { expect, test } from '@playwright/test'

// add-prediction-pool-integrity：duplicate_of_day 徽标 + 统计口径用户可见面。
// 专属测试库造数（track-record 套件，独立 DB/端口对），禁止 mock 业务接口。
test.describe('同日重复观点徽标', () => {
  test('观点日志显示「同日重复」徽标且总览统计不计 duplicate 行', async ({ page }) => {
    await page.request.post('/api/test/seed', {
      data: {
        track_record: {
          predictions: [
            { symbol: '600519.SH', direction: 'neutral', created_at: '2026-10-09T10:00:00' },
            {
              symbol: '600519.SH',
              direction: 'neutral',
              created_at: '2026-10-09T11:00:00',
              status: 'duplicate_of_day',
              resolution_rule: 'duplicate_of_day',
            },
          ],
        },
      },
    })
    await page.goto('/track-record')
    const log = page.getByTestId('prediction-log')
    await expect(log).toContainText('同日重复')
    // duplicate 行不产结算读数：行内无「命中/未中」字样
    const dupRow = page.getByRole('row', { name: /同日重复/ })
    await expect(dupRow).not.toContainText('命中')
    await expect(dupRow).not.toContainText('未中')
  })
})
```

（`prediction-log` testid 若前端现无，在本任务中给观点日志容器补 `data-testid="prediction-log"`——纯测试钩子，不改布局。行定位优先 role+name。真实 selector 以生成时浏览器快照为准，禁止盲写。）

- [ ] **Step 3: 本地跑 track-record 专属套件**

Run: `cd tests/e2e/playwright && npx playwright test --config playwright.track-record.config.ts`
Expected: 新 spec PASS（首次跑前删除 `data/test-e2e-track-record.db` 残留）

- [ ] **Step 4: Commit**

```bash
git add src/finance_agent/api.py tests/e2e/playwright/tests/track-record-duplicates.spec.ts
git commit -m "test(e2e): duplicate徽标E2E+seed predictions造数 (add-prediction-pool-integrity)"
```

---

### Task 9: dry-run 核对 + 全量验证 + 人工验证报告

**Files:**
- Create: `tests/scripts/dry_run_day_master.py`
- Create: `tests/validation/2026-10-06-add-prediction-pool-integrity-validation.md`
- Modify: `openspec/changes/add-prediction-pool-integrity/tasks.md`（回填勾选）

- [ ] **Step 1: 写 dry-run 脚本**（只读，不写生产库）

```python
"""存量生产库日主分类 dry-run（add-prediction-pool-integrity，只读）。

用法：uv run python tests/scripts/dry_run_day_master.py [--db data/sessions.db]
输出每 symbol 的 open 观点分组：归属日 / 主 vs duplicate 计数 / 将被关闭的行 id 列表。
不改任何数据；基准交易日历以日批同源基准指数（000300）近 280 日K线日期近似。
"""

import argparse

from finance_agent.data.akshare_client import AKShareClient
from finance_agent.outcome.track_record.judgment import day_master_ids
from finance_agent.outcome.track_record.model import list_predictions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/sessions.db")
    args = parser.parse_args()

    preds = [p for p in list_predictions(db_path=args.db) if p["status"] == "open"]
    client = AKShareClient()
    bench = client.fetch_index_kline("000300", days=280)
    calendar = sorted({str(d)[:10] for d in bench["日期"]}) if bench is not None and not bench.empty else []
    masters = day_master_ids(preds, calendar)
    by_symbol: dict[str, list[dict]] = {}
    for p in preds:
        by_symbol.setdefault(p["symbol"], []).append(p)
    total_dup = 0
    for sym in sorted(by_symbol):
        group = by_symbol[sym]
        dups = [p for p in group if p["prediction_id"] not in masters]
        total_dup += len(dups)
        print(f"{sym}: open={len(group)} 主={len(group)-len(dups)} duplicate={len(dups)}")
        for p in dups:
            print(f"    将关闭: {p['prediction_id']} created={p['created_at']} dir={p['direction']}")
    print(f"\n合计 open={len(preds)} 主={len(masters)} 将关闭 duplicate={total_dup}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑 dry-run 并人工核对**

Run: `uv run python tests/scripts/dry_run_day_master.py`
Expected: 688072.SH 显示 主=1（按归属日分组后可能 >1——18 条跨多归属日，逐日各 1 主），duplicate 计数与 created_at 时间线一致；把完整输出粘贴进验证报告

- [ ] **Step 3: 全量验证**（verification-before-completion）

```bash
uv run ruff check && uv run mypy
uv run pytest tests/outcome tests/evals -q
cd frontend && npx vitest run && cd ..
cd tests/e2e/playwright && npx playwright test && npx playwright test --config playwright.track-record.config.ts && cd ../..
```
Expected: 全绿；任何红项先修后重跑（E2E 红先 playwright-debugger 诊断）

- [ ] **Step 4: 人工验证报告**（模板按 docs/project-workflow.md §3 Step 5）

`tests/validation/2026-10-06-add-prediction-pool-integrity-validation.md` 必含：
- dry-run 完整输出与逐 symbol 人工核对结论
- 观点日志徽标实机抽查（本地起前后端，造数库验证）截图路径
- overview 统计数字在 duplicate 关闭前后的对照（样本量分母变化）
- playwright-report 路径（三套件）
- 异常记录与结论段

- [ ] **Step 5: tasks.md 回填 + Commit**

勾选 `openspec/changes/add-prediction-pool-integrity/tasks.md` 对应项（E2E 项要求三套件全绿后勾），提交：

```bash
git add tests/scripts/dry_run_day_master.py tests/validation/2026-10-06-add-prediction-pool-integrity-validation.md openspec/changes/add-prediction-pool-integrity/tasks.md
git commit -m "test(outcome): dry-run核对+人工验证报告收口 (add-prediction-pool-integrity)"
```

- [ ] **Step 6: 部署窗口确认（不自动执行）**

提醒 owner：部署（docker compose 重建）前查 `GET /api/sessions` 无 running 会话（红线）；目标窗口 10-08 净值重启前。archive（sync+归档）在人工验证报告完成且正式库 dry-run 复核后进行。
