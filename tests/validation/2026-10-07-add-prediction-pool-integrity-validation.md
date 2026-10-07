# 人工验证报告: add-prediction-pool-integrity

**日期**: 2026-10-07
**验证人**: ZCode implementer（Task 9：存量库 dry-run 核对 + 全量验证 + 逐项人工终裁）
**关联 delta**: openspec/changes/add-prediction-pool-integrity/
**E2E 门禁**: tests/e2e/playwright/playwright-report/index.html（默认套件 HTML 报告，对应 2026-10-07 12:27 串行门禁轮）；track-record 套件为 list reporter（无 HTML，结果见 §3.2）
**worktree / HEAD**: `.worktrees/prediction-pool-integrity`，分支 `add-prediction-pool-integrity`，验证起点 HEAD=7fc4ef17

---

## 1. 门禁总览

| 门禁 | 命令 | 结果 | 备注 |
|---|---|---|---|
| Lint | `uv run ruff check .` | ✅ 绿 | 全仓 All checks passed |
| 类型检查 | `uv run mypy src/finance_agent` | ✅ 绿（基线持平） | 83 errors / 21 files，与基线完全一致，无新增 |
| 后端定向 | `uv run pytest tests/outcome tests/test_api_track_record.py -q` | ✅ 绿 | **532 passed**（与门禁声称一致） |
| 后端全量 | `uv run pytest -q -m "not live"` | ✅ 绿 | **4152 passed, 6 skipped, 12 deselected**（10m38s；实测不依赖 Docker/Langfuse，全 stub） |
| 前端单测 | `cd frontend && npx vitest run` | ✅ 绿 | **645 passed / 77 files**（与门禁声称一致） |
| E2E 默认套件 | `npx playwright test --workers=1` | ✅ 绿 | **27 passed, 8 skipped, 0 failed**（跳过均为 @live 按设计跳过，见 §3.1） |
| E2E track-record | `npx playwright test --config playwright.track-record.config.ts` | ✅ 绿 | **8 passed**（含 duplicate 徽标用例） |

---

## 2. 存量生产库 dry-run 核对

### 2.1 方法与只读性

- **目标库**：主检出生产库 `D:\WorkSpace\finance_analysis_agent\data\sessions.db`（worktree 的 data/ 不含生产数据）。脚本从 worktree 运行，`--db` 传主检出绝对路径。
- **只读声明（静态）**：`tests/scripts/dry_run_day_master.py` 的全部数据路径 = `list_predictions`（纯 SELECT，见 `track_record/model.py`）+ `AKShareClient`（网络读）。无 `update_prediction_status`、无 sqlite3 直连、无任何 INSERT/UPDATE 路径（grep 验证）。
- **只读实证（动态）**：脚本运行前后生产库 md5 均为 `a2e9f80953965a57e120f8dba19dfd7f`，未发生任何写入。
- **与日批同源**：calendar = `fetch_index_kline("000300", 280)` 的「日期」列（`str[:10]` 规范化，与 `track_record/job.py::_normalize_dates` 同款）；日主 = `day_master_ids(open 池, calendar)`；open 池显式 `limit=100_000`。
- **对简报脚本样例的一处修正**：简报样例未传 limit，`list_predictions` 默认 50 会把生产库 76 条 open **静默截断**为最新 50 条（ oldest 26 条永不进判定）——正是本变更 P1 修复波修掉的取数病灶。脚本按 `model.py` 钳制上限显式传 `limit=100_000`，与 `job.py` 两处 open 池读取同款。

### 2.2 归属日模式与降级窗口（环境异常如实记录）

1. **基准指数取数降级**：东财 `index_zh_a_hist` 三次 ConnectionError（attempt 1/3..3/3）→ `fetch_index_kline` 内部回退新浪源**成功**，交易日历完整取得：280 个交易日，2025-08-07 .. 2026-09-30。**未**触发 calendar 空列表的全量自然日降级。
2. **局部自然日降级窗口**：日历末日 = 2026-09-30（最后一个已完成交易日；今日 10-07 尚未收盘/假期未结束）。所有 `created_at` 晚于 09-30 收盘的产出（09-30 深夜批 23:42-23:59 共 7 条 + 国庆假期 10-01..10-06 产出）在 `derive_attribution_date` 中找不到「次一交易日」，按代码文档降级为**自然日归属**（同日去重仍成立）。
3. **情景 B（上限参考，脚本扩展）**：对日历补「次一交易日 2026-10-08」再判定——晚于 09-30 收盘的全部产出收敛到该日分组，duplicate 19 → **38**。差异行即降级窗口产出（具体到行见 §2.3 两情景输出对比）。
4. **降级是瞬态的，不产生永久性口径污染**：日批第二阶段**每批重读 open 池并按当日日历重算**（`job.py::settle_open_predictions` 第二阶段）。次一交易日 K 线落地后的第一批会按完整交易日历重分类，剩余 ~19 条假期窗口 duplicate 将在彼时关闭；已按情景 A 关闭的 duplicate 不受影响（duplicate 不进任何分母，其归属日本身无读数意义）。**不存在 duplicate 以日主身份永久滞留分母的路径**。

