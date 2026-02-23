"""
Course Profile System

Extracts course data from screenshots using AI vision (OpenAI or Anthropic),
stores it as a JSON profile, and feeds it into the model.

Usage:
    # From screenshots:
    python course.py --screenshots data/course_images/ --course "Pebble Beach"

    # Saves to data/courses/pebble_beach.json for reuse next year

Course profiles store:
    - Course facts (par, yardage, type, scoring conditions, etc.)
    - Skill difficulty ratings (SG:OTT, SG:APP, SG:ARG, SG:Putting)
    - Stat comparisons (tour avg vs course-specific with relative differences)
    - Correlated courses

Provider priority: OpenAI (if OPENAI_API_KEY set) > Anthropic (if ANTHROPIC_API_KEY set)
"""

import os
import json
import base64
import glob
from typing import Optional

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

COURSES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "courses")
CORRELATED_COURSES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "correlated_courses.json"
)


def load_correlated_courses() -> dict:
    """Load the correlated courses database."""
    if os.path.exists(CORRELATED_COURSES_PATH):
        with open(CORRELATED_COURSES_PATH) as f:
            return json.load(f)
    return {}


def _normalize_course_key(course_name: str) -> str:
    """Convert course name to lookup key."""
    return (
        course_name.lower()
        .replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("'", "")
        .replace("-", "_")
        .replace("__", "_")
        .strip("_")
    )


def get_course_characteristics(course_name: str) -> dict | None:
    """Get characteristics and correlated courses for a course."""
    courses = load_correlated_courses()
    if not courses:
        return None

    key = _normalize_course_key(course_name)

    # Try exact match first
    if key in courses:
        return courses[key]

    # Try partial match
    for k, v in courses.items():
        if k == "_meta":
            continue
        display = v.get("display_name", "").lower()
        if key in _normalize_course_key(display) or _normalize_course_key(display) in key:
            return v

    return None


EXTRACTION_PROMPT = """You are extracting golf course data from a Betsperts Golf screenshot. 
Extract ALL information visible in the image into a structured JSON format.

Return ONLY valid JSON (no markdown, no explanation). Use this structure, filling in whatever fields are visible:

{
    "course_facts": {
        "tournament": "",
        "course_name": "",
        "par": null,
        "yardage": null,
        "length_category": "",
        "location": "",
        "course_type": "",
        "architect": "",
        "avg_scoring_conditions": "",
        "bunkers": null,
        "water_danger_holes": null,
        "elevation": "",
        "greens_surface": "",
        "greens_speed": "",
        "stimpmeter": null,
        "avg_greens_size": "",
        "fairway_grass": "",
        "rough_grass": "",
        "rough_length": "",
        "ott_club_type": "",
        "fairway_width": null,
        "correlated_courses": []
    },
    "skill_ratings": {
        "sg_ott": "",
        "sg_app": "",
        "sg_arg": "",
        "sg_putting": "",
        "sg_putting_under_15ft": "",
        "sg_putting_over_15ft": "",
        "fairway_accuracy": "",
        "missed_fairway_penalty": "",
        "rough_penalty": "",
        "gir_accuracy": "",
        "scrambling_rough": "",
        "scrambling_short_grass": "",
        "sand_saves": "",
        "three_putt_avoidance": "",
        "par3_scoring": "",
        "par4_scoring": "",
        "par5_scoring": ""
    },
    "stat_comparisons": [
        {
            "category": "",
            "statistic": "",
            "tour_average": null,
            "course_value": null,
            "relative_difference_pct": null
        }
    ]
}

For skill_ratings, use the exact text from the image (e.g. "Very Difficult", "Easy", "Average", "Difficult").
For stat_comparisons, extract every row of any comparison table you see.
If a field is not visible in the image, omit it or set to null.
"""


def _get_vision_provider() -> str:
    """Determine which vision API to use. OpenAI preferred (structured output)."""
    if HAS_OPENAI and os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if HAS_ANTHROPIC and os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "none"


def extract_from_image(image_path: str, api_key: str = None) -> dict:
    """
    Extract course data from a single screenshot using AI vision.

    Uses OpenAI (if OPENAI_API_KEY set) or Anthropic (if ANTHROPIC_API_KEY set).
    The api_key parameter is kept for backward compatibility but the function
    will auto-detect the provider from environment variables.
    """
    # Read and encode image
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    ext = os.path.splitext(image_path)[1].lower()
    media_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                   ".gif": "image/gif", ".webp": "image/webp"}
    media_type = media_types.get(ext, "image/png")

    provider = _get_vision_provider()

    # Override: if api_key looks like an Anthropic key and no OpenAI key is set
    if api_key and not os.environ.get("OPENAI_API_KEY"):
        provider = "anthropic"

    if provider == "openai":
        response_text = _extract_with_openai(image_data, media_type)
    elif provider == "anthropic":
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        response_text = _extract_with_anthropic(image_data, media_type, key)
    else:
        raise RuntimeError(
            "No vision API available. Set OPENAI_API_KEY or ANTHROPIC_API_KEY. "
            "Install: pip install openai  (or: pip install anthropic)"
        )

    # Clean up markdown code blocks
    if response_text.startswith("```"):
        response_text = response_text.split("\n", 1)[1]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        print(f"  Warning: Could not parse JSON from AI response for {image_path}")
        print(f"  Raw response: {response_text[:200]}...")
        return {"raw_text": response_text}


