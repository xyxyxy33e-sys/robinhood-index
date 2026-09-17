# External data sources — what is actually available, and what it changes (2026-09-17)

Owner request (in-session, 9/17 ~13:45 ET): "check if webull has data that can improve
the current strategy" → "use any data you need". Four MCP sources were probed against
what the strategy consumes today (Robinhood 1-min SPY bars, VIX quote, option
quotes/greeks/OI, news). Every endpoint below was called, not assumed.

Standing rule applied throughout (`logs/backtest/external_sources_review.md`): nothing
is wired into `config/strategy.yaml` on plausibility. The one thing that could be
tested was tested (`logs/backtest/overnight_session_test.md`) and came back null. The
rest goes in as **journal-only context**, same path every diagnostic here has followed.

## Webull (account CVS6VUFB, Individual Cash, Trading authorization for this client)

| Endpoint | Status | Relevance |
|---|---|---|
| `get_stock_bars` SPY M1/M5, sessions PRE/RTH/ATH/**OVN** | works, delay 0, history back to at least June | RTH/PRE duplicate Robinhood. **OVN (20:00–04:00 ET) is new** — tested, null (`overnight_session_test.md`). |
| `get_stock_snapshot` (extend_hour + overnight) | works | one-call overnight/premarket high-low-volume summary — the cheap way to log the overnight range. |
| `get_stock_capital_flow` SPY (`category=US_STOCK`; `US_ETF` is rejected) | works, **daily** rows, max 5 per call | large/medium/small order in/out. Daily granularity only; context line, no intraday use. |
| `get_stock_noii_snapshot` | **works since ~14:00 ET today (LV2 enabled)** for Nasdaq-listed names under `category=US_STOCK` (`US_ETF` rejected) | **SPY is NYSE-Arca-listed → its NOII is structurally empty** (paired 0, side 4). **QQQ works** (e.g. 9/16 close: paired 462k, imbalance 24k) and is the strategy's own proxy-symbol, so the 09:28 ET opening-cross imbalance for QQQ is a real Phase 2 input. Side-code mapping (`imbalance_side` 3/4) is undocumented — logged raw. |
| `get_stock_noii_bars` (imbalance history) | still `STOCK QUOTES LV2` gated as of 14:15 ET — may lag entitlement | would allow a backtest of opening imbalance vs drive; re-check. |
| `get_stock_quotes` depth > 1 | still rejected (`depth not more than 1`) as of 14:15 ET | book depth; re-check. |
| `get_stock_tick` | works | trades carry `side: "N"` — no aggressor flag, so no buy/sell pressure series. |
| `get_futures_*` (ES) | `US_FUTURES` not subscribed; depth needs `FUTURES LV2` | ES overnight bars were the highest-value item; blocked. **No VX/VIX product exists in Webull's 2,303-product list**, so VIX futures are unavailable regardless. |
| `get_stock_footprint` | `FOOTPRINT` not subscribed | order-flow imbalance; blocked. |
| `get_event_*` (Kalshi-style contracts) | works | **Fed decision odds live and liquid** (9/17 14:00 ET: Oct hike-25 48¢, hold 53¢, cut ~1¢; OI 400–700k). CPI / payrolls / unemployment / GDP series exist; each instrument's `expected_exp_date` is the release date → a machine-readable macro calendar for the regime veto. Replaces headline-scraped "hike odds 93% (FedWatch via Benzinga)". |
| `get_gainers_losers`, `get_market_sectors` | work | micro-cap dominated; useless for breadth. |

## Public.com (16 accounts on the key; sole BROKERAGE is 5OG87042, options level NONE)

| Endpoint | Status | Relevance |
|---|---|---|
| `get_price_history` VIX, `instrument_type=INDEX`, period DAY | works — **5-minute intraday VIX bars** | Robinhood gives a VIX quote + daily history only. This is the missing input for the "intraday VIX velocity" next step named in `config/strategy.yaml` (`vix_change_watch_pts_per_day` comment). |
| `get_price_history` SPY DAY `ALL_SESSIONS` | works | 30-min bars incl. `preMarketOvernight` (00:00–04:00) / `postMarketOvernight` (20:00–24:00) — a second overnight source; same null as above. |
| `get_option_chain` SPY (any expiry) | works, needs an `account_id` | full chain with **greeks + IV, bid/ask/size, OI, volume** per contract. A second live options source; not needed while Robinhood quotes work, useful as a cross-check on IV. |
| `get_quotes` | works | L1. |

## Alpha Vantage (free key: 25 requests/day, 1/sec — burned ~8 today)

| Endpoint | Status | Relevance |
|---|---|---|
| `REALTIME_PUT_CALL_RATIO` SPY | works | full-chain and per-expiry P/C (9/17 14:00 ET: full chain 1.03; the 9/24 7-DTE expiry 1.95). One call per day at Phase 1 is affordable. |
| `HISTORICAL_PUT_CALL_RATIO` | rate-limited today; free-tier endpoint | 2008→ history — the only *backtestable* new series found. Not yet pulled (budget). |
| `TIME_SERIES_INTRADAY` (extended hours, monthly history) | rate-limited today; free-tier | redundant with Webull for bars. |
| `INDEX_DATA` VIX daily | rate-limited today; free-tier | redundant (Robinhood daily). |
| `HISTORICAL_OPTIONS` (15y chains with IV/greeks) | **premium — blocked** | would have solved the "historical IV not retrievable" gap from `external_sources_review.md` §3. Still unsolved. |
| `NEWS_SENTIMENT` tickers=SPY | works, **0 items** for SPY today | ETF coverage is thin; not useful for the regime scan. |

## co-invest (Liquid)

No SPY/SPX market (`search_markets` → none); `get_news` is a generic Google-News feed;
positioning data is crypto/DEX-oriented. **Not applicable.**

## What changes

1. **Nothing in `config/strategy.yaml` or the score.** No gate, no weight, no threshold.
2. **New journal-only context line** at Phase 1 (`docs/PLAYBOOK.md` step 1c) computed by
   `strategy_calc.py context` from: overnight SPY range/close (Webull snapshot), Fed
   decision odds + next CPI/NFP release dates (Webull events), P/C ratio full-chain +
   7-DTE expiry (Alpha Vantage), capital flow large-order net ratio (Webull), and VIX
   09:00 vs 09:29 from Public.com 5-min bars. Plus a Phase 2 line: QQQ NOII pre-open
   snapshot at ~09:28 ET. Every field is optional; a missing source is logged as
   missing, never estimated.
3. **Negative result recorded** for the overnight session
   (`logs/backtest/overnight_session_test.md`) so it is not re-tested on plausibility.

## What would actually move the needle (owner decisions)

- **Webull `US_FUTURES` subscription** → ES overnight/premarket bars. The only
  deep-liquidity pre-open tape on offer; the SPY overnight ATS (43k–110k shares/night)
  tested null, and ES may not do better, but it is the one thing that cannot be
  evaluated without paying.
- **Alpha Vantage premium** → `HISTORICAL_OPTIONS`. Would let the IV/RV question
  (`external_sources_review.md` §3: "we are LONG premium and have no volatility
  input") be backtested instead of accumulated forward one trade at a time.
- Re-check `get_stock_noii_bars` and `get_stock_quotes depth=10` tomorrow — if the LV2
  entitlement has finished propagating, QQQ opening-imbalance history becomes
  backtestable against the 09:30–09:45 drive.
