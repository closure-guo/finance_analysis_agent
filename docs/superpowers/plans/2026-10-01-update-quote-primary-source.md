# update-quote-primary-source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 行情 quote 主源从东财全市场 spot 翻页切换为腾讯 qt.gtimg.cn 单标的直查（1 请求/标的），东财降为回退，根治触发 IP 封禁的请求量模式。

**Architecture:** `akshare_client.py` 新增 `_fetch_tencent_quote`（GBK 解析 + 字段位序常量表 + 亿→元归一）与 `_quote_via_chain`（腾讯 → 东财 spot 惰性共享 → 百度+腾讯日线）统一链；`fetch_stock_quote` 与 `fetch_peer_data` 都走该链。PE 一律不由 quote 层产出（腾讯 PE 是 TTM 口径，按 spec 不消费），compute 的 derived_ttm 契约零改动。

**Tech Stack:** Python 3.12 / uv / pytest / akshare 1.18.94 / requests（已有依赖）

**关联 delta:** `openspec/changes/update-quote-primary-source/`（proposal / specs×2 / design / tasks）

## Global Constraints

- 实施在隔离 worktree：`.worktrees/quote-tencent-primary`，分支 `feat/quote-tencent-primary`（基于 origin/main 最新）
- 提交格式：`feat(data): ...` / `test(data): ...` / `docs: ...`；禁止 merge commit；完成后走 PR（origin/main 禁直推）
- 静态门禁：`uv run ruff check` 全绿；`uv run mypy` 81 错误/20 文件为环境漂移基线，**零增量**；全量 `uv run pytest tests/ --ignore=tests/evals` 0 failed
- 腾讯串字段位序以 2026-10-01 金样本（sh688072）钉死：`[3]=最新价 [31]=涨跌 [32]=涨跌% [33]=最高 [34]=最低 [38]=换手率 [39]=PE(TTM,不消费) [44]=流通市值(亿) [45]=总市值(亿) [46]=PB [1]=名称 [2]=代码`
- market_cap/float_market_cap 单位=亿 ×1e8 归一到**元**（与 C1 修复后的统一元契约对齐）；PB 不做跨源融合
- PE 契约（以 delta spec data-source-resilience 为权威）：**腾讯**市盈率字段（TTM 口径）MUST NOT 进入 quote 输出；东财回退路径的 static PE（`市盈率-动态`→`PE`）为既有保留契约，双源形单测继续生效；`state.stock_quote` 是普通 dict，新增键（如 `float_market_cap`）无 D6 通道卫兵问题（已核实 state.py:36）
- 非交互类变更（纯后端数据层），不适用 E2E 门禁（project-workflow §2 判别）
- prompt 零改动；citation 源路径（`quote.*`）零改动

---

### Task 1: `_fetch_tencent_quote` 单标的抓取函数（TDD）

**Files:**
- Modify: `src/finance_agent/data/akshare_client.py`（模块级常量，加在 `_add_prefix` 之前 L137 附近；方法加在 `_quote_from_spot_df` 之后）
- Test: `tests/data/test_akshare_client.py`（新增 `TestFetchTencentQuote` 类）

**Interfaces:**
- Consumes: `AKShareClient._to_sina_symbol(stock_code: str) -> str`（已有，akshare_client.py:734）
- Produces: `AKShareClient._fetch_tencent_quote(stock_code: str) -> dict | None`——成功返回含 `name/code/price/change/pct_change/high/low/turnover_rate/float_market_cap/market_cap/PB` 的 dict（market_cap/float_market_cap 为元），失败返回 None；Task 2/3 依赖此签名

- [ ] **Step 1: Write the failing test**

在 `tests/data/test_akshare_client.py` 文件末尾追加，并在文件头部 import 区补 `import requests`（当前未导入，`requests.Response` 构造 fake 响应用）：

