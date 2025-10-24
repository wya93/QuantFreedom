# QuantFreedom Backtesting Framework

QuantFreedom 是一个可扩展的加密货币量化交易与回测系统，支持现货与合约市场模拟。框架提供数据加载、交易撮合、策略开发、组合管理、绩效评估等完整功能，帮助量化研究者快速验证交易想法。

## 功能特性
- 📈 支持 CSV 格式 OHLCV 数据加载
- ⚙️ 灵活的交易撮合引擎：手续费、滑点、委托延迟
- 🧠 策略接口：`on_bar`、`on_order`、`on_fill`
- 💼 仓位与资金管理，支持单边/双边、杠杆上限及可扩展永续合约，策略可开多做空
- 📊 丰富绩效指标与图表输出
- 🧾 内置交易日志：终端实时打印每笔买入卖出明细与汇总统计
- ✅ 单元测试覆盖核心撮合与资金路径

## 安装
```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\\Scripts\\activate
pip install -r requirements.txt
```

> ℹ️ 框架核心仅依赖标准库，`requirements.txt` 中的 matplotlib 仅用于生成示例图表，可按需安装。

## 示例数据格式
示例数据位于 `examples/data/BTC_USD_1h.csv`，包含以下列：

```text
timestamp,open,high,low,close,volume
2021-01-01T00:00:00Z,29300,29500,29200,29450,120.5
...
```

- `timestamp`: ISO8601 字符串，UTC 时间
- `open/high/low/close`: K 线价格
- `volume`: 成交量

## 运行示例
执行示例策略（双均线交叉，可配置做空开关）：

```bash
python examples/run_example.py \
  --data examples/data/BTC_USD_1h.csv \
  --strategy src/strategies/sma_cross.py \
  --max_leverage 3 \
  --params '{"allow_short": true}'
```

常用运行参数：

- `--initial_capital`：初始资金，默认 `100000`。
- `--max_leverage`：账户最大杠杆倍数，默认 `1.0`（无杠杆）。下单时若仓位名义价值超出 `equity * max_leverage` 将抛出错误，避免策略超量使用资金。SMA 示例策略会按照 `capital_fraction * max_leverage` 的目标名义敞口下单，因此在 `--max_leverage 10` 时默认设置下的仓位规模会明显大于 `--max_leverage 2`，可直观体现杠杆影响。
- `--fee` / `--slippage`：手续费与滑点设定。
- `--params`：JSON 字符串形式的策略自定义参数。

运行后将生成：
- `outputs/equity_curve.csv`：净值曲线
- `outputs/trades.csv`：交易明细
- `outputs/report.json`：回测指标
- `outputs/equity_plot.png`：净值与买卖点图

> 终端日志会实时输出每笔成交的价格、数量、手续费、持仓/现金变化，以及最终的买卖次数、成交量、净收益等统计，便于快速审计策略表现。

### 指标预热与均线稳定性

很多交易 APP 会在图表上展示长时间累计的均线指标，如果仅从某个时间点开始下载数据，本地重新计算的 SMA 在最开始的几根 K 线会因为缺少更早的历史数据而与 APP 的数值存在差异。推荐的做法：

1. **多下载一段“预热”历史**：例如策略用到 `long_window=200` 的均线，可在真正的回测起点之前再额外抓取 200～400 根 K 线作为指标预热区间。这样即使正式统计从较晚的时间开始，均线已经在本地用足够的历史数据进行平滑。
2. **利用 `warmup_bars` 延迟开仓**：`SMACrossStrategy` 提供了 `warmup_bars` 参数，会在累积 `long_window + warmup_bars` 根 K 线之后才开始下单。结合上面的“多下载一段历史”做法，可以保证策略决策时所用的均线已经充分稳定，而不会因为 CSV 起点不同而产生随机波动。
3. **对照抽样验证**：在表格软件或 Notebook 中用相同的公式对某一段收盘价求均线，与 APP 或交易所导出的指标对比，确认差异仅存在于预热阶段且在若干根 K 线后趋于一致。

如需在命令行直接设置，可通过：

```bash
python examples/run_example.py \
  --data your_dataset.csv \
  --strategy src/strategies/sma_cross.py \
  --params '{"short_window": 50, "long_window": 200, "warmup_bars": 200}'
```

确保 CSV 覆盖 `long_window + warmup_bars` 根以上的数据后，就能得到与 APP 指标一致、可复现的回测结果。

## 下载真实行情数据

仓库提供 `tools/download_binance_ohlcv.py`，用于按需从 Binance 公共 API 拉取 K 线。示例命令：

