# Backtesting Guide

## Purpose

This document defines how the ICT Silver Bullet trading bot should be backtested.

Backtesting is required before paper trading and live trading.

The goal is not to create a perfect-looking backtest. The goal is to test whether the strategy survives realistic conditions such as fees, slippage, spreads, losing streaks, and changing market regimes.

## Core Rule

No live trading should be allowed unless the strategy has passed:

```text
historical backtesting
out-of-sample testing
walk-forward validation
paper trading
risk engine testing
kill switch testing
```

## Backtesting Philosophy

A backtest should be realistic, conservative, and repeatable.

The bot must avoid:

```text
overfitting
lookahead bias
survivorship bias
ignoring fees
ignoring slippage
ignoring spread
optimizing on final test data
changing strategy rules after seeing results
```

A simple strategy with honest results is better than a complex strategy with fake profitability.

## Backtest Modes

The backtester should support:

```text
single-symbol backtest
multi-symbol backtest
single-session backtest
multi-session backtest
walk-forward backtest
parameter sensitivity test
Monte Carlo simulation
```

## Required Historical Data

Minimum candle fields:

```text
symbol
timeframe
open_time
close_time
open
high
low
close
volume
```

Recommended timeframes:

```text
1m
5m
15m
1h
4h
1d
```

Recommended initial backtesting pair:

```text
BTCUSDT
```

Secondary pair:

```text
ETHUSDT
```

## Recommended Starting Timeframe

Start with:

```text
Execution timeframe: 5m
Structure timeframe: 15m
Higher timeframe bias: 1h, 4h, 1d
```

After the strategy logic works, test:

```text
Execution timeframe: 1m
```

## Backtest Date Splits

Use time-based splits only.

Do not use random splits.

Example:

```text
Training / development period: oldest 60%
Validation period: next 20%
Final test period: latest 20%
```

The final test period must not be used for parameter optimization.

## Event-Driven Backtesting

The backtester should simulate candles one by one.

At each candle, the bot should:

```text
load current candle
update session state
update market structure
update liquidity levels
detect sweeps
detect displacement
detect FVGs
check for entry conditions
send signal to risk engine
simulate order execution
manage open trade
record logs
update equity
```

The strategy must not use future candles when making current decisions.

## Required Simulation Features

The backtester must simulate:

```text
fees
slippage
spread
limit order fills
missed fills
stop loss
take profit
partial take profit
breakeven movement
trailing stop, if enabled
session-end exit, if enabled
max daily loss
max consecutive losses
max trades per day
kill switch behavior
```

## Fees

Fees must be included in every trade.

Recommended default:

```text
maker_fee = 0.0002
taker_fee = 0.0005
```

These values should be configurable.

## Slippage

Slippage should be simulated conservatively.

Example:

```text
slippage_bps = 1 to 5 basis points
```

For market orders, assume worse slippage.

For limit orders, do not assume guaranteed fills.

## Spread

The backtester should include a spread estimate.

If real bid/ask data is unavailable, use a conservative spread model.

Example:

```text
spread_bps = 1 to 3 basis points
```

## Entry Simulation

Supported entry types:

```text
limit entry
market entry
confirmation entry
```

Default Silver Bullet entry:

```text
limit order at 50% of FVG
```

A limit order should only be considered filled if price trades through the entry level.

## Stop Loss Simulation

Every trade must have a stop loss.

Long stop options:

```text
below swept low
below FVG low
below displacement candle low
```

Short stop options:

```text
above swept high
above FVG high
above displacement candle high
```

Default:

```text
stop beyond swept liquidity with configurable buffer
```

## Take Profit Simulation

Target options:

```text
nearest opposing liquidity
previous session high or low
previous day high or low
fixed R multiple
```

Default:

```text
primary target = nearest opposing liquidity
fallback target = minimum 2R
```

## Partial Take Profit

The backtester should support partial TP.

Example:

```text
Take 50% at 1R
Move stop to breakeven
Take remaining 50% at final target
```

Partial TP rules must be configurable.

## Breakeven Rule

Breakeven movement should be configurable.

Example:

```text
move stop to breakeven after price reaches 1R
```

The backtest must record when stop loss is moved.