### 2.3 dry-run 完整输出

```
AKShare 调用异常: index_zh_a_hist: ConnectionError (attempt 1/3)
AKShare 调用异常: index_zh_a_hist: ConnectionError (attempt 2/3)
AKShare 调用异常: index_zh_a_hist: ConnectionError (attempt 3/3)
AKShare 调用全部失败 (3 次): index_zh_a_hist
== dry-run day-master 核对（db=D:\WorkSpace\finance_analysis_agent\data\sessions.db，只读）==
open 池读取: 76 条（status=open, limit=100_000）
归属日模式: 交易日历归属（基准 000300 近 280 个交易日）
日历范围: 2025-08-07 .. 2026-09-30

──── 情景：A·今日日历窗口（截至 2026-09-30） ────

002916.SZ: open=5 主=5 duplicate=0
    归属日分布: ['2026-09-28', '2026-09-29', '2026-09-30', '2026-10-02', '2026-10-05']
    [主] p_df6dcbdc0a37 归属日=2026-09-28 created=2026-09-25T18:02:31.877988 dir=neutral
    [主] p_85d7eecce699 归属日=2026-09-29 created=2026-09-28T18:03:26.363675 dir=neutral
    [主] p_3ee2cfcbf5d8 归属日=2026-09-30 created=2026-09-30T23:42:50.798128 dir=long
    [主] p_e7289345344e 归属日=2026-10-02 created=2026-10-02T18:02:36.225080 dir=neutral
    [主] p_382a5686ba2b 归属日=2026-10-05 created=2026-10-05T18:02:24.028652 dir=neutral

300033.SZ: open=6 主=5 duplicate=1
    归属日分布: ['2026-09-28', '2026-09-30', '2026-10-02', '2026-10-05', '2026-10-06']
    [主] p_df94e71115c9 归属日=2026-09-28 created=2026-09-25T18:05:12.541048 dir=neutral
    [duplicate→将关闭] p_61ccddb2e67c 归属日=2026-09-30 created=2026-09-29T18:05:32.972394 dir=neutral
    [主] p_1568382c0fc7 归属日=2026-09-30 created=2026-09-30T23:45:27.064871 dir=neutral
    [主] p_9d15670dad39 归属日=2026-10-02 created=2026-10-02T18:05:22.924548 dir=neutral
    [主] p_0b3cedfb6c82 归属日=2026-10-05 created=2026-10-05T18:04:47.441880 dir=neutral
    [主] p_a85ac044cf75 归属日=2026-10-06 created=2026-10-06T18:05:22.276397 dir=neutral

300750.SZ: open=1 主=1 duplicate=0
    归属日分布: ['2026-09-07']
    [主] p_193ff13c0c17 归属日=2026-09-07 created=2026-09-06T19:59:00.556664 dir=neutral

600015.SH: open=5 主=4 duplicate=1
    归属日分布: ['2026-09-29', '2026-09-30', '2026-10-02', '2026-10-06']
    [主] p_b2c131c670ae 归属日=2026-09-29 created=2026-09-28T18:12:07.088497 dir=neutral
    [duplicate→将关闭] p_c8082e794631 归属日=2026-09-30 created=2026-09-29T18:08:34.960822 dir=neutral
    [主] p_d7a4bf5f0d67 归属日=2026-09-30 created=2026-09-30T23:48:17.877823 dir=neutral
    [主] p_bd1f048b1c14 归属日=2026-10-02 created=2026-10-02T18:08:10.051195 dir=short
    [主] p_e975559f34bc 归属日=2026-10-06 created=2026-10-06T18:07:43.241734 dir=long

600026.SH: open=6 主=5 duplicate=1
    归属日分布: ['2026-09-28', '2026-09-29', '2026-09-30', '2026-10-04', '2026-10-06']
    [主] p_5eb9b61dd8b9 归属日=2026-09-28 created=2026-09-25T18:10:25.305475 dir=neutral
    [主] p_19164c8c9df2 归属日=2026-09-29 created=2026-09-28T18:15:10.037642 dir=neutral
    [主] p_95bf51fa1d2a 归属日=2026-09-30 created=2026-09-30T23:50:54.983608 dir=neutral
    [duplicate→将关闭] p_3c56d32d41c2 归属日=2026-10-04 created=2026-10-04T14:49:14.883021 dir=neutral
    [主] p_0a05d6d62b52 归属日=2026-10-04 created=2026-10-04T19:33:40.698178 dir=neutral
    [主] p_27532a65e93c 归属日=2026-10-06 created=2026-10-06T18:10:15.803733 dir=long

600029.SH: open=6 主=5 duplicate=1
    归属日分布: ['2026-09-28', '2026-09-29', '2026-09-30', '2026-10-02', '2026-10-05']
    [主] p_403a27107cf9 归属日=2026-09-28 created=2026-09-25T18:12:58.473864 dir=neutral
    [主] p_4736678f99bb 归属日=2026-09-29 created=2026-09-28T18:18:13.001963 dir=neutral
    [duplicate→将关闭] p_0566685ffbf9 归属日=2026-09-30 created=2026-09-29T18:14:35.194451 dir=neutral
    [主] p_2bf012cf07bb 归属日=2026-09-30 created=2026-09-30T23:53:51.070073 dir=short
    [主] p_78a6b6607590 归属日=2026-10-02 created=2026-10-02T18:20:34.158713 dir=neutral
    [主] p_e5fa9597a4d1 归属日=2026-10-05 created=2026-10-05T18:12:37.879907 dir=neutral

600515.SH: open=4 主=4 duplicate=0
    归属日分布: ['2026-09-29', '2026-09-30', '2026-10-02', '2026-10-05']
    [主] p_b29e2af68229 归属日=2026-09-29 created=2026-09-28T18:21:15.369350 dir=neutral
    [主] p_e989355e3fa3 归属日=2026-09-30 created=2026-09-30T23:56:37.277534 dir=neutral
    [主] p_e82b398f1e95 归属日=2026-10-02 created=2026-10-02T18:22:59.899723 dir=neutral
    [主] p_bde18993d75a 归属日=2026-10-05 created=2026-10-05T18:15:12.354549 dir=neutral

600519.SH: open=7 主=4 duplicate=3
    归属日分布: ['2026-09-07', '2026-09-14', '2026-09-15', '2026-10-05']
    [duplicate→将关闭] p_f8be3fdc99d9 归属日=2026-09-07 created=2026-09-05T20:13:56.064183 dir=neutral
    [duplicate→将关闭] p_09355bc8e0b3 归属日=2026-09-07 created=2026-09-06T16:47:19.185773 dir=neutral
    [duplicate→将关闭] p_03befbb21c3a 归属日=2026-09-07 created=2026-09-06T16:53:33.299948 dir=neutral
    [主] p_aae99f7b6afc 归属日=2026-09-07 created=2026-09-06T16:53:42.964286 dir=neutral
    [主] p_bdbdc3bb0093 归属日=2026-09-14 created=2026-09-12T11:04:13.156705 dir=neutral
    [主] p_25b9a2fdaf5e 归属日=2026-09-15 created=2026-09-14T15:32:45.317296 dir=neutral
    [主] p_ff224c4aead6 归属日=2026-10-05 created=2026-10-05T10:57:30.375506 dir=neutral

600845.SH: open=3 主=2 duplicate=1
    归属日分布: ['2026-09-29', '2026-09-30']
    [主] p_81dc46e9f217 归属日=2026-09-29 created=2026-09-28T18:24:18.130712 dir=neutral
    [duplicate→将关闭] p_92ba009c8030 归属日=2026-09-30 created=2026-09-29T18:20:35.190766 dir=neutral
    [主] p_8819841a44ff 归属日=2026-09-30 created=2026-09-30T23:59:11.479954 dir=long

601058.SH: open=7 主=7 duplicate=0
    归属日分布: ['2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06']
    [主] p_95ccef329beb 归属日=2026-09-28 created=2026-09-25T18:20:23.026789 dir=neutral
    [主] p_9f282288ffb3 归属日=2026-09-29 created=2026-09-28T18:27:04.786396 dir=neutral
    [主] p_e0bc90de0848 归属日=2026-09-30 created=2026-09-29T18:23:29.369549 dir=neutral
    [主] p_dc0eeb83094f 归属日=2026-10-01 created=2026-10-01T00:02:04.792064 dir=short
    [主] p_a6d082e8b527 归属日=2026-10-02 created=2026-10-02T18:28:36.398606 dir=neutral
    [主] p_ae91e059ba74 归属日=2026-10-05 created=2026-10-05T18:20:17.307812 dir=neutral
    [主] p_17ec78dfa357 归属日=2026-10-06 created=2026-10-06T18:21:04.436680 dir=neutral

601066.SH: open=5 主=5 duplicate=0
    归属日分布: ['2026-09-29', '2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06']
    [主] p_72c87181eecd 归属日=2026-09-29 created=2026-09-28T18:29:55.792969 dir=neutral
    [主] p_2e3fffce4441 归属日=2026-10-01 created=2026-10-01T00:04:31.414601 dir=neutral
    [主] p_f28d0a4df19e 归属日=2026-10-02 created=2026-10-02T18:31:00.953721 dir=neutral
    [主] p_5f7e30f33826 归属日=2026-10-05 created=2026-10-05T18:23:19.025098 dir=neutral
    [主] p_25dd3171cfd0 归属日=2026-10-06 created=2026-10-06T18:23:40.768918 dir=neutral

601818.SH: open=3 主=3 duplicate=0
    归属日分布: ['2026-10-01', '2026-10-02', '2026-10-05']
    [主] p_7cb5c9c025b0 归属日=2026-10-01 created=2026-10-01T00:09:35.350360 dir=neutral
    [主] p_715978e8510f 归属日=2026-10-02 created=2026-10-02T18:33:40.685522 dir=neutral
    [主] p_24c928f13be5 归属日=2026-10-05 created=2026-10-05T18:25:55.536941 dir=neutral

688072.SH: open=18 主=7 duplicate=11
    归属日分布: ['2026-09-07', '2026-09-08', '2026-09-09', '2026-09-29', '2026-10-02', '2026-10-04', '2026-10-05']
    [主] p_a0cfe37769ae 归属日=2026-09-07 created=2026-09-07T14:30:26.589401 dir=neutral
    [duplicate→将关闭] p_1f1048504ff6 归属日=2026-09-08 created=2026-09-07T15:53:58.973195 dir=neutral
    [主] p_86688b4aab85 归属日=2026-09-08 created=2026-09-07T22:28:14.897591 dir=neutral
    [duplicate→将关闭] p_25177fa33db8 归属日=2026-09-09 created=2026-09-08T17:32:17.020459 dir=neutral
    [主] p_d1dc97e5bf63 归属日=2026-09-09 created=2026-09-08T19:32:05.213585 dir=neutral
    [主] p_4c3fa7d32d87 归属日=2026-09-29 created=2026-09-29T13:49:42.237034 dir=neutral
    [duplicate→将关闭] p_a6fc06ac8669 归属日=2026-10-02 created=2026-10-02T10:52:13.999418 dir=short
    [duplicate→将关闭] p_639d7b813cd6 归属日=2026-10-02 created=2026-10-02T18:01:23.830166 dir=neutral
    [duplicate→将关闭] p_e939a6099d1b 归属日=2026-10-02 created=2026-10-02T18:01:36.594214 dir=neutral
    [duplicate→将关闭] p_2d78c9a9d160 归属日=2026-10-02 created=2026-10-02T18:51:02.579841 dir=neutral
    [duplicate→将关闭] p_e9c31392d4b1 归属日=2026-10-02 created=2026-10-02T22:08:14.309172 dir=neutral
    [duplicate→将关闭] p_d2aef2ac6ba9 归属日=2026-10-02 created=2026-10-02T22:10:59.785176 dir=neutral
    [duplicate→将关闭] p_38653e6fec8a 归属日=2026-10-02 created=2026-10-02T22:14:14.838228 dir=short
    [主] p_075efe7b6770 归属日=2026-10-02 created=2026-10-02T22:26:23.345231 dir=neutral
    [duplicate→将关闭] p_eab98f67b846 归属日=2026-10-04 created=2026-10-04T11:49:56.741366 dir=neutral
    [主] p_a19c6c431553 归属日=2026-10-04 created=2026-10-04T20:02:33.025295 dir=neutral
    [duplicate→将关闭] p_86503f50eed3 归属日=2026-10-05 created=2026-10-05T01:53:22.604920 dir=neutral
    [主] p_a3fcd4fc7492 归属日=2026-10-05 created=2026-10-05T06:46:17.500965 dir=neutral

== A·今日日历窗口（截至 2026-09-30）: open=76 主=57 将关闭 duplicate=19 ==

──── 情景：B·日历补次一交易日 2026-10-08（上限参考） ────

002916.SZ: open=5 主=3 duplicate=2（差异行：09-30T23:42 与 10-02T18:02 两条转 duplicate，主 = 10-05T18:02）
300033.SZ: open=6 主=3 duplicate=3（09-30T23:45、10-02、10-05 三条转 duplicate；09-29T18:05 由 dup 转为 09-30 组主）
300750.SZ: open=1 主=1 duplicate=0（无差异）
600015.SH: open=5 主=3 duplicate=2（09-30T23:48、10-02 两条转 duplicate；09-29T18:08 转 09-30 组主）
600026.SH: open=6 主=3 duplicate=3（09-30T23:50、10-04 ×2 转 duplicate）
600029.SH: open=6 主=4 duplicate=2（09-30T23:53、10-02 转 duplicate；09-29T18:14 转 09-30 组主）
600515.SH: open=4 主=2 duplicate=2（09-30T23:56、10-02 转 duplicate）
600519.SH: open=7 主=4 duplicate=3（10-05T10:57 主保持，仅归属日 10-05 → 10-08，无计数变化）
600845.SH: open=3 主=3 duplicate=0（原 09-30 组拆分：09-29T18:20 升为主、09-30T23:59 归 10-08 组主，duplicate 1 → 0）
601058.SH: open=7 主=4 duplicate=3（10-01/10-02/10-05 三条转 duplicate，主 = 10-06T18:21）
601066.SH: open=5 主=2 duplicate=3（10-01/10-02/10-05 三条转 duplicate，主 = 10-06T18:23）
601818.SH: open=3 主=1 duplicate=2（10-01/10-02 转 duplicate，主 = 10-05T18:25）
688072.SH: open=18 主=5 duplicate=13（10-02 组 8 条 + 10-04 组 2 条 + 10-05 组 2 条全部并入 10-08 组：12 条转 duplicate，主 = 10-05T06:46）

== B·日历补次一交易日 2026-10-08（上限参考）: open=76 主=38 将关闭 duplicate=38 ==

两情景差异：duplicate 19 → 38（差 19 条为降级窗口产出）
（dry-run 未改动任何数据；正式关闭由日批第二阶段执行 duplicate_of_day）
```