```python
class TestFetchTencentQuote:
    """update-quote-primary-source：腾讯 qt.gtimg.cn 单标的行情直查（新主源）。

    金样本：2026-10-01 sh688072 实抓串（field 位序见 _TENCENT_FIELD_IDX）。
    总市值/流通市值单位=亿 ×1e8 归一到元；PE 字段（TTM 口径）MUST NOT 消费。
    """

    GOLDEN = (
        'v_sh688072="1~拓荆科技~688072~640.00~656.68~663.00~3387770~1660152~1727618'
        "~639.79~9~639.75~3~639.47~2~639.00~8~638.99~39~640.00~6~640.04~2~640.14~2"
        "~640.30~10~640.32~4~~20260930161437~-16.68~-2.54~675.00~635.73"
        "~640.00/3387770/2200617467~3387770~220062~1.19~85.97~~675.00~635.73~5.98"
        "~1818.80~1869.91~14.55~788.02~525.34~0.81~~20260930~161437"
    )

    @staticmethod
    def _gbk_response(payload: str):
        resp = requests.Response()
        resp.status_code = 200
        resp._content = payload.encode("gbk")
        return resp

    @patch("finance_agent.data.akshare_client.requests.get")
    def test_golden_sample_mapping(self, mock_get, client):
        mock_get.return_value = self._gbk_response(self.GOLDEN)
        result = client._fetch_tencent_quote("688072")
        assert result is not None
        assert result["name"] == "拓荆科技"
        assert result["code"] == "688072"
        assert result["price"] == 640.00
        assert result["change"] == -16.68
        assert result["pct_change"] == -2.54
        assert result["high"] == 675.00
        assert result["low"] == 635.73
        assert result["turnover_rate"] == 1.19
        assert result["market_cap"] == pytest.approx(1869.91e8)  # 亿 → 元
        assert result["float_market_cap"] == pytest.approx(1818.80e8)
        assert result["PB"] == 14.55

    @patch("finance_agent.data.akshare_client.requests.get")
    def test_pe_field_not_consumed(self, mock_get, client):
        """腾讯串携带 TTM 口径市盈率（field 39=85.97），quote MUST NOT 输出 PE 键。"""
        mock_get.return_value = self._gbk_response(self.GOLDEN)
        result = client._fetch_tencent_quote("688072")
        assert "PE" not in result
        assert "PE_ttm" not in result
        assert "PE_static" not in result

    @patch("finance_agent.data.akshare_client.requests.get")
    def test_truncated_string_missing_market_cap_returns_none(self, mock_get, client):
        """关键字段（price/market_cap）缺失 → None（触发回退），不抛异常。"""
        truncated = 'v_sh688072="1~拓荆科技~688072~640.00'  # 只有 4 段
        mock_get.return_value = self._gbk_response(truncated)
        assert client._fetch_tencent_quote("688072") is None

    @patch("finance_agent.data.akshare_client.requests.get")
    def test_request_exception_returns_none(self, mock_get, client):
        mock_get.side_effect = ConnectionError("refused")
        assert client._fetch_tencent_quote("688072") is None

    @patch("finance_agent.data.akshare_client.requests.get")
    def test_non_numeric_optional_field_skipped(self, mock_get, client):
        """可选字段非数值（如换手率位是 '-'）跳过该键，不炸解析。"""
        bad = self.GOLDEN.replace("~1.19~85.97~", "~-~85.97~")
        mock_get.return_value = self._gbk_response(bad)
        result = client._fetch_tencent_quote("688072")
        assert result is not None
        assert "turnover_rate" not in result
        assert result["market_cap"] == pytest.approx(1869.91e8)

    def test_symbol_prefix(self, client):
        """深市代码走 sz 前缀（_to_sina_symbol 复用）。"""
        assert client._to_sina_symbol("002371") == "sz002371"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/data/test_akshare_client.py::TestFetchTencentQuote -v`
Expected: FAIL（`AttributeError: 'AKShareClient' object has no attribute '_fetch_tencent_quote'`）

- [ ] **Step 3: Write minimal implementation**

`akshare_client.py` 顶部 import 区（L24 `import akshare as ak` 之前）加：

```python
import requests
```

`_add_prefix` 函数定义（L137）之前加模块级常量：

```python
# 腾讯 qt.gtimg.cn 单标的行情串字段位序（2026-10-01 金样本 sh688072 实抓钉死，
# update-quote-primary-source）。field 39 市盈率为 TTM 口径——腾讯无静态 PE，
# 按 delta spec MUST NOT 进入 quote 输出（PE 推导留给 compute derived_ttm）。
_TENCENT_FIELD_IDX: dict[str, int] = {
    "name": 1,
    "code": 2,
    "price": 3,
    "change": 31,
    "pct_change": 32,
    "high": 33,
    "low": 34,
    "turnover_rate": 38,
    "float_market_cap": 44,  # 亿
    "market_cap": 45,  # 亿
    "PB": 46,
}
# 亿 → 元归一字段（quote 层统一元契约，前端 Charts /1e8 显示「亿」）
_TENCENT_YI_FIELDS = frozenset({"float_market_cap", "market_cap"})
# 关键字段缺失即视为主源失败（触发回退）
_TENCENT_REQUIRED = ("price", "market_cap")
```

`AKShareClient` 类内、`_quote_from_spot_df` 方法之后加：

