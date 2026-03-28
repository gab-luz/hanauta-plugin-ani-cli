#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import random
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib import parse, request

from PyQt6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCursor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

FONTS_DIR = Path.home() / ".config" / "i3" / "assets" / "fonts"
PLUGIN_STATE_FILE = Path.home() / ".local" / "state" / "hanauta" / "plugins" / "ani-cli.json"
SERVICE_PLUGIN_STATE_DIR = Path.home() / ".local" / "state" / "hanauta" / "service" / "plugins"
SERVICE_PRELOAD_JSON = SERVICE_PLUGIN_STATE_DIR / "ani_cli_catalog.json"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w342"
HANAUTA_SRC = Path.home() / ".config" / "i3" / "hanauta" / "src"
THEME_PALETTE_FILE = Path.home() / ".local" / "state" / "hanauta" / "theme" / "pyqt_palette.json"

if str(HANAUTA_SRC) not in sys.path and HANAUTA_SRC.exists():
    sys.path.insert(0, str(HANAUTA_SRC))

try:
    from pyqt.shared.theme import load_theme_palette as _load_shared_theme_palette
    from pyqt.shared.theme import palette_mtime as _shared_palette_mtime
except Exception:
    _load_shared_theme_palette = None
    _shared_palette_mtime = None

IGNORE_TITLES = {
    "The Movie Database (TMDB)", "TV Shows", "Movies", "People", "Collections", 
    "Keywords", "Companies", "Networks", "Awards", "\u00c9missions t\u00e9l\u00e9vis\u00e9es",
    "Films", "Artistes", "Mots-cl\u00e9s", "Soci\u00e9t\u00e9s", "Diffuseurs", "Prix",
}


def load_plugin_state() -> dict[str, object]:
    try:
        payload = json.loads(PLUGIN_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def tmdb_api_key() -> str:
    raw = load_plugin_state().get("tmdb_api_key", "")
    return str(raw).strip()


def load_font_family() -> str:
    rubik = FONTS_DIR / "Rubik-VariableFont_wght.ttf"
    if rubik.exists():
        font_id = QFontDatabase.addApplicationFont(str(rubik))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]
    if QFont("Rubik").exactMatch():
        return "Rubik"
    return "Sans Serif"


def apply_antialias_font(widget: QWidget) -> None:
    base_font = widget.font()
    base_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    widget.setFont(base_font)
    for child in widget.findChildren(QWidget):
        font = child.font()
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        child.setFont(font)


def _normalize_poster_url(raw: str) -> str:
    text = str(raw).strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        if "/t/p/" not in text:
            return ""
        if "w342" in text:
            return text
        filename = text.split("/")[-1]
        if not filename:
            return ""
        return f"{TMDB_IMG_BASE}/{filename}"
    if not text.startswith("/t/p/"):
        return ""
    filename = text.split("/")[-1]
    if not filename:
        return ""
    return f"{TMDB_IMG_BASE}/{filename}"