（B 情景为脚本对日历补「次一交易日」的重判定，逐行完整输出见脚本复跑；此处 A 情景逐行全录，B 情景逐 symbol 摘要 + 差异行说明。B 的分组结果与「次一交易日取 10-07 还是 10-08」无关——全部降级窗口行收敛到同一恢复交易日分组。）

### 2.4 逐 symbol 人工核对结论

1. **总量勾稽**：76 open = 57 主 + 19 duplicate；13 个 symbol 的 open 数逐项相加 = 76 ✓；主/dup 相加 = 57/19 ✓。
2. **688072.SH（重点复核，简报指定）**：18 条 open 跨 **7 个归属日**（09-07 / 09-08 / 09-09 / 09-29 / 10-02 / 10-04 / 10-05），**逐日各 1 主**（7 主）+ 11 duplicate。逐组 created_at 时间线核对：
   - 09-07 组：仅 1 条（09-07T14:30 收盘前 → 归属当日 09-07）✓
   - 09-08 组：09-07T15:53（收盘后 → 次日 09-08）与 09-07T22:28 同组，主 = 22:28（组内最晚）✓
   - 09-09 组：09-08T17:32 与 09-08T19:32 同组，主 = 19:32 ✓
   - 10-02 组 8 条（10:52 → 22:26:23），主 = 22:26:23（组内最晚）✓，其余 7 条含 2 条 short 全部 duplicate ✓
   - 10-04 组：11:49 < 20:02，主 = 20:02 ✓；10-05 组：01:53 < 06:46，主 = 06:46 ✓