```python
def _fetch_tencent_quote(self, stock_code: str) -> dict | None:
    """腾讯 qt.gtimg.cn 单标的行情直查（update-quote-primary-source 新主源）。

    1 请求/标的，替代东财全市场 spot 翻页主源（~50 请求/次拿单只股票——
    本机 IP 被东财行情域封禁的直接成因，实测为 IP 级封禁、浏览器指纹伪装
    无效）。GBK 解码 + `~` 分割，字段位序见 _TENCENT_FIELD_IDX（金样本单测
    钉死）。总市值/流通市值单位为亿，×1e8 归一到元。解析失败/关键字段缺失
    返回 None 触发既有回退链，MUST NOT 抛异常。
    """
    symbol = self._to_sina_symbol(stock_code)
    try:
        resp = requests.get(f"https://qt.gtimg.cn/q={symbol}", timeout=10)
        text = resp.content.decode("gbk")
    except Exception as e:
        logger.warning("腾讯行情直查失败: %s %s", stock_code, e)
        return None
    fields = text.split("~")
    if len(fields) <= max(_TENCENT_FIELD_IDX.values()):
        logger.warning("腾讯行情串字段不足（%d 段）: %s", len(fields), stock_code)
        return None
    result: dict = {"name": fields[_TENCENT_FIELD_IDX["name"]], "code": stock_code}
    for key, idx in _TENCENT_FIELD_IDX.items():
        if key == "name":
            continue
        raw = fields[idx].strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        result[key] = value * 1e8 if key in _TENCENT_YI_FIELDS else value
    missing = [k for k in _TENCENT_REQUIRED if result.get(k) is None]
    if missing:
        logger.warning("腾讯行情关键字段缺失 %s: %s", missing, stock_code)
        return None
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/data/test_akshare_client.py::TestFetchTencentQuote -v`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/data/akshare_client.py tests/data/test_akshare_client.py
git commit -m "feat(data): 腾讯 qt.gtimg.cn 单标的行情直查函数——亿→元归一/PE 不消费/金样本单测 (update-quote-primary-source T1)"
```

---

### Task 2: `_quote_via_chain` 统一链 + `fetch_stock_quote` 主源切换（TDD）

**Files:**
- Modify: `src/finance_agent/data/akshare_client.py:344-394`（`fetch_stock_quote` 重构；新增 `_quote_fallback_baidu_tx` 与 `_quote_via_chain`）
- Test: `tests/data/test_akshare_client.py`（更新 `TestFetchStockQuote`/`TestFetchStockQuoteBaiduFallback`/`TestDataGapLogging`；新增 `TestFetchStockQuoteTencentPrimary`）

**Interfaces:**
- Consumes: Task 1 的 `_fetch_tencent_quote(stock_code) -> dict | None`
- Produces: `_quote_fallback_baidu_tx(stock_code: str) -> dict`（百度+腾讯日线回退，Task 3 复用）；`_quote_via_chain(stock_code: str, spot_df: pd.DataFrame | None = None) -> tuple[dict, pd.DataFrame | None]`（spot_df 传出供批调用方复用，Task 3 依赖）；`fetch_stock_quote(stock_code: str) -> dict` 对外签名不变

- [ ] **Step 1: Write the failing tests**

(a) 新增主源测试类（加在 `TestFetchStockQuoteBaiduFallback` 之前）：

```python
class TestFetchStockQuoteTencentPrimary:
    """update-quote-primary-source：腾讯单标的直查为主源。

    GOLDEN 内联（与 TestFetchTencentQuote.GOLDEN 同串）——本类在文件中
    位于该类之前，类体执行期不可前向引用。
    """

    GOLDEN = (
        'v_sh688072="1~拓荆科技~688072~640.00~656.68~663.00~3387770~1660152~1727618'
        "~639.79~9~639.75~3~639.47~2~639.00~8~638.99~39~640.00~6~640.04~2~640.14~2"
        "~640.30~10~640.32~4~~20260930161437~-16.68~-2.54~675.00~635.73"
        "~640.00/3387770/2200617467~3387770~220062~1.19~85.97~~675.00~635.73~5.98"
        "~1818.80~1869.91~14.55~788.02~525.34~0.81~~20260930~161437"
    )

    @staticmethod
    def _gbk_response(payload: str):
        resp = requests.Response()
        resp.status_code = 200
        resp._content = payload.encode("gbk")
        return resp

    @patch("finance_agent.data.akshare_client.ak")
    @patch("finance_agent.data.akshare_client.requests.get")
    def test_tencent_primary_no_spot_call(self, mock_get, mock_ak, client):
        mock_get.return_value = self._gbk_response(self.GOLDEN)
        result = client.fetch_stock_quote("688072")
        assert result["price"] == 640.00
        assert result["market_cap"] == pytest.approx(1869.91e8)
        assert "PE" not in result
        # 主源命中 → 不触发东财 spot 翻页
        mock_ak.stock_zh_a_spot_em.assert_not_called()
        assert client.sources_seen["market_cap"] == {"tencent"}

    @patch("finance_agent.data.akshare_client.ak")
    @patch("finance_agent.data.akshare_client.requests.get")
    def test_tencent_fail_falls_back_to_eastmoney(self, mock_get, mock_ak, client):
        mock_get.side_effect = ConnectionError("refused")
        mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame(
            {
                "代码": ["688072"],
                "名称": ["拓荆科技"],
                "最新价": [640.0],
                "总市值": [1.86e11],
                "市净率": [14.0],
            }
        )
        result = client.fetch_stock_quote("688072")
        assert result["price"] == 640.0
        assert result["market_cap"] == 1.86e11  # 东财主源单位=元（C1 契约）
        assert client.sources_seen["market_cap"] == {"eastmoney"}
