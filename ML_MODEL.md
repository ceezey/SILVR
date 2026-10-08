# ML Model Plan

## Purpose

The ML model is not the main trader.

The ML model is only a probability filter for rule-based ICT Silver Bullet setups.

The rule-based strategy finds potential trades. The ML model helps decide whether the setup is high enough quality to take.

## Forbidden ML Behavior

The ML model must not:

```text
generate trades independently
place orders
change stop loss without rules
increase risk above max risk
bypass risk management
bypass kill switch
optimize on final test data
```

## Allowed ML Behavior

The ML model may:

```text
approve a rule-based setup
reject a rule-based setup
reduce risk on a lower-confidence setup
label market regime
estimate probability of reaching TP before SL
```

## First ML Objective

The first ML objective should be classification:

```text
Will this rule-based setup hit take profit before stop loss?
```

Target label:

```text
1 = TP hit before SL
0 = SL hit before TP
```

Alternative labels for later:

```text
realized R multiple
maximum favorable excursion
maximum adverse excursion
time to target
setup quality class
```

## Dataset Unit

Each row should represent one detected setup.

One row is not one candle.

One row is one potential Silver Bullet setup.

## Input Data

Data sources:

```text
OHLCV candles
session labels
liquidity sweep events
FVG events
market structure events
displacement events
HTF bias
backtest outcomes
trade logs
```

## Suggested Features

### Session Features

```text
session_name
minutes_from_session_open
minutes_until_session_close
day_of_week
hour_new_york
```

### Liquidity Features

```text
swept_liquidity_type
distance_to_swept_level
sweep_depth_atr
sweep_rejection_strength
equal_high_or_low_present
nearest_opposing_liquidity_distance
```

### FVG Features

```text
fvg_direction
fvg_size
fvg_size_atr
fvg_midpoint_distance
fvg_age_candles
fvg_mitigation_percent
```

### Displacement Features

```text
displacement_body_size
displacement_range
displacement_body_to_range_ratio
displacement_atr_multiple
volume_expansion_ratio
close_position_in_candle
```

### Market Structure Features

```text
mss_confirmed
bos_confirmed
swing_lookback
distance_to_structure_break
htf_bias
counter_bias_trade
```

### Volatility Features

```text
atr
atr_percent
recent_range
volatility_regime
spread_estimate
```

### Trade Setup Features

```text
entry_price
stop_distance
target_distance
reward_to_risk
signal_quality_score
risk_percent
```

## Models to Try First

Start simple.

Recommended baseline models:

```text
Logistic Regression
Random Forest
Gradient Boosting
XGBoost or LightGBM if available
```

Do not start with deep learning.

A simple model that generalizes is better than a complex model that overfits.

## Train/Validation/Test Split

Use time-based splits only.

Do not use random split.

Example:

```text
Training: oldest 60%
Validation: next 20%
Testing: latest 20%
```

Reason:

Trading data is time-dependent. Random split can leak future market behavior into training.

## Data Leakage Rules

The model must not use future information.

Forbidden features:

```text
future high
future low
future close
whether TP was hit
whether SL was hit
post-entry candle data
future liquidity levels unknown at entry
```

All features must be known at signal time.

## Metrics

Use classification and trading metrics.

Classification metrics:

```text
accuracy
precision
recall
F1
ROC-AUC
PR-AUC
calibration
```

Trading metrics:

```text
profit factor
expectancy
average R
max drawdown
win rate
trade count
session-specific performance
```

Precision is especially important because the model is used as a filter.

## Probability Threshold

The ML filter should only approve trades above a threshold.

Example:

```text
minimum_probability = 0.60
```

Possible decisions:

```text
probability >= 0.65: allow normal risk
0.55 <= probability < 0.65: reduce risk
probability < 0.55: reject trade
```

These values must be configurable and validated through backtesting.

## Model Registry

Each trained model must record:

```text
model_version
training_start_date
training_end_date
validation_period
test_period
features_used
model_type
metrics
created_at
active_status
```

The bot must support rollback to an older model.

## Retraining

Retraining can be scheduled weekly or monthly.

A new model should only replace the active model if:

```text
out-of-sample performance improves
drawdown does not worsen significantly
trade count remains sufficient
calibration is acceptable
```

## ML Integration Flow

```text
Rule-based Silver Bullet signal
    ↓
Feature builder
    ↓
ML model predicts probability
    ↓
Probability threshold check
    ↓
Risk engine
    ↓
Execution engine
```

## Important Rule

The ML model is a filter, not a trader.

The deterministic strategy and risk engine remain in control.

## Implemented Probability Filter

The Phase 6 probability filter is optional and disabled by default.

Config keys:

```text
ML_FILTER_ENABLED=false
ML_REGISTRY_PATH=models/model_registry.json
ML_MIN_PROBABILITY=0.60
ML_REDUCE_RISK_THRESHOLD=0.55
```

Decisions:

```text
probability >= ML_MIN_PROBABILITY: approve
ML_REDUCE_RISK_THRESHOLD <= probability < ML_MIN_PROBABILITY: reduce_risk
probability < ML_REDUCE_RISK_THRESHOLD: reject
```

If ML is disabled or no active model is available, the filter leaves the rule-based signal unchanged and records an audit reason.

The reduce-risk decision can only shrink the risk-approved position size. It cannot increase configured risk or bypass the risk engine.

ML predictions are stored locally with:

```text
signal_id
model_version
probability
threshold
decision
features_snapshot
created_at
```

## Calibration Reporting

Classification models should be checked for probability calibration before
promotion. The calibration report exports:

```text
calibration_report.json
calibration_bins.csv
```

The report includes:

```text
Brier score
Expected Calibration Error
reliability bins
mean predicted probability per bin
actual win rate per bin
sample count per bin
```

Plotting is optional and not required by the current implementation.

## Model Promotion Policy

A candidate model may only become active after offline evaluation. The policy
checks:

```text
candidate validation score improves over the current active model
candidate test score does not degrade beyond the configured allowance
candidate Brier score is below the configured maximum
minimum validation/test/calibration sample counts are met
final test data was not used for optimization
```

Promotion output must be auditable and can return:

```text
promote
reject
keep_current
```

Each decision includes clear reasons and can be exported as JSON. Promotion does
not let ML generate trades or bypass the deterministic strategy, risk engine, or
kill switch.
