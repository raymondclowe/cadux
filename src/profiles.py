"""Multi-profile system for Cadux.

Each profile stores a connection config (API URL + secret key)
plus a last-used session ID. Profiles are persisted in
``page.client_storage`` so they survive app restarts.

Usage::

    from src.profiles import load_profiles, get_active_profile, create_profile

    profiles = load_profiles(page)
    profile = get_active_profile(page)  # returns Profile or None
    if not profile:
        profile = create_profile(page, "Home", url, key)
"""

import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)

_STORAGE_KEY_PROFILES = "cadux_profiles"
_STORAGE_KEY_ACTIVE = "cadux_active_profile_id"


@dataclass
class Profile:
    id: str
    name: str
    api_url: str
    secret_key: str
    active_session_id: Optional[str] = None


# ── Load / Save ──────────────────────────────────────────────────────


def load_profiles(page) -> list[Profile]:
    """Load all profiles from page.client_storage."""
    try:
        raw = page.client_storage.get(_STORAGE_KEY_PROFILES)
    except AttributeError:
        raw = None
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []
    return [Profile(**p) for p in data]


def save_profiles(page, profiles: list[Profile]):
    """Persist all profiles to page.client_storage."""
    raw = json.dumps([asdict(p) for p in profiles])
    try:
        page.client_storage.set(_STORAGE_KEY_PROFILES, raw)
    except AttributeError:
        logger.warning("Cannot persist profiles (no client_storage)")


# ── Active Profile ───────────────────────────────────────────────────


def get_active_profile_id(page) -> str | None:
    try:
        return page.client_storage.get(_STORAGE_KEY_ACTIVE)
    except AttributeError:
        return None


def set_active_profile_id(page, pid: str | None):
    try:
        page.client_storage.set(_STORAGE_KEY_ACTIVE, pid)
    except AttributeError:
        pass


def get_active_profile(page) -> Profile | None:
    pid = get_active_profile_id(page)
    if not pid:
        return None
    for p in load_profiles(page):
        if p.id == pid:
            return p
    return None


# ── CRUD ─────────────────────────────────────────────────────────────


def create_profile(page, name: str, api_url: str, secret_key: str) -> Profile:
    """Create a new profile, save it, and return it."""
    profiles = load_profiles(page)
    pid = _slugify(name)
    existing_ids = {p.id for p in profiles}
    if pid in existing_ids:
        suffix = 2
        while f"{pid}-{suffix}" in existing_ids:
            suffix += 1
        pid = f"{pid}-{suffix}"
    profile = Profile(id=pid, name=name, api_url=api_url, secret_key=secret_key)
    profiles.append(profile)
    save_profiles(page, profiles)
    return profile


def delete_profile(page, pid: str) -> bool:
    """Delete a profile by ID. Returns True if deleted."""
    profiles = load_profiles(page)
    before = len(profiles)
    profiles = [p for p in profiles if p.id != pid]
    if len(profiles) == before:
        return False
    save_profiles(page, profiles)
    # Clear active if it was the deleted one
    if get_active_profile_id(page) == pid:
        set_active_profile_id(page, None)
    return True


def update_profile(page, profile: Profile):
    """Update an existing profile in place."""
    profiles = load_profiles(page)
    for i, p in enumerate(profiles):
        if p.id == profile.id:
            profiles[i] = profile
            save_profiles(page, profiles)
            return True
    return False


def rename_profile(page, pid: str, new_name: str) -> bool:
    profiles = load_profiles(page)
    for p in profiles:
        if p.id == pid:
            p.name = new_name
            save_profiles(page, profiles)
            return True
    return False


# ── Helpers ──────────────────────────────────────────────────────────


def _slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "-").replace("_", "-")