```

(b) 更新既有类前置条件——三个类各加一个 autouse fixture 或逐测试加 `monkeypatch.setattr(client, "_fetch_tencent_quote", lambda code: None)`。`TestFetchStockQuote.test_returns_quote` 改名 `test_eastmoney_fallback_after_tencent_fail` 并加该 monkeypatch 行；`TestFetchStockQuoteBaiduFallback` 加类级 fixture：

```python
    @pytest.fixture(autouse=True)
    def _tencent_primary_down(self, monkeypatch):
        """本类钉死第二回退语义：腾讯主源与东财 spot 均不可达。"""
        monkeypatch.setattr(
            "finance_agent.data.akshare_client.AKShareClient._fetch_tencent_quote",
            lambda self, code: None,
        )
```

（`TestFetchStockQuoteBaiduFallback` 现有测试里 `mock_ak.stock_zh_a_spot_em.return_value = None` 即表达东财失败，语义不变。）`TestDataGapLogging.test_quote_degraded_to_name_only_logs_error` 同样加该 monkeypatch 行。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data/test_akshare_client.py::TestFetchStockQuoteTencentPrimary -v`
Expected: FAIL（当前实现主源仍是 spot_em，`assert_not_called()` 失败）

- [ ] **Step 3: Write minimal implementation**

`fetch_stock_quote`（L344-394）整体替换为三个方法：

```python
def _quote_fallback_baidu_tx(self, stock_code: str) -> dict:
    """第二回退：百度估值补 market_cap/PB + 腾讯日线补 price（原二级回退语义）。

    各源独立 try/except：任一失败不影响其余；全部失败仅名称时留 ERROR
    （维度缺失可观测）。百度总市值单位亿元 ×1e8 归一到元（终审 C1）。
    """
    result = self._fetch_name_fallback(stock_code)
    if result:
        result["code"] = stock_code
    for indicator, key, scale in (("总市值", "market_cap", 1e8), ("市净率", "PB", 1.0)):
        try:
            df_val = _call_ak(
                ak.stock_zh_valuation_baidu, symbol=stock_code, indicator=indicator
            )
            if df_val is not None and not df_val.empty and "value" in df_val.columns:
                result[key] = float(df_val.iloc[-1]["value"]) * scale
        except Exception:
            logger.warning("百度估值 %s 拉取失败: %s", indicator, stock_code)
    try:
        df_tx = _call_ak(
            ak.stock_zh_a_hist_tx, symbol=self._to_sina_symbol(stock_code), adjust="qfq"
        )
        if df_tx is not None and not df_tx.empty and "close" in df_tx.columns:
            result["price"] = float(df_tx.iloc[-1]["close"])
    except Exception:
        logger.warning("腾讯日线价格拉取失败: %s", stock_code)
    has_valuation = any(result.get(k) is not None for k in ("market_cap", "PB", "price"))
    self.sources_seen["market_cap"].add(
        "baidu" if result.get("market_cap") is not None else "missing"
    )
    if not has_valuation:
        logger.error("行情回退后仍缺估值/价格（PE/PB/市值/价格缺失）: %s", stock_code)
    return result

def _quote_via_chain(
    self, stock_code: str, spot_df: pd.DataFrame | None = None
) -> tuple[dict, pd.DataFrame | None]:
    """单标的完整行情链：腾讯主源 → 东财 spot（惰性共享）→ 百度+腾讯日线。

    spot_df 语义：None=未尝试（首次需要时拉取一次并传出供批调用复用）；
    空 DataFrame=已尝试且失败（哨兵，批调用不重复拉）。
    """
    q = self._fetch_tencent_quote(stock_code)
    if q is not None:
        self.sources_seen["market_cap"].add("tencent")
        return q, spot_df
    if spot_df is None:
        try:
            pulled = _call_ak(ak.stock_zh_a_spot_em)
            spot_df = pulled if pulled is not None else pd.DataFrame()
        except Exception as e:
            logger.warning("东财行情表拉取失败: %s", e)
            spot_df = pd.DataFrame()
    if not spot_df.empty:
        mapped = self._quote_from_spot_df(spot_df, stock_code)
        if mapped is not None:
            self.sources_seen["market_cap"].add(
                "eastmoney" if mapped.get("market_cap") is not None else "missing"
            )
            return mapped, spot_df
    logger.warning("腾讯/东财行情均不可用，尝试百度估值+腾讯日线回退: %s", stock_code)
    return self._quote_fallback_baidu_tx(stock_code), spot_df

def fetch_stock_quote(self, stock_code: str) -> dict:
    """个股行情（update-quote-primary-source 三级链）。

    主源：腾讯 qt.gtimg.cn 单标的直查（1 请求/标的）。东财全市场 spot
    翻页降为第一回退（仅主源失败时触发；该抓取模式是本机 IP 被东财
    行情域封禁的直接成因——实测 IP 级封禁，非代码注释早先猜测的 TLS
    指纹风控，浏览器指纹伪装无效）。第二回退：百度估值+腾讯日线。
    """
    q, _ = self._quote_via_chain(stock_code)
    return q
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/data/test_akshare_client.py -v`
Expected: PASS（全部，含既有 TestFetchStockQuote/TestFetchStockQuoteBaiduFallback/TestDataGapLogging 更新后）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/data/akshare_client.py tests/data/test_akshare_client.py
git commit -m "feat(data): quote 三级链重构——腾讯单标的主源/东财降回退1/百度+腾讯日线回退2 (update-quote-primary-source T2)"
```

---

### Task 3: `fetch_peer_data` 复用新链（TDD）

**Files:**
- Modify: `src/finance_agent/data/akshare_client.py:1054-1102`（`fetch_peer_data`）
- Test: `tests/data/test_akshare_client.py`（更新 `TestFetchPeerData`/`TestFetchPeerDataHeterogeneousRows`/`TestFetchPeerDataSharedSpot`）

**Interfaces:**
- Consumes: Task 2 的 `_quote_via_chain(stock_code, spot_df) -> tuple[dict, pd.DataFrame | None]` 与 `_quote_fallback_baidu_tx`
- Produces: `fetch_peer_data(stock_codes: list[str]) -> pd.DataFrame | None` 对外契约不变（列 name/code/PE/PB；出口 `_normalize_nan`）

- [ ] **Step 1: Write the failing tests**

(a) `TestFetchPeerData` 更新：docstring 改为「腾讯主源 mock + spot 快速失败 → 百度回退路径」；autouse fixture 保留 spot 失败；各测试把 `monkeypatch.setattr(client, "fetch_stock_quote", ...)` 换成 `_fetch_tencent_quote`/`_quote_fallback_baidu_tx` 组合：

```python
    def test_mixed_success_skips_failed_peer(self, client, monkeypatch):
        calls = []

        def fake_tencent(code):
            calls.append(code)
            if code == "688012":
                return {"name": "中微公司", "code": code, "PB": 10.0}
            return None  # 腾讯失败 → spot(fixture 失败) → 百度 name-only

        monkeypatch.setattr(client, "_fetch_tencent_quote", fake_tencent)
        monkeypatch.setattr(
            client, "_quote_fallback_baidu_tx", lambda code: {"name": "X", "code": code}
        )
        df = client.fetch_peer_data(["688012", "002371"])
        assert df is not None and len(df) == 1
        assert df.iloc[0]["name"] == "中微公司"
        assert df.iloc[0]["PB"] == 10.0
        assert calls == ["688012", "002371"]
