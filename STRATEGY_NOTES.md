# ICT Silver Bullet Strategy Notes

## Purpose

This document defines how the bot should interpret the ICT Silver Bullet model.

The goal is not to create a vague discretionary trading bot. The goal is to convert the strategy into clear, testable, rule-based logic.

## Core Idea

The ICT Silver Bullet model focuses on specific time windows where price may seek liquidity and then reverse or continue through an imbalance.

The bot should look for:

1. A valid trading session window
2. A liquidity sweep
3. Displacement
4. Market structure shift
5. Fair Value Gap
6. Retracement into the FVG
7. Entry with defined stop loss and liquidity-based target

## Configurable Session Windows

Default Silver Bullet windows should be configurable.

Suggested default timezone:

```text
America/New_York
```

Suggested default sessions:

```text
London Silver Bullet: 03:00-04:00 New York time
New York AM Silver Bullet: 10:00-11:00 New York time
New York PM Silver Bullet: 14:00-15:00 New York time
```

These must be stored in config and should not be hardcoded permanently.

Example config:

```yaml
silver_bullet_sessions:
  timezone: "America/New_York"
  sessions:
    - name: "london"
      start: "03:00"
      end: "04:00"
      enabled: true
    - name: "new_york_am"
      start: "10:00"
      end: "11:00"
      enabled: true
    - name: "new_york_pm"
      start: "14:00"
      end: "15:00"
      enabled: false
```

## Timeframes

Recommended initial setup:

```text
Execution timeframe: 1m or 5m
Structure timeframe: 5m or 15m
Higher timeframe bias: 1h, 4h, 1d
```

Start simple:

```text
Backtest on 5m first.
Then test 1m later.
```

## Long Setup Rules

A long setup is valid when all required conditions are met.

### Required Conditions

1. Current time is inside an enabled Silver Bullet session.
2. Price sweeps sell-side liquidity.
3. A bullish displacement candle appears.
4. Bullish market structure shift is confirmed.
5. A bullish Fair Value Gap forms.
6. Price retraces into the bullish FVG.
7. Reward-to-risk is acceptable.
8. Risk engine approves the trade.
9. Optional ML filter approves the trade if enabled.

### Long Entry

Entry options:

```text
Option A: 50% of bullish FVG
Option B: FVG open boundary
Option C: Limit order inside FVG
Option D: Market entry after FVG tap confirmation
```

Default:

```text
Use limit order at 50% of FVG.
```

### Long Stop Loss

Stop-loss options:

```text
Option A: Below swept low
Option B: Below FVG low
Option C: Below displacement candle low
```

Default:

```text
Use below swept low with configurable buffer.
```

### Long Take Profit

Target options:

```text
Option A: Nearest buy-side liquidity
Option B: Previous session high
Option C: Previous day high
Option D: Fixed R multiple
```

Default:

```text
Primary target: nearest buy-side liquidity.
Fallback target: minimum 2R.
```

## Short Setup Rules

A short setup is valid when all required conditions are met.

### Required Conditions

1. Current time is inside an enabled Silver Bullet session.
2. Price sweeps buy-side liquidity.
3. A bearish displacement candle appears.
4. Bearish market structure shift is confirmed.
5. A bearish Fair Value Gap forms.
6. Price retraces into the bearish FVG.
7. Reward-to-risk is acceptable.
8. Risk engine approves the trade.
9. Optional ML filter approves the trade if enabled.

### Short Entry

Entry options:

```text
Option A: 50% of bearish FVG
Option B: FVG open boundary
Option C: Limit order inside FVG
Option D: Market entry after FVG tap confirmation
```

Default:

```text
Use limit order at 50% of FVG.
```

### Short Stop Loss

Stop-loss options:

```text
Option A: Above swept high
Option B: Above FVG high
Option C: Above displacement candle high
```

Default:

```text
Use above swept high with configurable buffer.
```

### Short Take Profit

Target options:

```text
Option A: Nearest sell-side liquidity
Option B: Previous session low
Option C: Previous day low
Option D: Fixed R multiple
```

Default:

