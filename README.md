# QuantFreedom Backtesting Framework

QuantFreedom 是一个可扩展的加密货币量化交易与回测系统，支持现货与合约市场模拟。框架提供数据加载、交易撮合、策略开发、组合管理、绩效评估等完整功能，帮助量化研究者快速验证交易想法。

## 功能特性
- 📈 支持 CSV 格式 OHLCV 数据加载
- ⚙️ 灵活的交易撮合引擎：手续费、滑点、委托延迟
- 🧠 策略接口：`on_bar`、`on_order`、`on_fill`
- 💼 仓位与资金管理，支持单边和双边模式（可扩展永续合约）
- 📊 丰富绩效指标与图表输出
- ✅ 单元测试覆盖核心撮合与资金路径

## 安装
```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\\Scripts\\activate
pip install -r requirements.txt
```

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
执行示例策略（双均线交叉）：

```bash
python examples/run_example.py --data examples/data/BTC_USD_1h.csv --strategy src/strategies/sma_cross.py
```

运行后将生成：
- `outputs/equity_curve.csv`：净值曲线
- `outputs/trades.csv`：交易明细
- `outputs/report.json`：回测指标
- `outputs/equity_plot.png`：净值与买卖点图

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