```

（`test_quote_without_pe_pb_skipped`/`test_quote_nan_pe_pb_skipped`/`test_nan_pe_with_valid_pb_normalized`：mock 目标换成 `_fetch_tencent_quote` 返回同形状 dict；`test_all_failed_returns_none`：tencent→None + `_quote_fallback_baidu_tx`→name-only dict；`test_empty_input_returns_none` 不变。）

(b) `TestFetchPeerDataSharedSpot` 加 tencent-down 前置（每个测试加 `monkeypatch.setattr(client, "_fetch_tencent_quote", lambda code: None)`），`test_spot_table_serves_all_peers_without_fallback` 断言不变（spot 表 1× 拉取服务全部 peer、baidu/tx 不触发）——语义变为「腾讯失败后共享 spot 才启用」。

(c) 新增 tencent 主源服务 peer 的测试（加在 `TestFetchPeerDataSharedSpot`）：

```python
    @patch("finance_agent.data.akshare_client.ak")
    def test_tencent_primary_serves_peers_no_spot(self, mock_ak, client, monkeypatch):
        """主源健康：逐标的单请求服务全批，MUST NOT 触发东财 spot 翻页。"""
        def fake_tencent(code):
            return {
                "name": {"688012": "中微公司", "002371": "北方华创"}[code],
                "code": code,
                "PB": {"688012": 10.36, "002371": 11.26}[code],
            }

        monkeypatch.setattr(client, "_fetch_tencent_quote", fake_tencent)
        df = client.fetch_peer_data(["688012", "002371"])
        assert df is not None and len(df) == 2
        assert df.iloc[0]["PB"] == 10.36
        # 腾讯全命中 → 东财 spot/百度/腾讯日线零调用（请求量治理的核心断言）
        mock_ak.stock_zh_a_spot_em.assert_not_called()
        mock_ak.stock_zh_valuation_baidu.assert_not_called()

    def test_peer_pe_follows_serving_source(self, client, monkeypatch):
        """腾讯主源无 PE（spec 不消费）→ peer PE=None、PB 有值仍入行（PB 口径比较）。"""
        monkeypatch.setattr(
            client,
            "_fetch_tencent_quote",
            lambda code: {"name": "中微公司", "code": code, "PB": 10.36},
        )
        df = client.fetch_peer_data(["688012"])
        assert df is not None
        assert df.iloc[0]["PE"] is None
        assert df.iloc[0]["PB"] == 10.36