```text
Primary target: nearest sell-side liquidity.
Fallback target: minimum 2R.
```

## Liquidity Definitions

### Buy-Side Liquidity

Buy-side liquidity may exist above:

```text
Previous swing highs
Equal highs
Previous day high
Previous session high
Range high
Recent consolidation high
```

### Sell-Side Liquidity

Sell-side liquidity may exist below:

```text
Previous swing lows
Equal lows
Previous day low
Previous session low
Range low
Recent consolidation low
```

## Liquidity Sweep

A sweep happens when price trades beyond a known liquidity level and then closes back inside or shows rejection.

### Bullish Sweep

For a possible long:

```text
price_low < sell_side_liquidity_level
and close > sell_side_liquidity_level
```

Alternative stricter version:

```text
price_low < sell_side_liquidity_level
and candle closes bullish
and next candle confirms upward displacement
```

### Bearish Sweep

For a possible short:

```text
price_high > buy_side_liquidity_level
and close < buy_side_liquidity_level
```

Alternative stricter version:

```text
price_high > buy_side_liquidity_level
and candle closes bearish
and next candle confirms downward displacement
```

## Fair Value Gap Definition

### Bullish FVG

A bullish FVG exists when:

```text
candle_1.high < candle_3.low
```

The FVG zone is:

```text
lower_bound = candle_1.high
upper_bound = candle_3.low
```

### Bearish FVG

A bearish FVG exists when:

```text
candle_1.low > candle_3.high
```

The FVG zone is:

```text
lower_bound = candle_3.high
upper_bound = candle_1.low
```

## Displacement Definition

Displacement means strong directional movement after a sweep.

Possible filters:

```text
body_size > average_body_size * multiplier
range > ATR * multiplier
volume > average_volume * multiplier
close near candle extreme
```

Bullish displacement:

```text
large bullish candle
close near high
breaks minor structure
creates bullish FVG
```

Bearish displacement:

```text
large bearish candle
close near low
breaks minor structure
creates bearish FVG
```

## Market Structure Shift

A bullish MSS happens when price breaks a recent lower high after sweeping sell-side liquidity.

A bearish MSS happens when price breaks a recent higher low after sweeping buy-side liquidity.

The exact swing logic must be configurable.

Example:

```text
swing_lookback = 3
```

## Higher Timeframe Bias

HTF bias is used as a filter.

Possible states:

```text
bullish
bearish
neutral
```

Longs are preferred when HTF bias is bullish or neutral.

Shorts are preferred when HTF bias is bearish or neutral.

The bot may reject counter-bias trades unless reversal mode is enabled.

## Signal Quality Score

Each setup should receive a score from 0 to 100.

Suggested scoring:

```text
Session timing: 15 points
Liquidity sweep quality: 20 points
Displacement strength: 20 points
FVG quality: 15 points
HTF alignment: 15 points
Reward-to-risk: 10 points
Spread/volatility condition: 5 points
```

Minimum score:

```text
70
```

## Trade Invalidation

A setup is invalid if:

```text
Session window ends before entry
Price hits stop level before entry
FVG is fully invalidated
Opposite liquidity sweep occurs
Risk-reward becomes too low
Spread becomes too high
Daily loss limit is reached
Kill switch is active
```

## No-Trade Conditions

The bot should not trade when:

```text
Outside Silver Bullet window
No liquidity sweep
No FVG
No displacement
No MSS
Reward-to-risk below minimum
Spread too high
ATR too low
ATR too high
Already in a trade
Daily loss limit reached
Max trades per day reached
Exchange connection unstable
News filter blocks trading, if enabled
```

## Recommended Initial Defaults

```text
risk_per_trade = 0.5%
max_daily_loss = 2%
max_consecutive_losses = 3
max_trades_per_day = 3
minimum_rr = 2.0
minimum_signal_score = 70
use_ml_filter = false
use_htf_bias = true
allow_counter_bias = false
paper_trading_default = true
```

## Development Rule

The strategy must be implemented as deterministic rules first.

Only after deterministic rules are working should ML be introduced.