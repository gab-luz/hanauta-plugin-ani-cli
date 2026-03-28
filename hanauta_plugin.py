#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

PLUGIN_ROOT = Path(__file__).resolve().parent
ANI_FULLSCREEN_APP = PLUGIN_ROOT / "ani_cli_fullscreen.py"
SERVICE_KEY = "ani_cli_widget"
PLUGIN_STATE_FILE = Path.home() / ".local" / "state" / "hanauta" / "plugins" / "ani-cli.json"


def load_plugin_state() -> dict[str, object]:
    try:
        payload = json.loads(PLUGIN_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_plugin_state(payload: dict[str, object]) -> None:
    PLUGIN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLUGIN_STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _launch_fullscreen_app(window, api: dict[str, object]) -> None:
    entry_command = api.get("entry_command")
    run_bg = api.get("run_bg")
    command: list[str] = []
    if callable(entry_command):
        try:
            command = list(entry_command(ANI_FULLSCREEN_APP))
        except Exception:
            command = []
    if not command:
        command = ["python3", str(ANI_FULLSCREEN_APP)]
    if callable(run_bg):
        try:
            run_bg(command)
        except Exception:
            pass
    status = getattr(window, "ani_cli_status", None)
    if isinstance(status, QLabel):
        status.setText("Ani CLI fullscreen launched.")


def build_ani_cli_service_section(window, api: dict[str, object]) -> QWidget:
    SettingsRow = api["SettingsRow"]
    SwitchButton = api["SwitchButton"]
    ExpandableServiceSection = api["ExpandableServiceSection"]
    material_icon = api["material_icon"]
    icon_path = str(api.get("plugin_icon_path", "")).strip()

    service = window.settings_state.setdefault("services", {}).setdefault(
        SERVICE_KEY,
        {
            "enabled": False,
            "show_in_notification_center": False,
            "show_in_bar": False,
        },
    )

    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)

    window.ani_cli_bar_switch = SwitchButton(bool(service.get("show_in_bar", False)))
    window.ani_cli_bar_switch.toggledValue.connect(
        lambda enabled: window._set_service_bar_visibility(SERVICE_KEY, enabled)
    )
    window.service_display_switches[SERVICE_KEY] = window.ani_cli_bar_switch
    layout.addWidget(
        SettingsRow(
            material_icon("widgets"),
            "Show on bar",
            "Display an Ani CLI launcher icon on the bar.",
            window.icon_font,
            window.ui_font,
            window.ani_cli_bar_switch,
        )
    )

    open_button = QPushButton("Open Fullscreen Ani CLI")
    open_button.setObjectName("primaryButton")
    open_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    open_button.clicked.connect(lambda: _launch_fullscreen_app(window, api))
    layout.addWidget(
        SettingsRow(
            material_icon("open_in_new"),
            "Open fullscreen app",
            "Opens a fullscreen discover page with random anime picks and direct ani-cli playback actions.",
            window.icon_font,
            window.ui_font,
            open_button,
        )
    )

    plugin_state = load_plugin_state()
    tmdb_key_input = QLineEdit(str(plugin_state.get("tmdb_api_key", "")).strip())
    tmdb_key_input.setPlaceholderText("Optional TMDB API key")
    tmdb_key_input.setEchoMode(QLineEdit.EchoMode.Password)
    layout.addWidget(
        SettingsRow(
            material_icon("vpn_key"),
            "TMDB API key (optional)",
            "Leave empty to scrape public TMDB pages without a key. Add your key for cleaner search and faster metadata results.",
            window.icon_font,
            window.ui_font,
            tmdb_key_input,
        )
    )

    quality_input = QLineEdit(str(plugin_state.get("quality", "best")).strip() or "best")
    quality_input.setPlaceholderText("best, worst, 1080p, 720p...")
    layout.addWidget(
        SettingsRow(
            material_icon("high_quality"),
            "Playback quality",
            "Maps to ani-cli `-q/--quality`.",
            window.icon_font,
            window.ui_font,
            quality_input,
        )
    )

    select_nth_input = QLineEdit(str(plugin_state.get("select_nth", "1")).strip() or "1")
    select_nth_input.setPlaceholderText("1")
    layout.addWidget(
        SettingsRow(
            material_icon("looks_one"),
            "Select nth source",
            "Maps to ani-cli `-S/--select-nth` (which stream source entry to auto-pick).",
            window.icon_font,
            window.ui_font,
            select_nth_input,
        )
    )

    skip_title_input = QLineEdit(str(plugin_state.get("skip_title", "")).strip())
    skip_title_input.setPlaceholderText("Optional title for --skip-title")
    layout.addWidget(
        SettingsRow(
            material_icon("title"),
            "Skip title override",
            "Optional ani-skip query title (`--skip-title`) when intro skip is enabled.",
            window.icon_font,
            window.ui_font,
            skip_title_input,
        )
    )

    use_vlc_switch = SwitchButton(bool(plugin_state.get("use_vlc", False)))
    layout.addWidget(
        SettingsRow(
            material_icon("smart_display"),
            "Use VLC player",
            "Uses `--vlc` instead of mpv.",
            window.icon_font,
            window.ui_font,
            use_vlc_switch,
        )
    )

    dub_switch = SwitchButton(bool(plugin_state.get("dub", False)))
    layout.addWidget(
        SettingsRow(
            material_icon("record_voice_over"),
            "Prefer dubbed",
            "Uses `--dub` when available.",
            window.icon_font,
            window.ui_font,
            dub_switch,
        )
    )

    skip_intro_switch = SwitchButton(bool(plugin_state.get("skip_intro", True)))
    layout.addWidget(
        SettingsRow(
            material_icon("fast_forward"),
            "Skip intros",
            "Uses `--skip` (mpv only).",
            window.icon_font,
            window.ui_font,
            skip_intro_switch,
        )
    )

    syncplay_switch = SwitchButton(bool(plugin_state.get("syncplay", False)))
    layout.addWidget(
        SettingsRow(
            material_icon("groups"),
            "Syncplay mode",
            "Uses `--syncplay` for watch parties (requires syncplay setup).",
            window.icon_font,
            window.ui_font,
            syncplay_switch,
        )
    )

    nextep_switch = SwitchButton(bool(plugin_state.get("nextep_countdown", False)))
    layout.addWidget(
        SettingsRow(
            material_icon("hourglass_bottom"),
            "Next episode countdown",
            "Uses `--nextep-countdown` after playback.",
            window.icon_font,
            window.ui_font,
            nextep_switch,
        )
    )

    download_switch = SwitchButton(bool(plugin_state.get("download_mode", False)))
    layout.addWidget(
        SettingsRow(
            material_icon("download"),
            "Download mode",
            "Uses `--download` instead of launching the player immediately.",
            window.icon_font,
            window.ui_font,
            download_switch,
        )
    )

    no_detach_switch = SwitchButton(bool(plugin_state.get("no_detach", True)))
    layout.addWidget(
        SettingsRow(
            material_icon("link"),
            "Keep player attached",
            "Uses `--no-detach` (recommended for fullscreen handoff).",
            window.icon_font,
            window.ui_font,
            no_detach_switch,
        )
    )

    exit_after_play_switch = SwitchButton(bool(plugin_state.get("exit_after_play", True)))
    layout.addWidget(
        SettingsRow(
            material_icon("logout"),
            "Exit after play",
            "Uses `--exit-after-play` (recommended for returning to Hanauta).",
            window.icon_font,
            window.ui_font,
            exit_after_play_switch,
        )
    )

    extra_args_input = QLineEdit(str(plugin_state.get("extra_args", "")).strip())
    extra_args_input.setPlaceholderText("--continue  (advanced)")
    layout.addWidget(
        SettingsRow(
            material_icon("terminal"),
            "Extra ani-cli args",
            "Advanced: appended as raw flags (for options like --continue, --rofi, --logview).",
            window.icon_font,
            window.ui_font,
            extra_args_input,
        )
    )

    save_tmdb_button = QPushButton("Save Ani CLI Settings")
    save_tmdb_button.setObjectName("secondaryButton")
    save_tmdb_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def _save_tmdb_settings() -> None:
        state = load_plugin_state()
        state["tmdb_api_key"] = tmdb_key_input.text().strip()
        state["quality"] = quality_input.text().strip() or "best"
        select_nth_raw = select_nth_input.text().strip()
        state["select_nth"] = select_nth_raw if select_nth_raw.isdigit() else "1"
        state["skip_title"] = skip_title_input.text().strip()
        state["use_vlc"] = bool(use_vlc_switch.isChecked())
        state["dub"] = bool(dub_switch.isChecked())
        state["skip_intro"] = bool(skip_intro_switch.isChecked())
        state["syncplay"] = bool(syncplay_switch.isChecked())
        state["nextep_countdown"] = bool(nextep_switch.isChecked())
        state["download_mode"] = bool(download_switch.isChecked())
        state["no_detach"] = bool(no_detach_switch.isChecked())
        state["exit_after_play"] = bool(exit_after_play_switch.isChecked())
        state["extra_args"] = extra_args_input.text().strip()
        save_plugin_state(state)
        window.ani_cli_status.setText("Ani CLI settings saved. Relaunch fullscreen app to apply changes.")

    save_tmdb_button.clicked.connect(_save_tmdb_settings)
    layout.addWidget(
        SettingsRow(
            material_icon("save"),
            "Persist plugin config",
            "Stores Ani CLI plugin settings in local state (~/.local/state/hanauta/plugins/ani-cli.json).",
            window.icon_font,
            window.ui_font,
            save_tmdb_button,
        )
    )

    window.ani_cli_status = QLabel(
        "Disabled by default. Enable this service to expose Ani CLI on the bar and launch the fullscreen discover page."
    )
    window.ani_cli_status.setWordWrap(True)
    window.ani_cli_status.setStyleSheet("color: rgba(246,235,247,0.72);")
    layout.addWidget(window.ani_cli_status)

    section = ExpandableServiceSection(
        SERVICE_KEY,
        "Ani CLI",
        "Fullscreen anime launcher with animated discover screen and random titles.",
        "?",
        window.icon_font,
        window.ui_font,
        content,
        window._service_enabled(SERVICE_KEY),
        lambda enabled: window._set_service_enabled(SERVICE_KEY, enabled),
        icon_path=icon_path,
    )
    window.service_sections[SERVICE_KEY] = section
    return section


def register_hanauta_plugin() -> dict[str, object]:
    return {
        "id": SERVICE_KEY,
        "name": "Ani CLI",
        "service_sections": [
            {
                "key": SERVICE_KEY,
                "builder": build_ani_cli_service_section,
            }
        ],
    }
