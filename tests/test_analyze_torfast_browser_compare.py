import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from analyze_torfast_browser_compare import (
    browser_net_log_cache_summary_rows,
    css_discovery_gate_summary_rows,
    phase_summary_rows,
    pre_network_cancel_summary_rows,
    resource_discovery_summary_rows,
    resource_family_delta_rows,
    resource_family_summary_rows,
    resource_variant_swap_rows,
    same_origin_blocker_rows,
    same_origin_blocker_cache_signal_rows,
    same_origin_blocker_family_summary_rows,
    same_origin_blocker_owner_delta_rows,
    same_origin_blocker_owner_rows,
    same_origin_blocker_owner_summary_rows,
    same_origin_blocker_summary_rows,
    resource_delta_rows,
    resource_tail_summary_rows,
    same_origin_pressure_summary_rows,
    top_resource_rows,
)


TARGET = "https://www.torproject.org/download/"


def browser_run(
    *,
    load_ms: float,
    response_start_ms: float,
    dom_content_loaded_ms: float,
    load_event_end_ms: float,
    resources: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "ok": True,
        "load_ms": load_ms,
        "elapsed_ms": load_ms + 200.0,
        "screenshot": {"bytes": 100},
        "performance_timing": {
            "navigation": {
                "responseStart": response_start_ms,
                "domContentLoadedEventEnd": dom_content_loaded_ms,
                "loadEventEnd": load_event_end_ms,
            },
            "resources": resources,
        },
    }


def profile_run(*, run_index: int, boot_seconds: float, browser: dict[str, object]) -> dict[str, object]:
    return {
        "profile": "fixture",
        "run_index": run_index,
        "boot": {"ok": True, "seconds": boot_seconds},
        "benchmarks": {
            TARGET: {
                "summary": {"ok": True},
                "runs": [browser],
            }
        },
    }


def fixture_payload() -> dict[str, object]:
    return {
        "profiles": {
            "bundled_c_tor_browser": {
                "runs": [
                    profile_run(
                        run_index=1,
                        boot_seconds=10.0,
                        browser=browser_run(
                            load_ms=2000.0,
                            response_start_ms=100.0,
                            dom_content_loaded_ms=600.0,
                            load_event_end_ms=2000.0,
                            resources=[
                                {
                                    "name": "styles.css",
                                    "initiatorType": "css",
                                    "duration": 1300.0,
                                    "fetchStart": 50.0,
                                    "requestStart": 100.0,
                                    "responseStart": 200.0,
                                    "responseEnd": 1000.0,
                                },
                                {
                                    "name": "hero.png",
                                    "initiatorType": "img",
                                    "duration": 2300.0,
                                    "fetchStart": 150.0,
                                    "requestStart": 250.0,
                                    "responseStart": 300.0,
                                    "responseEnd": 1800.0,
                                },
                            ],
                        ),
                    ),
                    profile_run(
                        run_index=2,
                        boot_seconds=12.0,
                        browser=browser_run(
                            load_ms=2200.0,
                            response_start_ms=120.0,
                            dom_content_loaded_ms=700.0,
                            load_event_end_ms=2200.0,
                            resources=[
                                {
                                    "name": "styles.css",
                                    "initiatorType": "css",
                                    "duration": 1100.0,
                                    "fetchStart": 60.0,
                                    "requestStart": 120.0,
                                    "responseStart": 220.0,
                                    "responseEnd": 1100.0,
                                },
                                {
                                    "name": "hero.png",
                                    "initiatorType": "img",
                                    "duration": 2100.0,
                                    "fetchStart": 180.0,
                                    "requestStart": 300.0,
                                    "responseStart": 360.0,
                                    "responseEnd": 2000.0,
                                },
                            ],
                        ),
                    ),
                ]
            },
            "bundled_c_tor_browser_seeded": {
                "runs": [
                    profile_run(
                        run_index=1,
                        boot_seconds=2.0,
                        browser=browser_run(
                            load_ms=1600.0,
                            response_start_ms=90.0,
                            dom_content_loaded_ms=500.0,
                            load_event_end_ms=1600.0,
                            resources=[
                                {
                                    "name": "styles.css",
                                    "initiatorType": "css",
                                    "duration": 800.0,
                                    "fetchStart": 40.0,
                                    "requestStart": 80.0,
                                    "responseStart": 160.0,
                                    "responseEnd": 800.0,
                                },
                                {
                                    "name": "hero.png",
                                    "initiatorType": "img",
                                    "duration": 1600.0,
                                    "fetchStart": 120.0,
                                    "requestStart": 200.0,
                                    "responseStart": 260.0,
                                    "responseEnd": 1500.0,
                                },
                            ],
                        ),
                    ),
                    profile_run(
                        run_index=2,
                        boot_seconds=3.0,
                        browser=browser_run(
                            load_ms=1700.0,
                            response_start_ms=95.0,
                            dom_content_loaded_ms=550.0,
                            load_event_end_ms=1700.0,
                            resources=[
                                {
                                    "name": "styles.css",
                                    "initiatorType": "css",
                                    "duration": 700.0,
                                    "fetchStart": 45.0,
                                    "requestStart": 90.0,
                                    "responseStart": 150.0,
                                    "responseEnd": 850.0,
                                },
                                {
                                    "name": "hero.png",
                                    "initiatorType": "img",
                                    "duration": 1500.0,
                                    "fetchStart": 160.0,
                                    "requestStart": 230.0,
                                    "responseStart": 290.0,
                                    "responseEnd": 1600.0,
                                },
                            ],
                        ),
                    ),
                ]
            },
        }
    }


def slot_pressure_payload() -> dict[str, object]:
    blockers = []
    for index in range(6):
        blockers.append(
            {
                "name": f"https://cdn.example.com/blocker-{index}.png",
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": 2000.0,
                "fetchStart": 0.0,
                "requestStart": 0.0,
                "responseStart": 50.0,
                "responseEnd": 2000.0,
            }
        )
    queued = {
        "name": "https://cdn.example.com/queued.png",
        "initiatorType": "img",
        "nextHopProtocol": "http/1.1",
        "duration": 1300.0,
        "fetchStart": 500.0,
        "requestStart": 1600.0,
        "responseStart": 1700.0,
        "responseEnd": 1800.0,
    }
    return {
        "profiles": {
            "bundled_c_tor_browser_seeded": {
                "runs": [
                    profile_run(
                        run_index=1,
                        boot_seconds=2.0,
                        browser=browser_run(
                            load_ms=2000.0,
                            response_start_ms=100.0,
                            dom_content_loaded_ms=600.0,
                            load_event_end_ms=2000.0,
                            resources=[*blockers, queued],
                        ),
                    )
                ]
            }
        }
    }