```bash
python tools/download_binance_ohlcv.py \
  --symbol BTCUSDT \
  --interval 1h \
  --start 2023-01-01T00:00:00Z \
  --end 2023-02-01T00:00:00Z \
  --output examples/data/BTC_USDT_1h_real.csv
```

常用参数：

- `--symbol`：交易对（如 `BTCUSDT`、`ETHUSDT`）。
- `--interval`：K 线周期，支持 Binance 的全部周期（`1m`、`5m`、`1h`、`4h`、`1d` 等）。
- `--start`/`--end`：起止时间，ISO8601 字符串或毫秒时间戳，可选。
- `--limit`：仅指定下载的最大条数时可使用，省略起止时间。
- `--pause`：分页请求之间的休眠秒数，默认 `0.2` 秒以避免触发限频。
- `--output`：输出 CSV 路径，列顺序与框架要求一致。

下载完成后，可直接将生成的 CSV 作为 `--data` 参数传入回测脚本。

## 实盘交易（Binance USDT 永续合约）

项目内置 `examples/run_live_binance.py`，可在 Binance USDT 本位永续合约上实时执行策略。推荐先在 **Testnet** 环境完成联调，再切换至正式站。

### 环境准备

1. 在 Binance 生成 API Key（期货交易权限，若使用正式站请妥善保管）。
2. 将密钥写入环境变量：

   ```bash
   export BINANCE_API_KEY="你的APIKey"
   export BINANCE_API_SECRET="你的Secret"
   ```

3. 准备至少 20 USDT 的期货可用余额。脚本会默认以 20 USDT 本金、10x 杠杆估算下单数量，可通过参数调整。

### 单次执行

```bash
python examples/run_live_binance.py \
  --symbol BTCUSDT \
  --interval 1h \
  --strategy src/strategies/sma_cross.py \
  --params '{"capital_fraction": 0.5, "allow_short": true}' \
  --capital 20 \
  --leverage 10 \
  --testnet
```

- `--capital`：用于估算下单名义价值的本金，默认 20 USDT。
- `--leverage`：请求的最大杠杆倍数，默认 10x，脚本会在开仓前向 Binance 设置该杠杆。
- `--testnet`：连接到 Binance Futures Testnet（`https://testnet.binancefuture.com`）。若要在正式站交易，去掉该参数并确保账户及风控配置正确。
- `--poll`：若指定（单位：秒），脚本会保持常驻，每隔指定秒数重新拉取最新 1h K 线并执行策略。
- `--lookback`：可手动覆盖历史回溯长度；默认根据策略的 `long_window` + `warmup_bars` 自动回溯足够多的 K 线，确保 200 均线等指标在实盘启动时已经有稳定的历史数据。

运行期间日志会输出：

- 最近一次完成的 1h K 线价格；
- 实时仓位、现金、权益；
- 每次下单的成交均价、数量、手续费、单笔盈亏；
- Binance 返回的订单状态（默认使用市价单）。

> ⚠️ 实盘模式仅支持策略发起的市价单，并会在最新闭合的 K 线上执行信号。请务必在 Testnet 验证好策略行为、最小下单量以及风险控制再部署到正式环境。

## 添加新策略
1. 在 `src/strategies/` 下创建新文件，继承 `StrategyBase`。
2. 实现 `on_bar`、`on_order`、`on_fill` 方法，并在构造时传入参数。
3. 在 `examples/run_example.py` 中通过 `--strategy` 指定策略路径，或直接在脚本中实例化自定义策略。

示例：

```python
from src.strategy_base import StrategyBase

class MyStrategy(StrategyBase):
    def __init__(self, params):
        super().__init__(params)

    def on_bar(self, bar):
        # 根据 bar 数据发出下单
        pass

    def on_fill(self, fill):
        # 处理成交回报
        pass
```

## 项目结构
```
QuantFreedom/
├─ README.md
├─ requirements.txt
├─ src/
│   ├─ data_loader.py
│   ├─ exchange_sim.py
│   ├─ backtester.py
│   ├─ strategy_base.py
│   ├─ strategies/
│   │   └─ sma_cross.py
│   ├─ portfolio.py
│   ├─ metrics.py
│   ├─ utils.py
│   └─ live/
│       ├─ __init__.py
│       ├─ binance_client.py
│       └─ session.py
├─ examples/
│   ├─ run_example.py
│   └─ run_live_binance.py
├─ tests/
│   └─ test_backtester.py
└─ notebooks/
    └─ analyze_results.ipynb
```

欢迎根据需要扩展实盘接口、更多策略以及可视化工具。
