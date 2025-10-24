# QuantFreedom Backtesting Framework

QuantFreedom 是一个可扩展的加密货币量化交易与回测系统，支持现货与合约市场模拟。框架提供数据加载、交易撮合、策略开发、组合管理、绩效评估等完整功能，帮助量化研究者快速验证交易想法。

## 功能特性
- 📈 支持 CSV 格式 OHLCV 数据加载
- ⚙️ 灵活的交易撮合引擎：手续费、滑点、委托延迟
- 🧠 策略接口：`on_bar`、`on_order`、`on_fill`
- 💼 仓位与资金管理，支持单边和双边模式（可扩展永续合约），策略可开多做空
- 📊 丰富绩效指标与图表输出
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
python examples/run_example.py --data examples/data/BTC_USD_1h.csv --strategy src/strategies/sma_cross.py --params '{"allow_short": true}'
```

运行后将生成：
- `outputs/equity_curve.csv`：净值曲线
- `outputs/trades.csv`：交易明细
- `outputs/report.json`：回测指标
- `outputs/equity_plot.png`：净值与买卖点图

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
│   └─ utils.py
├─ examples/
│   └─ run_example.py
├─ tests/
│   └─ test_backtester.py
└─ notebooks/
    └─ analyze_results.ipynb
```

欢迎根据需要扩展实盘接口、更多策略以及可视化工具。
