# Unit Economics (Personal Trading) (UES)

**Project:** Silver Bot (ICT Silver Bullet trading bot)
**Version:** 0.1
**Owner:** Cian Jake Francisco
**Status:** Draft
**Last updated:** 2026-10-08
**Last reconciled:** 2026-10-08 against code at commit `62037d1`

This document answers "what does one trade cost, and what win rate is needed to pay for it". It is arithmetic on the coded cost model, not a forecast: no win rate, return or profit is claimed, and the three evidence reports are 0 bytes (G-1, D-86). Requirements and owner inputs are in [brd-silverbot.md](brd-silverbot.md); the kill criteria that use these numbers are in [val-silverbot.md](val-silverbot.md) §4; gaps are in [scrutiny-silverbot.md](scrutiny-silverbot.md).

## 0. Fit

This is a personal-trading framing of unit economics. There are no customers, subscriptions, pricing or margins. The "unit" is one trade; the "revenue" is the trade result in R (multiples of the amount risked); the "costs" are exchange fees, slippage and spread per trade plus the running cost of operating the bot. Money amounts depend on the owner's capital and budget and are Owner input required (OI-#) in [brd-silverbot.md](brd-silverbot.md) §8.

## 1. Cost per Trade

### 1.1 Coded defaults

| Parameter | Backtest default | Paper executor default | Where |
|---|---|---|---|
| Maker fee (entry) | 0.0002 (0.02% of notional) | 0.0002 | `src/silver_bot/backtest/models.py:32`; `src/silver_bot/execution/models.py:30` |
| Taker fee (all exits) | 0.0005 (0.05% of notional) | 0.0005 | `backtest/models.py:33`; `execution/models.py:31` |
| Slippage | 0.0 bps | 1.0 bps | `backtest/models.py:34`; `execution/models.py:32` |
| Spread | 0.0 bps | 1.0 bps | `backtest/models.py:35`; `execution/models.py:33` |

How the backtester applies them: entry fee uses the maker rate and every exit (stop, take-profit, partial, end of data) uses the taker rate, even for take-profit limit exits (`backtest/engine.py:274,352,376`). Slippage per side is `price * slippage_bps / 10_000` and half-spread per side is `price * (spread_bps / 10_000) / 2`; entry and exit prices are each worsened by both (`engine.py:426-440`). Funding fees, gap-through-stop fills and margin effects are not modelled (`engine.py:314,326`; G-20, G-21).

**Honest status.** The backtest defaults of 0 bps slippage and 0 bps spread apply no cost unless the caller overrides them, which is unrealistic for 1m crypto futures; the old BACKTESTING.md claimed these costs were modelled conservatively (D-5, G-11). The break-even table below therefore uses only the coded fees, and the fee-only case is a floor on cost, not an estimate of it.

### 1.2 Cost per trade as a fraction of notional

With slippage `s` bps and spread `p` bps, the round-trip cost as a fraction of notional is:

```text
f = maker_fee + taker_fee + 2 * (s / 10000) + 2 * (p / 10000) / 2
  = 0.0002 + 0.0005 + (2s + p) / 10000
```

At the coded backtest defaults (s = 0, p = 0): `f = 0.0007`, that is 0.07% of notional (7 bps) per round trip, all of it fees. With the paper executor defaults (s = 1, p = 1) the formula gives `f = 0.0007 + 3/10000 = 0.0010` (0.10%); this is shown only to illustrate the sensitivity, because how the paper executor applies those values is documented in the SDD (not yet written).

### 1.3 Cost per trade in R

Let `d` be the stop distance as a fraction of entry price, and let the amount risked be 1R. Position sizing makes notional equal to risk divided by stop distance, so:

```text
notional = 1R / d
c = cost in R = f * notional / 1R = f / d
```

The same fee fraction therefore costs more R when the stop is tighter: halve the stop distance and the cost in R doubles. This is why the stop distance and trade frequency (BRD-V2, BRD-V4) matter on a 1m timeframe. The simplification here ignores the small widening of the stop distance caused by entry slippage and spread; at the coded defaults of 0 bps that effect is zero.

### 1.4 Worked example (illustrative, in R and percent of notional only)