## Trade Exit Reasons

Every trade must have an exit reason.

Allowed exit reasons:

```text
stop_loss
take_profit
partial_take_profit
breakeven_stop
session_end
manual_exit
kill_switch
opposite_signal
invalidated_setup
```

## Required Backtest Outputs

The backtester must export:

```text
trades.csv
equity_curve.csv
backtest_report.json
rejected_signals.csv
daily_summary.csv
```

## Required Trade Log Fields

Each trade record should include:

```text
trade_id
symbol
session_name
direction
entry_time
exit_time
entry_price
exit_price
stop_loss
take_profit
position_size
risk_amount
realized_pnl
realized_r
fees
slippage
max_favorable_excursion
max_adverse_excursion
exit_reason
setup_quality_score
ml_probability
notes
```

## Required Metrics

The backtest report should include:

```text
total_trades
winning_trades
losing_trades
win_rate
profit_factor
expectancy
average_r
median_r
max_drawdown
max_drawdown_percent
largest_win
largest_loss
average_win
average_loss
consecutive_wins
consecutive_losses
total_fees
net_profit
return_percent
```

## Session-Specific Metrics

Because Silver Bullet is time-window based, results must be separated by session.

Track metrics for:

```text
London Silver Bullet
New York AM Silver Bullet
New York PM Silver Bullet
```

For each session, calculate:

```text
total_trades
win_rate
profit_factor
average_r
max_drawdown
net_profit
```

## Symbol-Specific Metrics

For each symbol, calculate:

```text
total_trades
win_rate
profit_factor
average_r
max_drawdown
net_profit
```

## Risk Metrics

The backtest must show:

```text
max daily loss hit count
max consecutive loss hit count
max trades per day hit count
kill switch activation count
largest intraday drawdown
worst losing streak
```

## Walk-Forward Validation

Walk-forward testing should be used before trusting any strategy parameters.

Example:

```text
Train/optimize on period 1
Test on period 2

Train/optimize on period 2
Test on period 3

Train/optimize on period 3
Test on period 4
```

The final report should show whether performance is stable across periods.

## Monte Carlo Testing

Monte Carlo testing should reshuffle trade results to estimate possible drawdown variations.

Monte Carlo report should include:

```text
expected drawdown range
worst-case drawdown estimate
probability of losing streaks
risk of ruin estimate
```

## Parameter Testing

Parameters may be tested, but not over-optimized.

Examples:

```text
minimum_signal_score
minimum_rr
fvg_minimum_size
displacement_atr_multiplier
swing_lookback
stop_buffer
ml_probability_threshold
```

Parameter testing must be done on training/validation data only.

The final test set must remain untouched until final validation.

## Pass/Fail Criteria

A backtest is not automatically good just because it is profitable.

Minimum suggested pass conditions:

```text
profit_factor >= 1.2
positive expectancy
max_drawdown acceptable for account size
enough trades for statistical relevance
performance is not from one lucky trade
performance is not isolated to one small period
strategy survives realistic fees and slippage
out-of-sample results are acceptable
```

These are minimum research thresholds, not profit guarantees.

## Red Flags

Reject or rework the strategy if:

```text
profit disappears after fees
profit disappears after slippage
only one month is profitable
one trade creates most of the profit
drawdown is too large
trade count is too small
walk-forward results collapse
Monte Carlo drawdown is unacceptable
paper trading does not match backtest behavior
```

## Backtest Before ML

The rule-based strategy must be backtested before adding ML.

ML should only be trained after the strategy can consistently produce clean historical setup labels.

## Backtest Before Paper Trading

Paper trading should only begin after:

```text
strategy engine works
risk engine works
backtester works
logs are clear
no lookahead bias is found
basic performance report is generated
```

## Backtest Before Live Trading

Live trading should only be considered after:

```text
backtest passes
out-of-sample test passes
walk-forward test is acceptable
paper trading is stable
kill switch is tested
Telegram alerts are tested
risk engine blocks unsafe trades
```

## Final Rule

A bad backtest means no live trading.

A good backtest does not guarantee profit.

The purpose of backtesting is to reject weak strategies early, not to prove guaranteed success.