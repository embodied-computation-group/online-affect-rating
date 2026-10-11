"""Quality-control library: parse result files and compute per-session QC metrics and flags.

Scope: checking data quality (attention, engagement, AI/automation signals). Time-series analysis,
group means and fMRI regressors belong in the separate analysis repository; the parsing here
(`load_session`) documents how to read the raw format (see docs/data.md).

A result file is newline-delimited JSON as written by task/js/experiment.js (JATOS result data, or the
NDJSON downloaded in local mode). Rating data are rebuilt from `chunk` lines, which survive reloads;
questionnaires come from `trial` lines (also reload-safe) and the `final` line when present.

Study-specific settings (film length, thresholds, questionnaire names, which dimensions are 2D) come from the
study file: pass `study = study_config.load_study("studies/<name>")` to the functions below. The advisory
thresholds are in the study file under qc.thresholds.
"""
from __future__ import annotations

import difflib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from study_config import SLOTS, dimension_axes, scale_pages


def scope_filter(rep, study: dict, scope: str = "exploratory"):
    """Restrict a qc_report DataFrame to a sample: "exploratory" (default), "confirmatory" or "all".

    The exploratory Prolific studies are listed in the study file (qc.exploratory_studies); every other real
    Prolific study is confirmatory. Scripts default to the exploratory sample so confirmatory data are not looked
    at before the registered analysis. A study without that list has no split: every real session is used.
    """
    if scope == "all":
        return rep
    if "prolific_study_id" not in rep:
        raise SystemExit("qc_report.csv lacks prolific_study_id - rerun qc/review.py")
    real = rep["prolific_study_id"].fillna("").str.fullmatch(r"[0-9a-f]{24}")  # drops local/test sessions
    exploratory_ids = study["qc"].get("exploratory_studies")
    if not exploratory_ids:
        return rep[real]
    expl = rep["prolific_study_id"].isin(set(exploratory_ids))
    return rep[real & ~expl] if scope == "confirmatory" else rep[expl]

@dataclass
class Session:
    path: Path
    meta: list[dict] = field(default_factory=list)
    trials: list[dict] = field(default_factory=list)  # questionnaire etc. (deduplicated)
    final: dict | None = None
    film_samples: pd.DataFrame | None = None
    film_inputs: pd.DataFrame | None = None
    film_events: pd.DataFrame | None = None
    practice: list[dict] = field(default_factory=list)  # practice trial dicts (scalars only)
    axes: int = 1  # 1 = one rating scale, 2 = 2D grid (from the study file)

    @property
    def m(self) -> dict:
        return self.meta[-1] if self.meta else {}

    @property
    def pid(self) -> str:
        return self.m.get("prolific_pid") or "?"

    @property
    def dimension(self) -> str:
        return self.m.get("dimension") or "?"

    @property
    def is2d(self) -> bool:
        return self.axes == 2

    def trial(self, task: str, **kw) -> list[dict]:
        out = [t for t in self.trials if t.get("task") == task]
        for k, v in kw.items():
            out = [t for t in out if t.get(k) == v]
        return out