def blocker_owner_delta_payload() -> dict[str, object]:
    def profile_resources(*, blocker_a_end: float) -> list[dict[str, object]]:
        blockers = [
            {
                "name": "https://cdn.example.com/blocker-a.png",
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": blocker_a_end,
                "fetchStart": 0.0,
                "requestStart": 0.0,
                "responseStart": 80.0,
                "responseEnd": blocker_a_end,
            },
            {
                "name": "https://cdn.example.com/blocker-b.png",
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": 1750.0,
                "fetchStart": 0.0,
                "requestStart": 0.0,
                "responseStart": 100.0,
                "responseEnd": 1750.0,
            },
        ]
        for index, response_end in enumerate((1700.0, 1650.0, 1600.0, 1500.0), start=2):
            blockers.append(
                {
                    "name": f"https://cdn.example.com/blocker-{index}.png",
                    "initiatorType": "img",
                    "nextHopProtocol": "http/1.1",
                    "duration": response_end,
                    "fetchStart": 0.0,
                    "requestStart": 0.0,
                    "responseStart": 100.0,
                    "responseEnd": response_end,
                }
            )
        blockers.extend(
            [
                {
                    "name": "https://cdn.example.com/queued-a.png",
                    "initiatorType": "img",
                    "nextHopProtocol": "http/1.1",
                    "duration": 1200.0,
                    "fetchStart": 200.0,
                    "requestStart": 1200.0,
                    "responseStart": 1250.0,
                    "responseEnd": 1400.0,
                },
                {
                    "name": "https://cdn.example.com/queued-b.png",
                    "initiatorType": "img",
                    "nextHopProtocol": "http/1.1",
                    "duration": 1250.0,
                    "fetchStart": 250.0,
                    "requestStart": 1300.0,
                    "responseStart": 1350.0,
                    "responseEnd": 1450.0,
                },
            ]
        )
        return blockers

    return {
        "profiles": {
            "bundled_c_tor_browser": {
                "runs": [
                    profile_run(
                        run_index=1,
                        boot_seconds=10.0,
                        browser=browser_run(
                            load_ms=2200.0,
                            response_start_ms=100.0,
                            dom_content_loaded_ms=800.0,
                            load_event_end_ms=2200.0,
                            resources=profile_resources(blocker_a_end=1800.0),
                        ),
                    )
                ]
            },
            "bundled_c_tor_browser_seeded": {
                "runs": [
                    profile_run(
                        run_index=1,
                        boot_seconds=2.0,
                        browser=browser_run(
                            load_ms=2100.0,
                            response_start_ms=100.0,
                            dom_content_loaded_ms=800.0,
                            load_event_end_ms=2100.0,
                            resources=profile_resources(blocker_a_end=2300.0),
                        ),
                    )
                ]
            },
        }
    }


def browser_run_with_net_log(
    *,
    load_ms: float,
    response_start_ms: float,
    dom_content_loaded_ms: float,
    load_event_end_ms: float,
    resources: list[dict[str, object]],
    log_files: list[str],
) -> dict[str, object]:
    run = browser_run(
        load_ms=load_ms,
        response_start_ms=response_start_ms,
        dom_content_loaded_ms=dom_content_loaded_ms,
        load_event_end_ms=load_event_end_ms,
        resources=resources,
    )
    run["url"] = TARGET
    run["current_url"] = TARGET
    run["browser_net_log"] = {
        "enabled": True,
        "ok": True,
        "files": log_files,
    }
    return run


def resource_family_payload() -> dict[str, object]:
    return {
        "profiles": {
            "bundled_c_tor_browser": {
                "runs": [
                    profile_run(
                        run_index=1,
                        boot_seconds=10.0,
                        browser=browser_run(
                            load_ms=2200.0,
                            response_start_ms=100.0,
                            dom_content_loaded_ms=800.0,
                            load_event_end_ms=2200.0,
                            resources=[
                                {
                                    "name": "https://www.torproject.org/static/js/download.js?h=4ce9d095",
                                    "initiatorType": "script",
                                    "nextHopProtocol": "http/1.1",
                                    "duration": 600.0,
                                    "fetchStart": 40.0,
                                    "requestStart": 100.0,
                                    "responseStart": 150.0,
                                    "responseEnd": 640.0,
                                    "encodedBodySize": 4096.0,
                                    "transferSize": 4608.0,
                                },
                                {
                                    "name": "https://www.torproject.org/static/images/download/png/get-connected@3x.png?h=5e2656db",
                                    "initiatorType": "img",
                                    "nextHopProtocol": "http/1.1",
                                    "duration": 1200.0,
                                    "fetchStart": 900.0,
                                    "requestStart": 1000.0,
                                    "responseStart": 1100.0,
                                    "responseEnd": 2100.0,
                                    "encodedBodySize": 122880.0,
                                    "transferSize": 123392.0,
                                },
                                {
                                    "name": "https://www.torproject.org/static/fonts/fontawesome/png/white/brands/github.png",
                                    "initiatorType": "css",
                                    "nextHopProtocol": "http/1.1",
                                    "duration": 900.0,
                                    "fetchStart": 1100.0,
                                    "requestStart": 1200.0,
                                    "responseStart": 1300.0,
                                    "responseEnd": 2000.0,
                                    "encodedBodySize": 8192.0,
                                    "transferSize": 8704.0,
                                },
                            ],
                        ),
                    )
                ]
            },
            "bundled_c_tor_browser_seeded": {
                "runs": [
                    profile_run(
                        run_index=1,
                        boot_seconds=2.0,
                        browser=browser_run(
                            load_ms=2000.0,
                            response_start_ms=90.0,
                            dom_content_loaded_ms=700.0,
                            load_event_end_ms=2000.0,
                            resources=[
                                {
                                    "name": "https://www.torproject.org/static/js/download.js?h=4ce9d095",
                                    "initiatorType": "script",
                                    "nextHopProtocol": "http/1.1",
                                    "duration": 550.0,
                                    "fetchStart": 35.0,
                                    "requestStart": 90.0,
                                    "responseStart": 140.0,
                                    "responseEnd": 585.0,
                                    "encodedBodySize": 4096.0,
                                    "transferSize": 4608.0,
                                },
                                {
                                    "name": "https://www.torproject.org/static/images/download/png/get-connected@3x.png?h=5e2656db",
                                    "initiatorType": "img",
                                    "nextHopProtocol": "http/1.1",
                                    "duration": 1200.0,
                                    "fetchStart": 1300.0,
                                    "requestStart": 1400.0,
                                    "responseStart": 1500.0,
                                    "responseEnd": 2600.0,
                                    "encodedBodySize": 122880.0,
                                    "transferSize": 123392.0,
                                },
                                {
                                    "name": "https://www.torproject.org/static/fonts/fontawesome/png/white/brands/github.png",
                                    "initiatorType": "css",
                                    "nextHopProtocol": "http/1.1",
                                    "duration": 700.0,
                                    "fetchStart": 900.0,
                                    "requestStart": 1000.0,
                                    "responseStart": 1080.0,
                                    "responseEnd": 1600.0,
                                    "encodedBodySize": 8192.0,
                                    "transferSize": 8704.0,
                                },
                            ],
                        ),
                    )
                ]
            },
        }
    }