3. **周末/节假日归属**：600519.SH 09-05（周六）T20:13、09-06（周日）T16:47、T16:53:33、T16:53:42 四条 → 全部归属 09-07（周一），主 = 组内最晚 16:53:42 ✓；09-12（周六）T11:04 → 09-14（周一）✓；09-14T15:32（收盘后）→ 09-15 ✓。收盘切分（CLOSE_TIME_CUTOFF=15:00）与「收盘后产出归属次一交易日」边界全部正确。
4. **收盘后批次归属次日**：各 symbol ~18:0x 产出均归属次一交易日（如 002916.SZ 09-25T18:02 → 09-28）✓；09-30 23:42-23:59 深夜批 7 条在 A 情景下落入自然日 09-30（降级窗口，见 §2.2），B 情景归恢复交易日 ✓。
5. **duplicate 与方向无关**：duplicate 行含 neutral/short/long（日主判定按 §1.9-v2 不筛方向；只有 superseded 阶段跳过 neutral）——与 `job.py` 实现一致，非缺陷 ✓。
6. **与简报预期的差异说明**：tasks.md 写「688072 预期 1 主 + N duplicate」；简报已自我修正为「按归属日分组后可能 >1——18 条跨多归属日，逐日各 1 主」。实际 = **7 主（7 个归属日各 1）+ 11 duplicate**，duplicate 与 created_at 时间线完全一致，符合 §1.9-v2 口径的预期形态。核对**通过**。
7. **不迁移数据**：dry-run 未写库（md5 前后一致），关闭动作留待正式日批执行 ✓。