Illustrative assumption, not a measurement and not a recommended setting: a stop distance of `d = 0.5%` of entry price (0.005).

- Cost as a fraction of notional: `f = 0.0007` (0.07%), fees only, coded backtest defaults.
- Cost in R: `c = 0.0007 / 0.005 = 0.14R`.
- Check with sizing: risk per trade of 0.5% of equity (`risk/models.py:18`) at `d = 0.5%` gives notional equal to 1.0 times equity (0.005 / 0.005), well inside the 3.0 leverage default (`risk/models.py:25`). Fees are 0.07% of that notional, which is 0.07% of equity, which is 0.14 of the 0.5% risked. This agrees with `c = 0.14R`.

So on this illustrative stop, every trade, win or lose, gives up 0.14R to fees before slippage and spread. No money amounts are needed: they follow from capital, which is Owner input required (OI-1).

## 2. Break-even Edge

### 2.1 Derivation

Define, for a trade that risks 1R with reward-to-risk ratio `RR` (target distance divided by stop distance) and cost `c` in R from section 1.3:

- A winning trade returns `RR - c` in R (the target is reached, then costs are paid).
- A losing trade returns `-(1 + c)` in R (the stop is hit, plus costs; entry and exit fees are paid on a loss too).
- Win probability is `p`.

Expectancy per trade:

```text
E = p * (RR - c) - (1 - p) * (1 + c)
  = p*RR - p*c - 1 - c + p + p*c
  = p * (RR + 1) - (1 + c)
```

The `p*c` terms cancel. Setting `E = 0` gives the break-even win rate:

```text
p_breakeven = (1 + c) / (1 + RR)
```

At `c = 0` this reduces to the familiar `1 / (1 + RR)`. Each unit of cost in R raises the required win rate by `c / (1 + RR)`. Any win rate above `p_breakeven` has positive expectancy under this model; any below has negative. Break-even is not a target: a profit factor of at least 1.2 is the old research threshold (BRD-M1), and that needs a win rate above break-even.

### 2.2 Table

`c = 0` is the no-cost reference (the slippage and spread defaults contribute 0, but the coded fees are not zero, so c = 0 is a lower bound that no coded configuration reaches). `c = 0.14R` is the illustrative fee-only value from section 1.4 (coded fees, `d = 0.5%`), the only illustrative cost used here.

| RR | Formula at c = 0: 1 / (1 + RR) | Break-even win rate at c = 0 | Formula at c = 0.14R: 1.14 / (1 + RR) | Break-even win rate at c = 0.14R |
|---|---|---|---|---|
| 1.5 | 1 / 2.5 | 40.0% | 1.14 / 2.5 | 45.6% |
| 2 | 1 / 3 | 33.3% | 1.14 / 3 | 38.0% |
| 3 | 1 / 4 | 25.0% | 1.14 / 4 | 28.5% |

Arithmetic check (expectancy must be zero at each break-even): RR 1.5, c = 0: 0.4 x 1.5 - 0.6 x 1 = 0.6 - 0.6 = 0. RR 2, c = 0.14: 0.38 x 1.86 - 0.62 x 1.14 = 0.7068 - 0.7068 = 0. RR 3, c = 0.14: 0.285 x 2.86 - 0.715 x 1.14 = 0.8151 - 0.8151 = 0. RR 1.5, c = 0.14: 0.456 x 1.36 - 0.544 x 1.14 = 0.62016 - 0.62016 = 0. RR 2, c = 0: 0.3333 x 2 - 0.6667 x 1 = 0. RR 3, c = 0: 0.25 x 3 - 0.75 x 1 = 0.

The minimum reward-to-risk the risk engine accepts is 2.0 by default (`risk/models.py:20`), so the RR 2 and RR 3 rows are the ones reachable under default risk settings; RR 1.5 is shown for reference and would be rejected at the default.

What the table does not say: whether the strategy achieves any of these win rates. That is the question the evidence reports must answer (G-1).

## 3. Running Costs & Runway

Amounts are not invented. The monthly budget is Owner input required (OI-2).