def blocker_family_payload() -> dict[str, object]:
    blockers = [
        {
            "name": "https://www.torproject.org/static/fonts/fontawesome/png/white/brands/github.png",
            "initiatorType": "css",
            "nextHopProtocol": "http/1.1",
            "duration": 2000.0,
            "fetchStart": 0.0,
            "requestStart": 0.0,
            "responseStart": 50.0,
            "responseEnd": 2000.0,
        },
        {
            "name": "https://www.torproject.org/static/fonts/fontawesome/png/white/brands/twitter.png",
            "initiatorType": "css",
            "nextHopProtocol": "http/1.1",
            "duration": 2000.0,
            "fetchStart": 0.0,
            "requestStart": 0.0,
            "responseStart": 50.0,
            "responseEnd": 2000.0,
        },
        {
            "name": "https://www.torproject.org/static/fonts/fontawesome/png/white/brands/linkedin.png",
            "initiatorType": "css",
            "nextHopProtocol": "http/1.1",
            "duration": 2000.0,
            "fetchStart": 0.0,
            "requestStart": 0.0,
            "responseStart": 50.0,
            "responseEnd": 2000.0,
        },
        {
            "name": "https://www.torproject.org/static/images/tor-browser-mobile-window/png/TBA10.0.png?h=727fc609",
            "initiatorType": "img",
            "nextHopProtocol": "http/1.1",
            "duration": 2100.0,
            "fetchStart": 0.0,
            "requestStart": 0.0,
            "responseStart": 60.0,
            "responseEnd": 2100.0,
        },
        {
            "name": "https://www.torproject.org/static/images/tb85/tb85@2x.png",
            "initiatorType": "css",
            "nextHopProtocol": "http/1.1",
            "duration": 2200.0,
            "fetchStart": 0.0,
            "requestStart": 0.0,
            "responseStart": 75.0,
            "responseEnd": 2200.0,
        },
        {
            "name": "https://www.torproject.org/static/fonts/SourceSansPro/SourceSansPro-Bold.ttf",
            "initiatorType": "other",
            "nextHopProtocol": "http/1.1",
            "duration": 2300.0,
            "fetchStart": 0.0,
            "requestStart": 0.0,
            "responseStart": 100.0,
            "responseEnd": 2300.0,
        },
    ]
    queued = [
        {
            "name": "https://www.torproject.org/static/images/download/svg/get-connected.svg?h=5e2656db",
            "initiatorType": "img",
            "nextHopProtocol": "http/1.1",
            "duration": 1300.0,
            "fetchStart": 500.0,
            "requestStart": 1600.0,
            "responseStart": 1700.0,
            "responseEnd": 1800.0,
        },
        {
            "name": "https://www.torproject.org/static/images/download/svg/stay-safe.svg?h=f11bdbfa",
            "initiatorType": "img",
            "nextHopProtocol": "http/1.1",
            "duration": 1300.0,
            "fetchStart": 500.0,
            "requestStart": 1600.0,
            "responseStart": 1700.0,
            "responseEnd": 1800.0,
        },
    ]
    return {
        "profiles": {
            "bundled_c_tor_browser_seeded": {
                "runs": [
                    profile_run(
                        run_index=1,
                        boot_seconds=2.0,
                        browser=browser_run(
                            load_ms=2000.0,
                            response_start_ms=100.0,
                            dom_content_loaded_ms=600.0,
                            load_event_end_ms=2000.0,
                            resources=[*blockers, *queued],
                        ),
                    )
                ]
            }
        }
    }


def resource_discovery_payload() -> dict[str, object]:
    resource_url = (
        "https://www.torproject.org/static/fonts/fontawesome/png/white/brands/github.png"
    )
    product_url = (
        "https://www.torproject.org/static/images/tor-browser-mobile-window/png/TBA10.0.png?h=727fc609"
    )
    browser = browser_run(
        load_ms=2000.0,
        response_start_ms=100.0,
        dom_content_loaded_ms=600.0,
        load_event_end_ms=2000.0,
        resources=[
            {
                "name": resource_url,
                "initiatorType": "css",
                "nextHopProtocol": "http/1.1",
                "duration": 900.0,
                "fetchStart": 1100.0,
                "requestStart": 1200.0,
                "responseStart": 1300.0,
                "responseEnd": 2000.0,
            },
            {
                "name": product_url,
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": 1200.0,
                "fetchStart": 900.0,
                "requestStart": 1000.0,
                "responseStart": 1100.0,
                "responseEnd": 2100.0,
            },
        ],
    )
    browser["performance_timing"]["page_resource_discovery"] = {
        "ok": True,
        "row_count": 2,
        "rows": [
            {
                "url": "https://www.torproject.org/fonts/fontawesome/png/white/brands/github.png",
                "direct_ref_count": 0,
                "css_ref_count": 2,
                "dom_tags": [],
                "dom_rels": [],
                "css_properties": ["background-image"],
                "css_stylesheets": [
                    "https://www.torproject.org/static/fonts/fontawesome/css/all.min.css?h=3c73ff1c"
                ],
                "css_selectors": [".social a.github"],
                "css_rule_kinds": ["style"],
                "direct_refs": [],
                "css_refs": [],
            },
            {
                "url": product_url,
                "direct_ref_count": 1,
                "css_ref_count": 0,
                "dom_tags": ["img"],
                "dom_rels": [],
                "css_properties": [],
                "css_stylesheets": [],
                "css_selectors": [],
                "css_rule_kinds": [],
                "direct_refs": [],
                "css_refs": [],
            },
        ],
    }
    return {
        "profiles": {
            "bundled_c_tor_browser_seeded": {
                "runs": [
                    profile_run(run_index=1, boot_seconds=2.0, browser=browser)
                ]
            }
        }
    }


