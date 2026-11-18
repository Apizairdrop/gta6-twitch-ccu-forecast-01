"""gta6-twitch-ccu-forecast-01: forecast GTA VI's launch-day Twitch viewers.

Method: comparable day-curve ratios, anchored on the case's hour-1 print.
  - Median shape: the median log-ratio ln(v_h / v_1) per hour h = 2..24 across
    past launches whose unlock rolled at midnight local time (the same unlock
    structure as GTA VI: New Zealand first, then Europe, then the US coasts),
    excluding early-access-contaminated and weak-tier launches. GTA VI's own
    pre-release category history (no release-day hours) is excluded.
  - Spread: the empirical 5/25/50/75/95 quantiles of the same log-ratios
    across ALL valid comparables (more games -> a stabler spread), re-centred
    on the rolling-pool median.
  - q_tau(h) = p1 * exp(median_h + (Q_tau,h - Q_50,h)), p1 = hour-1 print.
  - Fallbacks (never crash, never emit an invalid row): if the rolling pool
    is too small, widen it to all rolling launches, then to all comparables;
    an hour with too few ratios falls back to the spread pool's own quantiles,
    then to the house baseline's persistence spread.

Leave-one-out backtest over the kit's comparables (each comparable forecast
from the others, pinball loss on the log scale, same formula as RULES.txt):
  rolling-midnight targets (the GTA VI analogues): loss 0.283 vs house
  baseline 0.406, 90% coverage 0.902, typical median miss 41% vs 61%.
  All 30 valid comparables as targets: loss 0.429 vs baseline 0.462.
The backtest and the filter choices share the same 30 games, so treat the
0.283 as optimistic; the filters are justified by GTA VI's known rolling
midnight-local unlock, not by per-game peeking.

Deterministic (no randomness, no network, stdlib only) and fast (<0.1 s/case).
"""

