"""
Course Profile System

Extracts course data from Betsperts screenshots using Claude Vision,
stores it as a JSON profile, and feeds it into the model.

Usage:
    # From screenshots:
    python course.py --screenshots data/course_images/ --course "Pebble Beach" --tournament "AT&T Pebble Beach 2026"

    # Saves to data/courses/pebble_beach.json for reuse next year

Course profiles store:
    - Course facts (par, yardage, type, scoring conditions, etc.)
    - Skill difficulty ratings (SG:OTT, SG:APP, SG:ARG, SG:Putting)
    - Stat comparisons (tour avg vs course-specific with relative differences)
    - Correlated courses
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

COURSES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "courses")


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


def extract_from_image(image_path: str, api_key: str) -> dict:
    """Extract course data from a single screenshot using Claude Vision."""
    if not HAS_ANTHROPIC:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    # Read and encode image
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    # Determine media type
    ext = os.path.splitext(image_path)[1].lower()
    media_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                   ".gif": "image/gif", ".webp": "image/webp"}
    media_type = media_types.get(ext, "image/png")

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

    # Parse response
    response_text = message.content[0].text.strip()
    # Clean up if wrapped in markdown code blocks
    if response_text.startswith("```"):
        response_text = response_text.split("\n", 1)[1]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        print(f"  Warning: Could not parse JSON from Claude response for {image_path}")
        print(f"  Raw response: {response_text[:200]}...")
        return {"raw_text": response_text}


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