def _rows_to_df(rows: list[list], cols: list[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=cols)
    n = len(cols)
    return pd.DataFrame([(list(r) + [None] * n)[:n] for r in rows], columns=cols)


def load_session(path: str | Path, study: dict) -> Session:
    """Read one result file. `study` (the study file) says which rating dimensions are 2D."""
    path = Path(path)
    s = Session(path)
    chunks = []
    trial_lines = []
    for line in path.read_text(encoding="utf8").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        typ = obj.get("type")
        if typ == "meta":
            s.meta.append(obj)
        elif typ == "chunk":
            chunks.append(obj)
        elif typ == "trial":
            trial_lines.append(obj["trial"])
        elif typ == "final":
            s.final = obj

    # Questionnaire/other trials: `trial` lines (all page loads) + final data of the last load, deduplicated.
    seen = set()
    final_trials = (s.final or {}).get("data", [])
    for t in trial_lines + [t for t in final_trials if t.get("task") not in ("film", "practice")]:
        key = (t.get("task"), t.get("time_elapsed"), t.get("trial_index"), json.dumps(t.get("response"), sort_keys=True, default=str))
        if key in seen:
            continue
        seen.add(key)
        s.trials.append(t)
    s.practice = [{k: v for k, v in t.items() if k not in ("samples", "inputs", "events")}
                  for t in final_trials if t.get("task") == "practice"]

    # Film rating data from chunks (tags "film", "film_resume_<n>").
    if s.dimension in study["rating"]["dimensions"]:
        s.axes = dimension_axes(study, s.dimension)
    is2d = s.is2d
    vcols = ["value_x", "value_y"] if is2d else ["value"]
    scols = ["t_stim", "t_frame", "t_wall", *vcols, "playing"]
    icols = ["t_stim", "t_wall", *vcols, "src", "dx", "dy"]
    samp, inp, ev = [], [], []
    for c in sorted(chunks, key=lambda c: (c.get("t", ""), c.get("chunk", 0))):
        tag = c.get("tag", "")
        if not tag.startswith("film"):
            continue
        for row in c.get("samples", []):
            if len(row) == len(scols) - 1:  # files from before t_frame was recorded
                row = [row[0], None, *row[1:]]
            samp.append([*row, tag])
        inp += [[*r, tag] for r in c.get("inputs", [])]
        ev += [{**e, "segment": tag} for e in c.get("events", [])]
    s.film_samples = _rows_to_df([r[:-1] for r in samp], scols).assign(segment=[r[-1] for r in samp]) if samp else _rows_to_df([], scols)
    s.film_inputs = _rows_to_df([r[:-1] for r in inp], icols).assign(segment=[r[-1] for r in inp]) if inp else _rows_to_df([], icols)
    s.film_events = pd.DataFrame(ev)
    return s


# ------------------------------------------------------------------------------ metrics ---
def _longest_identical_run(dx: np.ndarray, dy: np.ndarray, min_px: float = 0) -> int:
    best = run = 0
    prev = None
    for a, b in zip(dx, dy):
        cur = (a, b)
        big_enough = math.hypot(a, b) >= max(min_px, 1e-9)
        if big_enough and cur == prev:
            run += 1
        else:
            run = 1 if big_enough else 0
        best = max(best, run)
        prev = cur
    return best


def _longest_no_input(inputs: pd.DataFrame, samples: pd.DataFrame) -> float:
    """Longest stretch of film time (s) without any rating input, while the film was playing."""
    if samples.empty:
        return float("nan")
    play = samples.loc[samples["playing"] == 1, "t_stim"]
    if play.empty:
        return float("nan")
    times = np.sort(np.concatenate([[play.min()], inputs["t_stim"].to_numpy(dtype=float), [play.max()]]))
    return float(np.max(np.diff(times))) if len(times) > 1 else float("nan")


def _paired_s(events: pd.DataFrame, start_e: str, end_es: tuple) -> float:
    """Total wall time (s) from each `start_e` event to the next end event, within each segment."""
    if events.empty or "e" not in events:
        return 0.0
    total = 0.0
    for _, seg in events.groupby("segment", sort=False):
        start = None
        for e, t in zip(seg["e"], seg["t_wall"]):
            if e == start_e and start is None:
                start = t
            elif e in end_es and start is not None:
                total += (t - start) / 1000
                start = None
    return total


def _interrupted_s(events: pd.DataFrame) -> float:
    """Total wall time between each `interrupt` and the next `resume` (or segment end), all segments."""
    if events.empty or "e" not in events:
        return 0.0
    total = 0.0
    for _, seg in events.groupby("segment", sort=False):
        start = None
        for e, t in zip(seg["e"], seg["t_wall"]):
            if e == "interrupt" and start is None:
                start = t
            elif e in ("resume", "end") and start is not None:
                total += (t - start) / 1000
                start = None
    return total


def _coverage(samples: pd.DataFrame, film_duration_s: float) -> float:
    """Share of the film's whole seconds with at least one playing sample."""
    if samples.empty:
        return 0.0
    t = samples.loc[samples["playing"] == 1, "t_stim"].to_numpy(dtype=float)
    if t.size == 0:
        return 0.0
    covered = np.unique(np.floor(t)).size  # seconds of film with at least one playing sample
    return min(1.0, covered / math.floor(film_duration_s))


def ai_marker_hits(text: str, markers: list[str]) -> list[str]:
    """The phrasing markers (regular expressions from qc.ai_markers in the study file) found in a text."""
    tl = text.lower()
    return [m for m in markers if re.search(m, tl)]


def _pages(study: dict, types: tuple, slots=SLOTS) -> list[dict]:
    """Questionnaire pages of the given types in the given places of the session, in order."""
    q = study["questionnaires"]
    return [p for slot in slots for p in (q.get(slot) or []) if p["type"] in types]


def _page_trials(s: Session, name: str) -> list[dict]:
    """The saved trials of a questionnaire page (pages with an attention check are saved as task "attention")."""
    return [t for t in s.trials if t.get("task") == name or (t.get("task") == "attention" and t.get("page") == name)]


def session_metrics(s: Session, study: dict) -> dict:
    """All QC measures of one session, as one report row."""
    T = study["qc"]["thresholds"]
    sm = (s.final or {}).get("summary", {}) or {}
    integ = (s.final or {}).get("integrity", {}) or {}
    r: dict = {
        "file": s.path.name,
        "prolific_pid": s.pid,
        "study": s.dimension,
        "jatos_id": s.m.get("jatos_study_result_id"),
        "prolific_study_id": s.m.get("prolific_study_id"),
        "n_loads": max([m.get("n_loads") or 1 for m in s.meta] or [1]),
        "completed": any(t.get("task") == "end" for t in s.trials),
        "consent": next((t.get("consent") for t in s.trials if t.get("task") == "consent"), None),
    }

    # attention
    att = s.trial("attention")
    r["att_failed"] = sum(t.get("n_failed", 0) for t in att)
    r["att_total"] = sum(t.get("n_checks", 0) for t in att)

    # practice / quadrant
    pm = [p.get("practice_mae") for p in s.practice if p.get("practice_mae") is not None]
    r["practice_runs"] = len(s.practice)
    r["practice_err_last"] = pm[-1] if pm else sm.get("practice_mae_last")
    quad = s.trial("quadrant_practice")
    r["quadrant_correct"] = sum(bool(q.get("correct")) for q in quad) if quad else None

    # film coverage / interruptions
    fs, fi, fe = s.film_samples, s.film_inputs, s.film_events
    r["coverage"] = round(_coverage(fs, study["film"]["duration_s"]), 3)
    evn = fe["e"] if not fe.empty and "e" in fe else pd.Series(dtype=str)
    r["n_interruptions"] = int((evn == "interrupt").sum())
    r["n_stalls"] = int((evn == "stall").sum())
    r["stalled_s"] = round(_paired_s(fe, "stall", ("stall_end", "end")), 1)
    r["interrupted_s"] = round(_interrupted_s(fe), 1)
    r["away_s_total"] = round(integ.get("away_ms", sm.get("away_ms_total", 0) or 0) / 1000, 1) if (integ or sm) else None
    r["n_blur"] = integ.get("n_blur", sm.get("n_window_blur"))
    r["n_hidden"] = integ.get("n_hidden", sm.get("n_page_hidden"))

    # rating engagement
    r["n_inputs"] = len(fi)
    r["longest_no_input_s"] = round(_longest_no_input(fi, fs), 1)
    vcol = "value_y" if s.is2d else "value"
    if not fs.empty:
        v = fs.loc[fs["playing"] == 1, vcol].astype(float)
        r["value_sd"] = round(float(v.std()), 2) if len(v) > 1 else None
        r["frac_at_bounds"] = round(float(((v <= 0) | (v >= 100)).mean()), 3) if len(v) else None
        if s.is2d:
            vx = fs.loc[fs["playing"] == 1, "value_x"].astype(float)
            r["valence_sd"] = round(float(vx.std()), 2) if len(vx) > 1 else None

    # mouse automation signals (raw, unclamped deltas)
    mouse = fi[fi["src"] == "m"] if not fi.empty else fi
    dx = mouse["dx"].to_numpy(dtype=float) if not mouse.empty else np.array([])
    dy = mouse["dy"].to_numpy(dtype=float) if not mouse.empty else np.array([])
    steps = np.hypot(dx, dy)
    r["n_mouse_events"] = int(steps.size)
    r["frac_key_inputs"] = round(float((fi["src"] == "k").mean()), 3) if len(fi) else None
    r["max_step_px"] = int(steps.max()) if steps.size else 0
    # Teleport = a large step that is isolated in time. Fast human flicks are large too, but come in dense bursts.
    r["n_big_steps"] = int((steps > T["teleport_px"]).sum())
    if steps.size:
        tw = mouse["t_wall"].to_numpy(dtype=float)
        gap_prev = np.diff(tw, prepend=-np.inf)
        gap_next = np.diff(tw, append=np.inf)
        iso = (gap_prev > T["teleport_isolation_ms"]) & (gap_next > T["teleport_isolation_ms"])
        r["n_teleports"] = int(((steps > T["teleport_px"]) & iso).sum())
    else:
        r["n_teleports"] = 0
    r["identical_run_max"] = _longest_identical_run(dx, dy, T["identical_min_px"])
    r["frac_big_steps"] = round(float((steps > T["teleport_px"]).mean()), 3) if steps.size else None
    if steps.size:
        moving = steps > 0
        off = (dx == 0) if not s.is2d else ((dx == 0) | (dy == 0))
        r["frac_pure_axis"] = round(float(off[moving].mean()), 3) if moving.any() else None
    else:
        r["frac_pure_axis"] = None
    r["untrusted_events"] = sm.get("film_untrusted_events")

    # Scale questionnaires (e.g. STICSA pre/post): total, all-same-answer flag, and post - pre change
    timepoints = {}
    for page in scale_pages(study):
        timepoints.setdefault(page["scale"], []).append(page.get("timepoint"))
    for name, tps in timepoints.items():
        for tp in tps:
            col = f"{name}_{tp}" if tp else name
            st = s.trial(name, timepoint=tp) if tp else s.trial(name)
            r[col] = st[-1].get("total") if st else None
            r[f"{col}_straightline"] = (len({i["response"] for i in st[-1]["items"]}) == 1) if st else None
        if "pre" in tps and "post" in tps:
            pre, post = r[f"{name}_pre"], r[f"{name}_post"]
            r[f"{name}_change"] = (post - pre) if None not in (pre, post) else None

    # Answers to the post-film likert and multiple-choice pages, as q_<question name> columns
    for page in _pages(study, ("likert", "multi_choice"), slots=("after_film", "end")):
        saved = _page_trials(s, page["name"])
        if saved:
            r.update({f"q_{k}": v for k, v in (saved[-1].get("response") or {}).items()})

    # free text (the first free_text page of the study)
    text_pages = _pages(study, ("free_text",))
    text_name = text_pages[0]["name"] if text_pages else None
    ft = s.trial(text_name) if text_name else []
    text = ft[-1].get("text", "") if ft else ""
    r["text"] = text
    r["text_words"] = ft[-1].get("n_words") if ft else None
    r["text_chars"] = ft[-1].get("n_chars", len(text)) if ft else None
    r["text_keys"] = ft[-1].get("n_keys") if ft else None
    r["text_keys_per_char"] = (round(r["text_keys"] / r["text_chars"], 2)
                               if ft and r["text_chars"] and r["text_keys"] is not None else None)
    rt_min = (ft[-1].get("rt") or 0) / 60000 if ft else 0
    r["text_cpm"] = round(r["text_chars"] / rt_min) if ft and rt_min > 0 else None
    r["text_away_s"] = round((ft[-1].get("away_ms") or 0) / 1000, 1) if ft else None
    r["text_input_types"] = json.dumps(ft[-1].get("input_types")) if ft and ft[-1].get("input_types") else ""
    tev = [e for e in integ.get("events", []) if text_name and e.get("task") == text_name]
    r["text_paste_drop_attempts"] = sum(e.get("e") in ("paste_blocked", "drop_blocked", "insert_blocked") for e in tev)
    r["paste_blocked"] = integ.get("paste_blocked", sm.get("paste_blocked"))
    r["copy_blocked"] = integ.get("copy_blocked", sm.get("copy_blocked"))
    r["ai_markers"] = ";".join(ai_marker_hits(text, study["qc"].get("ai_markers") or [])) if text else ""

    # feedback: the answer to the first question of the first "text" page
    fb_pages = _pages(study, ("text",))
    fb_page = fb_pages[0] if fb_pages else None
    fb = s.trial(fb_page["name"]) if fb_page else []
    fb_question = fb_page["questions"][0]["name"] if fb_page else None
    r["feedback"] = ((fb[-1].get("response") or {}).get(fb_question) or "") if fb else ""
    return r


def add_duplicate_text_flags(rows: list[dict], study: dict) -> None:
    """Add each session's highest text similarity to another session (and who, above the threshold)."""
    T = study["qc"]["thresholds"]
    for i, a in enumerate(rows):
        best, who = 0.0, None
        for j, b in enumerate(rows):
            if i == j or not a.get("text") or not b.get("text"):
                continue
            ratio = difflib.SequenceMatcher(None, a["text"].lower(), b["text"].lower()).ratio()
            if ratio > best:
                best, who = ratio, b.get("prolific_pid")
        a["text_max_similarity"] = round(best, 2)
        a["text_most_similar_to"] = who if best >= T["duplicate_text_ratio"] else ""


def flags(r: dict, study: dict) -> tuple[str, list[str], list[str]]:
    """Return (verdict, reject_reasons, review_reasons) for a report row. Verdicts are advisory.
    Thresholds come from the study file (qc.thresholds, qc.review_answers)."""
    T = study["qc"]["thresholds"]
    rej, rev = [], []
    # Objective evidence (Prolific: rejection needs clear evidence the terms were broken)
    att_reject = T["attention_failed_reject"]
    if r.get("att_failed", 0) >= att_reject:
        rej.append("failed both attention checks" if att_reject == 2 else f"failed {r['att_failed']} attention checks")
    if (r.get("untrusted_events") or 0) > 0:
        rej.append(f"{r['untrusted_events']} script-generated input events")
    if (r.get("text_chars") or 0) >= T["text_min_chars_for_key_check"] and r.get("text_keys_per_char") is not None \
            and r["text_keys_per_char"] < T["text_keys_per_char_reject"]:
        msg = f"text not typed ({r['text_keys']} keystrokes for {r['text_chars']} characters)"
        outside = (r.get("text_paste_drop_attempts") or 0) > 0 or (r.get("text_away_s") or 0) > 10
        if outside:  # inserted from elsewhere after blocked paste/drop attempts or time in another window
            rej.append(msg + " after paste/drop attempts or time away")
        else:  # e.g. voice dictation / IME: the participant's own words, no evidence of misconduct
            rev.append(msg + " - no paste attempts or time away: possibly dictation; check input types/text")
    # Patterns that need a human look (automation)
    if r.get("n_teleports", 0) >= T["teleport_count_review"]:
        rev.append(f"{r['n_teleports']} isolated mouse jumps > {T['teleport_px']} px")
    if (r.get("frac_big_steps") or 0) > T["big_step_frac_review"] and r.get("n_mouse_events", 0) >= 50:
        rev.append(f"erratic input: {r['frac_big_steps']:.0%} of mouse steps > {T['teleport_px']} px - inspect the "
                   "rating trace; likely exclusion, not evidence of misconduct")
    if r.get("identical_run_max", 0) >= T["identical_run_review"]:
        rev.append(f"{r['identical_run_max']} identical mouse steps in a row")
    if (r.get("frac_pure_axis") or 0) >= T["pure_axis_review"] and r.get("n_mouse_events", 0) >= T["pure_axis_min_events"]:
        rev.append(f"no off-axis mouse jitter ({r['frac_pure_axis']:.0%} pure-axis moves)")
    if (r.get("text_cpm") or 0) > T["typing_cpm_review"]:
        rev.append(f"very fast text ({r['text_cpm']} chars/min)")
    hits = [h for h in (r.get("ai_markers") or "").split(";") if h]
    if len(hits) >= T["ai_markers_review"]:
        rev.append(f"LLM-style phrasing ({len(hits)} markers)")
    if r.get("text_most_similar_to"):
        rev.append(f"text {r['text_max_similarity']:.0%} similar to {r['text_most_similar_to']}")
    if (r.get("paste_blocked") or 0) > 0 or (r.get("copy_blocked") or 0) > 0:
        rev.append(f"{r.get('copy_blocked') or 0} copy / {r.get('paste_blocked') or 0} paste attempts (blocked)"
                   + (f", {r['text_away_s']:.0f} s away while writing" if (r.get("text_away_s") or 0) > 10 else ""))
    # Engagement / attention (exclusion candidates, not rejection)
    n_failed = r.get("att_failed") or 0
    if 0 < n_failed < att_reject:
        rev.append(f"failed {n_failed} attention check" + ("s" if n_failed > 1 else ""))
    if r.get("coverage", 1) < T["coverage_min"]:
        rev.append(f"film coverage {r['coverage']:.0%}")
    if r.get("n_interruptions", 0) > T["interruptions_review"] or (r.get("interrupted_s") or 0) > T["interrupted_s_review"]:
        rev.append(f"{r['n_interruptions']} interruptions ({r.get('interrupted_s')} s)")
    if (r.get("stalled_s") or 0) > T["stalled_s_review"]:
        rev.append(f"film buffered {r['stalled_s']:.0f} s ({r['n_stalls']} stalls)")
    if (r.get("longest_no_input_s") or 0) > T["no_input_s_review"]:
        rev.append(f"no rating input for {r['longest_no_input_s']:.0f} s")
    if (r.get("away_s_total") or 0) > T["away_s_review"]:
        rev.append(f"away from the window {r['away_s_total']:.0f} s")
    dims = study["rating"]["dimensions"]
    is2d = r.get("study") in dims and dimension_axes(study, r["study"]) == 2
    thr = T["practice_err2d_review"] if is2d else T["practice_mae_review"]
    if r.get("practice_err_last") is not None and r["practice_err_last"] > thr:
        rev.append(f"practice error {r['practice_err_last']} after {r['practice_runs']} runs")
    if r.get("quadrant_correct") is not None and r["quadrant_correct"] < T["quadrant_min"]:
        rev.append(f"quadrant practice {r['quadrant_correct']}/6")
    for rule in study["qc"].get("review_answers") or []:  # e.g. had seen the film before
        if r.get(f"q_{rule['question']}") == rule["answer"]:
            rev.append(rule["reason"])
    if r.get("n_loads", 1) > 1:
        rev.append(f"{r['n_loads']} page loads")
    if not r.get("completed"):
        rev.append("did not complete")
    verdict = "REJECT-ELIGIBLE" if rej else ("REVIEW" if rev else "OK")
    return verdict, rej, rev


def prereg_hard_exclusion(r, study: dict) -> str:
    """The study's preregistered hard exclusions (study file: qc.hard_exclusions; for the heights study the
    preregistration's 'Data inclusion and exclusion' rules 1-7), applied exactly as written.
    Returns '' if included, else the reasons. Takes a qc_report row (dict or Series), e.g.
    rep.apply(lambda row: prereg_hard_exclusion(row, study), axis=1)."""
    x = study["qc"]["hard_exclusions"]
    g = (lambda k: r.get(k)) if hasattr(r, "get") else (lambda k: getattr(r, k, None))
    num = lambda k: (g(k) if g(k) is not None and g(k) == g(k) else 0)  # noqa: E731  (NaN -> 0)
    w = []
    if num("att_failed") >= x["attention_failed_at_least"]:
        n = x["attention_failed_at_least"]
        w.append("both attention checks failed" if n == 2 else f"{n} or more attention checks failed")
    if num("untrusted_events") > 0:
        w.append("script-generated input")
    kpc = g("text_keys_per_char")
    if kpc is not None and kpc == kpc and num("text_chars") >= x["text_min_chars"] and kpc < x["text_keys_per_char_below"]:
        w.append("free text not typed")
    if num("frac_big_steps") > x["big_step_frac_above"]:
        w.append("erratic input")
    if num("stalled_s") > x["stalled_s_above"] or num("interrupted_s") > x["interrupted_s_above"]:
        w.append("disrupted viewing")
    if num("coverage") < x["coverage_below"]:
        w.append(f"film coverage < {x['coverage_below']:.0%}")
    for rule in x.get("answers") or []:  # e.g. had seen the film before
        if g(f"q_{rule['question']}") == rule["answer"]:
            w.append(rule["reason"])
    return "; ".join(w)