### 2.5 overview 数字对照（duplicate 关闭前后）

当前生产库池构成（关闭前，只读查询）：

| status | 条数 |
|---|---|
| open | 76（long 4 / neutral 67 / short 5） |
| unresolvable | 39 |
| resolved_neutral | 12 |
| **合计** | **127**（13 个 open symbol，created 2026-08-04 .. 2026-10-06） |

日批首跑关闭 19 条 duplicate 后：open **57** + duplicate_of_day **19**，total 仍 127。

**样本量分母影响分析**：

- **已结算分母（settled = win/loss 类终态）**：关闭前后均为 0——19 条 duplicate 在关闭前是 open，本就不进任何已结算分母；关闭后计入**观点总数**、不进**已结算分母**（该口径由 E2E `track-record-prediction-duplicates.spec.ts` 实机断言：settled=win+loss 不含 duplicate）。
- **净值组合构成（盯市分母）**：Task 4 已切日主视图——duplicate 行不进组合；superseded 行的 marks 仍进 NAV 聚合（回归钉住 398f0d4a）。
- **样本积累横幅「已判定 N 条」**：不因 duplicate 关闭变化（当前 0）。
- **可观察变化**：观点日志「当前持有」tab 行数 76 → 57；「已判定」tab 出现 19 条「同日重复」徽标行（无结算读数）。
- **IC/ICIR 显著性读数**： settled=0 → 样本不足红线生效，不产出读数（§1.9-v2 / settlement-significance-stats spec 的「样本不足不产出」门禁），duplicate 关闭不改变该状态。

