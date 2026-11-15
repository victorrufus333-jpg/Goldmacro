# Gold Macro Signal — Task 2 Confidence and Conviction Report

## Delivered

Task 2 adds `scripts/build_confidence.py` and `data/confidence.json`. The engine reads the existing vintage-aware signal records and post-release GC=F reaction records. It does not fetch a new consensus feed, alter the existing BUY/SELL/UNSURE thresholds, or place trades.

For each release type and configured indicator, the engine calculates the Spearman rank relationship between the indicator delta, signed so the configured BUY direction is positive, and the measured post-release GC=F return. It records indicator sample N, rho, an explicitly approximate two-sided p-value, status, and a reliability weight. The weight is positive only when the measured relationship is positive and is shrunk for small N; underpowered rows remain visible and are not presented as validated predictors.

For each historical or upcoming signal, the engine calculates a weighted-vote conviction percentage and a confidence percentage blended from weighted vote support and a shrunk similar-case hit rate. Historical contexts use only chronologically prior cases. Upcoming contexts use completed historical cases. Similar cases require a configured minimum vote-pattern similarity and are capped at the configured top K.

## Live run evidence

The live run generated confidence contexts for 40 historical reconstructions and 13 upcoming signals, covering 17 release-indicator rule pairs.

- In-sample directional validation: N 22, wins 9, losses 13, observed win rate 40.91%.
- Walk-forward out-of-sample validation: eligible records 40; directional N 22, wins 9, losses 13, observed win rate 40.91%; 18 eligible cases were skipped because they were UNSURE or lacked a directional grade.
- Calibration buckets were emitted for 0–39, 40–59, 60–74, 75–89, and 90–100 confidence percentages. Most observed cases fall in the 40–59 bucket; the current sample is too small to claim calibrated probabilities.
- Status now includes `confidence_engine` with the generated record count and last-checked time.

## Automation and hosting

The daily GitHub Action now runs the confidence engine after signal generation and commits `data/confidence.json` when generated data changes. The lock-window Action also runs the engine so a captured live lock has confidence fields. The GitHub Pages deployment Action rebuilds `dist/` after every main-branch push. The confirmed public host is `https://victorrufus333-jpg.github.io/Goldmacro/`.

## Honest limitations

The p-values use a deterministic large-sample normal approximation and are not exact permutation p-values. The historical sample is small and spans limited regimes, so reliability can change materially as new releases arrive. FRED vintage observations are not a licensed real-time consensus feed. Gold is measured with the free `GC=F` COMEX futures front-month proxy, not spot XAUUSD. Confidence is evidence strength, not a probability guarantee or financial advice. The immutable public ledger remains separate and is not backfilled with reconstructed history.
