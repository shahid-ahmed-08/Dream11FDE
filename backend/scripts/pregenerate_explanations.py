"""
Pre-generate AI explanations for all key moments across all 3 preset teams.
Caches results to data/ai_cache/{packet_hash}.json.

Usage:
  python backend/scripts/pregenerate_explanations.py [--team safe_pick|differential|finisher_fan]
  Reads GEMINI_API_KEY from .env or environment if present.
"""
import json
import os
import sys
import time
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env if it exists
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Pre-generate AI explanations for preset teams.")
    parser.add_argument("--team", choices=["safe_pick", "differential", "finisher_fan"],
                        help="Generate for one preset. Defaults to all 3.")
    return parser.parse_args()


def run_team(team_key: str, api_key: str, report: dict):
    from backend.app.services.fan_session import FanSession
    from backend.app.services.preset_teams import PRESET_TEAMS
    from backend.app.services.ai_explainer import get_explanation_sync
    from backend.app.services.replay_engine import load_match_stream_items

    team = PRESET_TEAMS[team_key]
    session = FanSession(session_id=f"pregen-{team_key}", fan_team=team, ai_api_key=api_key)
    all_items = load_match_stream_items(session.match_id)

    total_km = 0
    real_ai = 0
    fallback = 0
    all_km_explanations = []

    t0 = time.perf_counter()
    for item in all_items:
        if item.item_type != "delivery" or item.delivery is None:
            continue
        ev_dict = item.delivery.model_dump()
        _total, _delta, _rank, km_result = session.process_one_delivery(ev_dict)

        if km_result and km_result.facts_packet:
            total_km += 1
            explanation = get_explanation_sync(km_result.facts_packet, api_key)
            if explanation.is_fallback:
                fallback += 1
            else:
                real_ai += 1
            km_result.explanation = explanation

            all_km_explanations.append({
                "ball": ev_dict.get("ball_display"),
                "innings": ev_dict.get("innings"),
                "event_id": ev_dict.get("event_id"),
                "is_hattrick": km_result.facts_packet.is_hattrick,
                "reasons": km_result.reasons,
                "explanation_en": explanation.explanation_en,
                "explanation_hi": explanation.explanation_hi,
                "watch_next_en": explanation.watch_next_en,
                "watch_next_hi": explanation.watch_next_hi,
                "is_fallback": explanation.is_fallback,
            })

    elapsed = round(time.perf_counter() - t0, 2)
    summary = session.get_final_summary()

    # Pick 6 representative sample explanations for display:
    # 2 early/mid moments, 2 hat-trick moments, 2 final over moments
    early_moments = [x for x in all_km_explanations if not x["is_hattrick"] and not (x["ball"] and x["ball"].startswith("19."))]
    hattrick_moments = [x for x in all_km_explanations if x["is_hattrick"]]
    final_over_moments = [x for x in all_km_explanations if x["ball"] and x["ball"].startswith("19.")]

    samples = []
    if early_moments:
        samples.extend(early_moments[:2])
    if hattrick_moments:
        samples.extend(hattrick_moments[:2])
    else:
        samples.extend(early_moments[2:4])
    if final_over_moments:
        samples.extend(final_over_moments[:2])
    elif len(early_moments) > 4:
        samples.extend(early_moments[4:6])

    report[team_key] = {
        "team_name": team.name,
        "captain": team.captain,
        "vice_captain": team.vice_captain,
        "total_key_moments": total_km,
        "real_ai_calls": real_ai,
        "fallback_calls": fallback,
        "final_points": summary.final_points,
        "final_rank": summary.final_simulated_rank,
        "elapsed_seconds": elapsed,
        "sample_explanations": samples,
    }
    return report


def main():
    args = parse_args()
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[WARN] GEMINI_API_KEY not set — all explanations will use deterministic fallback templates.")
    else:
        print(f"[INFO] Using Gemini API key: {api_key[:6]}...{api_key[-4:]}")

    team_keys = [args.team] if args.team else ["safe_pick", "differential", "finisher_fan"]
    report = {}

    for tk in team_keys:
        print(f"\n[INFO] Processing team: {tk} ...")
        run_team(tk, api_key, report)
        r = report[tk]
        print(f"  Key moments: {r['total_key_moments']}")
        print(f"  Real AI: {r['real_ai_calls']}  Fallback: {r['fallback_calls']}")
        print(f"  Final points: {r['final_points']}  Rank: {r['final_rank']}")
        print(f"  Time: {r['elapsed_seconds']}s")

    print("\n" + "="*70)
    print("PRE-GENERATION REPORT")
    print("="*70)
    for tk, r in report.items():
        print(f"\nTeam: {r['team_name']} ({tk})")
        print(f"  C={r['captain']}, VC={r['vice_captain']}")
        print(f"  Key moments: {r['total_key_moments']}  (target 25-45)")
        print(f"  Real Gemini: {r['real_ai_calls']}  Fallback: {r['fallback_calls']}")
        print(f"  Final: {r['final_points']} pts, rank {r['final_rank']}/10000")
        print(f"  Runtime: {r['elapsed_seconds']}s")

    # Show sample explanations from "differential" team
    if "differential" in report:
        diff_report = report["differential"]
        print(f"\n{'='*70}")
        print("SAMPLE EXPLANATIONS — Differential Team (Rashid Khan C)")
        print("="*70)
        for i, ex in enumerate(diff_report["sample_explanations"][:6], 1):
            ht_tag = " [HAT-TRICK]" if ex["is_hattrick"] else ""
            print(f"\n  [{i}] Ball {ex['ball']}{ht_tag} | Reasons: {', '.join(ex['reasons'][:2])}")
            print(f"      EN: {ex['explanation_en']}")
            print(f"      HI: {ex['explanation_hi']}")
            print(f"      Watch(EN): {ex['watch_next_en']}")
            print(f"      Watch(HI): {ex['watch_next_hi']}")
            print(f"      Fallback: {ex['is_fallback']}")

    # Save report
    out_path = PROJECT_ROOT / "data" / "ai_cache" / "pregen_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[INFO] Full report saved to {out_path}")


if __name__ == "__main__":
    main()
