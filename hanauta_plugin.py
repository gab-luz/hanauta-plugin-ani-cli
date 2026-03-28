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

    save_tmdb_button = QPushButton("Save Ani CLI Settings")
    save_tmdb_button.setObjectName("secondaryButton")
    save_tmdb_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def _save_tmdb_settings() -> None:
        state = load_plugin_state()
        state["tmdb_api_key"] = tmdb_key_input.text().strip()
        save_plugin_state(state)
        window.ani_cli_status.setText("Ani CLI settings saved. Relaunch fullscreen app to apply updated TMDB key.")

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