---

## 3. E2E 三套件

### 3.1 执行环境、异常与偏差（如实记录）

本次验证在本 worktree 首次以完整流程跑 E2E 门禁，暴露并修复了 **两个环境缺陷**（均非本变更代码问题）：

1. **父检出 `.env` 泄漏（已修复，影响 eval-ops 用例）**：worktree 原无自己的 `.env`，`api.py` 启动时 `load_dotenv()` 向上查找到**主检出**的 `.env`（其中 2026-10-04 起存在 `COHORT_ENABLED=1`）→ 后端启动即把 `cohort_enabled=1` 引导进共享测试库的 `ops_config` 表 → `eval-ops-console` 的「cohort 默认未开启」断言必红（API 级直接复现：`GET /api/v1/ops/cohort` 返回 `enabled:true` 且 `ops_config` 出现 `cohort_enabled=1`）。**修复**：worktree 本地放置 `.env` 副本并注释该行（`.env` 在 .gitignore 第 162 行，不入库）。修复后 eval-ops 5 用例在串行与全量并行下均绿。
2. **默认并行度下的流式用例连锁失败（未修代码，按串行门禁执行）**：`fullyParallel` 默认 8 workers（16 核机）对该套件**共享的单进程后端 + 单 SQLite 测试库**过订阅。定位链：失败 trace 中 `POST /api/agui/quick -> -1`（响应在途被中止、无首字节）；后端日志可见 eval-ops `integrity_check` 手动补跑同步执行 19-22s+（含 AKShare 3 次退避重试的窗口）与流式用例在途窗口重叠——手动补跑占住共享库写窗口期间，流式用例的逐块同步落库停滞，流式响应在首字节前/中途停滞，表现为**随机流式子集失败**（agui-chat / streaming / interaction / sidebar / session-switch / concurrent-streaming，每轮失败集合不同：8 workers 16 failed → 4 workers 8 failed → 串行 0 failed）。全部涉事用例在低并发/串行下**多次全绿**，且与本变更 diff 无交集（本分支未触碰 agui/流式/聊天路径）。**处置**：官方门禁按 `--workers=1` 串行执行（35 用例全跑、只降并发、不跳过任何用例）；workers=1 为仓库既有先例（track-record 与 timeline 专属配置均为串行）。**遗留建议（不属本变更范围，建议独立 issue）**：eval-ops 手动补跑/回测类用例与流式门禁用例需要隔离（专属测试库或专属 config），根因是共享库 + 单进程后端的写争用，非本变更引入。
3. **@live 用例按设计跳过**：`thinking-banner`（×3）/`search-banner`（×3）/`deep-thinking-toolcall`（×1）的 @live 用例前置要求「真实 LLM 后端（不带 TESTING=1）」，其设计跳过条件即「无 API key」（stub 环境无法满足前提，spec 内注释明示）。门禁执行时显式 `env -u LLM_API_KEY -u DEEPSEEK_API_KEY` 使其按设计跳过（合计 8 skipped）；真实 LLM 行为由 **nightly @live** 防漂移覆盖，不属于 PR 门禁。
4. **其他环境状态**：Langfuse 容器未启动（localhost:3000 不可达）→ prompt 拉取自动回退本地（日志 WARN「可能版本漂移」，属设计内降级）；Docker daemon 未启动——后端全量 pytest 实测不需要 Docker；AKShare 东财源本机连接失败（新浪回退正常）。