def _pick_title(row: dict[str, object]) -> str:
    for key in ("name", "title", "original_name", "original_title"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def _safe_hex(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    if not text.startswith("#"):
        text = f"#{text}"
    if len(text) != 7:
        return fallback
    try:
        int(text[1:], 16)
    except ValueError:
        return fallback
    return text.upper()


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    normalized = _safe_hex(color, "#000000")
    return (
        int(normalized[1:3], 16),
        int(normalized[3:5], 16),
        int(normalized[5:7], 16),
    )


def rgba(color: str, alpha: float) -> str:
    red, green, blue = _hex_to_rgb(color)
    clamped = max(0.0, min(1.0, alpha))
    return f"rgba({red}, {green}, {blue}, {clamped:.2f})"


def blend(color_a: str, color_b: str, ratio: float) -> str:
    ra, ga, ba = _hex_to_rgb(color_a)
    rb, gb, bb = _hex_to_rgb(color_b)
    t = max(0.0, min(1.0, ratio))
    red = int(ra + (rb - ra) * t)
    green = int(ga + (gb - ga) * t)
    blue = int(ba + (bb - ba) * t)
    return f"#{red:02X}{green:02X}{blue:02X}"


def theme_palette_mtime() -> float:
    if _shared_palette_mtime is not None:
        try:
            return float(_shared_palette_mtime())
        except Exception:
            pass
    try:
        return THEME_PALETTE_FILE.stat().st_mtime
    except OSError:
        return 0.0


def load_runtime_theme() -> dict[str, object]:
    if _load_shared_theme_palette is not None:
        try:
            theme = _load_shared_theme_palette()
            return {
                "primary": str(theme.primary),
                "on_primary": str(theme.on_primary),
                "secondary": str(theme.secondary),
                "background": str(theme.background),
                "surface": str(theme.surface),
                "surface_container": str(theme.surface_container),
                "surface_container_high": str(theme.surface_container_high),
                "on_surface": str(theme.on_surface),
                "on_surface_variant": str(theme.on_surface_variant),
                "outline": str(theme.outline),
                "text": str(theme.text),
                "text_muted": str(theme.text_muted),
                "active_text": str(theme.active_text),
                "use_matugen": bool(theme.use_matugen),
            }
        except Exception:
            pass
    fallback = {
        "primary": "#CBA6F7",
        "on_primary": "#11111B",
        "secondary": "#89B4FA",
        "background": "#11111B",
        "surface": "#181825",
        "surface_container": "#1E1E2E",
        "surface_container_high": "#313244",
        "on_surface": "#CDD6F4",
        "on_surface_variant": "#A6ADC8",
        "outline": "#6C7086",
        "text": "#CDD6F4",
        "text_muted": "rgba(205,214,244,0.78)",
        "active_text": "#11111B",
        "use_matugen": False,
    }
    try:
        payload = json.loads(THEME_PALETTE_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            fallback["primary"] = _safe_hex(payload.get("primary"), fallback["primary"])
            fallback["on_primary"] = _safe_hex(payload.get("on_primary"), fallback["on_primary"])
            fallback["secondary"] = _safe_hex(payload.get("secondary"), fallback["secondary"])
            fallback["background"] = _safe_hex(payload.get("background"), fallback["background"])
            fallback["surface"] = _safe_hex(payload.get("surface"), fallback["surface"])
            fallback["surface_container"] = _safe_hex(payload.get("surface_container"), fallback["surface_container"])
            fallback["surface_container_high"] = _safe_hex(payload.get("surface_container_high"), fallback["surface_container_high"])
            fallback["on_surface"] = _safe_hex(payload.get("on_surface"), fallback["on_surface"])
            fallback["on_surface_variant"] = _safe_hex(payload.get("on_surface_variant"), fallback["on_surface_variant"])
            fallback["outline"] = _safe_hex(payload.get("outline"), fallback["outline"])
            fallback["text"] = _safe_hex(payload.get("on_surface"), fallback["text"])
            fallback["text_muted"] = rgba(fallback["on_surface_variant"], 0.78)
            fallback["active_text"] = _safe_hex(payload.get("on_primary"), fallback["active_text"])
            fallback["use_matugen"] = bool(payload.get("use_matugen", False))
    except Exception:
        pass
    return fallback


def load_service_preloaded_rows() -> list[dict[str, object]]:
    try:
        payload = json.loads(SERVICE_PRELOAD_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("items", [])
    if not isinstance(rows, list):
        return []
    output: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title", "")).strip()
        detail_url = str(row.get("detail_url", "")).strip()
        tmdb_id = str(row.get("tmdb_id", "")).strip()
        poster_path = Path(str(row.get("poster_path", "")).strip()).expanduser()
        if not title or not poster_path.exists():
            continue
        try:
            image_bytes = poster_path.read_bytes()
        except Exception:
            continue
        if not image_bytes:
            continue
        output.append(
            {
                "title": title,
                "image": image_bytes,
                "detail_url": detail_url,
                "tmdb_id": tmdb_id,
            }
        )
    return output


class CatalogWorker(QThread):
    loaded = pyqtSignal(list)
    _last_live_query_at = 0.0

    def __init__(self, query: str, refresh_seed: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.query = query.strip()
        self.refresh_seed = refresh_seed

    def run(self) -> None:
        self.loaded.emit(self._fetch_items())

    def _fetch_items(self) -> list[dict[str, object]]:
        if not self.query:
            preloaded = load_service_preloaded_rows()
            if preloaded:
                return preloaded
        if self.query and len(self.query) < 2:
            return load_service_preloaded_rows()
        if self.query:
            now = time.monotonic()
            if now - CatalogWorker._last_live_query_at < 1.0:
                return load_service_preloaded_rows()
            CatalogWorker._last_live_query_at = now
        key = tmdb_api_key()
        if key:
            rows = self._fetch_via_tmdb_api(key)
            if rows:
                return rows
        return self._fetch_via_tmdb_html()

    def _fetch_via_tmdb_api(self, key: str) -> list[dict[str, object]]:
        try:
            if self.query:
                params = {
                    "api_key": key,
                    "query": self.query,
                    "include_adult": "false",
                    "language": "en-US",
                    "page": "1",
                }
                url = "https://api.themoviedb.org/3/search/multi?" + parse.urlencode(params)
            else:
                params = {
                    "api_key": key,
                    "include_adult": "false",
                    "with_genres": "16",
                    "with_origin_country": "JP",
                    "sort_by": "popularity.desc",
                    "language": "en-US",
                    "page": str((self.refresh_seed % 5) + 1),
                }
                url = "https://api.themoviedb.org/3/discover/tv?" + parse.urlencode(params)
            req = request.Request(url, headers={"User-Agent": "HanautaAniCli/1.0"})
            with request.urlopen(req, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            rows = payload.get("results", [])
            if not isinstance(rows, list):
                return []
            output: list[dict[str, object]] = []
            seen: set[str] = set()
            for row in rows:
                if not isinstance(row, dict):
                    continue
                media_type = str(row.get("media_type", "tv")).strip() or "tv"
                if media_type not in {"tv", "anime"}:
                    continue
                title = _pick_title(row)
                poster_url = _normalize_poster_url(str(row.get("poster_path", "")).strip())
                tmdb_id = str(row.get("id", "")).strip()
                if not title or not poster_url or not tmdb_id:
                    continue
                key_id = f"{title.lower()}::{poster_url}"
                if key_id in seen:
                    continue
                seen.add(key_id)
                image_bytes = self._download_image_bytes(poster_url)
                if not image_bytes:
                    continue
                output.append(
                    {
                        "title": title,
                        "image": image_bytes,
                        "detail_url": f"https://www.themoviedb.org/tv/{tmdb_id}",
                        "tmdb_id": tmdb_id,
                    }
                )
                if len(output) >= 16:
                    break
            return output
        except Exception:
            return []

    def _fetch_via_tmdb_html(self) -> list[dict[str, object]]:
        try:
            if self.query:
                url = "https://www.themoviedb.org/search/tv?query=" + parse.quote_plus(self.query)
            else:
                page = (self.refresh_seed % 8) + 1
                url = f"https://www.themoviedb.org/keyword/210024-anime/tv?page={page}"
            req = request.Request(url, headers={"User-Agent": "HanautaAniCli/1.0"})
            with request.urlopen(req, timeout=8) as response:
                html_text = response.read().decode("utf-8", errors="ignore")
        except Exception:
            return []

        cards = re.findall(
            r'<a[^>]+href="(?P<href>/tv/[^\"]+)"[^>]*>\s*(?P<img><img[^>]+>)',
            html_text,
            flags=re.IGNORECASE,
        )
        output: list[dict[str, object]] = []
        seen: set[str] = set()
        for card in cards:
            href, img_tag = card
            title_match = re.search(r'alt="([^"]+)"', img_tag, flags=re.IGNORECASE)
            if title_match is None:
                continue
            title = html.unescape(title_match.group(1)).strip()
            if not title or title in IGNORE_TITLES:
                continue
            image_match = re.search(r'https?://[^"\' ]*/t/p/[^"\' ]+|/t/p/[^"\' ]+', img_tag, flags=re.IGNORECASE)
            if image_match is None:
                continue
            poster_url = _normalize_poster_url(image_match.group(0))
            if not poster_url:
                continue
            detail_url = "https://www.themoviedb.org" + href
            key_id = f"{title.lower()}::{poster_url}"
            if key_id in seen:
                continue
            seen.add(key_id)
            image_bytes = self._download_image_bytes(poster_url)
            if not image_bytes:
                continue
            output.append(
                {
                    "title": title,
                    "image": image_bytes,
                    "detail_url": detail_url,
                    "tmdb_id": self._extract_tmdb_id(detail_url),
                }
            )
            if len(output) >= 16:
                break

        if self.query:
            q = self.query.lower()
            filtered = [item for item in output if q in str(item.get("title", "")).lower()]
            return filtered or output
        return output

    def _extract_tmdb_id(self, detail_url: str) -> str:
        match = re.search(r"/tv/(\d+)", detail_url)
        return match.group(1) if match else ""

    def _download_image_bytes(self, url: str) -> bytes:
        try:
            req = request.Request(url, headers={"User-Agent": "HanautaAniCli/1.0"})
            with request.urlopen(req, timeout=3.5) as response:
                data = response.read()
            return data if data else b""
        except Exception:
            return b""


class EpisodeWorker(QThread):
    loaded = pyqtSignal(int)

    def __init__(self, tmdb_id: str, detail_url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tmdb_id = tmdb_id.strip()
        self.detail_url = detail_url.strip()

    def run(self) -> None:
        episodes = self._fetch_episode_count()
        self.loaded.emit(max(1, episodes))

    def _fetch_episode_count(self) -> int:
        key = tmdb_api_key()
        if key and self.tmdb_id:
            try:
                params = {
                    "api_key": key,
                    "language": "en-US",
                }
                url = f"https://api.themoviedb.org/3/tv/{self.tmdb_id}?" + parse.urlencode(params)
                req = request.Request(url, headers={"User-Agent": "HanautaAniCli/1.0"})
                with request.urlopen(req, timeout=8) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="ignore"))
                count = int(payload.get("number_of_episodes", 0) or 0)
                if count > 0:
                    return min(count, 999)
            except Exception:
                pass

        if self.detail_url:
            try:
                req = request.Request(self.detail_url, headers={"User-Agent": "HanautaAniCli/1.0"})
                with request.urlopen(req, timeout=8) as response:
                    text = response.read().decode("utf-8", errors="ignore")
                match = re.search(r'"numberOfEpisodes"\s*:\s*(\d+)', text)
                if match:
                    return min(int(match.group(1)), 999)
            except Exception:
                pass

        return 24


class PosterCard(QFrame):
    clicked = pyqtSignal(int)

    def __init__(
        self,
        index: int,
        title: str,
        image_bytes: bytes,
        font_family: str,
        width: int,
        theme: dict[str, object],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.index = index
        self.title = title
        self.font_family = font_family
        self.theme = dict(theme)
        self._selected = False
        self._hovered = False
        self.setObjectName("posterCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._build_ui(image_bytes, width)
        self._apply_state()

    def _build_ui(self, image_bytes: bytes, width: int) -> None:
        card_width = max(108, int(width * 0.60))
        cover_height = max(132, int(card_width * 1.42))

        self.setFixedWidth(card_width)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.cover = QLabel()
        self.cover.setFixedSize(card_width - 24, cover_height)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pixmap = QPixmap()
        if image_bytes:
            pixmap.loadFromData(image_bytes)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self.cover.width(),
                self.cover.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Modern heavy border-radius for images
            self.cover.setPixmap(self._rounded_pixmap(scaled, 14))

        self.title_label = QLabel(self.title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.title_label.setWordWrap(True)
        title_font = QFont(self.font_family, 10)
        title_font.setWeight(QFont.Weight.DemiBold)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("background: transparent; border: none;")

        layout.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.title_label)

    def _rounded_pixmap(self, pixmap: QPixmap, radius: int) -> QPixmap:
        output = QPixmap(pixmap.size())
        output.fill(Qt.GlobalColor.transparent)
        painter = QPainter(output)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        path = QPainterPath()
        path.addRoundedRect(0, 0, float(pixmap.width()), float(pixmap.height()), float(radius), float(radius))
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return output

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._apply_state()

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = True
        self._apply_state()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = False
        self._apply_state()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def _apply_state(self) -> None:
        primary = str(self.theme.get("primary", "#CBA6F7"))
        secondary = str(self.theme.get("secondary", "#89B4FA"))
        text = str(self.theme.get("text", "#CDD6F4"))
        if self._selected:
            border = f"2px solid {primary}"
            bg = rgba(primary, 0.18)
            # Keep selected card labels readable on all Matugen palettes.
            label_color = text
        elif self._hovered:
            border = f"2px solid {secondary}"
            bg = rgba(secondary, 0.10)
            label_color = text
        else:
            border = "2px solid transparent"
            bg = "transparent"
            label_color = rgba(text, 0.92)
        self.title_label.setStyleSheet(f"background: transparent; border: none; color: {label_color};")
        self.setStyleSheet(f"QFrame#posterCard {{ background: {bg}; border: {border}; border-radius: 20px; }}")

    def update_theme(self, theme: dict[str, object]) -> None:
        self.theme = dict(theme)
        self._apply_state()


class AniCliFullscreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("rootWindow")
        self.font_family = load_font_family()
        self.theme = load_runtime_theme()
        self._theme_mtime = theme_palette_mtime()
        self._refresh_seed = random.randint(1, 1000)
        self._catalog_worker: CatalogWorker | None = None
        self._episode_worker: EpisodeWorker | None = None
        self._current_rows: list[dict[str, object]] = []
        self._poster_cards: list[PosterCard] = []
        self._selected_index = -1
        self._grid_columns = 4
        self._active_row: dict[str, object] | None = None
        self._anims: list[QPropertyAnimation] = []
        self._playback_process: subprocess.Popen | None = None
        self._playback_poll_timer = QTimer(self)
        self._playback_poll_timer.setInterval(750)
        self._playback_poll_timer.timeout.connect(self._poll_playback_process)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(220)
        self._debounce.timeout.connect(self._run_search)
        self._theme_timer = QTimer(self)
        self._theme_timer.setInterval(3000)
        self._theme_timer.timeout.connect(self._reload_theme_if_needed)
        self._theme_timer.start()
        self._install_keyboard_shortcuts()

        self._build_ui()
        ui_font = QFont(self.font_family, 11)
        ui_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(ui_font)
        apply_antialias_font(self)
        self._go_fullscreen()
        self._refresh_catalog()

    def _go_fullscreen(self) -> None:
        self.setWindowTitle("Hanauta Ani CLI")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.showFullScreen()
        QTimer.singleShot(120, self._focus_search_field)

    def _focus_search_field(self) -> None:
        self.search_input.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.search_input.selectAll()
        center = self.search_input.rect().center()
        QCursor.setPos(self.search_input.mapToGlobal(center))

    def _build_ui(self) -> None:
        self._apply_theme()

        root = QVBoxLayout(self)
        # Added margins around the entire app to give it that "floating island" look 
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)

        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 14, 20, 14)
        top_layout.setSpacing(14)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Search anime on TMDB...")
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.returnPressed.connect(self._run_search)
        self.search_input.installEventFilter(self)

        search_action = QAction(self)
        search_action.setIcon(self._search_icon())
        self.search_input.addAction(search_action, QLineEdit.ActionPosition.LeadingPosition)

        self.refresh_button = QPushButton("Refresh Catalog")
        self.refresh_button.setObjectName("refreshButton")
        self.refresh_button.clicked.connect(self._refresh_catalog)

        self.close_button = QPushButton("\u2715")
        self.close_button.setObjectName("closeRound")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setFixedSize(36, 36)
        self.close_button.clicked.connect(self.close)

        top_layout.addWidget(self.search_input, 1)
        top_layout.addWidget(self.refresh_button)
        top_layout.addWidget(self.close_button)

        self.stack = QStackedWidget()
        self.catalog_page = self._build_catalog_page()
        self.episodes_page = self._build_episodes_page()
        self.stack.addWidget(self.catalog_page)
        self.stack.addWidget(self.episodes_page)

        root.addWidget(top_bar)
        root.addWidget(self.stack, 1)

    def _build_catalog_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        panel = QFrame()
        panel.setObjectName("glassPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 24, 24, 24)
        panel_layout.setSpacing(16)

        self.status_label = QLabel("Loading catalog...")
        self.status_label.setObjectName("statusLabel")

        self.scroll = QScrollArea()
        self.scroll.setObjectName("posterScroll")
        self.scroll.setWidgetResizable(True)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(4, 4, 4, 8)
        self.grid.setSpacing(16)
        self.scroll.setWidget(self.grid_host)

        panel_layout.addWidget(self.status_label)
        panel_layout.addWidget(self.scroll, 1)
        layout.addWidget(panel, 1)
        return page

    def _build_episodes_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        panel = QFrame()
        panel.setObjectName("glassPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(32, 32, 32, 32)
        panel_layout.setSpacing(20)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        self.back_button = QPushButton("Back to Catalog")
        self.back_button.setObjectName("ghostButton")
        self.back_button.clicked.connect(self._back_to_catalog)
        header_row.addWidget(self.back_button)
        header_row.addStretch(1)

        self.episode_title_label = QLabel("Select an Episode")
        self.episode_title_label.setObjectName("episodeTitle")
        self.episode_title_label.setWordWrap(True)
        title_font = QFont(self.font_family, 24)
        title_font.setWeight(QFont.Weight.Bold)
        self.episode_title_label.setFont(title_font)
        self.episode_title_label.setStyleSheet("color: #cba6f7;")

        self.episode_hint = QLabel("Arrow keys to navigate, Enter to play selected episode.")
        self.episode_hint.setObjectName("episodeHint")

        self.episodes_list = QListWidget()
        self.episodes_list.setObjectName("episodesList")
        self.episodes_list.itemActivated.connect(self._launch_selected_episode)
        self.episodes_list.installEventFilter(self)

        panel_layout.addLayout(header_row)
        panel_layout.addWidget(self.episode_title_label)
        panel_layout.addWidget(self.episode_hint)
        panel_layout.addWidget(self.episodes_list, 1)
        layout.addWidget(panel, 1)
        return page

    def _search_icon(self) -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(str(self.theme.get("on_surface_variant", "#A6ADC8"))))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawEllipse(2, 2, 8, 8)
        painter.drawLine(9, 9, 14, 14)
        painter.end()
        return QIcon(pixmap)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self.stack.currentIndex() == 0 and self._current_rows:
            QTimer.singleShot(80, self._rerender_current_rows)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
            return

        if self.stack.currentIndex() == 0:
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
                self._navigate_catalog(key)
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._open_selected_card()
                return
        else:
            if key == Qt.Key.Key_Backspace:
                self._back_to_catalog()
                return
            if key == Qt.Key.Key_Up:
                self.episodes_list.setCurrentRow(max(0, self.episodes_list.currentRow() - 1))
                return
            if key == Qt.Key.Key_Down:
                self.episodes_list.setCurrentRow(min(self.episodes_list.count() - 1, self.episodes_list.currentRow() + 1))
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._launch_selected_episode()
                return

        super().keyPressEvent(event)

    def _on_search_changed(self, _: str) -> None:
        self._debounce.start()

    def _run_search(self) -> None:
        self._start_catalog_worker(self.search_input.text().strip())

    def _refresh_catalog(self) -> None:
        self._refresh_seed += 1
        self._start_catalog_worker(self.search_input.text().strip())

    def _start_catalog_worker(self, query: str) -> None:
        if self._catalog_worker is not None and self._catalog_worker.isRunning():
            self._catalog_worker.terminate()
            self._catalog_worker.wait(120)
        self.refresh_button.setEnabled(False)
        self.status_label.setText("Searching TMDB..." if query else "Refreshing anime catalog...")
        self._clear_grid()

        worker = CatalogWorker(query=query, refresh_seed=self._refresh_seed, parent=self)
        worker.loaded.connect(self._render_results)
        worker.finished.connect(lambda: self.refresh_button.setEnabled(True))
        self._catalog_worker = worker
        worker.start()

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._poster_cards = []
        self._selected_index = -1

    def _layout_plan(self, count: int) -> tuple[int, int]:
        viewport_width = max(600, self.scroll.viewport().width() - 12)
        if count <= 1:
            return 1, min(720, int(viewport_width * 0.80))
        if count == 2:
            return 2, max(240, int(viewport_width * 0.45))
        if count == 3:
            return 3, max(210, int(viewport_width * 0.30))

        columns = max(3, min(6, viewport_width // 230))
        card_width = max(180, int((viewport_width - (columns - 1) * 14) / columns))
        return columns, card_width

    def _install_keyboard_shortcuts(self) -> None:
        bindings = [
            ("Left", lambda: self._shortcut_move(Qt.Key.Key_Left)),
            ("Right", lambda: self._shortcut_move(Qt.Key.Key_Right)),
            ("Up", lambda: self._shortcut_move(Qt.Key.Key_Up)),
            ("Down", lambda: self._shortcut_move(Qt.Key.Key_Down)),
            ("Return", self._shortcut_activate),
            ("Enter", self._shortcut_activate),
        ]
        self._shortcuts: list[QShortcut] = []
        for key, callback in bindings:
            shortcut = QShortcut(key, self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _shortcut_move(self, key: int) -> None:
        if self.stack.currentIndex() == 0:
            self._navigate_catalog(key)
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
            self.episodes_list.setCurrentRow(max(0, self.episodes_list.currentRow() - 1))
        elif key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
            self.episodes_list.setCurrentRow(min(self.episodes_list.count() - 1, self.episodes_list.currentRow() + 1))

    def eventFilter(self, watched: object, event: object) -> bool:
        if not isinstance(event, QEvent):
            return super().eventFilter(watched, event)  # type: ignore[arg-type]
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(watched, event)  # type: ignore[arg-type]
        key_event = event  # QKeyEvent
        key = key_event.key()  # type: ignore[attr-defined]

        if watched is self.search_input and self.stack.currentIndex() == 0:
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
                self._navigate_catalog(key)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._open_selected_card()
                return True

        if watched is self.episodes_list and self.stack.currentIndex() == 1:
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
                self.episodes_list.setCurrentRow(max(0, self.episodes_list.currentRow() - 1))
                return True
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
                self.episodes_list.setCurrentRow(min(self.episodes_list.count() - 1, self.episodes_list.currentRow() + 1))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._launch_selected_episode()
                return True

        return super().eventFilter(watched, event)  # type: ignore[arg-type]

    def _shortcut_activate(self) -> None:
        if self.stack.currentIndex() == 0:
            self._open_selected_card()
        else:
            self._launch_selected_episode()

    def _rerender_current_rows(self) -> None:
        self._render_results(self._current_rows)

    def _render_results(self, rows: list[dict[str, object]]) -> None:
        self._current_rows = list(rows)
        self._clear_grid()

        if not rows:
            self.status_label.setText("No anime covers found. Try a different search.")
            return

        self.status_label.setText(
            f"{len(rows)} result(s). Use arrow keys to move, then press Enter to open episodes."
        )
        self._grid_columns, card_width = self._layout_plan(len(rows))

        for index, row in enumerate(rows):
            title = str(row.get("title", "")).strip()
            image_bytes = row.get("image", b"")
            if not title or not isinstance(image_bytes, (bytes, bytearray)):
                continue
            card = PosterCard(index, title, bytes(image_bytes), self.font_family, card_width, self.theme, self.grid_host)
            card.clicked.connect(self._open_card_index)
            self._poster_cards.append(card)
            self.grid.addWidget(card, index // self._grid_columns, index % self._grid_columns)
            self._animate_fade_in(card, delay_ms=index * 22)

        if self._poster_cards:
            self._select_card(0)
        self._animate_fade_in(self.catalog_page, delay_ms=0)

    def _ani_cli_flags_from_settings(self) -> tuple[list[str], bool]:
        state = load_plugin_state()
        flags: list[str] = []
        select_nth = str(state.get("select_nth", "1")).strip()
        if not select_nth.isdigit():
            select_nth = "1"
        flags.extend(["-S", select_nth])
        quality = str(state.get("quality", "")).strip()
        if quality:
            flags.extend(["-q", quality])
        if bool(state.get("use_vlc", False)):
            flags.append("--vlc")
        if bool(state.get("dub", False)):
            flags.append("--dub")
        if bool(state.get("skip_intro", False)):
            flags.append("--skip")
        skip_title = str(state.get("skip_title", "")).strip()
        if skip_title:
            flags.extend(["--skip-title", skip_title])
        if bool(state.get("syncplay", False)):
            flags.append("--syncplay")
        if bool(state.get("nextep_countdown", False)):
            flags.append("--nextep-countdown")
        download_mode = bool(state.get("download_mode", False))
        if download_mode:
            flags.append("--download")

        # Keep current fullscreen flow stable by default.
        no_detach = bool(state.get("no_detach", True))
        exit_after_play = bool(state.get("exit_after_play", True))
        if no_detach:
            flags.append("--no-detach")
        if exit_after_play:
            flags.append("--exit-after-play")
        extra_args = str(state.get("extra_args", "")).strip()
        if extra_args:
            try:
                flags.extend(shlex.split(extra_args))
            except Exception:
                pass
        return flags, download_mode

    def _animate_fade_in(self, widget: QWidget, delay_ms: int = 0) -> None:
        if isinstance(widget, PosterCard):
            return
        def _start() -> None:
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(220)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda: widget.setGraphicsEffect(None))
            anim.start()
            self._anims.append(anim)

        if delay_ms > 0:
            QTimer.singleShot(delay_ms, _start)
        else:
            _start()

    def _reload_theme_if_needed(self) -> None:
        current_mtime = theme_palette_mtime()
        if current_mtime == self._theme_mtime:
            return
        self._theme_mtime = current_mtime
        self.theme = load_runtime_theme()
        self._apply_theme()
        if hasattr(self, "search_input"):
            for action in self.search_input.actions():
                self.search_input.removeAction(action)
            search_action = QAction(self)
            search_action.setIcon(self._search_icon())
            self.search_input.addAction(search_action, QLineEdit.ActionPosition.LeadingPosition)
        for card in self._poster_cards:
            card.update_theme(self.theme)

    def _apply_theme(self) -> None:
        theme = self.theme
        primary = str(theme.get("primary", "#CBA6F7"))
        secondary = str(theme.get("secondary", "#89B4FA"))
        on_primary = str(theme.get("on_primary", "#11111B"))
        background = str(theme.get("background", "#11111B"))
        surface = str(theme.get("surface", "#181825"))
        surface_container = str(theme.get("surface_container", "#1E1E2E"))
        surface_container_high = str(theme.get("surface_container_high", "#313244"))
        text = str(theme.get("text", "#CDD6F4"))
        text_muted = str(theme.get("text_muted", rgba("#CDD6F4", 0.78)))
        outline = str(theme.get("outline", "#6C7086"))
        status = rgba(str(theme.get("on_surface_variant", "#A6ADC8")), 0.78)

        self.setStyleSheet(
            f"""
            QWidget {{
                font-family: '{self.font_family}';
                color: {text};
            }}
            QWidget#rootWindow {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 {blend(background, surface, 0.15)},
                    stop: 0.5 {surface},
                    stop: 1 {background}
                );
            }}
            QFrame#topBar {{
                background: {rgba(surface_container, 0.85)};
                border-radius: 24px;
                border: 1px solid {rgba(outline, 0.28)};
            }}
            QLineEdit#searchInput {{
                background: {rgba(surface_container_high, 0.55)};
                border: 1px solid {rgba(outline, 0.34)};
                border-radius: 18px;
                padding: 10px 16px 10px 38px;
                font-size: 15px;
                color: {text};
            }}
            QLineEdit#searchInput:focus {{
                border: 1px solid {rgba(primary, 0.98)};
                background: {rgba(primary, 0.10)};
            }}
            QPushButton#refreshButton {{
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 {primary}, stop: 1 {secondary});
                border: none;
                border-radius: 18px;
                color: {on_primary};
                padding: 10px 20px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton#refreshButton:hover {{
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 {blend(primary, "#FFFFFF", 0.18)}, stop: 1 {blend(secondary, "#FFFFFF", 0.18)});
            }}
            QPushButton#closeRound {{
                background: {rgba(primary, 0.14)};
                border: 1px solid {rgba(primary, 0.36)};
                border-radius: 18px;
                color: {primary};
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton#closeRound:hover {{
                background: {primary};
                color: {on_primary};
            }}
            QFrame#glassPanel {{
                background: {rgba(surface_container, 0.68)};
                border: 1px solid {rgba(outline, 0.24)};
                border-radius: 24px;
            }}
            QLabel#statusLabel {{
                color: {status};
                font-weight: 600;
            }}
            QLabel#episodeTitle {{
                color: {blend(primary, text, 0.35)};
            }}
            QLabel#episodeHint {{
                color: {text_muted};
            }}
            QScrollArea#posterScroll {{
                border: none;
                background: transparent;
            }}
            QScrollArea#posterScroll > QWidget > QWidget {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 8px;
                margin: 10px 0 10px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {rgba(outline, 0.50)};
                min-height: 30px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {rgba(primary, 0.64)}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QListWidget#episodesList {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget#episodesList::item {{
                padding: 14px 20px;
                border-radius: 16px;
                margin-bottom: 6px;
                background: {rgba(surface_container_high, 0.45)};
                color: {text};
                font-size: 15px;
            }}
            QListWidget#episodesList::item:selected {{
                background: {primary};
                color: {on_primary};
                font-weight: bold;
            }}
            QPushButton#ghostButton {{
                background: {rgba(surface_container_high, 0.64)};
                border: none;
                color: {text};
                border-radius: 16px;
                padding: 10px 20px;
                font-weight: bold;
            }}
            QPushButton#ghostButton:hover {{
                background: {rgba(primary, 0.14)};
                color: {primary};
            }}
            """
        )

    def _select_card(self, index: int) -> None:
        if not self._poster_cards:
            self._selected_index = -1
            return
        self._selected_index = max(0, min(len(self._poster_cards) - 1, index))
        for i, card in enumerate(self._poster_cards):
            card.set_selected(i == self._selected_index)
        selected = self._poster_cards[self._selected_index]
        self.scroll.ensureWidgetVisible(selected, 20, 20)

    def _navigate_catalog(self, key: int) -> None:
        if not self._poster_cards:
            return
        if self._selected_index < 0:
            self._select_card(0)
            return
        index = self._selected_index
        if key == Qt.Key.Key_Left:
            index = max(0, index - 1)
        elif key == Qt.Key.Key_Right:
            index = min(len(self._poster_cards) - 1, index + 1)
        elif key == Qt.Key.Key_Up:
            index = max(0, index - self._grid_columns)
        elif key == Qt.Key.Key_Down:
            index = min(len(self._poster_cards) - 1, index + self._grid_columns)
        self._select_card(index)

    def _open_selected_card(self) -> None:
        if self._selected_index < 0 or self._selected_index >= len(self._current_rows):
            return
        self._open_card_index(self._selected_index)

    def _open_card_index(self, index: int) -> None:
        if index < 0 or index >= len(self._current_rows):
            return
        row = self._current_rows[index]
        self._active_row = row
        title = str(row.get("title", "Anime")).strip() or "Anime"
        detail_url = str(row.get("detail_url", "")).strip()
        tmdb_id = str(row.get("tmdb_id", "")).strip()

        self.episode_title_label.setText(title)
        self.episode_hint.setText(
            "Getting episodes for this anime. In a moment, pick one and press Enter to start watching."
        )
        self.episodes_list.clear()
        self.stack.setCurrentWidget(self.episodes_page)
        self._animate_fade_in(self.episodes_page, delay_ms=0)

        if self._episode_worker is not None and self._episode_worker.isRunning():
            self._episode_worker.terminate()
            self._episode_worker.wait(120)
        worker = EpisodeWorker(tmdb_id=tmdb_id, detail_url=detail_url, parent=self)
        worker.loaded.connect(self._render_episode_list)
        self._episode_worker = worker
        worker.start()

    def _render_episode_list(self, count: int) -> None:
        self.episodes_list.clear()
        count = max(1, min(999, int(count)))
        for number in range(1, count + 1):
            self.episodes_list.addItem(QListWidgetItem(f"Episode {number}"))
        self.episodes_list.setCurrentRow(0)
        self.episodes_list.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.episode_hint.setText(
            f"{count} episodes available. Use Up/Down arrows and Enter to play. "
            "The player will open and this screen returns after playback."
        )

    def _back_to_catalog(self) -> None:
        self.stack.setCurrentWidget(self.catalog_page)
        self._animate_fade_in(self.catalog_page, delay_ms=0)
        if self._selected_index >= 0:
            self._select_card(self._selected_index)
        self.search_input.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _launch_selected_episode(self) -> None:
        row = self._active_row or {}
        title = str(row.get("title", "")).strip()
        if not title:
            self.episode_hint.setText("No title selected.")
            return
        current = self.episodes_list.currentItem()
        if current is None:
            self.episode_hint.setText("Select an episode first.")
            return
        text = current.text()
        match = re.search(r"(\d+)", text)
        if match is None:
            self.episode_hint.setText("Could not parse episode number.")
            return
        episode = match.group(1)
        if shutil.which("ani-cli") is None:
            self.episode_hint.setText("Ani CLI is not installed yet.")
            return
        flags, download_mode = self._ani_cli_flags_from_settings()
        command = ["ani-cli", *flags, "-e", episode, title]
        try:
            self._playback_process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            if download_mode:
                self.episode_hint.setText(
                    f"Downloading {title} episode {episode}. "
                    "This can take a while depending on your connection."
                )
            else:
                self.episode_hint.setText(
                    f"Opening {title} episode {episode}. "
                    "Enjoy your episode; Hanauta returns automatically when playback ends."
                )
                self.hide()
                QTimer.singleShot(650, self._focus_mpv_window)
            self._playback_poll_timer.start()
        except Exception as exc:
            self.episode_hint.setText(f"Failed to launch episode: {exc}")

    def _focus_mpv_window(self) -> None:
        try:
            subprocess.Popen(
                ["i3-msg", '[class="mpv"] focus'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass

    def _poll_playback_process(self) -> None:
        process = self._playback_process
        if process is None:
            self._playback_poll_timer.stop()
            return
        if process.poll() is None:
            return
        self._playback_poll_timer.stop()
        self._playback_process = None
        self.showFullScreen()
        self.activateWindow()
        self.raise_()
        self.stack.setCurrentWidget(self.episodes_page)
        self.episodes_list.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.episode_hint.setText(
            "Episode finished. Pick another one anytime, or go back to browse another anime."
        )


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    window = AniCliFullscreen()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