def _extract_with_openai(image_data: str, media_type: str) -> str:
    """Extract course data using OpenAI GPT-4o vision."""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    response = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{image_data}",
                    },
                },
                {
                    "type": "text",
                    "text": EXTRACTION_PROMPT,
                },
            ],
        }],
        max_tokens=4096,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content.strip()


def _extract_with_anthropic(image_data: str, media_type: str, api_key: str) -> str:
    """Extract course data using Anthropic Claude vision."""
    if not HAS_ANTHROPIC:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    },
                },
                {
                    "type": "text",
                    "text": EXTRACTION_PROMPT,
                },
            ],
        }],
    )
    return message.content[0].text.strip()


def extract_from_folder(folder_path: str, api_key: str) -> dict:
    """Extract and merge course data from all images in a folder."""
    image_files = []
    for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
        image_files.extend(glob.glob(os.path.join(folder_path, ext)))

    if not image_files:
        print(f"No image files found in {folder_path}")
        return {}

    print(f"Processing {len(image_files)} screenshots...")

    merged = {
        "course_facts": {},
        "skill_ratings": {},
        "stat_comparisons": [],
    }

    for img_path in sorted(image_files):
        fname = os.path.basename(img_path)
        print(f"  Reading: {fname}...")
        try:
            data = extract_from_image(img_path, api_key)

            # Merge course_facts (non-empty values override)
            for key, val in data.get("course_facts", {}).items():
                if val is not None and val != "" and val != []:
                    merged["course_facts"][key] = val

            # Merge skill_ratings
            for key, val in data.get("skill_ratings", {}).items():
                if val is not None and val != "":
                    merged["skill_ratings"][key] = val

            # Append stat comparisons (dedup by statistic name)
            existing_stats = {s["statistic"] for s in merged["stat_comparisons"]}
            for comp in data.get("stat_comparisons", []):
                if comp.get("statistic") and comp["statistic"] not in existing_stats:
                    merged["stat_comparisons"].append(comp)
                    existing_stats.add(comp["statistic"])

            print(f"    ✓ Extracted: {len(data.get('course_facts', {}))} facts, "
                  f"{len(data.get('skill_ratings', {}))} ratings, "
                  f"{len(data.get('stat_comparisons', []))} stats")

        except Exception as e:
            print(f"    ✗ Error: {e}")

    return merged


def save_course_profile(course_name: str, data: dict) -> str:
    """Save course profile to JSON file for reuse."""
    os.makedirs(COURSES_DIR, exist_ok=True)
    safe_name = course_name.lower().replace(" ", "_").replace("'", "")
    filepath = os.path.join(COURSES_DIR, f"{safe_name}.json")

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    return filepath


def load_course_profile(course_name: str) -> Optional[dict]:
    """Load a saved course profile."""
    safe_name = course_name.lower().replace(" ", "_").replace("'", "")
    filepath = os.path.join(COURSES_DIR, f"{safe_name}.json")

    if os.path.exists(filepath):
        with open(filepath) as f:
            return json.load(f)
    return None


def list_saved_courses() -> list[str]:
    """List all saved course profiles."""
    if not os.path.isdir(COURSES_DIR):
        return []
    return [
        f.replace(".json", "").replace("_", " ").title()
        for f in os.listdir(COURSES_DIR)
        if f.endswith(".json")
    ]