### 3.2 各套件结果

- **默认套件**（`npx playwright test --workers=1`，跑前删 `data/test-e2e-sessions.db*`）：**27 passed / 8 skipped / 0 failed**（4m0s，GATE_EXIT=0）。串行轮中此前所有并行失败用例全绿（agui-chat ×2、concurrent-streaming ×2、streaming ×3、interaction、sidebar、session-switch、eval-ops ×5）。
- **track-record 套件**（`npx playwright test --config playwright.track-record.config.ts`，跑前删 `data/test-e2e-track-record.db*`）：**8 passed**（26.5s，exit 0）：
  1. 跑赢指数对比：空态渲染 ✓ 2. 造数后摘要与对比条、跑赢/跑输分色 ✓ 3. 跨度偏好决定请求参数 ✓
  4. β/α：快照有值渲染两格 ✓ 5. β/α：样本不足显示 — ✓
  6. 观点日志标题与缺省 tab ✓ 7. tab 切换与空态文案 ✓
  8. **同日重复徽标：duplicate 行渲染「同日重复」徽标且无结算读数，总览不计已结算** ✓（本变更 Task 8 新增用例）
- **playwright-report 路径**：`tests/e2e/playwright/playwright-report/index.html`（默认套件 HTML，对应串行门禁轮）。track-record 套件为 list reporter，无 HTML 报告，结果以上列逐用例记录为准。

### 3.3 徽标实机抽查

duplicate_of_day 徽标链路由 E2E **实机覆盖**（真实浏览器渲染、`/api/test/seed` 造数通道写入独立测试库、**无业务接口 mock**——红线合规）：

- 造数：同股（600519.SH）同日（2026-10-09）两条观点——10:00 open、11:00 duplicate_of_day 终态（经 `update_prediction_status` 同一状态变更路径置终态）；
- 断言：徽标文案「同日重复」（真源 `frontend/src/pages/trackRecord/predictionStatus.ts`）、duplicate 行**无**结算读数（不含 命中/未中/未结算 字样）、总览不计已结算（样本积累横幅「已判定 0 条」，若 duplicate 被误计入会变 1）、「当前持有」tab 只含 open 行、「已判定」tab 收录 duplicate、「全部」tab 两行并存；
- 截图/trace：套件通过（`screenshot: only-on-failure`、`trace: retain-on-failure`）→ 无失败截图产生；通过记录见 playwright-report。实机抽查**通过**。

---

## 4. 验证结果（delta Scenario 抽查核对）

| Scenario（delta spec） | 自动化覆盖 | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 同日重跑仅日主观点判定（track-record） | 单测（judgment/job 回归 532 内）+ dry-run 情景 A | 同 (symbol, 归属日) 仅 created_at 最晚者为主 | 688072.SH 等逐组核对相符 | ✅ |
| 同日观点变更链保留读数（track-record） | 单测（superseded 先行回归） | superseded 行 marks 仍进 NAV 聚合 | 398f0d4a 钉住回归绿 | ✅ |
| 重复行不计入分母（track-record） | E2E duplicates 用例 | duplicate 计观点总数、不进 settled | E2E 断言「已判定 0 条」相符 | ✅ |
| 同日重复不进组合（track-record-metrics） | 单测（NAV 分母回归） | 盯市组合构成消费日主视图 | 532 内组合分母用例绿 | ✅ |
| 收盘后产出归属次日（track-record） | 单测 + dry-run 人工核对 | 18:0x 产出 → 次一交易日 | 逐 symbol 核对相符（§2.4-4） | ✅ |
| 净值计算 / 首盯市日 / 日历覆盖空仓期 / 基准缺失降级（track-record-metrics） | 单测 | 各按口径 | 532 内回归绿 | ✅ |
| 月度 IC / 期数不足不展示 ICIR / 单期样本不足剔除 / 敞口对齐 / 结论必附分位 / 样本不足不产出（settlement-significance-stats） | 单测（significance 纯函数） | 各按 §1.9-v2 | 532 内回归绿；settled=0 下端点不产出读数 | ✅ |
| 预登记先于首批读数 / 口径变更不追改历史 | 文档核对 | metrics.md §1.9-v2 已登记（2026-10-06） | docs/evals/metrics.md §1.9-v2 存在且先于实现 | ✅ |
| E2E 覆盖不到的主观项（LLM 报告内容质量等） | 不适用 | — | 本变更未触及报告生成内容，无新增主观项 | ✅（不适用） |

