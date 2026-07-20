"""Speed profiles: trade warmth and cached state for speed, never anonymity.

Every profile keeps the exact same Tor quality: 3-hop circuits, stock
browser fingerprint, and the same hard quality gates. The only thing a
profile may change is what torfast keeps resident or cached *locally*
between runs:

- ``turbo``     keeps the managed Tor service, the runtime helper, and the
                shared directory seed warm, and makes ``launch`` behave like
                ``open`` so every start reuses the warm service.
- ``balanced``  is the shipped default behavior, unchanged.
- ``paranoid``  keeps nothing resident and nothing cached: every open is a
                cold one-shot launch on a fresh state root with no shared
                seeds and no runtime helper.

Selection order: an explicit ``--profile`` flag wins, then the
``TORFAST_PROFILE`` environment variable, then the saved config file, then
``balanced``.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import time
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_CONFIG_PATH = REPO_ROOT / "tmp" / "torfast-profile.json"
PROFILE_ENV = "TORFAST_PROFILE"
DEFAULT_PROFILE_NAME = "balanced"
RUNTIME_HELPER_DISABLED_ENV = "TORFAST_DISABLE_RUNTIME_HELPER"
WARM_RUNTIME_HELPER_PRESTART_ENABLED_ENV = (
    "TORFAST_ENABLE_WARM_RUNTIME_HELPER_PRESTART"
)


@dataclass(frozen=True)
class SpeedProfile:
    name: str
    symbol: str
    tagline: str
    open_estimate: str
    managed_reuse_on_open: bool
    keep_tor_warm_after_launch: bool
    dir_cache_seed: bool
    runtime_helper: bool
    fresh_state_root_per_open: bool
    allow_warm: bool


PROFILES: dict[str, SpeedProfile] = {
    "turbo": SpeedProfile(
        name="turbo",
        symbol="⚡",
        tagline="keep Tor warm, seeds on, helper resident; launch acts like open",
        open_estimate="≈1s repeated open",
        managed_reuse_on_open=True,
        keep_tor_warm_after_launch=True,
        dir_cache_seed=True,
        runtime_helper=True,
        fresh_state_root_per_open=False,
        allow_warm=True,
    ),
    "balanced": SpeedProfile(
        name="balanced",
        symbol="●",
        tagline="warm managed opens, cold one-shot launches (shipped default)",
        open_estimate="≈1s warm / ≈4s cold",
        managed_reuse_on_open=True,
        keep_tor_warm_after_launch=False,
        dir_cache_seed=True,
        runtime_helper=True,
        fresh_state_root_per_open=False,
        allow_warm=True,
    ),
    "paranoid": SpeedProfile(
        name="paranoid",
        symbol="○",
        tagline="nothing resident, nothing cached; every open is a cold one-shot",
        open_estimate="≈10s cold boot",
        managed_reuse_on_open=False,
        keep_tor_warm_after_launch=False,
        dir_cache_seed=False,
        runtime_helper=False,
        fresh_state_root_per_open=True,
        allow_warm=False,
    ),
}
PROFILE_ORDER = ("turbo", "balanced", "paranoid")


class ProfileError(RuntimeError):
    pass


def read_saved_profile_name(config_path: Path | None = None) -> str | None:
    path = config_path if config_path is not None else PROFILE_CONFIG_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    name = payload.get("profile") if isinstance(payload, dict) else None
    return name if isinstance(name, str) and name in PROFILES else None


def save_profile(name: str, config_path: Path | None = None) -> dict[str, object]:
    if name not in PROFILES:
        raise ProfileError(f"unknown profile: {name}")
    path = config_path if config_path is not None else PROFILE_CONFIG_PATH
    payload = {
        "profile": name,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temp_path.replace(path)
    return {"ok": True, "profile": name, "config_path": str(path)}


def active_profile_name(
    explicit: str | None = None,
    config_path: Path | None = None,
) -> str:
    if explicit is not None:
        if explicit not in PROFILES:
            raise ProfileError(f"unknown profile: {explicit}")
        return explicit
    env_value = os.environ.get(PROFILE_ENV)
    if env_value:
        if env_value not in PROFILES:
            raise ProfileError(f"unknown profile in {PROFILE_ENV}: {env_value}")
        return env_value
    saved = read_saved_profile_name(config_path)
    return saved if saved is not None else DEFAULT_PROFILE_NAME


def get_profile(name: str) -> SpeedProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ProfileError(f"unknown profile: {name}") from None


def describe_profiles(config_path: Path | None = None) -> dict[str, object]:
    active = active_profile_name(config_path=config_path)
    return {
        "ok": True,
        "active": active,
        "quality_note": (
            "every profile keeps 3-hop circuits, the stock browser "
            "fingerprint, and the same quality gates; profiles only change "
            "what stays resident or cached locally between runs"
        ),
        "profiles": [
            {
                "name": profile.name,
                "active": profile.name == active,
                "tagline": profile.tagline,
                "open_estimate": profile.open_estimate,
                "managed_reuse_on_open": profile.managed_reuse_on_open,
                "keep_tor_warm_after_launch": profile.keep_tor_warm_after_launch,
                "dir_cache_seed": profile.dir_cache_seed,
                "runtime_helper": profile.runtime_helper,
                "fresh_state_root_per_open": profile.fresh_state_root_per_open,
                "allow_warm": profile.allow_warm,
            }
            for profile in (PROFILES[name] for name in PROFILE_ORDER)
        ],
    }


def apply_profile_to_args(
    args,
    *,
    managed_state_root: str,
    auto_state_root: str,
    fresh_state_root: Callable[[str], Path],
    config_path: Path | None = None,
) -> SpeedProfile:
    """Resolve the active profile and fold it into a runtime args namespace.

    Explicit flags always win: the profile only fills in fields the user
    left at their defaults. Returns the resolved profile; raises
    ProfileError when the command contradicts the profile (warm under
    paranoid).
    """
    profile = get_profile(
        active_profile_name(getattr(args, "profile", None), config_path)
    )
    args.resolved_profile = profile.name

    command = getattr(args, "command", "")
    if command == "warm" and not profile.allow_warm:
        raise ProfileError(
            "the paranoid profile keeps nothing resident, so `torfast warm` "
            "has nothing to warm; switch with `torfast profile balanced` or "
            "pass `--profile balanced` for this run"
        )

    if not profile.dir_cache_seed and not getattr(args, "no_dir_cache_seed", False):
        args.no_dir_cache_seed = True
    if not profile.dir_cache_seed:
        args.no_browser_startup_seed = True

    if (
        profile.fresh_state_root_per_open
        and command in {"start", "open"}
        and getattr(args, "state_root", managed_state_root) == managed_state_root
    ):
        # paranoid opens are cold one-shots: a fresh root per run so no
        # seeded or leftover local state carries across opens.
        args.state_root = str(fresh_state_root(command))
    if (
        profile.keep_tor_warm_after_launch
        and command in {"launch", "plan"}
        and getattr(args, "state_root", auto_state_root) == auto_state_root
    ):
        # turbo launch reuses the stable managed root so the warm service
        # is actually findable on the next start.
        args.state_root = managed_state_root

    args.managed_reuse_on_open = profile.managed_reuse_on_open
    args.keep_tor_warm_after_launch = profile.keep_tor_warm_after_launch

    if not profile.runtime_helper:
        os.environ.setdefault(RUNTIME_HELPER_DISABLED_ENV, "1")
    elif profile.name == "turbo":
        os.environ.setdefault(WARM_RUNTIME_HELPER_PRESTART_ENABLED_ENV, "1")
    return profile