import json
import math
import os
import sys
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file would import. (This entry is a single file.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
BASE_SIGMA = 0.15  # house baseline spread, used only as a last-resort fallback

# A comparable is usable when its hour-1 print is not tiny/noisy and enough
# of its release-day hours were sampled (SullyGnome samples small categories
# sparsely; missing hours are skipped, never invented).
MIN_HOUR1 = 500
MIN_HOUR1_FRACTION_OF_PEAK = 0.01
MIN_RELEASE_DAY_HOURS = 12
MIN_POOL_GAMES = 3


def parse_ts(s):
    """ISO-8601 UTC timestamp -> epoch seconds (stdlib only)."""
    from datetime import datetime

    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def day_hours(comp):
    """viewers per release-day hour (1..24) from the comparable's day_start."""
    start = parse_ts(comp["day_start"])
    out = {}
    for row in comp.get("hourly") or []:
        v = row.get("viewers")
        if v is None or v <= 0:
            continue
        h = int((parse_ts(row["from"]) - start) // 3600) + 1
        if 1 <= h <= 24:
            out[h] = v
    return out


def is_target_history(comp):
    # GTA VI's own pre-release category history: no release-day hours.
    return (comp.get("name") or "").startswith("Grand Theft Auto VI")


def tier_of(comp):
    """Research tier from the unlock note ('Tier: comparable' etc.)."""
    unlock = comp.get("unlock") or ""
    if "Tier:" not in unlock:
        return None
    tail = unlock.split("Tier:", 1)[1].strip()
    return tail.split(".")[0].split(";")[0].strip().lower() or None


def is_rolling_midnight(comp):
    """Rolling midnight-local unlock, like GTA VI (NZ -> Europe -> US).

    The text before the 'Tier:' note must mention midnight local / rolling
    and must not describe a simultaneous or single-global unlock (a PC/GMT
    or single-time unlock has a totally different day curve).
    """
    unlock = (comp.get("unlock") or "").lower()
    pre = unlock.split("tier:")[0]
    if "simultaneous" in pre or "single global" in pre:
        return False
    return "midnight local" in pre or "rolling" in pre


def valid_comparables(case):
    """(name, {hour: viewers}) for comparables with a usable release day."""
    pool = []
    for comp in case.get("comparables") or []:
        if is_target_history(comp):
            continue
        hrs = day_hours(comp)
        if 1 not in hrs:
            continue
        p1 = hrs[1]
        peak = max(hrs.values())
        if p1 < MIN_HOUR1 or p1 < MIN_HOUR1_FRACTION_OF_PEAK * peak:
            continue
        if len(hrs) < MIN_RELEASE_DAY_HOURS:
            continue
        pool.append((comp.get("name") or "?", hrs, comp))
    return pool


def quantile(sorted_vals, q):
    """Linear-interpolation quantile of an already-sorted list."""
    n = len(sorted_vals)
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def log_ratios(pool, hour):
    """Sorted ln(v_h / v_1) across the pool's games that have hour h."""
    vals = []
    for _name, hrs, _comp in pool:
        if hour in hrs:
            vals.append(math.log(hrs[hour] / hrs[1]))
    return sorted(vals)


def baseline_row(p1, h):
    return [p1 * math.exp(z * BASE_SIGMA * math.sqrt(h - 1)) for z in Z]


def round2(x):
    """x rounded to 2 decimals, half up (as the starter does)."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if float(value).is_integer() else value


def hour1_print(case, name):
    """Hour-1 print (viewers) from the case's known entries.

    Takes the LAST hour-1 entry if several are listed (the most recent
    print wins over a superseded one) and requires its viewers to be a
    finite number. A missing or unusable hour-1 print is a data error,
    raised clearly here instead of crashing later on a None, a string
    or a NaN (which would make the whole case invalid).
    """
    entries = [k for k in case.get("known") or [] if k.get("hour") == 1]
    if not entries:
        raise ValueError(f"{name} has no hour-1 print")
    viewers = entries[-1].get("viewers")
    if isinstance(viewers, bool) or not isinstance(viewers, (int, float)):
        raise ValueError(f"{name} hour-1 print is not a number: {viewers!r}")
    if not math.isfinite(viewers):
        raise ValueError(f"{name} hour-1 print is not finite: {viewers!r}")
    return max(1, viewers)


def forecast_case(case, name):
    if case.get("levels") != LEVELS:
        raise ValueError(f"{name} asks for levels {case.get('levels')}, not {LEVELS}")
    p1 = hour1_print(case, name)

    pool = valid_comparables(case)
    rolling = [item for item in pool if is_rolling_midnight(item[2])]
    # Median shape pool: rolling launches of tier 'comparable' (or untiered).
    median_pool = [item for item in rolling
                   if tier_of(item[2]) in ("comparable", None)]
    if len(median_pool) < MIN_POOL_GAMES:
        median_pool = rolling
    if len(median_pool) < MIN_POOL_GAMES:
        median_pool = pool
    spread_pool = pool

    # The contract is hours 2..24, each once: refuse a case that asks for
    # anything else instead of silently writing a wrong-shaped forecast.
    want = [row.get("hour") for row in case.get("forecast") or []]
    if sorted(want) != list(range(2, 25)):
        raise ValueError(f"{name} asks to forecast hours {want}, not 2..24")

    hours = []
    for row in case["forecast"]:
        h = row["hour"]
        med_vals = log_ratios(median_pool, h)
        spr_vals = log_ratios(spread_pool, h)
        if len(spr_vals) >= MIN_POOL_GAMES and len(med_vals) >= MIN_POOL_GAMES:
            med = quantile(med_vals, 0.5)
            spr_q = [quantile(spr_vals, q) for q in LEVELS]
            spr_med = spr_q[2]
            qs = [p1 * math.exp(med + (q - spr_med)) for q in spr_q]
        elif len(spr_vals) >= MIN_POOL_GAMES:
            qs = [p1 * math.exp(quantile(spr_vals, q)) for q in LEVELS]
        else:
            qs = baseline_row(p1, h)
        # Clamp to the contest's bounds and enforce non-decreasing quantiles.
        qs = [min(max(q, 0.01), 1e9) for q in qs]
        for i in range(1, 5):
            qs[i] = max(qs[i], qs[i - 1])
        hours.append({"hour": h, "q": [round2(q) for q in qs]})
    return {"hours": hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
