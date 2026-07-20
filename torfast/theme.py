"""The torfast zen UI: chrome-only styling for the Tor Browser frame.

The theme is a single userChrome.css written into each fresh generated
browser profile. Websites can never read chrome styles; what they *can*
measure is viewport geometry. So the one hard rule for every line of CSS
here: nothing may change layout metrics — no toolbar or tab heights, no
paddings or margins that move edges, no hidden elements, no rounded or
inset content area. Colors, gradients, radii, shadows, and transitions
only. That keeps the content viewport byte-identical to a stock launch,
and the runtime fingerprint gates verify it stays that way.
"""

from __future__ import annotations

from pathlib import Path

UI_THEME_NAME = "zen"
USERCHROME_RELATIVE_PATH = Path("chrome") / "userChrome.css"
THEME_PREF_LINE = (
    'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);'
)

ZEN_USERCHROME_CSS = """\
/* torfast zen ui — chrome-only, geometry-safe.
   Hard rule: nothing in this file may change layout metrics (heights,
   paddings, margins, visibility). Websites can measure the viewport;
   they can never read these styles. Colors, radii, shadows, and
   transitions only. */

:root {
  --torfast-bg: #14111d;
  --torfast-surface: #1d1929;
  --torfast-raised: #262133;
  --torfast-line: rgba(255, 255, 255, 0.07);
  --torfast-text: #e8e4f2;
  --torfast-muted: rgba(232, 228, 242, 0.6);
  --torfast-accent: #b9a5f5;
  --torfast-glow: rgba(185, 165, 245, 0.25);
  --torfast-radius: 10px;
}

/* ---- frame: one calm surface, no dividing lines ----
   only border-*color* is ever touched: changing a border's width or
   adding one would move the content edge by a pixel. */
#navigator-toolbox {
  background-color: var(--torfast-bg) !important;
  background-image: none !important;
  border-bottom-color: transparent !important;
}
#TabsToolbar,
#nav-bar,
#PersonalToolbar {
  background: transparent !important;
  box-shadow: none !important;
  border-color: transparent !important;
  color: var(--torfast-text) !important;
}

/* ---- tabs: soft pills that recede until you need them ---- */
.tabbrowser-tab .tab-background {
  border-radius: var(--torfast-radius) !important;
  background-color: transparent !important;
  background-image: none !important;
  box-shadow: none !important;
  transition: background-color 140ms ease !important;
}
.tabbrowser-tab:hover:not([selected]) .tab-background {
  background-color: var(--torfast-surface) !important;
}
.tabbrowser-tab[selected] .tab-background,
.tabbrowser-tab[multiselected] .tab-background {
  background-color: var(--torfast-raised) !important;
  box-shadow: inset 0 0 0 1px var(--torfast-line) !important;
}
.tabbrowser-tab:not([selected]) .tab-label {
  opacity: 0.65 !important;
  transition: opacity 140ms ease !important;
}
.tabbrowser-tab:hover:not([selected]) .tab-label {
  opacity: 0.9 !important;
}
.tab-close-button {
  border-radius: 6px !important;
  transition: background-color 140ms ease !important;
}

/* ---- urlbar: a quiet floating field with a focus glow ----
   outline and box-shadow never participate in layout, so the hairline
   ring is safe no matter what the stock urlbar border is. */
#urlbar-background,
#searchbar {
  background-color: var(--torfast-surface) !important;
  border-color: transparent !important;
  outline: 1px solid var(--torfast-line) !important;
  outline-offset: -1px !important;
  border-radius: var(--torfast-radius) !important;
  box-shadow: none !important;
  transition: outline-color 140ms ease, box-shadow 140ms ease !important;
}
#urlbar[focused="true"] > #urlbar-background {
  outline-color: var(--torfast-accent) !important;
  box-shadow: 0 0 0 3px var(--torfast-glow) !important;
}
#urlbar-input {
  color: var(--torfast-text) !important;
}
#urlbar-input::placeholder {
  color: var(--torfast-muted) !important;
}

/* urlbar results panel matches the field */
.urlbarView {
  background-color: var(--torfast-surface) !important;
  border-radius: var(--torfast-radius) !important;
}
.urlbarView-row[selected] > .urlbarView-row-inner {
  background-color: var(--torfast-raised) !important;
  border-radius: 8px !important;
}

/* ---- buttons: round hover targets, no boxes ---- */
.toolbarbutton-1:not([disabled]):hover .toolbarbutton-icon,
.toolbarbutton-1:not([disabled]):hover .toolbarbutton-badge-stack,
.toolbarbutton-1[open] .toolbarbutton-icon,
.toolbarbutton-1[open] .toolbarbutton-badge-stack {
  border-radius: 8px !important;
  background-color: var(--torfast-raised) !important;
  transition: background-color 140ms ease !important;
}

/* ---- menus and panels: same surface language ---- */
menupopup,
panel {
  --panel-background: var(--torfast-surface) !important;
  --panel-border-color: var(--torfast-line) !important;
  --panel-border-radius: var(--torfast-radius) !important;
}

/* ---- bookmarks bar text stays quiet ---- */
#PersonalToolbar .bookmark-item {
  border-radius: 8px !important;
  transition: background-color 140ms ease !important;
}
#PersonalToolbar .bookmark-item:hover {
  background-color: var(--torfast-surface) !important;
}
"""


def apply_ui_theme_to_profile(profile_dir: Path) -> dict[str, object]:
    """Write the zen userChrome.css and its enabling pref into a profile.

    Idempotent: rewrites the stylesheet and only appends the pref line to
    user.js when it is not already present.
    """
    report: dict[str, object] = {
        "ok": True,
        "applied": False,
        "theme": UI_THEME_NAME,
        "profile_dir": str(profile_dir),
    }
    try:
        css_path = profile_dir / USERCHROME_RELATIVE_PATH
        css_path.parent.mkdir(parents=True, exist_ok=True)
        css_path.write_text(ZEN_USERCHROME_CSS, encoding="utf-8")

        user_js_path = profile_dir / "user.js"
        existing = ""
        if user_js_path.exists():
            existing = user_js_path.read_text(encoding="utf-8")
        if THEME_PREF_LINE not in existing:
            prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
            user_js_path.write_text(prefix + THEME_PREF_LINE + "\n", encoding="utf-8")

        report["applied"] = True
        report["userchrome_path"] = str(css_path)
        report["user_js_path"] = str(user_js_path)
    except OSError as exc:
        report["ok"] = False
        report["error"] = str(exc)
    return report
