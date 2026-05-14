from pathlib import Path

from config.paths import (
    RULEBOOK_DB_PATH,
    RULEBOOK_DB_V2_PATH,
    RULEBOOK_V1_OUTPUT_PATH,
    RULEBOOK_V2_OUTPUT_PATH,
)

# Central switch for runtime / comparison work.
# Change this in one place when you want downstream stages to use a different
# rulebook approach during testing.
ACTIVE_RULEBOOK_PROFILE = "v2"

RULEBOOK_PROFILES: dict[str, dict[str, object]] = {
    "v1": {
        "label": "legacy_final_mapping_only",
        "path": RULEBOOK_V1_OUTPUT_PATH,
        "built_output_path": RULEBOOK_V1_OUTPUT_PATH,
        "baseline_db_path": RULEBOOK_DB_PATH,
        "builder_scripts": [
            "pipeline/0_build_rulebook/create_mappings.py",
        ],
        "notes": "Legacy rulebook built from Final_Mapping only and written to output_docs.",
    },
    "v2": {
        "label": "override_priority_conflict_resolved",
        "path": RULEBOOK_V2_OUTPUT_PATH,
        "built_output_path": RULEBOOK_V2_OUTPUT_PATH,
        "baseline_db_path": RULEBOOK_DB_V2_PATH,
        "builder_scripts": [
            "pipeline/0_build_rulebook/extract_mappings_v2.py",
            "pipeline/0_build_rulebook/build_rulebook_v2.py",
        ],
        "notes": "Conflict-resolved rulebook using Auto Mapping, OVERRIDE, and Final_Mapping, written to output_docs.",
    },
}


def get_rulebook_profile(profile_name: str | None = None) -> dict[str, object]:
    name = profile_name or ACTIVE_RULEBOOK_PROFILE
    if name not in RULEBOOK_PROFILES:
        valid = ", ".join(sorted(RULEBOOK_PROFILES))
        raise ValueError(f"Unknown rulebook profile: {name}. Use one of: {valid}")
    return RULEBOOK_PROFILES[name]


def get_rulebook_path(profile_name: str | None = None) -> Path:
    profile = get_rulebook_profile(profile_name)
    return profile["path"]  # type: ignore[return-value]


def get_active_rulebook_path() -> Path:
    return get_rulebook_path(ACTIVE_RULEBOOK_PROFILE)


def get_active_rulebook_name() -> str:
    return ACTIVE_RULEBOOK_PROFILE


def get_rulebook_built_output_path(profile_name: str | None = None) -> Path:
    profile = get_rulebook_profile(profile_name)
    return profile["built_output_path"]  # type: ignore[return-value]
