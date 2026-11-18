# Forecast GTA VI's launch-day Twitch viewers hour by hour

[![make.fun bounty](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Apizairdrop/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Apizairdrop/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

Entry for the [gta6-twitch-ccu-forecast-01 bounty on make.fun](https://make.fun/bounty/gta6-twitch-ccu-forecast-01):
forecast how many people watch Grand Theft Auto VI live on Twitch in each
hour of its release day, 2026-11-19 (UTC), after the first hour — five
quantiles (5/25/50/75/95%) per hour, scored by mean pinball loss on the log
scale.

## How it works

`main.py` (Python 3.13, standard library only, deterministic, no network)
reads the case file, anchors on the hour-1 print `p1`, and forecasts from
the day curves of past big launches shipped in the case (`comparables`):

- **Median shape** — the median log-ratio `ln(v_h / v_1)` per hour across past
  launches whose unlock rolled at midnight local time, the same unlock
  structure as GTA VI (New Zealand first, then Europe, then the US coasts),
  excluding early-access-contaminated and weak-tier launches. GTA VI's own
  pre-release category history (no release-day hours) is excluded.
- **Spread** — the empirical 5/25/50/75/95 quantiles of the same log-ratios
  across *all* valid comparables (more games → a stabler spread), re-centred
  on the rolling-pool median: `q_tau(h) = p1 * exp(median_h + (Q_tau,h - Q_50,h))`.
- Comparables are filtered (hour-1 print ≥ 500 and ≥ 1% of the day peak,
  ≥ 12 release-day hours sampled; missing hours are skipped, never invented),
  with fallbacks that never emit an invalid row.

## Backtest (leave-one-out over the kit's comparables)

Each comparable forecast from the others, pinball loss on the log scale:

| targets | this entry | house baseline |
| --- | --- | --- |
| rolling-midnight launches (the GTA VI analogues) | **0.283** | 0.406 |
| all 30 valid comparables | **0.429** | 0.462 |

90% coverage 0.902 on the rolling targets (honest ≈ 0.9); typical median
miss 41% vs the baseline's 61%. The filters were chosen from GTA VI's known
rolling midnight-local unlock, but the backtest and the filter choices share
the same 30 games, so treat 0.283 as optimistic — the final is a single
game and the true edge is probably smaller.

## Run locally

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Writes one `<id>.out` per `<id>.in`: `{"hours": [{"hour": h, "q": [q05, q25, q50, q75, q95]}, ...]}`,
23 rows, hours 2–24. Two runs are byte-identical and take ~0.05 s per case.