---

## 5. 异常记录（汇总）

| # | 异常 | 定性 | 处置 |
|---|---|---|---|
| 1 | 东财 `index_zh_a_hist` 三次 ConnectionError | 环境网络（本机东财源不可达） | `fetch_index_kline` 内部新浪回退成功，日历完整；已记录 |
| 2 | 父检出 `.env` 泄漏 → cohort 被自动开启 → eval-ops 断言红 | **worktree 环境缺陷**（.env 查找路径向上穿越） | worktree 本地 `.env` 副本注释该行；API 级复现 + 修复复验通过；已记入 §3.1 |
| 3 | 默认并行（8/4 workers）下流式用例随机子集失败 | **预存测试隔离缺陷**：eval-ops 手动补跑（20-60s 同步 + AKShare 网络重试）与流式用例争用单进程后端 + 共享 SQLite 写窗口 | 官方门禁串行（workers=1，仓库既有先例）全绿；与本变更 diff 无交集；建议独立 issue 隔离两类用例 |
| 4 | Langfuse 不可达（WinError 10061） | 环境（容器未启动） | prompt 回退本地（设计内降级），门禁不受影响 |
| 5 | Docker daemon 未启动 | 环境 | 后端全量 pytest 实测不需要 Docker（全 stub），4152 全绿 |
| 6 | 简报脚本样例 `list_predictions` 未显式传 limit | 简报样例缺陷 | 脚本按 `limit=100_000` 修正（否则 76 条 open 被截断为 50）；已在脚本注释与 §2.1 说明 |
| 7 | mypy 83 errors / 21 files | 预存基线 | 与基线一致，无新增，按约定视为通过 |

---

## 6. 结论

- [x] 全部门禁绿：ruff ✅ / mypy 基线持平 ✅ / pytest 定向 532 ✅ / pytest 全量 4152 ✅ / vitest 645 ✅ / E2E 默认套件 27 passed 0 failed ✅ / E2E track-record 8 passed ✅
- [x] 存量生产库 dry-run 核对通过：76 open = 57 主 + 19 duplicate（今日日历窗口口径），688072.SH 7 主/11 duplicate 与 created_at 时间线完全一致；不迁移数据，md5 前后一致证明只读
- [x] 降级窗口（日历截至 09-30）已量化（情景 B：上限 38 duplicate）且为瞬态——日批每批重读 open 池按当日日历重算，恢复交易日后自动补齐关闭
- [x] 人工验证报告落 `tests/validation/`（本文件）
- [ ] **待办（owner 操作，非本任务）**：10-08 净值重启窗口前完成部署（docker compose 重建，重建前查 `GET /api/sessions` 无 running 会话——红线）；部署后正式库日批复核 dry-run 结论；随后 archive（sync + 归档）

tasks.md 对应项勾选状态：除最后一项「10-08 前部署」为 owner 待办保持未勾外，其余实施与验证项均已真实完成并勾选。

---

## 7. 部署窗口提醒（Step 6，不自动执行）

- 部署动作：`docker compose up -d --build`（**重建前必查** `GET /api/sessions` 无 `status=running` 会话——宿主机改码不触发容器内 reload，重建撞上运行中分析会把它杀成 interrupted，见红线/一日三例教训）。
- 目标窗口：**2026-10-08 净值重启前**。部署后首个日批注意 §2.2：若运行时点次一交易日 K 线尚未落地，假期窗口 duplicate 按自然日口径先关一批，恢复交易日后首批自动补齐（设计内自愈，无需人工干预）。
- archive（sync + 归档）在本报告完成且正式库 dry-run 复核后进行。