def generate_profile_from_decompositions(decomp_data: dict) -> dict | None:
    """
    Auto-generate a basic course profile from DG player decomposition data.

    The spread (max - min) of each fit adjustment tells us how much that
    skill differentiates players at this course. Larger spread = harder/
    more important skill. This lets us create a profile without screenshots.

    Used as a fallback when no manual course profile exists.
    """
    players = decomp_data.get("players", [])
    if not players or len(players) < 20:
        return None

    course_name = decomp_data.get("course_name", "Unknown")
    event_name = decomp_data.get("event_name", "Unknown")

    # Compute the spread (impact) of each fit component
    def _spread(field):
        vals = [p.get(field) for p in players if p.get(field) is not None]
        if len(vals) < 10:
            return 0.0
        return max(vals) - min(vals)

    sg_cat_spread = _spread("strokes_gained_category_adjustment")
    drive_dist_spread = _spread("driving_distance_adjustment")
    drive_acc_spread = _spread("driving_accuracy_adjustment")
    approach_spread = _spread("cf_approach_comp")
    short_spread = _spread("cf_short_comp")
    total_fit_spread = _spread("total_fit_adjustment")

    # Convert spreads to difficulty ratings
    # Calibrated from typical PGA Tour ranges:
    # OTT (driving): combine distance + accuracy spread
    ott_impact = drive_dist_spread + drive_acc_spread
    # APP (approach): approach comp + part of SG category
    app_impact = approach_spread + sg_cat_spread * 0.4
    # ARG (around green): short comp
    arg_impact = short_spread
    # Putting: remainder of SG category adjustment
    putt_impact = sg_cat_spread * 0.3

    def _impact_to_rating(impact, thresholds):
        """Convert impact score to difficulty rating."""
        if impact >= thresholds[0]:
            return "Very Difficult"
        elif impact >= thresholds[1]:
            return "Difficult"
        elif impact >= thresholds[2]:
            return "Average"
        elif impact >= thresholds[3]:
            return "Easy"
        else:
            return "Very Easy"

    # Thresholds calibrated from typical PGA Tour decomposition ranges
    skill_ratings = {
        "sg_ott": _impact_to_rating(ott_impact, [0.15, 0.10, 0.06, 0.03]),
        "sg_app": _impact_to_rating(app_impact, [0.25, 0.15, 0.08, 0.04]),
        "sg_arg": _impact_to_rating(arg_impact, [0.10, 0.06, 0.03, 0.015]),
        "sg_putting": _impact_to_rating(putt_impact, [0.20, 0.12, 0.06, 0.03]),
    }

    # Get correlated courses from database
    course_chars = get_course_characteristics(course_name)
    correlated_courses = []
    characteristics = {}
    if course_chars:
        correlated_courses = course_chars.get("correlated", [])
        characteristics = course_chars.get("characteristics", {})

    profile = {
        "course_facts": {
            "tournament": event_name,
            "course_name": course_name,
            "source": "auto_generated_from_dg_decompositions",
            "correlated_courses": correlated_courses,
        },
        "skill_ratings": skill_ratings,
        "fit_spreads": {
            "ott_impact": round(ott_impact, 4),
            "app_impact": round(app_impact, 4),
            "arg_impact": round(arg_impact, 4),
            "putt_impact": round(putt_impact, 4),
            "total_fit_spread": round(total_fit_spread, 4),
            "sg_category_spread": round(sg_cat_spread, 4),
        },
        "characteristics": characteristics,
    }

    # Auto-save the profile
    save_course_profile(course_name, profile)

    return profile


def course_to_model_weights(profile: dict) -> dict:
    """
    Convert course profile skill ratings into model weight adjustments.

    If a course says SG:APP is "Very Difficult", that means approach play
    matters MORE at this course → increase the weight on approach.

    Returns adjustments to apply on top of base weights.
    """
    ratings = profile.get("skill_ratings", {})

    # Map difficulty text to a weight multiplier
    # "Very Difficult" = this skill separates players a LOT → high weight
    # "Easy" = everyone does about the same → low weight
    difficulty_map = {
        "very difficult": 1.5,
        "difficult": 1.25,
        "average": 1.0,
        "easy": 0.75,
        "very easy": 0.6,
    }

    def _rating_to_mult(rating_text: str) -> float:
        if not rating_text:
            return 1.0
        return difficulty_map.get(rating_text.lower().strip(), 1.0)

    adjustments = {
        "course_sg_ott_mult": _rating_to_mult(ratings.get("sg_ott", "")),
        "course_sg_app_mult": _rating_to_mult(ratings.get("sg_app", "")),
        "course_sg_arg_mult": _rating_to_mult(ratings.get("sg_arg", "")),
        "course_sg_putt_mult": _rating_to_mult(ratings.get("sg_putting", "")),
    }

    # Also extract key numeric facts for the model
    facts = profile.get("course_facts", {})
    stats = profile.get("stat_comparisons", [])

    # Build a stat lookup
    stat_lookup = {}
    for s in stats:
        if s.get("statistic") and s.get("relative_difference_pct") is not None:
            stat_lookup[s["statistic"].lower()] = s["relative_difference_pct"]

    adjustments["course_profile"] = {
        "par": facts.get("par"),
        "yardage": facts.get("yardage"),
        "scoring_conditions": facts.get("avg_scoring_conditions", ""),
        "greens_speed": facts.get("greens_speed", ""),
        "correlated_courses": facts.get("correlated_courses", []),
        "stat_differences": stat_lookup,
    }

    return adjustments