| Item | Monthly cost | Source or status |
|---|---|---|
| VPS (24/7 host) | Owner input required (OI-2) | DEPLOYMENT.md §Recommended Hosting lists "Oracle Cloud Always Free VPS" and "Low-cost VPS" (line 27 and nearby). If the owner uses the Always Free tier the hosting cost is 0 by that tier's name, but the old document states no amount and the current terms of the tier are not verified here (Open), so it is recorded under OI-2. |
| Historical and live market data | Owner input required (OI-8) | The historical fetch is a stub that raises NotImplementedError (G-13); the source is not chosen. Public exchange data may be free but that is not established by the repository (Open). |
| Exchange | No account fee stated; trading fees per section 1 | Maker 0.0002 and taker 0.0005 are coded defaults; the real fee tier of the owner's account is Owner input required (OI-10). |
| Telegram alerts | No cost stated in the repository | Open. A real transport does not exist yet (G-15). |
| Owner time | Owner input required (OI-5) | Monitoring hours per day. |

Runway: months of running cost the owner can fund = budget divided by monthly running cost. With OI-2 unanswered, no runway figure is computed.

## 4. Capital & Risk Budget

Percentages below are the coded defaults, with their exact scope. Money values need the owner's capital (OI-1).

| Item | Default | Where | Scope and caveat |
|---|---|---|---|
| Risk per trade (RiskConfig) | 0.005 (0.5% of equity) | `src/silver_bot/risk/models.py:18` | `RiskConfig` accepts up to 0.05 (5%) at `risk/models.py:29-30`. Not wired to Settings (D-11, G-5). |
| Risk per trade (Settings cap) | 0.005 | `src/silver_bot/config/settings.py:51,174,186` | Validated only in demo mode; any float is accepted in other modes. |
| Max daily loss (RiskConfig) | 0.02 (2% of equity) | `risk/models.py:21`; check at `risk/engine.py:63-65` | Daily state is in memory and resets on restart (G-7). |
| Max daily loss (Settings cap) | 0.02 | `settings.py:175,188` | Demo mode only. |
| Max leverage (RiskConfig) | 3.0 | `risk/models.py:25`; check at `risk/engine.py:77-78` | |
| Max leverage (Settings cap) | 3 | `settings.py:176,190` | Demo mode only. |
| Max consecutive losses / trades per day / open positions | 3 / 3 / 1 | `risk/models.py:22-24` | |
| Money at risk per trade | Owner input required (OI-1) | | = risk fraction x capital. |
| Money loss that triggers a stop | Owner input required (OI-3) | | Owner drawdown tolerance. |

Worked bound in percent of equity (no money assumed): at the defaults, each full stop-out loses about 0.5% of equity plus costs, and at most 3 trades per day are allowed (`risk/models.py:23`), so a day of three full stop-outs loses about 1.5% of equity plus costs, below the 2% daily loss cap. If `risk_per_trade` is raised towards the 0.05 ceiling, one stop-out alone is about 5% of equity, which already exceeds the 2% daily cap; the cap can then only block the next request, not prevent the loss. This is why a single risk source of truth matters (G-5).

## 5. Owner Input

All money values and the running-budget figure come from the Owner Input Register: [brd-silverbot.md](brd-silverbot.md) §8. This document uses OI-1 (capital), OI-2 (running budget), OI-3 (drawdown tolerance), OI-5 (monitoring hours), OI-8 (data source) and OI-10 (venue account). Once answered, section 3 runway and section 4 money rows can be filled by arithmetic only.

## Self-Check

- [x] Cost defaults (fee, slippage, spread) are quoted exactly as coded with file and line, and the 0 bps backtest default is flagged as unrealistic (D-5, G-11).
- [x] The break-even formula p = (1 + c) / (1 + RR) is derived algebraically from the cost model, with c in R as a variable, and the table is checked by substituting back into the expectancy.
- [x] The only illustrative cost is c = 0.14R, labelled as such, derived from the coded fees and a stated stop distance assumption of 0.5%.
- [x] Risk percentages state their scope: Settings caps apply in demo mode only, and RiskConfig allows up to 0.05 per trade (D-11, G-5).
- [x] No money amount is stated; running costs and capital are Owner input required (OI-#) or Open.
- [x] No performance or profit claim is made; G-1 and D-86 are cited.
- [ ] Section 3 and section 4 money rows are filled (open until the owner answers OI-1, OI-2 and OI-3).
