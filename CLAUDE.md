# robinhood-index

Agent-operated 0DTE index-options day-trading strategy (SPY/QQQ/IWM) on the
Robinhood agentic account.

- If you are a scheduled morning session: execute `docs/PLAYBOOK.md` top to bottom.
- Strategy rules and rationale: `docs/STRATEGY.md`. Parameters: `config/strategy.yaml`.
- **Respect `mode` in the config.** `dry_run` = never place, cancel, or modify orders.
- All math (sentiment score, sizing, stops) goes through `scripts/strategy_calc.py` —
  never improvise these numbers.
- Working branch for everything (code + daily journals):
  `claude/robinhood-day-options-strategy-y8eskp`. The default branch may be empty.
- Hard invariants: no entries after 11:30 ET, flat by 13:00 ET, resting stop-limit on
  every open position, never exceed the `risk:` limits in config.