def css_discovery_gate_payload() -> dict[str, object]:
    stylesheet_url = "https://www.torproject.org/static/css/bootstrap.css?h=0d5c9bf6"
    resource_url = (
        "https://www.torproject.org/static/fonts/fontawesome/png/white/brands/github.png"
    )
    browser = browser_run(
        load_ms=2000.0,
        response_start_ms=100.0,
        dom_content_loaded_ms=600.0,
        load_event_end_ms=2000.0,
        resources=[
            {
                "name": stylesheet_url,
                "initiatorType": "link",
                "nextHopProtocol": "http/1.1",
                "duration": 700.0,
                "fetchStart": 0.0,
                "requestStart": 100.0,
                "responseStart": 200.0,
                "responseEnd": 700.0,
            },
            {
                "name": resource_url,
                "initiatorType": "css",
                "nextHopProtocol": "http/1.1",
                "duration": 900.0,
                "fetchStart": 800.0,
                "requestStart": 1200.0,
                "responseStart": 1300.0,
                "responseEnd": 1700.0,
            },
        ],
    )
    browser["performance_timing"]["page_resource_discovery"] = {
        "ok": True,
        "row_count": 1,
        "rows": [
            {
                "url": "https://www.torproject.org/fonts/fontawesome/png/white/brands/github.png",
                "direct_ref_count": 0,
                "css_ref_count": 1,
                "dom_tags": [],
                "dom_rels": [],
                "css_properties": ["background-image"],
                "css_stylesheets": [stylesheet_url],
                "css_selectors": [".fa-github-png"],
                "css_rule_kinds": ["style"],
                "direct_refs": [],
                "css_refs": [],
            }
        ],
    }
    return {
        "profiles": {
            "bundled_c_tor_browser_seeded": {
                "runs": [
                    profile_run(run_index=1, boot_seconds=2.0, browser=browser)
                ]
            }
        }
    }


def resource_variant_swap_payload() -> dict[str, object]:
    png_url = (
        "https://www.torproject.org/static/images/download/png/get-connected@3x.png?h=5e2656db"
    )
    svg_url = (
        "https://www.torproject.org/static/images/download/svg/get-connected.svg?h=5e2656db"
    )
    browser = browser_run(
        load_ms=2000.0,
        response_start_ms=100.0,
        dom_content_loaded_ms=600.0,
        load_event_end_ms=2000.0,
        resources=[
            {
                "name": png_url,
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": 1000.0,
                "fetchStart": 900.0,
                "requestStart": 1000.0,
                "responseStart": 1100.0,
                "responseEnd": 1900.0,
            },
            {
                "name": svg_url,
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": 1200.0,
                "fetchStart": 1200.0,
                "requestStart": 1300.0,
                "responseStart": 1400.0,
                "responseEnd": 2000.0,
            },
        ],
    )
    browser["performance_timing"]["page_resource_discovery"] = {
        "ok": True,
        "row_count": 1,
        "rows": [
            {
                "url": svg_url,
                "direct_ref_count": 1,
                "css_ref_count": 0,
                "dom_tags": ["img"],
                "dom_rels": [],
                "css_properties": [],
                "css_stylesheets": [],
                "css_selectors": [],
                "css_rule_kinds": [],
                "direct_refs": [],
                "css_refs": [],
            }
        ],
    }
    return {
        "profiles": {
            "bundled_c_tor_browser_seeded": {
                "runs": [
                    profile_run(run_index=1, boot_seconds=2.0, browser=browser)
                ]
            }
        }
    }


def pre_network_cancel_payload() -> dict[str, object]:
    png_url = (
        "https://www.torproject.org/static/images/download/png/get-connected@3x.png?h=5e2656db"
    )
    svg_url = (
        "https://www.torproject.org/static/images/download/svg/get-connected.svg?h=5e2656db"
    )
    fallback_url = (
        "https://www.torproject.org/static/js/fallback.js?h=8a716acd"
    )
    browser = browser_run(
        load_ms=2000.0,
        response_start_ms=100.0,
        dom_content_loaded_ms=600.0,
        load_event_end_ms=2000.0,
        resources=[
            {
                "name": png_url,
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": 0.0,
                "fetchStart": 900.0,
                "requestStart": 900.0,
                "responseStart": 900.0,
                "responseEnd": 900.0,
                "transferSize": 0.0,
                "encodedBodySize": 0.0,
            },
            {
                "name": fallback_url,
                "initiatorType": "script",
                "nextHopProtocol": "http/1.1",
                "duration": 0.0,
                "fetchStart": 950.0,
                "requestStart": 950.0,
                "responseStart": 950.0,
                "responseEnd": 950.0,
                "transferSize": 0.0,
                "encodedBodySize": 0.0,
            },
            {
                "name": svg_url,
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": 1200.0,
                "fetchStart": 1200.0,
                "requestStart": 1300.0,
                "responseStart": 1400.0,
                "responseEnd": 2000.0,
                "transferSize": 30272.0,
                "encodedBodySize": 29972.0,
            },
        ],
    )
    browser["browser_activity_probe"] = {
        "enabled": True,
        "ok": True,
        "rows": [
            {
                "source": "observer_topic",
                "topic": "http-on-stop-request",
                "uri": png_url,
                "channel_id": 11,
            },
            {
                "source": "http_activity",
                "uri": png_url,
                "channel_id": 11,
            },
            {
                "source": "observer_topic",
                "topic": "http-on-stop-request",
                "uri": fallback_url,
                "channel_id": 12,
            },
            {
                "source": "observer_topic",
                "topic": "http-on-stop-request",
                "uri": fallback_url,
                "channel_id": 13,
            },
            {
                "source": "observer_topic",
                "topic": "http-on-examine-response",
                "uri": svg_url,
                "channel_id": 14,
                "localPort": 0,
                "remotePort": 443,
            },
            {
                "source": "observer_topic",
                "topic": "http-on-stop-request",
                "uri": svg_url,
                "channel_id": 14,
                "localPort": 0,
                "remotePort": 443,
            },
        ],
    }
    browser["browser_request_blocker"] = {
        "enabled": True,
        "ok": True,
        "blocked_request_count": 2,
        "rows": [
            {"uri": fallback_url},
            {"uri": fallback_url},
        ],
    }
    browser["performance_timing"]["page_resource_discovery"] = {
        "ok": True,
        "row_count": 2,
        "rows": [
            {
                "url": svg_url,
                "direct_ref_count": 1,
                "css_ref_count": 0,
                "dom_tags": ["img"],
                "dom_rels": [],
                "css_properties": [],
                "css_stylesheets": [],
                "css_selectors": [],
                "css_rule_kinds": [],
                "direct_refs": [],
                "css_refs": [],
            },
            {
                "url": fallback_url,
                "direct_ref_count": 1,
                "css_ref_count": 0,
                "dom_tags": ["script"],
                "dom_rels": [],
                "css_properties": [],
                "css_stylesheets": [],
                "css_selectors": [],
                "css_rule_kinds": [],
                "direct_refs": [],
                "css_refs": [],
            },
        ],
    }
    return {
        "profiles": {
            "bundled_c_tor_browser_seeded": {
                "runs": [
                    profile_run(run_index=1, boot_seconds=2.0, browser=browser)
                ]
            }
        }
    }


