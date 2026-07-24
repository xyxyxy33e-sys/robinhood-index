# External strategy sources — review and applicability

Three external sources were reviewed. **A shared blocker rules out most of them:**
`place_option_order` in this MCP is **single-leg only** ("Multi-leg spreads (Level 3
strategies) aren't supported yet, even on option_level_3 accounts"; spreads/condors/
butterflies are listed as "Supported in the Robinhood apps only"). The agentic
account 576391551 is **option_level_2**. So no spread, condor or butterfly can be
placed by this agent at all, regardless of settings.

## 1. alphacrunching — 7DTE SPX put credit spread
5-wide, short strike ~delta 40, Mondays near the close, filters = proprietary
"Weekly Triumph Rate" > 50% plus SPX 5sma > 10sma daily. Claims 80% win rate
2023–mid-2026, credit $1.55–1.70.
- **Not placeable** (2-leg spread).
- **Stats don't survive arithmetic:** max loss $340 vs $160 credit ⇒ breakeven win
  rate 68%. At the claimed 80%, expectancy ≈ +$60/trade on ~$340 collateral weekly
  ≈ 900% annualised. Implausible for a publicly described method. No max drawdown,
  trade count, or worst trade disclosed.
- The 5sma/10sma gate was tested on our strategy → **negative result**, see
  `trend_filter_test.md`. It is a risk filter for SHORT premium, not a direction
  predictor for LONG premium.

## 2. "Al Losada" webinar deck (simpleoptionstrategies.com PDF)
SPX weekly credit spreads, 10–30 wide. ~25 of 52 slides are sales copy for a paid
alert service.
- **Not placeable** (multi-leg).
- **Its own worked example is the tell:** a put spread entered 9/15/2023 is rolled
  SEVEN times (615-1 … 615-7) across a 282-point / 6.6% SPX decline before finally
  expiring worthless. That demonstrates deferring a loss, not edge.
- **Genuinely useful:** slide 13 — decay from 5 days to expiry is **100%**. We spent
  this project buying options inside that window. Our 25.6% June win rate against a
  33.3% breakeven is the signature of paying theta at its steepest. Independent
  support for moving off 0DTE.

## 3. spintwig — Short SPX Vertical Put 7-DTE, s1 signal
Could not retrieve (Cloudflare bot protection; no Wayback snapshot). From search
metadata: one position per trading day, **Jan 2007 – Jul 2024, 48,000+ trades**, 18
variants. The "s1 signal" is a boolean daily indicator for **volatility being priced
incorrectly**; filtering to s1-TRUE days improved total return, risk-adjusted return,
max drawdown and drawdown duration.
- **Not placeable** (2-leg spread).
- **Most rigorous of the three** — and a scale reminder: 48,000 trades over 17.5
  years vs our ~114 trades over two months examined from many angles.
- **Actionable mirror image:** their edge is selling premium when IV > subsequent
  realised vol. We are LONG premium and have **no volatility input at all**. That is
  a structural omission, arguably larger than any entry-time or DTE parameter tuned
  in this project. Historical IV is not retrievable via these tools, so it cannot be
  backtested → we now journal IV, greeks and IV/RV at every signal during dry-run
  (see `scripts/strategy_calc.py rvol` and PLAYBOOK Phase 3e).

## 4. Aggregated 0DTE summary (Reddit / YouTube / Option Alpha marketing)
Four strategies: short verticals, iron condors/butterflies, directional momentum
longs, lottery butterflies. **Only directional momentum longs are placeable** — which
is what this strategy already is.
- **Strike advice already adopted:** "buy ATM or slightly ITM". At 0DTE we used
  0.35–0.45 delta (OTM); the current 7DTE config targets 0.45–0.55 (ATM).
- **Entry timing — CONVERGENT EVIDENCE, worth acting on:** the source says enter
  ~10:15–10:30 after morning volatility resolves. Our own July data independently
  showed 9:45 entries 2-for-10 (−$523) vs 10:00+ entries 12-for-22 (+$1,854). Two
  unrelated lines agreeing is stronger than either alone. `entry_earliest` is
  currently 09:45 by owner decision — this is the single item most worth revisiting.
- **"Use SPX not SPY" — priced, and impossible at this account size:**
  SPX 7DTE ATM call = **$91.10/share = $9,110/contract**, 9× the $1,000 per-position
  cap and 78% of the account. XSP (mini-SPX, cash-settled, 1256 treatment) is the
  right size at **$882/contract** with a tight 1.3% spread, but **open interest 21,
  volume 7** — failing our OI ≥ 500 / volume ≥ 100 filters by 25× and 14×. Neither is
  usable. The underlying concern is moot anyway: we exit at 3 DTE and never hold to
  expiry, so auto-exercise cannot arise.
- **"Never use market orders" conflicts with our stop-market.** Their reasoning holds
  for 0DTE gamma. We chose stop-market because a stop-limit can gap through its floor
  and never fill, and with overnight holds an unfilled stop is worse than slippage.
  Retained, but it is a real tradeoff.
- **Credibility:** no win rates, sample sizes, drawdowns or methodology anywhere.
  Mechanical advice is largely sound; profitability claims are unverifiable.

## Standing lesson
Every externally sourced idea adopted so far has been **measured before adoption**,
and the one that looked most plausible (the SMA trend filter) failed badly on our
data. Do not wire an external rule into `config/strategy.yaml` on plausibility alone.
