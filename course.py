#!/usr/bin/env python3
"""
Course Profile Tool — Extract course data from Betsperts screenshots.

Usage:
    # Extract from screenshots and save profile:
    python3 course.py --screenshots data/course_images/ --course "Pebble Beach"

    # List saved courses:
    python3 course.py --list

    # View a saved profile:
    python3 course.py --view "Pebble Beach"

Before running, set your Anthropic API key:
    export ANTHROPIC_API_KEY=your_key_here
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.course_profile import (
    extract_from_folder,
    save_course_profile,
    load_course_profile,
    list_saved_courses,
    course_to_model_weights,
)


def main():
    parser = argparse.ArgumentParser(description="Course Profile Tool")
    parser.add_argument("--screenshots", "-s", help="Folder with course screenshots")
    parser.add_argument("--course", "-c", help="Course name (e.g. 'Pebble Beach')")
    parser.add_argument("--list", "-l", action="store_true", help="List saved course profiles")
    parser.add_argument("--view", "-v", help="View a saved course profile")
    args = parser.parse_args()

    if args.list:
        courses = list_saved_courses()
        if courses:
            print("\nSaved course profiles:")
            for c in courses:
                print(f"  • {c}")
        else:
            print("\nNo saved courses yet. Run with --screenshots to create one.")
        return

    if args.view:
        profile = load_course_profile(args.view)
        if profile:
            print(f"\n{'='*60}")
            print(f"  Course Profile: {args.view}")
            print(f"{'='*60}")
            print(json.dumps(profile, indent=2))

            # Show model weight adjustments
            adjustments = course_to_model_weights(profile)
            print(f"\n  Model Weight Multipliers:")
            for k, v in adjustments.items():
                if k != "course_profile" and v != 1.0:
                    print(f"    {k}: {v}x")
        else:
            print(f"No profile found for '{args.view}'")
        return

    if args.screenshots and args.course:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("\nERROR: Set your Anthropic API key first:")
            print("  export ANTHROPIC_API_KEY=your_key_here")
            print("\nGet a key at: https://console.anthropic.com/settings/keys")
            sys.exit(1)

        if not os.path.isdir(args.screenshots):
            print(f"\nERROR: Folder not found: {args.screenshots}")
            print(f"Create the folder and put your course screenshots in it.")
            sys.exit(1)

        print(f"\n{'='*60}")
        print(f"  Extracting Course Data: {args.course}")
        print(f"  From: {args.screenshots}")
        print(f"{'='*60}")

        data = extract_from_folder(args.screenshots, api_key)

        if not data or (not data.get("course_facts") and not data.get("skill_ratings")):
            print("\nNo data extracted. Check your screenshots.")
            sys.exit(1)

        # Save profile
        filepath = save_course_profile(args.course, data)
        print(f"\n  ✓ Profile saved to: {filepath}")

        # Show summary
        facts = data.get("course_facts", {})
        ratings = data.get("skill_ratings", {})
        stats = data.get("stat_comparisons", [])

        print(f"\n  Summary:")
        if facts.get("par"):
            print(f"    Par {facts['par']}, {facts.get('yardage', '?')} yards")
        if facts.get("avg_scoring_conditions"):
            print(f"    Scoring: {facts['avg_scoring_conditions']}")
        if facts.get("greens_surface"):
            print(f"    Greens: {facts['greens_surface']}, {facts.get('greens_speed', '?')}")

        print(f"\n  Skill Difficulty Ratings:")
        for key in ["sg_ott", "sg_app", "sg_arg", "sg_putting"]:
            if key in ratings:
                label = key.replace("sg_", "SG:").upper().replace("SG:OTT", "SG:OTT").replace("SG:APP", "SG:APP")
                print(f"    {label}: {ratings[key]}")

        if stats:
            print(f"\n  Stat Comparisons: {len(stats)} stats extracted")

        # Show weight adjustments
        adjustments = course_to_model_weights(data)
        print(f"\n  Model Weight Multipliers (applied during analysis):")
        for k, v in adjustments.items():
            if k != "course_profile":
                mult_text = f"{v}x" if v != 1.0 else "1.0x (no change)"
                print(f"    {k}: {mult_text}")

        print(f"\n  This profile will be used automatically when you run analyze.py")
        print(f"  for any tournament at {args.course}.")
        print(f"{'='*60}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