class AnalyzeTorfastBrowserCompareTests(unittest.TestCase):
    def test_phase_summary_rows_capture_launch_and_navigation_medians(self) -> None:
        rows = phase_summary_rows(fixture_payload())

        baseline = next(row for row in rows if row["profile"] == "bundled_c_tor_browser")
        seeded = next(
            row for row in rows if row["profile"] == "bundled_c_tor_browser_seeded"
        )

        self.assertEqual(baseline["median_load_ms"], 2100.0)
        self.assertEqual(baseline["median_launch_load_ms"], 13100.0)
        self.assertEqual(baseline["median_nav_response_to_dom_ms"], 540.0)
        self.assertEqual(baseline["median_nav_dom_to_load_ms"], 1450.0)
        self.assertEqual(seeded["median_load_ms"], 1650.0)
        self.assertEqual(seeded["median_launch_load_ms"], 4150.0)
        self.assertEqual(seeded["median_slowest_resource_ms"], 1550.0)

    def test_resource_tail_summary_rows_aggregate_tail_counts(self) -> None:
        rows = resource_tail_summary_rows(fixture_payload())

        baseline = next(row for row in rows if row["profile"] == "bundled_c_tor_browser")
        seeded = next(
            row for row in rows if row["profile"] == "bundled_c_tor_browser_seeded"
        )

        self.assertEqual(baseline["resources"], 4)
        self.assertEqual(baseline["queued_1000ms"], 0)
        self.assertEqual(baseline["slow_resources_2s"], 2)
        self.assertEqual(baseline["resources_ending_final_1s"], 3)
        self.assertEqual(baseline["median_fetch_to_request_ms"], 80.0)
        self.assertEqual(baseline["max_fetch_to_request_ms"], 120.0)
        self.assertEqual(baseline["median_duration_ms"], 1700.0)
        self.assertEqual(baseline["median_end_before_load_ms"], 600.0)
        self.assertEqual(seeded["slow_resources_2s"], 0)
        self.assertEqual(seeded["median_fetch_to_request_ms"], 57.5)
        self.assertEqual(seeded["median_duration_ms"], 1150.0)
        self.assertEqual(seeded["max_tail_after_dom_ms"], 1050.0)

    def test_top_resource_rows_sort_by_tail_then_duration(self) -> None:
        rows = top_resource_rows(fixture_payload(), limit=1)

        self.assertEqual(len(rows), 2)
        baseline = next(row for row in rows if row["profile"] == "bundled_c_tor_browser")
        seeded = next(
            row for row in rows if row["profile"] == "bundled_c_tor_browser_seeded"
        )

        self.assertEqual(baseline["resource"], "hero.png")
        self.assertEqual(baseline["median_fetch_to_request_ms"], 110.0)
        self.assertEqual(baseline["median_tail_after_dom_ms"], 1250.0)
        self.assertEqual(seeded["resource"], "hero.png")
        self.assertEqual(seeded["median_fetch_to_request_ms"], 75.0)
        self.assertEqual(seeded["median_duration_ms"], 1550.0)

    def test_resource_delta_rows_compare_seeded_against_bundled_by_default(self) -> None:
        rows = resource_delta_rows(fixture_payload(), limit=2)

        self.assertEqual(len(rows), 2)
        hero = next(row for row in rows if row["resource"] == "hero.png")
        styles = next(row for row in rows if row["resource"] == "styles.css")

        self.assertEqual(hero["compare_profile"], "bundled_c_tor_browser_seeded")
        self.assertEqual(hero["baseline_profile"], "bundled_c_tor_browser")
        self.assertEqual(hero["delta_fetch_to_request_ms"], -35.0)
        self.assertEqual(hero["delta_duration_ms"], -650.0)
        self.assertEqual(hero["delta_tail_after_dom_ms"], -225.0)
        self.assertEqual(hero["phase_hint"], "faster")
        self.assertEqual(styles["delta_duration_ms"], -450.0)

        reverse_rows = resource_delta_rows(
            fixture_payload(),
            limit=2,
            baseline_profile="bundled_c_tor_browser_seeded",
            compare_profile="bundled_c_tor_browser",
        )
        reverse_hero = next(row for row in reverse_rows if row["resource"] == "hero.png")

        self.assertEqual(reverse_hero["delta_fetch_to_request_ms"], 35.0)
        self.assertEqual(reverse_hero["delta_wait_ms"], -5.0)
        self.assertEqual(reverse_hero["delta_receive_ms"], 295.0)
        self.assertEqual(reverse_hero["phase_hint"], "response receive")

    def test_same_origin_pressure_summary_rows_detect_http11_slot_pressure(self) -> None:
        rows = same_origin_pressure_summary_rows(slot_pressure_payload())
        self.assertEqual(len(rows), 1)

        row = rows[0]
        self.assertEqual(row["profile"], "bundled_c_tor_browser_seeded")
        self.assertEqual(row["queued_1000ms"], 1)
        self.assertEqual(row["slot_pressure_rows"], 1)
        self.assertEqual(row["median_active_same_origin_at_request"], 6.0)
        self.assertEqual(row["median_max_same_origin_active_in_queue"], 0.0)
        self.assertEqual(row["max_same_origin_active_in_queue"], 6)
        self.assertIn("queued.png", row["top_slot_pressure_resources"])

    def test_top_resource_rows_keep_slot_pressure_counts_and_protocol(self) -> None:
        rows = top_resource_rows(slot_pressure_payload(), limit=7)
        row = next(row for row in rows if row["resource"] == "https://cdn.example.com/queued.png")
        self.assertEqual(row["resource"], "https://cdn.example.com/queued.png")
        self.assertEqual(row["protocol"], "http/1.1")
        self.assertEqual(row["slot_pressure_runs"], 1)
        self.assertEqual(row["median_fetch_to_request_ms"], 1100.0)
        self.assertEqual(row["median_max_same_origin_active_in_queue"], 6.0)

    def test_same_origin_blocker_rows_capture_blocker_chain(self) -> None:
        rows = same_origin_blocker_rows(slot_pressure_payload())
        self.assertEqual(len(rows), 1)

        row = rows[0]
        self.assertEqual(row["profile"], "bundled_c_tor_browser_seeded")
        self.assertEqual(row["fetch_to_request_ms"], 1100.0)
        self.assertEqual(row["blockers_before_request"], 6)
        self.assertIn("blocker-0.png", row["top_blockers"])
        self.assertIn("blocker-5.png", row["top_blockers"])

    def test_same_origin_blocker_summary_rows_roll_up_top_blockers(self) -> None:
        rows = same_origin_blocker_summary_rows(slot_pressure_payload())
        self.assertEqual(len(rows), 1)

        row = rows[0]
        self.assertEqual(row["slot_pressure_rows"], 1)
        self.assertEqual(row["median_blockers_before_request"], 6.0)
        self.assertEqual(row["max_blockers_before_request"], 6.0)
        self.assertIn("blocker-", row["top_blockers"])

    def test_same_origin_blocker_owner_rows_capture_blocker_runtime(self) -> None:
        rows = same_origin_blocker_owner_rows(slot_pressure_payload())
        self.assertEqual(len(rows), 6)

        row = next(
            row
            for row in rows
            if row["blocker_resource"] == "https://cdn.example.com/blocker-0.png"
        )
        self.assertEqual(row["queued_resource"], "https://cdn.example.com/queued.png")
        self.assertEqual(row["blocker_duration_ms"], 2000.0)
        self.assertEqual(row["blocker_remaining_at_request_ms"], 400.0)
        self.assertEqual(row["blocker_overlap_in_queue_ms"], 1100.0)
        self.assertEqual(row["blocker_age_at_request_ms"], 1600.0)

    def test_same_origin_blocker_owner_summary_rows_roll_up_owner_metrics(self) -> None:
        rows = same_origin_blocker_owner_summary_rows(slot_pressure_payload())
        self.assertEqual(len(rows), 6)

        row = next(
            row
            for row in rows
            if row["blocker_resource"] == "https://cdn.example.com/blocker-0.png"
        )
        self.assertEqual(row["blocker_occurrences"], 1)
        self.assertEqual(row["runs"], 1)
        self.assertEqual(row["queued_resource_count"], 1)
        self.assertEqual(row["median_blocker_duration_ms"], 2000.0)
        self.assertEqual(row["median_blocker_remaining_at_request_ms"], 400.0)
        self.assertEqual(row["median_blocker_overlap_in_queue_ms"], 1100.0)
        self.assertEqual(row["median_blocker_age_at_request_ms"], 1600.0)
        self.assertIn("queued.png", row["top_queued_resources"])

    def test_same_origin_blocker_owner_delta_rows_compare_owner_lifetime(self) -> None:
        rows = same_origin_blocker_owner_delta_rows(
            blocker_owner_delta_payload(),
            limit=3,
        )
        self.assertEqual(len(rows), 3)

        row = next(
            row
            for row in rows
            if row["blocker_resource"] == "https://cdn.example.com/blocker-a.png"
        )
        self.assertEqual(row["compare_profile"], "bundled_c_tor_browser_seeded")
        self.assertEqual(row["baseline_profile"], "bundled_c_tor_browser")
        self.assertEqual(row["compare_blocker_occurrences"], 2)
        self.assertEqual(row["baseline_blocker_occurrences"], 2)
        self.assertEqual(row["delta_blocker_occurrences"], 0.0)
        self.assertEqual(row["compare_median_blocker_duration_ms"], 2300.0)
        self.assertEqual(row["baseline_median_blocker_duration_ms"], 1800.0)
        self.assertEqual(row["delta_median_blocker_duration_ms"], 500.0)
        self.assertEqual(
            row["compare_median_blocker_remaining_at_request_ms"], 1050.0
        )
        self.assertEqual(
            row["baseline_median_blocker_remaining_at_request_ms"], 550.0
        )
        self.assertEqual(
            row["delta_median_blocker_remaining_at_request_ms"], 500.0
        )
        self.assertEqual(row["delta_median_blocker_overlap_in_queue_ms"], 0.0)

    def test_resource_family_summary_rows_group_assets_by_family(self) -> None:
        rows = resource_family_summary_rows(resource_family_payload())

        download_row = next(
            row
            for row in rows
            if row["profile"] == "bundled_c_tor_browser"
            and row["family"] == "download png"
        )
        js_row = next(
            row
            for row in rows
            if row["profile"] == "bundled_c_tor_browser_seeded"
            and row["family"] == "site js"
        )

        self.assertEqual(download_row["resources"], 1)
        self.assertEqual(download_row["unique_resources"], 1)
        self.assertEqual(download_row["median_request_start_ms"], 1000.0)
        self.assertEqual(download_row["median_fetch_to_request_ms"], 100.0)
        self.assertAlmostEqual(download_row["median_encoded_body_kib"], 120.0)
        self.assertIn("get-connected@3x.png", download_row["top_resources"])

        self.assertEqual(js_row["median_request_start_ms"], 90.0)
        self.assertEqual(js_row["median_duration_ms"], 550.0)
        self.assertAlmostEqual(js_row["median_transfer_size_kib"], 4.5)

    def test_resource_family_delta_rows_flag_later_discovery(self) -> None:
        rows = resource_family_delta_rows(resource_family_payload(), limit=3)

        download_row = next(row for row in rows if row["family"] == "download png")
        fontawesome_row = next(
            row for row in rows if row["family"] == "fontawesome png"
        )

        self.assertEqual(download_row["compare_profile"], "bundled_c_tor_browser_seeded")
        self.assertEqual(download_row["baseline_profile"], "bundled_c_tor_browser")
        self.assertEqual(download_row["delta_request_start_ms"], 400.0)
        self.assertEqual(download_row["delta_fetch_to_request_ms"], 0.0)
        self.assertEqual(download_row["delta_duration_ms"], 0.0)
        self.assertEqual(download_row["delta_encoded_body_kib"], 0.0)
        self.assertEqual(download_row["phase_hint"], "request discovery")

        self.assertEqual(fontawesome_row["delta_request_start_ms"], -200.0)
        self.assertEqual(fontawesome_row["delta_duration_ms"], -200.0)
        self.assertEqual(fontawesome_row["phase_hint"], "faster")

    def test_same_origin_blocker_family_summary_rows_group_cascades(self) -> None:
        rows = same_origin_blocker_family_summary_rows(blocker_family_payload())

        fontawesome_row = next(
            row
            for row in rows
            if row["queued_family"] == "download svg"
            and row["blocker_family"] == "fontawesome png"
        )
        product_row = next(
            row
            for row in rows
            if row["queued_family"] == "download svg"
            and row["blocker_family"] == "product window png"
        )

        self.assertEqual(fontawesome_row["blocker_occurrences"], 6)
        self.assertEqual(fontawesome_row["runs"], 1)
        self.assertEqual(fontawesome_row["queued_resource_count"], 2)
        self.assertEqual(fontawesome_row["blocker_resource_count"], 3)
        self.assertEqual(fontawesome_row["median_blocker_remaining_at_request_ms"], 400.0)
        self.assertEqual(fontawesome_row["median_blocker_overlap_in_queue_ms"], 1100.0)
        self.assertIn("brands/github.png", fontawesome_row["top_blocker_resources"])

        self.assertEqual(product_row["blocker_occurrences"], 2)
        self.assertEqual(product_row["median_blocker_remaining_at_request_ms"], 500.0)

    def test_resource_discovery_summary_rows_classify_css_and_dom_families(self) -> None:
        rows = resource_discovery_summary_rows(resource_discovery_payload())

        fontawesome_row = next(
            row for row in rows if row["family"] == "fontawesome png"
        )
        product_row = next(
            row for row in rows if row["family"] == "product window png"
        )

        self.assertEqual(fontawesome_row["resources"], 1)
        self.assertEqual(fontawesome_row["css_only_resources"], 1)
        self.assertEqual(fontawesome_row["dom_only_resources"], 0)
        self.assertEqual(fontawesome_row["css_background_resources"], 1)
        self.assertEqual(
            fontawesome_row["top_css_stylesheets"],
            "css/all.min.css?h=3c73ff1c",
        )
        self.assertEqual(fontawesome_row["top_css_selectors"], ".social a.github")

        self.assertEqual(product_row["dom_only_resources"], 1)
        self.assertEqual(product_row["img_dom_resources"], 1)
        self.assertEqual(product_row["css_only_resources"], 0)
        self.assertEqual(product_row["median_request_start_ms"], 1000.0)

    def test_css_discovery_gate_summary_rows_measure_after_stylesheet_end(self) -> None:
        rows = css_discovery_gate_summary_rows(css_discovery_gate_payload())

        row = next(row for row in rows if row["family"] == "fontawesome png")
        self.assertEqual(row["stylesheet"], "css/bootstrap.css?h=0d5c9bf6")
        self.assertEqual(row["resources"], 1)
        self.assertEqual(row["median_stylesheet_response_end_ms"], 700.0)
        self.assertEqual(row["median_fetch_start_after_stylesheet_end_ms"], 100.0)
        self.assertEqual(row["median_request_start_after_stylesheet_end_ms"], 500.0)
        self.assertEqual(row["top_css_selectors"], ".fa-github-png")

    def test_resource_variant_swap_rows_detect_png_to_svg_swap(self) -> None:
        rows = resource_variant_swap_rows(resource_variant_swap_payload())

        row = next(row for row in rows if row["loaded_family"] == "download png")
        self.assertEqual(row["current_family"], "download svg")
        self.assertEqual(row["resources"], 1)
        self.assertEqual(row["median_request_start_ms"], 1000.0)
        self.assertIn("get-connected@3x.png", row["top_loaded_resources"])
        self.assertIn("get-connected.svg", row["top_current_resources"])

    def test_pre_network_cancel_summary_rows_capture_placeholder_and_blocked_rows(self) -> None:
        rows = pre_network_cancel_summary_rows(pre_network_cancel_payload())

        png_row = next(row for row in rows if row["loaded_family"] == "download png")
        fallback_row = next(row for row in rows if row["loaded_family"] == "site js")

        self.assertEqual(png_row["current_family"], "download svg")
        self.assertFalse(png_row["request_blocked"])
        self.assertEqual(png_row["resources"], 1)
        self.assertEqual(png_row["unique_resources"], 1)
        self.assertEqual(png_row["stop_request_rows"], 1)
        self.assertEqual(png_row["channel_count"], 1)
        self.assertEqual(png_row["median_request_start_ms"], 900.0)
        self.assertIn("get-connected@3x.png", png_row["top_loaded_resources"])
        self.assertIn("get-connected.svg", png_row["top_current_resources"])

        self.assertEqual(fallback_row["current_family"], "site js")
        self.assertTrue(fallback_row["request_blocked"])
        self.assertEqual(fallback_row["resources"], 1)
        self.assertEqual(fallback_row["stop_request_rows"], 2)
        self.assertEqual(fallback_row["channel_count"], 2)
        self.assertIn("fallback.js", fallback_row["top_loaded_resources"])
        self.assertEqual(fallback_row["top_current_resources"], "")

    def test_browser_net_log_cache_summary_rows_capture_page_cache_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "download.moz_log"
            resource_url = (
                "https://www.torproject.org/static/images/tor-logo@2x.png?h=16ad42bc"
            )
            log_path.write_text(
                "\n".join(
                    [
                        f"2026-06-20 13:17:07.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=parent1 uri={resource_url}, gid=42 browserid=5]",
                        "2026-06-20 13:17:07.100010 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "2026-06-20 13:17:07.100020 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "2026-06-20 13:17:07.100030 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "2026-06-20 13:17:07.100040 UTC - [Parent]: D/nsHttp nsHttpChannel::OpenCacheEntry [this=abc123]",
                        f"2026-06-20 13:17:07.100050 UTC - [Parent]: D/nsHttp nsHttpChannel::OnCacheEntryAvailable [this=abc123 entry=cafe0001 new=1 status=0] for {resource_url}",
                        "2026-06-20 13:17:07.100060 UTC - [Parent]: E/nsHttp nsHttpTransaction::ProcessData [this=deadbeef count=1024]",
                        "2026-06-20 13:17:07.100070 UTC - [Parent]: E/nsHttp nsHttpTransaction::ParseLine [HTTP/1.1 200 OK]",
                        "2026-06-20 13:17:07.100080 UTC - [Parent]: E/nsHttp nsHttpTransaction::ParseLine [Cache-Control: max-age=3600]",
                        "2026-06-20 13:17:07.100090 UTC - [Parent]: E/nsHttp nsHttpTransaction::ParseLine [ETag: \"abc\"]",
                        "2026-06-20 13:17:07.100100 UTC - [Parent]: E/nsHttp nsHttpTransaction::ParseLine [Last-Modified: Wed, 17 Jun 2026 10:04:36 GMT]",
                        "2026-06-20 13:17:07.100110 UTC - [Parent]: E/nsHttp nsHttpTransaction::ParseLine [Content-Type: image/png]",
                        "2026-06-20 13:17:07.100120 UTC - [Parent]: V/nsHttp nsHttpConnection::OnHeadersAvailable [this=conn1 trans=deadbeef response-head=head1]",
                        "2026-06-20 13:17:07.100130 UTC - [Parent]: D/nsHttp nsHttpChannel::InitCacheEntry [this=abc123 entry=cafe0001]",
                        "2026-06-20 13:17:07.100140 UTC - [Parent]: V/nsHttp nsHttpResponseHead::MustValidate ??",
                        "2026-06-20 13:17:07.100150 UTC - [Parent]: V/nsHttp no mandatory validation requirement",
                    ]
                ),
                encoding="utf-8",
            )
            payload = {
                "profiles": {
                    "bundled_c_tor_browser_seeded": {
                        "runs": [
                            profile_run(
                                run_index=1,
                                boot_seconds=2.0,
                                browser=browser_run_with_net_log(
                                    load_ms=1500.0,
                                    response_start_ms=100.0,
                                    dom_content_loaded_ms=600.0,
                                    load_event_end_ms=1500.0,
                                    resources=[
                                        {
                                            "name": resource_url,
                                            "initiatorType": "img",
                                            "nextHopProtocol": "http/1.1",
                                            "duration": 1200.0,
                                            "fetchStart": 0.0,
                                            "requestStart": 10.0,
                                            "responseStart": 50.0,
                                            "responseEnd": 1200.0,
                                        }
                                    ],
                                    log_files=[str(log_path)],
                                ),
                            )
                        ]
                    }
                }
            }

            rows = browser_net_log_cache_summary_rows(payload)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["profile"], "bundled_c_tor_browser_seeded")
            self.assertEqual(row["target"], TARGET)
            self.assertEqual(row["rows"], 1)
            self.assertEqual(row["unique_uris"], 1)
            self.assertEqual(row["same_origin_rows"], 1)
            self.assertEqual(row["http11_rows"], 1)
            self.assertEqual(row["status_200_rows"], 1)
            self.assertEqual(row["status_304_rows"], 0)
            self.assertEqual(row["cache_entry_new_rows"], 1)
            self.assertEqual(row["cache_entry_reused_rows"], 0)
            self.assertEqual(row["must_validate_yes_rows"], 0)
            self.assertEqual(row["must_validate_no_rows"], 1)
            self.assertEqual(row["etag_rows"], 1)
            self.assertEqual(row["last_modified_rows"], 1)
            self.assertEqual(row["cache_control_max_age_rows"], 1)

    def test_same_origin_blocker_cache_signal_rows_join_cache_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "download-slot.moz_log"
            blocker_url = "https://cdn.example.com/blocker-0.png"
            log_path.write_text(
                "\n".join(
                    [
                        f"2026-06-20 13:17:07.100000 UTC - [Parent]: D/nsHttp HttpChannelParent RecvAsyncOpen [this=parent1 uri={blocker_url}, gid=42 browserid=5]",
                        "2026-06-20 13:17:07.100010 UTC - [Parent]: D/nsHttp Creating nsHttpChannel [this=abc123, nsIChannel=abc124]",
                        "2026-06-20 13:17:07.100020 UTC - [Parent]: D/nsHttp nsHttpChannel::DispatchTransaction [this=abc123, aTransWithStickyConn=0]",
                        "2026-06-20 13:17:07.100030 UTC - [Parent]: V/nsHttp Creating nsHttpTransaction @deadbeef",
                        "2026-06-20 13:17:07.100040 UTC - [Parent]: D/nsHttp nsHttpChannel::OpenCacheEntry [this=abc123]",
                        f"2026-06-20 13:17:07.100050 UTC - [Parent]: D/nsHttp nsHttpChannel::OnCacheEntryAvailable [this=abc123 entry=cafe0001 new=1 status=0] for {blocker_url}",
                        "2026-06-20 13:17:07.100060 UTC - [Parent]: E/nsHttp nsHttpTransaction::ProcessData [this=deadbeef count=1024]",
                        "2026-06-20 13:17:07.100070 UTC - [Parent]: E/nsHttp nsHttpTransaction::ParseLine [HTTP/1.1 200 OK]",
                        "2026-06-20 13:17:07.100080 UTC - [Parent]: E/nsHttp nsHttpTransaction::ParseLine [Cache-Control: max-age=3600]",
                        "2026-06-20 13:17:07.100090 UTC - [Parent]: E/nsHttp nsHttpTransaction::ParseLine [ETag: \"abc\"]",
                        "2026-06-20 13:17:07.100100 UTC - [Parent]: E/nsHttp nsHttpTransaction::ParseLine [Last-Modified: Wed, 17 Jun 2026 10:04:36 GMT]",
                        "2026-06-20 13:17:07.100110 UTC - [Parent]: E/nsHttp nsHttpTransaction::ParseLine [Content-Type: image/png]",
                        "2026-06-20 13:17:07.100120 UTC - [Parent]: V/nsHttp nsHttpConnection::OnHeadersAvailable [this=conn1 trans=deadbeef response-head=head1]",
                        "2026-06-20 13:17:07.100130 UTC - [Parent]: D/nsHttp nsHttpChannel::InitCacheEntry [this=abc123 entry=cafe0001]",
                        "2026-06-20 13:17:07.100140 UTC - [Parent]: V/nsHttp nsHttpResponseHead::MustValidate ??",
                        "2026-06-20 13:17:07.100150 UTC - [Parent]: V/nsHttp no mandatory validation requirement",
                    ]
                ),
                encoding="utf-8",
            )
            blockers = []
            for index in range(6):
                blockers.append(
                    {
                        "name": f"https://cdn.example.com/blocker-{index}.png",
                        "initiatorType": "img",
                        "nextHopProtocol": "http/1.1",
                        "duration": 2000.0,
                        "fetchStart": 0.0,
                        "requestStart": 0.0,
                        "responseStart": 50.0,
                        "responseEnd": 2000.0,
                    }
                )
            queued = {
                "name": "https://cdn.example.com/queued.png",
                "initiatorType": "img",
                "nextHopProtocol": "http/1.1",
                "duration": 1300.0,
                "fetchStart": 500.0,
                "requestStart": 1600.0,
                "responseStart": 1700.0,
                "responseEnd": 1800.0,
            }
            payload = {
                "profiles": {
                    "bundled_c_tor_browser_seeded": {
                        "runs": [
                            profile_run(
                                run_index=1,
                                boot_seconds=2.0,
                                browser=browser_run_with_net_log(
                                    load_ms=2000.0,
                                    response_start_ms=100.0,
                                    dom_content_loaded_ms=600.0,
                                    load_event_end_ms=2000.0,
                                    resources=[*blockers, queued],
                                    log_files=[str(log_path)],
                                ),
                            )
                        ]
                    }
                }
            }

            rows = same_origin_blocker_cache_signal_rows(payload)
            row = next(
                row
                for row in rows
                if row["blocker_resource"] == blocker_url
            )
            self.assertEqual(row["blocker_occurrences"], 1)
            self.assertEqual(row["net_log_matches"], 1)
            self.assertEqual(row["status_codes"], "200")
            self.assertEqual(row["cache_entry_summary"], "new 1/1")
            self.assertEqual(row["must_validate_summary"], "no 1/1")
            self.assertEqual(row["cache_control_summary"], "max-age=3600")
            self.assertEqual(row["etag_summary"], "present 1/1")
            self.assertEqual(row["last_modified_summary"], "present 1/1")
            self.assertEqual(row["content_type_summary"], "image/png")


if __name__ == "__main__":
    unittest.main()
