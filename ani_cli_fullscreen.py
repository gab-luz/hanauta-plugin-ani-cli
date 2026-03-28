#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib import parse, request

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QThread, QTimer, Qt, pyqtSignal
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
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w342"

IGNORE_TITLES = {
    "The Movie Database (TMDB)",
    "TV Shows",
    "Movies",
    "People",
    "Collections",
    "Keywords",
    "Companies",
    "Networks",
    "Awards",
    "\u00c9missions t\u00e9l\u00e9vis\u00e9es",
    "Films",
    "Artistes",
    "Mots-cl\u00e9s",
    "Soci\u00e9t\u00e9s",
    "Diffuseurs",
    "Prix",
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
    return "Sans Serif"


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


class CatalogWorker(QThread):
    loaded = pyqtSignal(list)

    def __init__(self, query: str, refresh_seed: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.query = query.strip()
        self.refresh_seed = refresh_seed

    def run(self) -> None:
        self.loaded.emit(self._fetch_items())

    def _fetch_items(self) -> list[dict[str, object]]:
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
                if len(output) >= 24:
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
            if len(output) >= 24:
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

    def __init__(self, index: int, title: str, image_bytes: bytes, font_family: str, width: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self.title = title
        self.font_family = font_family
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
        layout.setContentsMargins(10, 10, 10, 12)
        layout.setSpacing(10)

        self.cover = QLabel()
        self.cover.setFixedSize(card_width - 20, cover_height)
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
            self.cover.setPixmap(self._rounded_pixmap(scaled, 16))

        self.title_label = QLabel(self.title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.title_label.setWordWrap(True)
        title_font = QFont(self.font_family, 10)
        title_font.setWeight(QFont.Weight.Medium)
        self.title_label.setFont(title_font)

        layout.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.title_label)

    def _rounded_pixmap(self, pixmap: QPixmap, radius: int) -> QPixmap:
        output = QPixmap(pixmap.size())
        output.fill(Qt.GlobalColor.transparent)
        painter = QPainter(output)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
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
        if self._selected:
            border = "2px solid rgba(180, 201, 255, 0.98)"
            bg = "rgba(255,255,255,0.10)"
        elif self._hovered:
            border = "1px solid rgba(255,255,255,0.26)"
            bg = "rgba(255,255,255,0.08)"
        else:
            border = "1px solid rgba(255,255,255,0.12)"
            bg = "rgba(255,255,255,0.05)"
        self.setStyleSheet(f"background: {bg}; border: {border}; border-radius: 18px;")


class AniCliFullscreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.font_family = load_font_family()
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
        self._install_keyboard_shortcuts()

        self._build_ui()
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
        self.setStyleSheet(
            """
            QWidget {
                font-family: '%s';
                color: #F5F4FF;
                background: #0B1020;
            }
            QFrame#topBar {
                background: rgba(16, 22, 42, 0.96);
                border-bottom: 1px solid rgba(255, 255, 255, 0.10);
            }
            QLineEdit#searchInput {
                background: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: 16px;
                padding: 11px 14px 11px 34px;
                font-size: 14px;
                color: #F6F2FF;
            }
            QLineEdit#searchInput:focus {
                border: 1px solid rgba(145, 178, 255, 0.92);
                background: rgba(255, 255, 255, 0.12);
            }
            QPushButton#refreshButton {
                background: rgba(111, 149, 255, 0.95);
                border: 0;
                border-radius: 14px;
                color: #F9F7FF;
                padding: 10px 14px;
                font-weight: 500;
            }
            QPushButton#refreshButton:hover { background: rgba(132, 166, 255, 0.98); }
            QPushButton#closeRound {
                background: rgba(255,255,255,0.12);
                border: 1px solid rgba(255,255,255,0.26);
                border-radius: 18px;
                color: #FFFFFF;
                font-size: 16px;
                font-weight: 500;
            }
            QPushButton#closeRound:hover { background: rgba(255,110,130,0.86); }
            QScrollArea#posterScroll {
                border: none;
                background: #0B1020;
            }
            QListWidget#episodesList {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 14px;
                padding: 6px;
                outline: none;
            }
            QListWidget#episodesList::item {
                padding: 10px 12px;
                border-radius: 10px;
                margin: 2px;
                color: rgba(247,244,255,0.94);
            }
            QListWidget#episodesList::item:selected {
                background: rgba(119,159,255,0.38);
                border: 1px solid rgba(173,197,255,0.86);
            }
            QPushButton#ghostButton {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.18);
                color: #F5EEFF;
                border-radius: 12px;
                padding: 9px 12px;
                font-weight: 500;
            }
            QPushButton#ghostButton:hover { background: rgba(255,255,255,0.14); }
            """ % self.font_family
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 12, 16, 12)
        top_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Search anime on TMDB...")
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.returnPressed.connect(self._run_search)

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
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        self.status_label = QLabel("Loading catalog...")
        self.status_label.setStyleSheet("color: rgba(238,236,255,0.78);")

        self.scroll = QScrollArea()
        self.scroll.setObjectName("posterScroll")
        self.scroll.setWidgetResizable(True)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(4, 4, 4, 8)
        self.grid.setSpacing(14)
        self.scroll.setWidget(self.grid_host)

        layout.addWidget(self.status_label)
        layout.addWidget(self.scroll, 1)
        return page

    def _build_episodes_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 18, 24, 22)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        self.back_button = QPushButton("Back to Catalog")
        self.back_button.setObjectName("ghostButton")
        self.back_button.clicked.connect(self._back_to_catalog)
        header_row.addWidget(self.back_button)
        header_row.addStretch(1)

        self.episode_title_label = QLabel("Select an Episode")
        self.episode_title_label.setWordWrap(True)
        title_font = QFont(self.font_family, 22)
        title_font.setWeight(QFont.Weight.DemiBold)
        self.episode_title_label.setFont(title_font)

        self.episode_hint = QLabel("Arrow keys to navigate, Enter to play selected episode.")
        self.episode_hint.setStyleSheet("color: rgba(241,236,255,0.72);")

        self.episodes_list = QListWidget()
        self.episodes_list.setObjectName("episodesList")
        self.episodes_list.itemActivated.connect(self._launch_selected_episode)

        layout.addLayout(header_row)
        layout.addWidget(self.episode_title_label)
        layout.addWidget(self.episode_hint)
        layout.addWidget(self.episodes_list, 1)
        return page

    def _search_icon(self) -> QIcon:
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("#D8D1EC"))
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
        if key == Qt.Key.Key_Up:
            self.episodes_list.setCurrentRow(max(0, self.episodes_list.currentRow() - 1))
        elif key == Qt.Key.Key_Down:
            self.episodes_list.setCurrentRow(min(self.episodes_list.count() - 1, self.episodes_list.currentRow() + 1))

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
            card = PosterCard(index, title, bytes(image_bytes), self.font_family, card_width, self.grid_host)
            card.clicked.connect(self._open_card_index)
            self._poster_cards.append(card)
            self.grid.addWidget(card, index // self._grid_columns, index % self._grid_columns)
            self._animate_fade_in(card, delay_ms=index * 22)

        if self._poster_cards:
            self._select_card(0)
        self._animate_fade_in(self.catalog_page, delay_ms=0)

    def _animate_fade_in(self, widget: QWidget, delay_ms: int = 0) -> None:
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
        command = [
            "ani-cli",
            "-S",
            "1",
            "--no-detach",
            "--exit-after-play",
            "-e",
            episode,
            title,
        ]
        try:
            self._playback_process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
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