```

(d) `TestFetchPeerDataHeterogeneousRows.test_mixed_none_and_value_pe_no_nan_leak` 改为经真实链驱动（tencent down → spot 表供 688012 行含 PE → 002371 表未命中 → 百度 PB）：

```python
    @patch("finance_agent.data.akshare_client.ak")
    def test_mixed_none_and_value_pe_no_nan_leak(self, mock_ak, client, monkeypatch):
        monkeypatch.setattr(client, "_fetch_tencent_quote", lambda code: None)
        monkeypatch.setattr("finance_agent.data.akshare_client._AK_MAX_RETRIES", 1)
        monkeypatch.setattr("finance_agent.data.akshare_client._AK_RETRY_DELAY", 0)
        mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame(
            {
                "名称": ["中微公司"],
                "代码": ["688012"],
                "最新价": [200.0],
                "总市值": [1.5e11],
                "市盈率-动态": [55.0],
                "市净率": [9.0],
            }
        )
        mock_ak.stock_zh_valuation_baidu.return_value = pd.DataFrame({"value": [11.26]})
        mock_ak.stock_zh_a_hist_tx.return_value = pd.DataFrame(
            {"date": ["2026-09-29"], "open": [1.0], "close": [1.1], "high": [1.2], "low": [0.9]}
        )
        df = client.fetch_peer_data(["688012", "002371"])
        assert df is not None and len(df) == 2
        # 出口无 NaN（is None 可靠判空）：spot 行 PE=55.0，回退行 PE=None
        assert df.iloc[0]["PE"] == 55.0
        assert df.iloc[1]["PE"] is None
        assert not any(isinstance(v, float) and pd.isna(v) for v in df["PE"].tolist())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/data/test_akshare_client.py -k "Peer" -v`
Expected: FAIL（现实现先拉共享 spot 表，与 tencent 主源前置矛盾）

- [ ] **Step 3: Write minimal implementation**

`fetch_peer_data`（L1054-1102）替换为：

```python
def fetch_peer_data(self, stock_codes: list[str]) -> pd.DataFrame | None:
    """逐标的抓取同业名称/PE/PB（复用 _quote_via_chain 三级链）。

    单标的失败或无 PE/PB 跳过不拖垮整批；全部失败或输入空返回 None。
    spot 表惰性共享：腾讯主源健康时逐标的 1 请求、零 spot 调用；腾讯
    失败后首个标的触发一次全市场 spot 拉取，批内复用（N 标的 1×）。
    """
    codes = [str(c).strip() for c in (stock_codes or []) if str(c).strip()]
    if not codes:
        return None
    spot_df: pd.DataFrame | None = None
    rows: list[dict] = []
    for code in codes:
        try:
            q, spot_df = self._quote_via_chain(code, spot_df)
        except Exception as e:
            logger.warning("同业 %s 行情抓取失败，跳过: %s", code, e)
            continue
        pe = q.get("PE") or q.get("pe")
        pb = q.get("PB") or q.get("pb")
        # 停牌 peer 的 NaN PE/PB（东财 spot 实测行为）按缺数归一——NaN 真值
        # 直通会毒化同业均值（终审 C1 同源问题）
        if pe is not None and pd.isna(pe):
            pe = None
        if pb is not None and pd.isna(pb):
            pb = None
        if pe is None and pb is None:
            logger.warning("同业 %s 无 PE/PB（全回退失败），跳过", code)
            continue
        rows.append({"name": q.get("name") or code, "code": code, "PE": pe, "PB": pb})
    if not rows:
        return None
    # 出口根因归一（终审 C1）：混合行 DataFrame 构造把 None 强转回 float64
    # NaN 毒化同业均值——出口必须 _normalize_nan
    return self._normalize_nan(pd.DataFrame(rows, columns=["name", "code", "PE", "PB"]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/data/test_akshare_client.py -v`
Expected: PASS（全部）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/data/akshare_client.py tests/data/test_akshare_client.py
git commit -m "refactor(data): fetch_peer_data 复用三级链——腾讯主源逐标的/spot 表惰性共享 (update-quote-primary-source T3)"
```

---

### Task 4: 口径裁决双源形单测 + 既有估值回归

**Files:**
- Test: `tests/data/test_akshare_client.py`（新增 `TestQuoteSourceCaliber`）

**Interfaces:**
- Consumes: Task 1/2 的全部产出
- Produces: 双源形金样本断言（腾讯/百度各自期望值钉死、不融合）——防后续改动破坏单位/口径契约

- [ ] **Step 1: Write the failing test**

```python
class TestQuoteSourceCaliber:
    """口径裁决单测（update-quote-primary-source design §2）。

    双源形：腾讯主源与百度回退各自的 market_cap/PB 期望值独立钉死，
    MUST NOT 跨源融合；market_cap 统一为元；PE 双路径均不产出。
    """

    @patch("finance_agent.data.akshare_client.requests.get")
    def test_tencent_caliber_golden(self, mock_get, client):
        mock_get.return_value = TestFetchTencentQuote._gbk_response(
            TestFetchTencentQuote.GOLDEN
        )
        result = client.fetch_stock_quote("688072")
        assert result["market_cap"] == pytest.approx(1869.91e8)  # 元
        assert result["PB"] == 14.55  # 腾讯口径，原样保留
        assert "PE" not in result

    @patch("finance_agent.data.akshare_client.ak")
    def test_baidu_caliber_golden(self, mock_ak, client, monkeypatch):
        monkeypatch.setattr(
            "finance_agent.data.akshare_client.AKShareClient._fetch_tencent_quote",
            lambda self, code: None,
        )
        mock_ak.stock_zh_a_spot_em.return_value = None
        mock_ak.stock_zh_valuation_baidu.side_effect = [
            pd.DataFrame({"date": [date(2026, 9, 7)], "value": [1869.91]}),
            pd.DataFrame({"date": [date(2026, 9, 7)], "value": [14.71]}),
        ]
        mock_ak.stock_zh_a_hist_tx.return_value = pd.DataFrame(
            {"date": [date(2026, 9, 8)], "close": [640.0]}
        )
        mock_ak.stock_info_a_code_name.return_value = pd.DataFrame(
            {"code": ["688072"], "name": ["拓荆科技"]}
        )
        result = client.fetch_stock_quote("688072")
        assert result["market_cap"] == pytest.approx(1869.91e8)  # 元（×1e8 归一）
        assert result["PB"] == 14.71  # 百度口径，与腾讯原样并存、不融合
        assert "PE" not in result
```

（文件头若缺 `from datetime import date` 则补。）

- [ ] **Step 2: Run test to verify it passes against current implementation**

Run: `uv run pytest tests/data/test_akshare_client.py::TestQuoteSourceCaliber -v`
Expected: PASS（本任务是契约钉死——若 FAIL 说明 Task 1/2 实现偏离 design，修复后重跑）

- [ ] **Step 3: Run valuation-integrity regression**

Run: `uv run pytest tests/nodes/test_compute_valuation.py tests/data/test_akshare_client.py -q`
Expected: 全部 PASS（derived_ttm 推导路径零改动）

- [ ] **Step 4: Commit**

```bash
git add tests/data/test_akshare_client.py
git commit -m "test(data): quote 双源形口径金样本——腾讯/百度各自钉死不融合 (update-quote-primary-source T4)"
```

---

### Task 5: 文档连锁（metrics.md §1 登记 + incident 033 C1 改写 + 观测项）

**Files:**
- Modify: `docs/evals/metrics.md`（§1 台账追加条目，沿用现有编号风格取下一可用号）
- Modify: `docs/incidents/033-stale-financials-valuation-chain-break-20260929.md`

**Interfaces:** 无代码接口；tasks.md 第 5/6 项的文档半。

- [ ] **Step 1: metrics.md §1 追加口径切点**

读 `docs/evals/metrics.md` §1 现有条目编号，取下一可用号，追加（内容按现有条目格式微调编号）：

```markdown
### 1.X quote 主源口径（update-quote-primary-source）

- 2026-10-01 起：行情 quote 主源由东财 stock_zh_a_spot_em（全市场翻页）切换为腾讯
  qt.gtimg.cn 单标的直查，东财降为回退1。触发背景：东财行情域（push2/push2his）对本机
  IP 实施封禁（2026-09-26 起，实测 IP 级、指纹伪装无效）。
- market_cap 单位契约不变（元；来源值亿 ×1e8）。PB 存在腾讯/百度双源口径差（2026-09-30
  拓荆样本 14.55 vs 14.71，净资产快照口径不同），主源命中即以主源为准，不做跨源融合。
- 腾讯 PE 字段（TTM 口径）不消费：quote 无 PE 时 compute 恒走 derived_ttm 推导口径。
  东财主源时代的 static 口径 PE 在生产链路不再默认出现——涉及 static 口径 GARP 的 eval
  断言按缺失桶解释。
- **eval 对照期警示**：跨 2026-10-01 切点的 run 对比需标注数据源（尤其 PB 与相对估值
  输入）；runs.jsonl 后续行建议在备注列登记 quote_source。
```

- [ ] **Step 2: incident 033 C1 保留意见改写**

在 `docs/incidents/033-...md` 状态/遗留段，将 C1 保留意见改写为（保留原文 strike-through 或按文档既有修订风格）：

```markdown
- ~~C1 保留意见：merge 后首次东财可用的 run 须抽验主源 PE 路径~~ **已重新定性
  （2026-10-01，update-quote-primary-source）**：东财行情域对本机 IP 封禁长期化
  （实测 IP 级、指纹伪装无效），quote 主源切换为腾讯单标的直查，东财降为回退1，
  生产链路 static 口径 PE 不再默认出现（compute 恒 derived_ttm）。C1 的单位归一
  代码与双源形单测作为回退路径资产保留。**新抽验义务：东财回退路径解封后，于任一
  实跑中抽验一次回退分支的 market_cap 量级与 sources_seen 标注。**
- 新增观测项（同 IP 风险外溢）：东财非行情域（解禁/新闻/研报/季度利润表，
  datacenter/搜索/emweb 域）与被封 push2 共享出口 IP，2026-10-01 实测仍可用。
  数据源监控快照（/api/cache/stats sources_seen）需盯住这些域的健康度；
  若扩散，评估 Tushare Pro 补基本面（T-1 语义仅适合非行情数据）。
```

- [ ] **Step 3: Commit**

```bash
git add docs/evals/metrics.md docs/incidents/033-stale-financials-valuation-chain-break-20260929.md
git commit -m "docs: metrics §1 登记 quote 主源切点 + incident 033 C1 重新定性/观测项 (update-quote-primary-source T5)"
```

---

### Task 6: 全管线人工验证（封禁环境实跑）

**Files:**
- Create: `tests/validation/2026-10-01-update-quote-primary-source-validation.md`

**Interfaces:** 依赖 Task 1-5 完成。验证环境复用 2026-10-01 incident 033 复跑先例（隔离冷启动）。

- [ ] **Step 1: 隔离冷启动后端**

```bash
mkdir -p .verify-quote-src && cp .env .verify-quote-src/.env
cd .verify-quote-src && PYTHONPATH="D:/WorkSpace/finance_analysis_agent" \
  SESSIONS_DB_PATH="$PWD/sessions.db" REPORTS_DIR="$PWD/reports" \
  uv run --project /d/WorkSpace/finance_analysis_agent uvicorn finance_agent.api:app \
  --host 127.0.0.1 --port 8011
```

Expected: `/api/health` 返回 `{"status":"ok"}`；冷缓存（新 cwd 无 cache.db）

- [ ] **Step 2: 发起 688072 实跑（worktree 代码）**

worktree 内跑 uvicorn（uv run --project 指向 worktree 根），POST `/api/analyze`
（body 用 UTF-8 文件：`{"query":"拓荆科技 688072 深度分析","stock_code":"688072","stock_name":"拓荆科技"}`）。
Expected: 管线 completed、全节点完成、三格式报告导出；后端日志**无**「东财行情不可用」warning（腾讯主源命中）、无 ERROR 级行情日志。

- [ ] **Step 3: 逐项核对 delta spec 场景**

| 核对项 | 预期（对照 2026-10-01 incident 033 基线报告） |
|---|---|
| 披露节估值快照 | 市值 ~1869 亿量级（当日腾讯值）、PE=TTM 推导口径、PB（腾讯口径） |
| GARP | failures 含「行业平均 PE 数据缺失（未参与比较）」诚实桶；无「PE >= 行业平均」伪文案 |
| 快照/健康度/季度趋势 | 与基线同构（中报 41.0%/47.85%/88.33 亿/51.31 亿；半导体设备口径 48.8 分带警告；单季毛利率序列） |
| 决策完整性 | 仓位「未提供」渲染、FM 置信度漂移说明、reeval_triggers 在场 |
| sources_seen | Langfuse/监控面 market_cap 桶含 `tencent` |
| 后端日志 | 无东财 push2 调用（封禁环境无法成功，若出现即主源未生效） |

- [ ] **Step 4: 落验证报告并提交**

报告含上表逐项结果 + 报告路径 + trace id；结论勾选。清理验证目录。

```bash
git add tests/validation/2026-10-01-update-quote-primary-source-validation.md
git commit -m "docs(validation): 688072 封禁环境实跑验证报告 (update-quote-primary-source T6)"
```

---

### Task 7: 静态门禁 + 分支收口

**Files:** 无新文件（门禁命令 + PR）

- [ ] **Step 1: 全量回归**

Run: `uv run pytest tests/ --ignore=tests/evals -q`
Expected: 0 failed（注意：全量测试需 Langfuse 在线，确认 docker compose 基础设施在跑）

- [ ] **Step 2: Lint + 类型**

Run: `uv run ruff check && uv run mypy`
Expected: ruff 全绿；mypy 与 main 基线持平（81 错/20 文件，零增量——用同命令在 main 与分支双侧对比）

- [ ] **Step 3: openspec 收口检查**

Run: `openspec validate update-quote-primary-source --strict`
Expected: valid；tasks.md 全部勾选

- [ ] **Step 4: 推分支 + 建 PR**

```bash
git push -u origin feat/quote-tencent-primary
gh pr create --base main --title "feat(data): 行情 quote 主源切换腾讯单标的直查——东财降回退（update-quote-primary-source）" --body "<概要：三因——IP 封禁根因/口径裁决/验证证据，引用 delta 与 validation 报告>"
```

Expected: PR 创建成功（origin/main 禁 merge commit，走 PR 流程）
