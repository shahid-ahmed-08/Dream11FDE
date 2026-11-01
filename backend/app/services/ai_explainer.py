"""
AI Explainer Service
Calls Gemini API to generate natural-language explanations for key moments.
Features: disk cache, number validation, timeout fallback, authentic Mumbai Hinglish.
"""
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

import httpx

from backend.app.models.key_moment import AIExplanation, FactsPacket

logger = logging.getLogger(__name__)

# Cache directory
_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "ai_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_km_config():
    p = Path(__file__).resolve().parent.parent / "config" / "key_moments.json"
    with open(p) as f:
        return json.load(f)


def _cache_path(packet_hash: str) -> Path:
    return _CACHE_DIR / f"{packet_hash}.json"


def _load_from_cache(packet_hash: str) -> Optional[AIExplanation]:
    fp = _cache_path(packet_hash)
    if fp.exists():
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            return AIExplanation(**data)
        except Exception as e:
            logger.warning(f"Cache read error for {packet_hash}: {e}")
    return None


def _save_to_cache(packet_hash: str, explanation: AIExplanation):
    fp = _cache_path(packet_hash)
    try:
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(explanation.model_dump(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Cache write error for {packet_hash}: {e}")


def _extract_numbers_from_packet(facts: FactsPacket) -> set:
    """Extract all numeric values that appear in the facts packet so we can validate AI response."""
    numbers = set()

    def collect(obj):
        if isinstance(obj, (int, float)) and not isinstance(obj, bool):
            numbers.add(round(float(obj), 1))
            numbers.add(int(obj))
            numbers.add(abs(round(float(obj), 1)))
            numbers.add(abs(int(obj)))
        elif isinstance(obj, dict):
            for v in obj.values():
                collect(v)
        elif isinstance(obj, list):
            for v in obj:
                collect(v)

    collect(facts.model_dump())

    # Also parse numbers from text fields (event_description, match_situation, thresholds)
    all_text = f"{facts.event_description} {facts.match_situation} {' '.join(facts.upcoming_thresholds)}"
    for token in re.findall(r"-?\d+(?:\.\d+)?", all_text):
        try:
            val = float(token)
            numbers.add(round(val, 1))
            numbers.add(int(val))
            numbers.add(abs(round(val, 1)))
            numbers.add(abs(int(val)))
        except ValueError:
            pass

    return numbers


def _validate_response_numbers(text: str, allowed_numbers: set) -> bool:
    """
    Check that numbers appearing in the AI text are drawn from the facts packet.
    Allows small integers (0-10), multipliers, common match constants as free pass.
    Returns True if valid.
    """
    found = re.findall(r"-?\d+(?:\.\d+)?", text)
    # Free pass numbers: small integers 0-10, standard multipliers, match year, sample pool size
    free_pass = set(range(0, 11)) | {1.5, 2.0, 2.5, 2023, 2024, 2022, 10000}
    for n_str in found:
        try:
            n = float(n_str)
        except ValueError:
            continue
        if n in free_pass or int(n) in free_pass:
            continue
        rounded = round(n, 1)
        int_n = int(n)
        abs_rounded = abs(rounded)
        abs_int = abs(int_n)
        if (
            rounded not in allowed_numbers
            and int_n not in allowed_numbers
            and n not in allowed_numbers
            and abs_rounded not in allowed_numbers
            and abs_int not in allowed_numbers
        ):
            logger.warning(f"Number {n} in AI response not found in facts packet (allowed: {sorted(allowed_numbers)})")
            return False
    return True


def _build_prompt(facts: FactsPacket) -> str:
    affected_lines = []
    for ap in facts.affected_fan_players:
        tag = " [CAPTAIN 2.0x]" if ap.is_captain else (" [VICE-CAPTAIN 1.5x]" if ap.is_vice_captain else "")
        affected_lines.append(
            f"  - {ap.player_name}{tag}: raw delta={ap.raw_delta:+.1f}, "
            f"weighted delta={ap.weighted_delta:+.1f} (multiplier={ap.multiplier}x), "
            f"player total={ap.current_player_total}"
        )
    affected_str = "\n".join(affected_lines) if affected_lines else "  - None directly"

    thresholds_str = "\n".join(f"  - {t}" for t in facts.upcoming_thresholds) if facts.upcoming_thresholds else "  - Match situation overview"

    rank_context = ""
    if facts.points_rose_but_rank_dropped or (facts.team_delta > 0 and facts.rank_movement < 0):
        rank_context = (
            "CRITICAL NOTE ON RANK DROP: The fan's points went UP by "
            f"{facts.team_delta:+.1f}, but their simulated rank DROPPED by {abs(facts.rank_movement)} "
            f"(from {facts.simulated_rank_before} to {facts.simulated_rank_after}). "
            "You MUST state plainly that other teams in the 10,000 pool gained more points on this ball."
        )

    return f"""You are an expert cricket fantasy commentary assistant commentating on IPL 2023 Match 13 (GT vs KKR) for an Indian fantasy cricket fan.

=== FACTS PACKET (USE ONLY NUMBERS FROM HERE) ===
Ball: {facts.ball_display} (Innings {facts.innings})
Event: {facts.event_description}
Match situation: {facts.match_situation}
Is wicket: {facts.is_wicket} | Is six: {facts.is_six} | Is milestone: {facts.is_milestone} | Is hat-trick: {facts.is_hattrick}
Fan Team total BEFORE: {facts.team_total_before} | AFTER: {facts.team_total_after} | DELTA: {facts.team_delta:+.1f}
Simulated rank BEFORE: {facts.simulated_rank_before} | AFTER: {facts.simulated_rank_after} | MOVEMENT: {facts.rank_movement:+d}
{rank_context}

Affected fan players:
{affected_str}

Upcoming thresholds (active players only):
{thresholds_str}
=== END FACTS PACKET ===

Write a response in EXACTLY this JSON structure (no markdown, no other keys):
{{
  "explanation_en": "<explanation in English>",
  "explanation_hi": "<explanation in authentic spoken Mumbai Hinglish>",
  "watch_next_en": "<1 sentence watch next in English>",
  "watch_next_hi": "<1 sentence watch next in authentic Mumbai Hinglish>"
}}

STRICT CONTENT & STRUCTURE RULES:
1. Both explanations MUST state, in plain words and in this EXACT ORDER:
   (a) What happened in the match on this delivery (batter, bowler, run/wicket outcome).
   (b) Which of the fan's players were affected and by how many points (EXPLICITLY mention the captain or vice-captain multiplier if applied).
   (c) What that did to the fan's total points and simulated rank.
       * If the fan's points went up but their rank dropped, you MUST explicitly state that other competing teams gained more points. Never give a bare "rank dropped" without that reason.
2. The Hinglish version MUST read like natural, lively spoken Mumbai cricket Hinglish (e.g., using natural phrases like 'boss', 'bhai', 'chhakka', 'wicket', 'chadh gayi', 'slip ho gayi', 'rival teams ne aur points bator liye'). It must NOT read like mechanically translated English.
3. Maximum 2 sentences for the explanation fields, 1 sentence for the watch_next fields.
4. Watch-next lines must refer ONLY to the active thresholds or match situation from the facts packet.
5. ABSOLUTE NUMBER RULE: Do NOT invent, calculate, or hallucinate any numbers not present in the facts packet.
"""


def _build_fallback(facts: FactsPacket, error_msg: Optional[str] = None) -> AIExplanation:
    """Deterministic fallback template matching all requirements:
    1. what happened in the match
    2. which of the fan's players it affected and by how many points (mentioning captain/VC multipliers)
    3. what that did to the fan's total and simulated rank (explaining if points rose but rank fell)
    Spoken Mumbai Hinglish for HI version.
    """
    # 1. Match event
    desc = facts.event_description
    if facts.is_hattrick:
        event_en = f"Over {facts.ball_display}: {desc} — a dramatic hat-trick delivery."
        event_hi = f"Over {facts.ball_display}: {desc} — hat-trick ball pe tagda drama hua!"
    elif facts.is_six:
        event_en = f"Over {facts.ball_display}: {desc} — huge six!"
        event_hi = f"Over {facts.ball_display}: {desc} — boundary ke bahar lamba chhakka mara!"
    elif facts.is_wicket:
        event_en = f"Over {facts.ball_display}: {desc}."
        event_hi = f"Over {facts.ball_display}: {desc} — bada wicket gira!"
    else:
        event_en = f"Over {facts.ball_display}: {desc}."
        event_hi = f"Over {facts.ball_display}: {desc}."

    # 2. Player impact & points with multipliers
    if facts.affected_fan_players:
        ap_en_list = []
        ap_hi_list = []
        for ap in facts.affected_fan_players:
            mult_desc_en = f" ({ap.multiplier}x captain multiplier applied)" if ap.is_captain else (f" ({ap.multiplier}x vice-captain multiplier applied)" if ap.is_vice_captain else "")
            mult_desc_hi = f" ({ap.multiplier}x captain multiplier ke sath)" if ap.is_captain else (f" ({ap.multiplier}x vice-captain multiplier ke sath)" if ap.is_vice_captain else "")
            sign = "+" if ap.weighted_delta >= 0 else ""
            ap_en_list.append(f"{ap.player_name} brought {sign}{ap.weighted_delta} points{mult_desc_en}")
            ap_hi_list.append(f"{ap.player_name} ne {sign}{ap.weighted_delta} points dilaye{mult_desc_hi}")
        player_impact_en = "This affected " + ", while ".join(ap_en_list) + "."
        player_impact_hi = "Isse " + " aur ".join(ap_hi_list) + "."
    else:
        player_impact_en = "None of your squad players scored or lost points directly on this ball."
        player_impact_hi = "Aapke squad ke kisi player ke points direct change nahi hue."

    # 3. Total & Simulated Rank movement
    tot = facts.team_total_after
    move = facts.rank_movement
    curr_rank = facts.simulated_rank_after
    delta = facts.team_delta
    sign_delta = "+" if delta >= 0 else ""

    if facts.points_rose_but_rank_dropped or (delta > 0 and move < 0):
        rank_en = (
            f"Your team total rose by {sign_delta}{delta} to {tot} points, but your simulated rank dropped by {abs(move)} "
            f"places to {curr_rank} because competing teams with rival scorers gained more points."
        )
        rank_hi = (
            f"Points toh {sign_delta}{delta} badhke total {tot} ho gaye, lekin simulated rank {abs(move)} spots girke {curr_rank} "
            f"pe khisak gayi kyunki doosri teams ne rival players se aur zyada points kheench liye."
        )
    elif move > 0:
        rank_en = (
            f"Your team total moved by {sign_delta}{delta} to {tot} points, lifting your simulated rank by {move} "
            f"places up to {curr_rank} among 10,000 teams."
        )
        rank_hi = (
            f"Aapka team total {sign_delta}{delta} points ke sath {tot} ho gaya, aur simulated rank seedha {move} "
            f"positions chadhkar 10,000 teams mein {curr_rank} number pe pahunch gayi boss!"
        )
    elif move < 0:
        rank_en = (
            f"Your team total shifted by {sign_delta}{delta} to {tot} points, causing your simulated rank to drop by {abs(move)} "
            f"places to {curr_rank} as rival fantasy combinations gained ground."
        )
        rank_hi = (
            f"Total score {sign_delta}{delta} change hoke {tot} hua, aur rival squads ke aage nikalne se simulated rank {abs(move)} "
            f"spots slip hoke {curr_rank} pe aa gayi."
        )
    else:
        rank_en = f"Your team total reached {tot} points ({sign_delta}{delta}), leaving your simulated rank unchanged at {curr_rank}."
        rank_hi = f"Aapka total {tot} points pe pahuncha ({sign_delta}{delta}) aur simulated rank bina hile {curr_rank} pe freeze rahi."

    en = f"{event_en} {player_impact_en} {rank_en}"
    hi = f"{event_hi} {player_impact_hi} {rank_hi}"

    # Watch next
    if facts.upcoming_thresholds:
        t0 = facts.upcoming_thresholds[0]
        watch_en = f"Watch next: {t0}."
        watch_hi = f"Agli nazar: {t0} pe rakho boss."
    else:
        watch_en = "Watch how the match situation unfolds in the coming overs."
        watch_hi = "Agli overs mein match ka rukh dekhte hain kis taraf palat-ta hai."

    return AIExplanation(
        explanation_en=en,
        explanation_hi=hi,
        watch_next_en=watch_en,
        watch_next_hi=watch_hi,
        is_fallback=True,
        validation_passed=True,
        ai_error=error_msg,
    )


def _call_gemini_api_sync(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    """
    Synchronous HTTP call to Gemini API using httpx.Client with automatic retry on 429 rate limits.
    """
    import time
    with httpx.Client(timeout=timeout) as client:
        for attempt in range(2):
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code == 429 and attempt == 0:
                logger.warning("Gemini 429 rate limit hit, waiting 5s before retry...")
                time.sleep(5.0)
                continue
            resp.raise_for_status()
            return resp.json()


def get_explanation_sync(facts: FactsPacket, api_key: str) -> AIExplanation:
    """
    Synchronous implementation of get_explanation.
    Returns cached result if available.
    Falls back to template if API fails, times out, or validation fails.
    """
    km_config = _load_km_config()
    ai_enabled = km_config.get("ai_enabled", True)
    timeout_sec = km_config.get("ai_timeout_seconds", 5.0)
    model = km_config.get("gemini_model", "gemini-2.5-flash")

    # Check cache first
    cached = _load_from_cache(facts.packet_hash)
    if cached is not None:
        return cached

    # If AI is disabled or no API key, return fallback
    if not ai_enabled or not api_key:
        fallback = _build_fallback(facts)
        return fallback

    prompt = _build_prompt(facts)
    allowed_numbers = _extract_numbers_from_packet(facts)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
            "thinkingConfig": {
                "thinkingBudget": 0
            },
        },
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    try:
        data = _call_gemini_api_sync(url, payload, headers, timeout_sec)

        # Extract text from response
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Parse JSON
        parsed = json.loads(text)
        required_keys = {"explanation_en", "explanation_hi", "watch_next_en", "watch_next_hi"}
        if not required_keys.issubset(parsed.keys()):
            raise ValueError(f"Missing keys in AI response: {required_keys - parsed.keys()}")

        # Validate numbers
        full_text = " ".join(str(v) for v in parsed.values())
        is_valid = _validate_response_numbers(full_text, allowed_numbers)

        explanation = AIExplanation(
            explanation_en=parsed["explanation_en"],
            explanation_hi=parsed["explanation_hi"],
            watch_next_en=parsed["watch_next_en"],
            watch_next_hi=parsed["watch_next_hi"],
            is_fallback=False,
            validation_passed=is_valid,
        )

        if not is_valid:
            err_text = f"Number validation failed: numbers in response not found in facts packet"
            logger.warning(f"AI response failed number validation for {facts.packet_hash}, using fallback")
            fallback = _build_fallback(facts, error_msg=err_text)
            _save_to_cache(facts.packet_hash, fallback)
            return fallback

        _save_to_cache(facts.packet_hash, explanation)
        return explanation

    except Exception as e:
        err_msg = str(e)
        logger.warning(f"AI call failed for {facts.packet_hash}: {err_msg}")
        fallback = _build_fallback(facts, error_msg=err_msg)
        return fallback


async def get_explanation(facts: FactsPacket, api_key: str) -> AIExplanation:
    """Async wrapper using anyio threadpool to prevent socket blocking on Windows."""
    import anyio
    return await anyio.to_thread.run_sync(get_explanation_sync, facts, api_key)
