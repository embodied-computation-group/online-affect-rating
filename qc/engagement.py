"""Engagement / compliance check for the continuous ratings (were people actually watching?).

Real ratings: frequent small adjustments that change when the film changes. Half-watching (e.g. a phone or second
screen): a few large moves, long gaps, timing unrelated to the film's events.

Per participant (completed sessions of the 2D rating dimensions, e.g. affect2d):
  bouts_per_min   movement episodes (inputs separated by > bout_gap_s start a new bout) per minute of film
  longest_gap_s   longest stretch of film without any rating input
  r_arousal, r_valence  leave-one-out correlation with the mean of everyone else (1 Hz)
  lock_ratio      share of the participant's bouts starting within +-window_s of "group events" (the top event_pct %
                  of |d/dt| of the leave-one-out group mean, valence or arousal), divided by the share expected by
                  chance (bout times circularly shifted 1000x). ~1 = unrelated to the film; >1 = tracks the film.
  lock_p          permutation p-value for lock_ratio
  flag            LOW-ENGAGEMENT if few bouts AND weak agreement; "check" if one of them; reasons listed.
                  NOTE (2026-10-04, n = 23): lock_ratio is NOT discriminative yet - the +-10 s windows around the
                  top-10 % change moments cover most of the film, so even r = 0.96 raters score ~1. Reported only,
                  not used in the flag; needs narrower events/windows (e.g. segment edges) before use.

Settings are in the study file under qc.engagement.
Run after qc/review.py:  python qc/engagement.py --study studies/heights-film   -> qc/out/engagement.csv
  (exploratory sample by default; add --confirmatory or --all)
Interpretation: a flag is a reason to look at the plot and text, not proof. Prolific allows rejection for
objectively demonstrated low effort; disagreeing with the group alone is not that.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qc_lib import load_session, scope_filter  # noqa: E402
from study_config import StudyFileError, dimension_axes, load_study  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW, OUT = ROOT / "data" / "raw", ROOT / "qc" / "out"


def bouts(times: np.ndarray, bout_gap: float) -> np.ndarray:
    """Start times of movement bouts: inputs more than bout_gap s apart start a new bout."""
    if times.size == 0:
        return times
    t = np.sort(times)
    starts = np.concatenate([[True], np.diff(t) > bout_gap])
    return t[starts]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", required=True, help="study folder, e.g. studies/heights-film")
    ap.add_argument("--confirmatory", action="store_true", help="use the confirmatory sample")
    ap.add_argument("--all", action="store_true", help="use all sessions")
    a = ap.parse_args()
    try:
        study = load_study(a.study)
    except StudyFileError as err:
        sys.exit(str(err))
    E = study["qc"]["engagement"]
    BOUT_GAP, WIN, EVENT_PCT, NPERM = E["bout_gap_s"], E["window_s"], E["event_pct"], E["n_permutations"]
    T = np.arange(0, np.floor(study["film"]["duration_s"]), 1.0)
    dims_2d = [d for d in study["rating"]["dimensions"] if dimension_axes(study, d) == 2]

    rep = pd.read_csv(OUT / "qc_report.csv")
    rep = scope_filter(rep, study, "all" if a.all else "confirmatory" if a.confirmatory else "exploratory")
    done = set(rep.loc[(rep["completed"] == True) & rep["study"].isin(dims_2d), "prolific_pid"])  # noqa: E712
    status = dict(zip(rep["prolific_pid"], rep.get("prolific_status", pd.Series(dtype=str))))
    S = {}
    for p in sorted(RAW.glob("*.ndjson")):
        s = load_session(p, study)
        if not (s.meta and s.pid in done and s.is2d) or s.film_samples.empty:
            continue
        d = s.film_samples[s.film_samples["playing"] == 1].sort_values("t_stim")
        t = d["t_stim"].astype(float)
        S[s.pid] = (np.interp(T, t, d["value_x"].astype(float)), np.interp(T, t, d["value_y"].astype(float)),
                    s.film_inputs["t_stim"].astype(float).to_numpy())
    pids = list(S)
    V, A = np.vstack([S[p][0] for p in pids]), np.vstack([S[p][1] for p in pids])
    rng = np.random.default_rng(0)
    rows = []
    for i, p in enumerate(pids):
        o = [j for j in range(len(pids)) if j != i]
        mv, ma = V[o].mean(0), A[o].mean(0)
        r_a, r_v = np.corrcoef(A[i], ma)[0, 1], np.corrcoef(V[i], mv)[0, 1]
        # group events: fastest-changing moments of the leave-one-out mean (smoothed 5 s)
        sm = lambda x: pd.Series(x).rolling(5, center=True, min_periods=1).mean().to_numpy()  # noqa: E731
        rate = np.abs(np.gradient(sm(ma))) + np.abs(np.gradient(sm(mv)))
        ev = T[rate >= np.percentile(rate, 100 - EVENT_PCT)]
        b = bouts(S[p][2], BOUT_GAP)
        near = lambda bt: np.mean([np.any(np.abs(ev - x) <= WIN) for x in bt]) if bt.size else np.nan  # noqa: E731
        obs = near(b)
        L = T.max()
        null = np.array([near((b + rng.uniform(0, L)) % L) for _ in range(NPERM)]) if b.size else np.array([np.nan])
        lock_ratio = obs / np.nanmean(null) if b.size and np.nanmean(null) > 0 else np.nan
        lock_p = (np.sum(null >= obs) + 1) / (NPERM + 1) if b.size else np.nan
        gaps = np.diff(np.sort(np.concatenate([[0], S[p][2], [L]])))
        rows.append({"pid": p, "status": status.get(p), "bouts_per_min": round(b.size / (L / 60), 1),
                     "longest_gap_s": round(float(gaps.max()), 0), "r_arousal": round(r_a, 2),
                     "r_valence": round(r_v, 2), "lock_ratio": round(lock_ratio, 2), "lock_p": round(lock_p, 3)})
    df = pd.DataFrame(rows)

    def flag(r):
        why = []
        if r["bouts_per_min"] < E["min_bouts_per_min"] or r["longest_gap_s"] > E["max_gap_s"]:
            why.append(f"sparse ratings ({r['bouts_per_min']} bouts/min, longest gap {r['longest_gap_s']:.0f} s)")
        if max(r["r_arousal"], r["r_valence"]) < E["min_r"]:
            why.append(f"weak agreement (r_a {r['r_arousal']}, r_v {r['r_valence']})")
        return ("LOW-ENGAGEMENT" if len(why) == 2 else ("check" if why else "ok")), "; ".join(why)

    df[["flag", "reasons"]] = df.apply(lambda r: pd.Series(flag(r)), axis=1)
    df = df.sort_values(["flag", "lock_ratio"], ascending=[True, True])
    df.to_csv(OUT / "engagement.csv", index=False)
    with pd.option_context("display.width", 220, "display.max_colwidth", 90):
        print(df.to_string(index=False))
    print("\nwrote", OUT / "engagement.csv")


if __name__ == "__main__":
    main()
