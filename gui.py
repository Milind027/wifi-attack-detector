import sys
import time
import logging
import csv
import os
import threading
from collections import Counter
from logging.handlers import RotatingFileHandler
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QStackedWidget, QSizePolicy, QFrame, QSystemTrayIcon, QMenu,
    QAction, QAbstractItemView, QLineEdit, QMessageBox, QComboBox,
    QSpinBox, QCheckBox, QGroupBox, QInputDialog
)
from PyQt5.QtCore import Qt, QTimer, QDateTime
from PyQt5.QtGui import (
    QFont, QFontDatabase, QColor, QPainter, QPen, QBrush,
    QIcon, QPixmap
)
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtGui import QTextDocument
from database import Database
from oui_lookup import lookup_vendor
from config import (
    PROJECT_DIR, LOG_PATH, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT,
    DEAUTH_THRESHOLD_COUNT, DEAUTH_THRESHOLD_WINDOW
)

# Configure logging
log_dir = PROJECT_DIR
log_path = LOG_PATH
os.makedirs(log_dir, exist_ok=True)
logger = logging.getLogger()
if not logger.handlers:
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))
    handler = RotatingFileHandler(log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)


# ── Hacker Palette ─────────────────────────────────────────────────────────────

DARK = {
    "bg": "#050a0e", "bg2": "#0a1118", "bg3": "#0f1a24", "line": "#0d2137",
    "txt": "#b8c4ce", "mute": "#2a4a5a", "mute2": "#3d6070",
    "grn": "#00ff88", "red": "#ff3355", "ylw": "#ffaa00",
    "pur": "#bf5af2", "blue": "#00d4ff", "track": "#0a1a28",
}
LIGHT = {
    "bg": "#e8eef2", "bg2": "#dce4ea", "bg3": "#cfd9e0", "line": "#b4c4d0",
    "txt": "#0a1a28", "mute": "#7a8a9a", "mute2": "#5a6a7a",
    "grn": "#00994d", "red": "#cc2244", "ylw": "#aa7700",
    "pur": "#8040c0", "blue": "#0088bb", "track": "#c0ccd6",
}


def make_qss(p: dict) -> str:
    return f"""
* {{ font-family:'IBM Plex Mono','Fira Code','Consolas',monospace; }}
QMainWindow, QWidget#root {{ background:{p['bg']}; color:{p['txt']}; }}
QWidget#sidebar {{
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {p['bg']}, stop:1 {p['bg2']});
    border-right:1px solid {p['line']};
}}
QPushButton#nav_btn {{
    background:transparent; border:none; border-radius:6px;
    padding:9px; color:{p['mute2']}; font-size:18px;
}}
QPushButton#nav_btn:hover {{ background:{p['bg3']}; color:{p['grn']}; }}
QPushButton#nav_btn[active="true"] {{
    background:{p['bg3']}; color:{p['grn']};
    border-left:2px solid {p['grn']};
}}
QWidget#topbar {{
    background:{p['bg']}; border-bottom:1px solid {p['line']};
}}
QLabel#status_label {{
    color:{p['grn']}; font-size:12px; letter-spacing:1px;
}}
QLabel#app_title {{
    color:{p['grn']}; font-size:14px; font-weight:700;
    letter-spacing:2px;
}}
QPushButton#top_btn {{
    background:{p['bg3']}; border:1px solid {p['line']}; border-radius:4px;
    color:{p['mute2']}; font-size:11px; padding:4px 14px; min-width:60px;
}}
QPushButton#top_btn:hover {{ border-color:{p['grn']}; color:{p['grn']}; }}
QPushButton#stop_btn {{
    background:transparent; border:1px solid {p['line']}; border-radius:4px;
    color:{p['red']}; font-size:11px; padding:5px 16px; min-width:70px;
    font-weight:700; letter-spacing:1px;
}}
QPushButton#stop_btn:hover {{ background:rgba(255,51,85,0.1); border-color:{p['red']}; }}
QPushButton#stop_btn[running="false"] {{ color:{p['grn']}; }}
QPushButton#stop_btn[running="false"]:hover {{ background:rgba(0,255,136,0.08); border-color:{p['grn']}; }}
QWidget#stat_card {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {p['bg2']}, stop:1 {p['bg3']});
    border:1px solid {p['line']}; border-radius:10px;
}}
QLabel#stat_label {{
    color:{p['mute2']}; font-size:10px; letter-spacing:2px; font-weight:600;
}}
QLabel#stat_value {{
    font-size:26px; font-weight:700; color:{p['txt']}; letter-spacing:-0.5px;
}}
QWidget#table_card {{
    background:{p['bg2']}; border:1px solid {p['line']}; border-radius:10px;
}}
QLabel#section_label {{
    color:{p['grn']}; font-size:10px; letter-spacing:2px; font-weight:700;
}}
QPushButton#export_btn {{
    background:{p['bg3']}; border:1px solid {p['line']}; border-radius:4px;
    color:{p['mute2']}; font-size:11px; padding:5px 14px;
}}
QPushButton#export_btn:hover {{ border-color:{p['blue']}; color:{p['blue']}; }}
QTableWidget {{
    background:transparent; border:none; gridline-color:{p['line']};
    color:{p['txt']}; font-size:12px;
    selection-background-color:rgba(0,255,136,0.08); outline:none;
    alternate-background-color:{p['bg3']};
}}
QTableWidget::item {{ padding:7px 14px; border-bottom:1px solid {p['line']}; }}
QTableWidget::item:selected {{ background:rgba(0,255,136,0.1); color:{p['grn']}; }}
QHeaderView::section {{
    background:{p['bg2']}; color:{p['grn']};
    font-size:9px; letter-spacing:2px; padding:8px 14px; font-weight:700;
    border:none; border-bottom:1px solid {p['line']};
}}
QScrollBar:vertical {{ background:{p['bg']}; width:5px; border:none; }}
QScrollBar::handle:vertical {{ background:{p['line']}; border-radius:2px; min-height:30px; }}
QScrollBar::handle:vertical:hover {{ background:{p['grn']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar:horizontal {{ background:{p['bg']}; height:5px; border:none; }}
QScrollBar::handle:horizontal {{ background:{p['line']}; border-radius:2px; min-width:30px; }}
QScrollBar::handle:horizontal:hover {{ background:{p['grn']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}
QFrame#divider {{ background:{p['line']}; border:none; max-height:1px; min-height:1px; }}
QWidget#alert_banner {{
    background:rgba(255,51,85,0.08); border-left:3px solid {p['red']};
    border-radius:0 6px 6px 0;
}}
QLabel#alert_text {{ color:{p['red']}; font-size:11px; font-weight:600; }}
QWidget#chart_card {{
    background:{p['bg2']}; border:1px solid {p['line']}; border-radius:10px;
}}
QWidget#page {{ background:{p['bg']}; }}
QWidget#settings_page {{ background:{p['bg']}; }}
QLineEdit {{
    background:{p['bg3']}; color:{p['txt']}; border:1px solid {p['line']};
    border-radius:4px; padding:8px 12px; font-size:12px;
}}
QLineEdit:focus {{ border-color:{p['grn']}; }}
QComboBox {{
    background:{p['bg3']}; color:{p['txt']}; border:1px solid {p['line']};
    border-radius:4px; padding:6px 10px; font-size:12px;
}}
QComboBox:hover {{ border-color:{p['blue']}; }}
QComboBox QAbstractItemView {{ background:{p['bg2']}; color:{p['txt']}; border:1px solid {p['line']}; }}
QSpinBox {{
    background:{p['bg3']}; color:{p['txt']}; border:1px solid {p['line']};
    border-radius:4px; padding:6px 10px; font-size:12px;
}}
QSpinBox:focus {{ border-color:{p['grn']}; }}
QCheckBox {{ color:{p['txt']}; font-size:12px; spacing:8px; }}
QCheckBox::indicator {{ width:16px; height:16px; border:1px solid {p['line']}; border-radius:3px; background:{p['bg3']}; }}
QCheckBox::indicator:checked {{ background:{p['grn']}; border-color:{p['grn']}; }}
QGroupBox {{
    color:{p['grn']}; border:1px solid {p['line']}; border-radius:10px;
    margin-top:12px; padding-top:22px; font-weight:700; letter-spacing:1px;
}}
QGroupBox::title {{ subcontrol-origin:margin; left:12px; padding:0 6px; }}
QMenu {{ background:{p['bg2']}; color:{p['txt']}; border:1px solid {p['line']}; border-radius:6px; padding:4px; }}
QMenu::item {{ padding:6px 20px; border-radius:4px; }}
QMenu::item:selected {{ background:{p['bg3']}; color:{p['grn']}; }}
"""


# ── Tag / color helpers ────────────────────────────────────────────────────────

ATTACK_COLORS = {
    "deauth":       ("#ff3355","rgba(255,51,85,0.12)","rgba(255,51,85,0.28)"),
    "evil twin":    ("#ffaa00","rgba(255,170,0,0.12)","rgba(255,170,0,0.28)"),
    "evil_twin":    ("#ffaa00","rgba(255,170,0,0.12)","rgba(255,170,0,0.28)"),
    "pmkid":        ("#bf5af2","rgba(191,90,242,0.12)","rgba(191,90,242,0.28)"),
    "probe flood":  ("#00d4ff","rgba(0,212,255,0.12)","rgba(0,212,255,0.28)"),
    "probe_flood":  ("#00d4ff","rgba(0,212,255,0.12)","rgba(0,212,255,0.28)"),
    "beacon flood": ("#00d4ff","rgba(0,212,255,0.12)","rgba(0,212,255,0.28)"),
    "beacon_flood": ("#00d4ff","rgba(0,212,255,0.12)","rgba(0,212,255,0.28)"),
    "targeted_deauth": ("#ff3355","rgba(255,51,85,0.12)","rgba(255,51,85,0.28)"),
}

SEV_COLORS = {"low": "#00ff88", "medium": "#ffaa00", "high": "#ff3355", "critical": "#bf5af2"}


class TagLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        key = text.lower()
        col, bg, border = ATTACK_COLORS.get(key, ("#888","rgba(128,128,128,0.12)","rgba(128,128,128,0.28)"))
        self.setStyleSheet(f"""QLabel{{color:{col};background:{bg};border:1px solid {border};
            border-radius:3px;font-family:'IBM Plex Mono',monospace;font-size:10px;padding:2px 7px;}}""")
        self.setAlignment(Qt.AlignCenter)


class PulseDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._alpha = 255; self._direction = -4; self._running = True
        self._timer = QTimer(self); self._timer.timeout.connect(self._tick); self._timer.start(30)

    def set_running(self, v):
        self._running = v; self._alpha = 255; self.update()

    def _tick(self):
        if not self._running: return
        self._alpha += self._direction * 5
        if self._alpha <= 40: self._direction = 4
        if self._alpha >= 255: self._direction = -4
        self._alpha = max(40, min(255, self._alpha)); self.update()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        color = QColor(78, 201, 148, self._alpha) if self._running else QColor(74, 74, 74, 255)
        p.setBrush(QBrush(color)); p.setPen(Qt.NoPen); p.drawEllipse(1, 1, 8, 8)


class BarChart(QWidget):
    def __init__(self, data=None, parent=None):
        super().__init__(parent)
        self.data = data or []; self.setMinimumHeight(64)

    def set_data(self, data): self.data = data; self.update()

    def paintEvent(self, e):
        if not self.data: return
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h, n = self.width(), self.height(), len(self.data)
        max_val = max(v for v, _ in self.data) or 1
        gap = 3; bar_w = max(4, (w - gap * (n - 1)) // n)
        for i, (val, color) in enumerate(self.data):
            if val == 0:
                bar_h = max(2, int(h * 0.15))
            else:
                bar_h = max(int(h * 0.15), int((val / max_val) * (h - 4)))
            x = i * (bar_w + gap); y = h - bar_h
            p.setBrush(QBrush(QColor(color))); p.setPen(Qt.NoPen)
            p.drawRoundedRect(x, y, bar_w, bar_h, 2, 2)


class MiniBar(QWidget):
    def __init__(self, pct, color, parent=None):
        super().__init__(parent)
        self.pct = pct; self.color = color; self.setFixedHeight(4)

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        track = QColor(DARK["track"] if True else LIGHT["track"])
        p.setBrush(QBrush(track)); p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, 4, 2, 2)
        fill_w = int(w * self.pct / 100)
        if fill_w > 0:
            c = QColor(self.color); c.setAlphaF(0.85)
            p.setBrush(QBrush(c)); p.drawRoundedRect(0, 0, fill_w, 4, 2, 2)


class StatCard(QWidget):
    def __init__(self, label, value, color=None, parent=None):
        super().__init__(parent)
        self.setObjectName("stat_card")
        lay = QVBoxLayout(self); lay.setContentsMargins(15, 13, 15, 13); lay.setSpacing(5)
        lbl = QLabel(label.upper()); lbl.setObjectName("stat_label"); lay.addWidget(lbl)
        self.val_label = QLabel(value); self.val_label.setObjectName("stat_value")
        if color: self.val_label.setStyleSheet(f"color:{color};")
        lay.addWidget(self.val_label)

    def set_value(self, v, color=None):
        self.val_label.setText(v)
        if color: self.val_label.setStyleSheet(f"color:{color};")


class AlertBanner(QWidget):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setObjectName("alert_banner")
        lay = QHBoxLayout(self); lay.setContentsMargins(12, 7, 12, 7)
        self._lbl = QLabel(f"!  {text}"); self._lbl.setObjectName("alert_text")
        self._lbl.setWordWrap(True); lay.addWidget(self._lbl)
        self.setVisible(bool(text))

    def set_text(self, text):
        self._lbl.setText(f"!  {text}"); self.setVisible(True)


# ── Dashboard page ──────────────────────────────────────────────────────────────

class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18); root.setSpacing(14)

        # alert banner
        self.alert = AlertBanner("")
        root.addWidget(self.alert)

        # stat cards row
        stat_row = QHBoxLayout(); stat_row.setSpacing(10)
        self.stat_total   = StatCard("total", "0")
        self.stat_24h     = StatCard("last 24h", "0", "#ff3355")
        self.stat_flagged = StatCard("flagged MACs", "0", "#ffaa00")
        self.stat_nets    = StatCard("networks", "0")
        for c in [self.stat_total, self.stat_24h, self.stat_flagged, self.stat_nets]:
            stat_row.addWidget(c)
        root.addLayout(stat_row)

        # attack table card
        tcard = QWidget(); tcard.setObjectName("table_card")
        tlay = QVBoxLayout(tcard); tlay.setContentsMargins(0, 0, 0, 0); tlay.setSpacing(0)

        # table header row
        thead = QWidget(); thead.setObjectName("table_card")
        thead.setStyleSheet("border-bottom:1px solid #262626; border-radius:0;")
        thr = QHBoxLayout(thead); thr.setContentsMargins(14, 8, 14, 8)
        sec_lbl = QLabel("RECENT ATTACKS"); sec_lbl.setObjectName("section_label")
        thr.addWidget(sec_lbl); thr.addStretch()

        self.export_csv_btn = QPushButton("export csv"); self.export_csv_btn.setObjectName("export_btn")
        self.export_pdf_btn = QPushButton("export pdf"); self.export_pdf_btn.setObjectName("export_btn")
        thr.addWidget(self.export_csv_btn); thr.addWidget(self.export_pdf_btn)
        tlay.addWidget(thead)

        # table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["TIME", "TYPE", "SRC MAC", "TARGET", "SSID", "SEV"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setColumnWidth(0, 80); self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 155); self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(5, 50)
        tlay.addWidget(self.table)
        root.addWidget(tcard)

        # bottom charts row
        bot = QHBoxLayout(); bot.setSpacing(10)

        # bar chart card
        bc = QWidget(); bc.setObjectName("chart_card")
        bcl = QVBoxLayout(bc); bcl.setContentsMargins(14, 13, 14, 13); bcl.setSpacing(8)
        blbl = QLabel("ATTACKS TODAY  BY HOUR"); blbl.setObjectName("section_label")
        bcl.addWidget(blbl)
        self.bar_chart = BarChart()
        bcl.addWidget(self.bar_chart)
        row_lbl = QHBoxLayout()
        for t in ["00:00", "now"]:
            l = QLabel(t)
            l.setStyleSheet("font-size:10px;color:#4a4a4a;font-family:'IBM Plex Mono',monospace;")
            row_lbl.addWidget(l, alignment=Qt.AlignLeft if t == "00:00" else Qt.AlignRight)
        bcl.addLayout(row_lbl)
        bot.addWidget(bc, 3)

        # type breakdown card
        tc = QWidget(); tc.setObjectName("chart_card")
        self._type_card_layout = QVBoxLayout(tc)
        self._type_card_layout.setContentsMargins(14, 13, 14, 13); self._type_card_layout.setSpacing(10)
        tlbl = QLabel("BY TYPE"); tlbl.setObjectName("section_label")
        self._type_card_layout.addWidget(tlbl)
        self._type_card_layout.addStretch()
        self._type_card = tc
        bot.addWidget(tc, 1)

        root.addLayout(bot)

    def update_type_breakdown(self, type_data):
        """type_data: list of (name, pct, color)"""
        # Clear old bars (keep first label + stretch)
        while self._type_card_layout.count() > 1:
            item = self._type_card_layout.takeAt(1)
            if item.widget(): item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget(): sub.widget().deleteLater()

        for name, pct, col in type_data:
            row = QHBoxLayout(); row.setSpacing(8)
            nl = QLabel(name); nl.setFixedWidth(70)
            nl.setStyleSheet("font-size:11px;color:#666;font-family:'IBM Plex Mono',monospace;")
            row.addWidget(nl)
            mb = MiniBar(pct, col); row.addWidget(mb, 1)
            pl = QLabel(f"{pct}%"); pl.setFixedWidth(32); pl.setAlignment(Qt.AlignRight)
            pl.setStyleSheet("font-size:10px;color:#4a4a4a;font-family:'IBM Plex Mono',monospace;")
            row.addWidget(pl)
            self._type_card_layout.insertLayout(self._type_card_layout.count(), row)
        self._type_card_layout.addStretch()

    def load_attacks(self, attacks):
        """attacks: list of dicts with keys: time, attack_type, src_mac, target, ssid, severity, vendor"""
        self.table.setRowCount(0)
        for row_data in attacks:
            r = self.table.rowCount(); self.table.insertRow(r); self.table.setRowHeight(r, 38)
            # time
            t = QTableWidgetItem(row_data.get("time", ""))
            t.setForeground(QColor("#666666")); t.setFont(QFont("IBM Plex Mono", 12))
            self.table.setItem(r, 0, t)
            # type tag
            tag = TagLabel(row_data.get("attack_type", ""))
            w = QWidget(); l = QHBoxLayout(w); l.setContentsMargins(14, 4, 14, 4)
            l.addWidget(tag); l.addStretch(); w.setStyleSheet("background:transparent;")
            self.table.setCellWidget(r, 1, w)
            # src mac
            mac = row_data.get("src_mac", ""); vendor = row_data.get("vendor", "")
            m = QTableWidgetItem(mac); m.setForeground(QColor("#666666"))
            m.setFont(QFont("IBM Plex Mono", 11))
            if vendor: m.setToolTip(vendor)
            self.table.setItem(r, 2, m)
            # target
            target = row_data.get("target", "broadcast")
            tgt = QTableWidgetItem(target); tgt.setFont(QFont("IBM Plex Mono", 11))
            tgt.setForeground(QColor("#ff3355") if target == "your device" else QColor("#666666"))
            self.table.setItem(r, 3, tgt)
            # ssid
            s = QTableWidgetItem(row_data.get("ssid", "—"))
            s.setFont(QFont("IBM Plex Mono", 12)); s.setForeground(QColor("#e8eef2"))
            self.table.setItem(r, 4, s)
            # severity
            sev = row_data.get("severity", "low")
            sv = QTableWidgetItem(sev); sv.setFont(QFont("IBM Plex Mono", 11))
            sv.setForeground(QColor(SEV_COLORS.get(sev, "#666")))
            sv.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, 5, sv)

    def load_attacks_from_db(self, logs):
        """Convert raw DB rows to attack dicts and load them."""
        attacks = []
        for log in logs:
            attack_type = log[5] if len(log) > 5 and log[5] else "deauth"
            severity = log[6] if len(log) > 6 and log[6] else "medium"
            ts = log[1]
            # Show only time portion
            time_str = ts.split(" ")[-1] if " " in ts else ts
            attacks.append({
                "time": time_str, "attack_type": attack_type.replace("_", " "),
                "src_mac": log[2], "target": log[3] if log[3] != "ff:ff:ff:ff:ff:ff" else "broadcast",
                "ssid": log[4] if log[4] and log[4] != "Unknown" else "—",
                "severity": severity, "vendor": lookup_vendor(log[2]),
            })
        self.load_attacks(attacks)


# ── Logs page ───────────────────────────────────────────────────────────────────

class LogsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 18, 18, 18); lay.setSpacing(10)

        title = QLabel("ATTACK LOGS"); title.setObjectName("section_label")
        lay.addWidget(title)

        # filter bar
        fbar = QHBoxLayout(); fbar.setSpacing(8)
        self.log_search = QLineEdit(); self.log_search.setPlaceholderText("search logs…")
        fbar.addWidget(self.log_search, 2)
        self.type_filter = QComboBox()
        self.type_filter.addItems(["All", "deauth", "targeted_deauth", "evil_twin", "probe_flood", "beacon_flood", "pmkid"])
        fbar.addWidget(self.type_filter)
        self.severity_filter = QComboBox()
        self.severity_filter.addItems(["All", "high", "medium", "low"])
        fbar.addWidget(self.severity_filter)
        self.clear_filter_btn = QPushButton("clear"); self.clear_filter_btn.setObjectName("export_btn")
        fbar.addWidget(self.clear_filter_btn)
        lay.addLayout(fbar)

        # table
        self.table = QTableWidget(); self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["TIME", "TYPE", "SRC MAC", "DST MAC", "SSID", "ATTACK", "SEV"])
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        lay.addWidget(self.table, 1)

        # bottom buttons
        brow = QHBoxLayout(); brow.setSpacing(8)
        self.refresh_btn = QPushButton("refresh"); self.refresh_btn.setObjectName("export_btn")
        self.export_csv_btn = QPushButton("export csv"); self.export_csv_btn.setObjectName("export_btn")
        self.export_pdf_btn = QPushButton("export pdf"); self.export_pdf_btn.setObjectName("export_btn")
        self.upload_btn = QPushButton("upload to drive"); self.upload_btn.setObjectName("export_btn")
        for b in [self.refresh_btn, self.export_csv_btn, self.export_pdf_btn, self.upload_btn]:
            brow.addWidget(b)
        brow.addStretch()
        lay.addLayout(brow)


# ── Settings page ───────────────────────────────────────────────────────────────

class SettingsPage(QWidget):
    def __init__(self, detector=None, username="", parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 18, 18, 18); lay.setSpacing(12)

        title = QLabel("SETTINGS"); title.setObjectName("section_label")
        lay.addWidget(title)

        # Interface
        irow = QHBoxLayout()
        irow.addWidget(QLabel("interface")); self.interface_combo = QComboBox()
        self.interface_combo.addItems(detector.get_available_interfaces() if detector else ["wlan0"])
        irow.addWidget(self.interface_combo)
        self.set_iface_btn = QPushButton("set"); self.set_iface_btn.setObjectName("export_btn")
        irow.addWidget(self.set_iface_btn); irow.addStretch()
        lay.addLayout(irow)

        # Username
        urow = QHBoxLayout()
        urow.addWidget(QLabel("new username")); self.new_username = QLineEdit()
        urow.addWidget(self.new_username)
        self.change_user_btn = QPushButton("change"); self.change_user_btn.setObjectName("export_btn")
        urow.addWidget(self.change_user_btn); urow.addStretch()
        lay.addLayout(urow)

        # Password
        prow = QHBoxLayout()
        prow.addWidget(QLabel("new password")); self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.Password)
        prow.addWidget(self.new_password)
        self.change_pass_btn = QPushButton("change"); self.change_pass_btn.setObjectName("export_btn")
        prow.addWidget(self.change_pass_btn); prow.addStretch()
        lay.addLayout(prow)

        # Email
        erow = QHBoxLayout()
        erow.addWidget(QLabel("notification email")); self.receiver_email = QLineEdit()
        erow.addWidget(self.receiver_email)
        self.update_email_btn = QPushButton("update"); self.update_email_btn.setObjectName("export_btn")
        erow.addWidget(self.update_email_btn); erow.addStretch()
        lay.addLayout(erow)

        # Drive
        drow = QHBoxLayout()
        self.connect_drive_btn = QPushButton("connect google drive"); self.connect_drive_btn.setObjectName("export_btn")
        self.disconnect_drive_btn = QPushButton("disconnect"); self.disconnect_drive_btn.setObjectName("export_btn")
        drow.addWidget(self.connect_drive_btn); drow.addWidget(self.disconnect_drive_btn); drow.addStretch()
        lay.addLayout(drow)

        # Threshold
        trow = QHBoxLayout()
        trow.addWidget(QLabel("deauth threshold"))
        self.threshold_count = QSpinBox(); self.threshold_count.setRange(1, 1000)
        self.threshold_count.setValue(DEAUTH_THRESHOLD_COUNT)
        trow.addWidget(self.threshold_count); trow.addWidget(QLabel("packets in"))
        self.threshold_window = QSpinBox(); self.threshold_window.setRange(1, 300)
        self.threshold_window.setValue(DEAUTH_THRESHOLD_WINDOW); self.threshold_window.setSuffix(" sec")
        trow.addWidget(self.threshold_window)
        self.apply_thresh_btn = QPushButton("apply"); self.apply_thresh_btn.setObjectName("export_btn")
        trow.addWidget(self.apply_thresh_btn); trow.addStretch()
        lay.addLayout(trow)

        # Alert channel toggles
        channels = QGroupBox("alert channels")
        clr = QVBoxLayout(channels)
        self.email_toggle = QCheckBox("email (gmail smtp)")
        self.telegram_toggle = QCheckBox("telegram bot")
        self.ntfy_toggle = QCheckBox("ntfy.sh push")
        self.twilio_toggle = QCheckBox("twilio sms")
        if detector:
            self.email_toggle.setChecked(bool(detector.notifier.receiver_email))
            self.telegram_toggle.setChecked(bool(detector.telegram.enabled))
            self.ntfy_toggle.setChecked(bool(detector.ntfy.enabled))
            self.twilio_toggle.setChecked(bool(detector.twilio.enabled))
        for t in [self.email_toggle, self.telegram_toggle, self.ntfy_toggle, self.twilio_toggle]:
            clr.addWidget(t)
        lay.addWidget(channels)

        self.logout_btn = QPushButton("log out"); self.logout_btn.setObjectName("stop_btn")
        lay.addWidget(self.logout_btn)
        lay.addStretch()


# ── Network Map page ────────────────────────────────────────────────────────────

class NetworkMapPage(QWidget):
    """Displays nearby access points detected from beacon frames."""

    SIGNAL_COLORS = {
        "good": "#00ff88",    # > -50 dBm
        "fair": "#ffaa00",    # -50 to -70
        "weak": "#ff3355",    # < -70
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 18, 18, 18); lay.setSpacing(10)

        # Header row
        hdr = QHBoxLayout(); hdr.setSpacing(8)
        title = QLabel("NETWORK MAP"); title.setObjectName("section_label")
        hdr.addWidget(title); hdr.addStretch()
        self.ap_count_lbl = QLabel("0 APs")
        self.ap_count_lbl.setStyleSheet(
            "color:#4a4a4a;font-size:11px;font-family:'IBM Plex Mono',monospace;")
        hdr.addWidget(self.ap_count_lbl)
        self.refresh_btn = QPushButton("refresh"); self.refresh_btn.setObjectName("export_btn")
        hdr.addWidget(self.refresh_btn)
        lay.addLayout(hdr)

        # AP table
        self.table = QTableWidget(); self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["BSSID", "VENDOR", "SSID", "CH", "SIGNAL", "ENC"])
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 160); self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(3, 50); self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 100)
        lay.addWidget(self.table, 1)

    def load_aps(self, nearby_aps: dict):
        """nearby_aps: {bssid: {ssid, channel, signal, last_seen, encryption}}"""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(nearby_aps))
        for row, (bssid, info) in enumerate(nearby_aps.items()):
            self.table.setRowHeight(row, 36)
            # BSSID
            b = QTableWidgetItem(bssid.upper())
            b.setFont(QFont("IBM Plex Mono", 11)); b.setForeground(QColor("#e8eef2"))
            self.table.setItem(row, 0, b)
            # Vendor
            vendor = lookup_vendor(bssid)
            v = QTableWidgetItem(vendor if vendor else "unknown")
            v.setFont(QFont("IBM Plex Mono", 11))
            v.setForeground(QColor("#00d4ff") if vendor else QColor("#4a4a4a"))
            self.table.setItem(row, 1, v)
            # SSID
            s = QTableWidgetItem(info.get("ssid", "Hidden"))
            s.setFont(QFont("IBM Plex Mono", 12)); s.setForeground(QColor("#e8eef2"))
            self.table.setItem(row, 2, s)
            # Channel
            ch = QTableWidgetItem(str(info.get("channel", "?")))
            ch.setFont(QFont("IBM Plex Mono", 11)); ch.setForeground(QColor("#00d4ff"))
            ch.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, ch)
            # Signal (color-coded)
            sig = info.get("signal", -100)
            if sig > -50:
                color = self.SIGNAL_COLORS["good"]
            elif sig > -70:
                color = self.SIGNAL_COLORS["fair"]
            else:
                color = self.SIGNAL_COLORS["weak"]
            si = QTableWidgetItem(f"{sig} dBm")
            si.setFont(QFont("IBM Plex Mono", 11)); si.setForeground(QColor(color))
            si.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, si)
            # Encryption
            enc = info.get("encryption", "?")
            ei = QTableWidgetItem(enc)
            ei.setFont(QFont("IBM Plex Mono", 11))
            ei.setForeground(QColor("#00ff88") if "WPA" in enc else QColor("#ff3355"))
            ei.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 5, ei)
        self.table.setSortingEnabled(True)
        self.ap_count_lbl.setText(f"{len(nearby_aps)} APs")


# ── Analytics page ──────────────────────────────────────────────────────────────

class HeatmapCell(QWidget):
    """Single cell in the hourly heatmap."""
    def __init__(self, value=0, max_val=1, parent=None):
        super().__init__(parent)
        self.value = value; self.max_val = max(max_val, 1)
        self.setFixedSize(28, 28); self.setToolTip(f"{value} attacks")

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        ratio = min(self.value / self.max_val, 1.0)
        if ratio > 0.7:
            color = QColor(224, 86, 86, int(80 + 175 * ratio))
        elif ratio > 0.3:
            color = QColor(200, 148, 42, int(60 + 175 * ratio))
        elif ratio > 0:
            color = QColor(78, 201, 148, int(40 + 140 * ratio))
        else:
            color = QColor(30, 30, 30, 120)
        p.setBrush(QBrush(color)); p.setPen(Qt.NoPen)
        p.drawRoundedRect(1, 1, 26, 26, 4, 4)
        if self.value > 0:
            p.setPen(QPen(QColor(255, 255, 255, 200)))
            p.setFont(QFont("IBM Plex Mono", 8))
            p.drawText(self.rect(), Qt.AlignCenter, str(self.value))


class AnalyticsPage(QWidget):
    """Attack analytics: top attackers, type breakdown, hourly heatmap."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 18, 18, 18); lay.setSpacing(14)

        title = QLabel("ANALYTICS"); title.setObjectName("section_label")
        lay.addWidget(title)

        # ── Top section: attackers table + type breakdown side by side
        top_row = QHBoxLayout(); top_row.setSpacing(12)

        # Top 10 Attackers card
        atk_card = QWidget(); atk_card.setObjectName("table_card")
        atk_lay = QVBoxLayout(atk_card); atk_lay.setContentsMargins(14, 12, 14, 12); atk_lay.setSpacing(6)
        atk_title = QLabel("TOP ATTACKERS"); atk_title.setObjectName("section_label")
        atk_lay.addWidget(atk_title)
        self.attackers_table = QTableWidget(); self.attackers_table.setColumnCount(4)
        self.attackers_table.setHorizontalHeaderLabels(["MAC", "VENDOR", "COUNT", "FLAG"])
        self.attackers_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.attackers_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.attackers_table.setShowGrid(False)
        self.attackers_table.verticalHeader().setVisible(False)
        self.attackers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.attackers_table.setColumnWidth(1, 120); self.attackers_table.setColumnWidth(2, 60)
        self.attackers_table.setColumnWidth(3, 50)
        atk_lay.addWidget(self.attackers_table, 1)
        top_row.addWidget(atk_card, 3)

        # Type breakdown card
        type_card = QWidget(); type_card.setObjectName("chart_card")
        self._type_lay = QVBoxLayout(type_card)
        self._type_lay.setContentsMargins(14, 12, 14, 12); self._type_lay.setSpacing(10)
        type_title = QLabel("ATTACK TYPES"); type_title.setObjectName("section_label")
        self._type_lay.addWidget(type_title)
        self._type_lay.addStretch()
        top_row.addWidget(type_card, 1)

        lay.addLayout(top_row, 3)


    def load_top_attackers(self, attacker_data: list, flagged_macs: set):
        """attacker_data: list of (mac, count) sorted descending."""
        self.attackers_table.setRowCount(len(attacker_data))
        for row, (mac, count) in enumerate(attacker_data[:10]):
            self.attackers_table.setRowHeight(row, 34)
            # MAC
            mi = QTableWidgetItem(mac.upper())
            mi.setFont(QFont("IBM Plex Mono", 11)); mi.setForeground(QColor("#e8eef2"))
            self.attackers_table.setItem(row, 0, mi)
            # Vendor
            vendor = lookup_vendor(mac)
            vi = QTableWidgetItem(vendor if vendor else "—")
            vi.setFont(QFont("IBM Plex Mono", 10))
            vi.setForeground(QColor("#00d4ff") if vendor else QColor("#4a4a4a"))
            self.attackers_table.setItem(row, 1, vi)
            # Count
            ci = QTableWidgetItem(str(count))
            ci.setFont(QFont("IBM Plex Mono", 12, QFont.Bold))
            ci.setForeground(QColor("#ff3355")); ci.setTextAlignment(Qt.AlignCenter)
            self.attackers_table.setItem(row, 2, ci)
            # Flag
            is_flagged = mac.upper() in flagged_macs
            fi = QTableWidgetItem("⚠️" if is_flagged else "")
            fi.setTextAlignment(Qt.AlignCenter)
            if is_flagged:
                for col in range(4):
                    item = self.attackers_table.item(row, col)
                    if item:
                        item.setBackground(QColor(40, 10, 15))
            self.attackers_table.setItem(row, 3, fi)

    def update_type_breakdown(self, type_data: list):
        """type_data: list of (name, pct, color)"""
        # Clear old entries (keep first label + stretch)
        while self._type_lay.count() > 1:
            item = self._type_lay.takeAt(1)
            if item.widget(): item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget(): sub.widget().deleteLater()

        for name, pct, col in type_data:
            row = QHBoxLayout(); row.setSpacing(8)
            nl = QLabel(name); nl.setFixedWidth(90)
            nl.setStyleSheet("font-size:11px;color:#666;font-family:'IBM Plex Mono',monospace;")
            row.addWidget(nl)
            mb = MiniBar(pct, col); row.addWidget(mb, 1)
            pl = QLabel(f"{pct}%"); pl.setFixedWidth(36); pl.setAlignment(Qt.AlignRight)
            pl.setStyleSheet("font-size:10px;color:#4a4a4a;font-family:'IBM Plex Mono',monospace;")
            row.addWidget(pl)
            self._type_lay.insertLayout(self._type_lay.count(), row)
        self._type_lay.addStretch()



# ── Main window ─────────────────────────────────────────────────────────────────

class WiFiMonitorGUI(QMainWindow):
    def __init__(self, detector=None, username="", drive_uploader=None):
        super().__init__()
        self.detector = detector
        self.db = Database()
        self.username = username
        self.drive_uploader = drive_uploader
        self._dark = True
        self._running = False
        self._quit_from_tray = False
        self.last_logs = []

        self.setWindowTitle("wifiwatch")
        self.setMinimumSize(960, 640)
        self.resize(1120, 700)
        self._build_ui()
        self._apply_theme()
        self._setup_tray()
        self._connect_signals()

        # Load initial data
        self.update_logs()
        self.update_stats()
        self._update_analytics()

        if self.detector:
            try:
                self.detector.sniff_thread.packet_signal.connect(self.update_logs_live)
            except Exception:
                pass

        # Timers
        self._refresh = QTimer(self); self._refresh.timeout.connect(self._poll_db); self._refresh.start(3000)
        self._stats_timer = QTimer(self); self._stats_timer.timeout.connect(self.update_stats); self._stats_timer.start(60000)
        self._analytics_timer = QTimer(self); self._analytics_timer.timeout.connect(self._update_analytics); self._analytics_timer.start(30000)
        self._netmap_timer = QTimer(self); self._netmap_timer.timeout.connect(self._refresh_network_map); self._netmap_timer.start(10000)

        # Auto backup
        if self.drive_uploader:
            try:
                if self.drive_uploader.check_existing_token(self.username):
                    self.start_auto_backup()
            except Exception:
                pass

        logging.debug("GUI initialized")

    def _build_ui(self):
        root = QWidget(); root.setObjectName("root")
        self.setCentralWidget(root)
        main = QHBoxLayout(root); main.setContentsMargins(0, 0, 0, 0); main.setSpacing(0)

        # ── Sidebar
        self._sidebar = QWidget(); self._sidebar.setObjectName("sidebar")
        self._sidebar.setFixedWidth(52)
        sb = QVBoxLayout(self._sidebar); sb.setContentsMargins(9, 14, 9, 14)
        sb.setSpacing(4); sb.setAlignment(Qt.AlignTop)

        NAV = [("⊞", "dashboard", 0), ("≡", "logs", 1), ("◎", "network", 2), ("△", "threats", 3)]
        self._nav_btns = []
        for icon, tip, idx in NAV:
            b = QPushButton(icon); b.setObjectName("nav_btn"); b.setFixedSize(34, 34); b.setToolTip(tip)
            b.clicked.connect(lambda _, i=idx: self._switch_page(i))
            sb.addWidget(b); self._nav_btns.append(b)
        sb.addStretch()

        self._theme_btn = QPushButton("◐"); self._theme_btn.setObjectName("nav_btn")
        self._theme_btn.setFixedSize(34, 34); self._theme_btn.setToolTip("toggle theme")
        self._theme_btn.clicked.connect(self._toggle_theme); sb.addWidget(self._theme_btn)

        settings_btn = QPushButton("⚙"); settings_btn.setObjectName("nav_btn")
        settings_btn.setFixedSize(34, 34); settings_btn.setToolTip("settings")
        settings_btn.clicked.connect(lambda: self._switch_page(4)); sb.addWidget(settings_btn)
        main.addWidget(self._sidebar)

        # ── Right pane
        right = QWidget(); right.setObjectName("root")
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)

        # top bar
        topbar = QWidget(); topbar.setObjectName("topbar"); topbar.setFixedHeight(40)
        tbl = QHBoxLayout(topbar); tbl.setContentsMargins(16, 0, 14, 0); tbl.setSpacing(10)
        self._pulse = PulseDot(); tbl.addWidget(self._pulse)
        self._status_lbl = QLabel("stopped"); self._status_lbl.setObjectName("status_label")
        tbl.addWidget(self._status_lbl); tbl.addStretch()

        self._user_lbl = QLabel(f"user: {self.username}")
        self._user_lbl.setStyleSheet("color:#4a4a4a;font-size:11px;font-family:'IBM Plex Mono',monospace;")
        tbl.addWidget(self._user_lbl)

        self._stop_btn = QPushButton("start"); self._stop_btn.setObjectName("stop_btn")
        self._stop_btn.setProperty("running", "false")
        self._stop_btn.clicked.connect(self.toggle_monitoring); tbl.addWidget(self._stop_btn)
        rl.addWidget(topbar)

        div = QFrame(); div.setObjectName("divider"); rl.addWidget(div)

        # stacked pages
        self._stack = QStackedWidget()
        self._dashboard = DashboardPage()
        self._logs_page = LogsPage()
        self._settings_page = SettingsPage(self.detector, self.username)
        self._network_page = NetworkMapPage()
        self._analytics_page = AnalyticsPage()
        self._stack.addWidget(self._dashboard)       # 0
        self._stack.addWidget(self._logs_page)        # 1
        self._stack.addWidget(self._network_page)     # 2
        self._stack.addWidget(self._analytics_page)   # 3
        self._stack.addWidget(self._settings_page)    # 4
        rl.addWidget(self._stack)
        main.addWidget(right)
        self._switch_page(0)

    def _connect_signals(self):
        """Wire all button signals to backend methods."""
        d = self._dashboard
        d.export_csv_btn.clicked.connect(self.export_logs)
        d.export_pdf_btn.clicked.connect(self.export_pdf)

        lp = self._logs_page
        lp.refresh_btn.clicked.connect(self.update_all_logs)
        lp.export_csv_btn.clicked.connect(self.export_logs)
        lp.export_pdf_btn.clicked.connect(self.export_pdf)
        lp.upload_btn.clicked.connect(self.upload_to_drive)
        lp.log_search.textChanged.connect(self._apply_log_filters)
        lp.type_filter.currentTextChanged.connect(self._apply_log_filters)
        lp.severity_filter.currentTextChanged.connect(self._apply_log_filters)
        lp.clear_filter_btn.clicked.connect(self._clear_log_filters)
        lp.table.customContextMenuRequested.connect(self._logs_context_menu)

        sp = self._settings_page
        sp.set_iface_btn.clicked.connect(self.change_interface)
        sp.change_user_btn.clicked.connect(self.change_username)
        sp.change_pass_btn.clicked.connect(self.change_password)
        sp.update_email_btn.clicked.connect(self.update_email_config)
        sp.connect_drive_btn.clicked.connect(self.connect_drive)
        sp.disconnect_drive_btn.clicked.connect(self.disconnect_drive)
        sp.apply_thresh_btn.clicked.connect(self.update_threshold)
        sp.logout_btn.clicked.connect(self.logout)
        sp.email_toggle.stateChanged.connect(self._toggle_email)
        sp.telegram_toggle.stateChanged.connect(self._toggle_telegram)
        sp.ntfy_toggle.stateChanged.connect(self._toggle_ntfy)
        sp.twilio_toggle.stateChanged.connect(self._toggle_twilio)

        # Network map
        self._network_page.refresh_btn.clicked.connect(self._refresh_network_map)

    # ── Navigation & theme ───────────────────────────────────────

    def _switch_page(self, idx):
        self._stack.setCurrentIndex(idx)
        for i, b in enumerate(self._nav_btns):
            b.setProperty("active", "true" if i == idx else "false")
            b.style().unpolish(b); b.style().polish(b)

    def _toggle_theme(self):
        self._dark = not self._dark; self._apply_theme()

    def _apply_theme(self):
        p = DARK if self._dark else LIGHT
        self.setStyleSheet(make_qss(p))

    # ── Monitoring toggle ────────────────────────────────────────

    def toggle_monitoring(self):
        self._running = not self._running
        self._pulse.set_running(self._running)
        if self._running:
            self._stop_btn.setText("stop"); self._stop_btn.setProperty("running", "true")
            iface = "wlan0mon"
            if self.detector:
                iface = getattr(self.detector, 'interface', 'wlan0mon')
                # Connect lightweight signals from background sniff thread
                st = self.detector.sniff_thread
                st.attack_signal.connect(self._on_attack_detected)
                st.ap_update_signal.connect(self._refresh_network_map)
                self.detector.start_monitoring()
            self._status_lbl.setText(f"monitoring  {iface}")
        else:
            self._stop_btn.setText("start"); self._stop_btn.setProperty("running", "false")
            self._status_lbl.setText("stopped")
            if self.detector:
                st = self.detector.sniff_thread
                try:
                    st.attack_signal.disconnect(self._on_attack_detected)
                    st.ap_update_signal.disconnect(self._refresh_network_map)
                except TypeError:
                    pass
                self.detector.stop_monitoring()
        self._stop_btn.style().unpolish(self._stop_btn); self._stop_btn.style().polish(self._stop_btn)
        logging.info(f"Monitoring {'started' if self._running else 'stopped'}")

    def _on_attack_detected(self, attack: dict):
        """Lightweight slot called on main thread when attack detected."""
        self.update_logs()
        self.update_stats()
        sev = attack.get("severity", "medium")
        if sev == "high":
            atype = attack.get("attack_type", "attack")
            src = attack.get("src_mac", "unknown")
            self.show_tray_notification("wifiwatch attack", f"{atype} from {src}", sev)

    def _refresh_network_map(self):
        """Lightweight slot to refresh network map page."""
        if hasattr(self, '_network_map_page'):
            self._network_map_page.refresh(self.detector)

    # ── DB polling & data refresh ────────────────────────────────

    def _poll_db(self):
        if not self._running:
            return
        self.update_logs()
        self.update_stats()

    def update_logs(self):
        logs = self.db.get_recent_logs(50)
        if logs != self.last_logs:
            self._dashboard.load_attacks_from_db(logs)
            self.last_logs = logs

    def update_all_logs(self):
        logs = self.db.get_all_logs()
        t = self._logs_page.table
        t.setRowCount(len(logs))
        for row, log in enumerate(logs):
            attack_type = log[5] if len(log) > 5 and log[5] else "deauth"
            severity = log[6] if len(log) > 6 and log[6] else "medium"
            t.setItem(row, 0, QTableWidgetItem(log[1]))
            t.setItem(row, 1, QTableWidgetItem(attack_type))
            t.setItem(row, 2, QTableWidgetItem(log[2]))
            t.setItem(row, 3, QTableWidgetItem(log[3]))
            t.setItem(row, 4, QTableWidgetItem(log[4]))
            t.setItem(row, 5, QTableWidgetItem(attack_type))
            sv = QTableWidgetItem(severity.upper())
            sv.setForeground(QColor(SEV_COLORS.get(severity, "#666")))
            t.setItem(row, 6, sv)
        self._apply_log_filters()
        self._highlight_flagged_rows()

    def update_stats(self):
        try:
            total = self.db.cursor.execute("SELECT COUNT(*) FROM attacks").fetchone()[0]
            recent = self.db.cursor.execute(
                "SELECT COUNT(*) FROM attacks WHERE timestamp >= datetime('now', '-24 hours', 'localtime')").fetchone()[0]
            flagged = len(self.db.get_flagged_threats())
            self._dashboard.stat_total.set_value(str(total))
            self._dashboard.stat_24h.set_value(str(recent), "#ff3355")
            self._dashboard.stat_flagged.set_value(str(flagged), "#ffaa00")
        except Exception:
            pass

    def update_logs_live(self, packet):
        """Called from sniff thread — defer all work to main thread."""
        try:
            from scapy.all import Dot11Deauth
            if packet.haslayer(Dot11Deauth):
                src = packet.addr2
                severity = "medium"
                if self.detector:
                    _, severity = self.detector._classify_deauth(packet.addr1)
                # Defer UI refresh to main thread (detector already logs to DB)
                QTimer.singleShot(0, self.update_logs)
                QTimer.singleShot(50, self.update_stats)
                if severity == "high":
                    attack_type = "deauth"
                    if self.detector:
                        attack_type, _ = self.detector._classify_deauth(packet.addr1)
                    QTimer.singleShot(0, lambda: self.show_tray_notification(
                        "wifiwatch attack", f"{attack_type} from {src}", severity))
        except Exception:
            pass

    def _refresh_network_map(self):
        """Refresh the network map page from detector's nearby AP data."""
        try:
            if self.detector and hasattr(self.detector, 'nearby_aps'):
                self._network_page.load_aps(self.detector.nearby_aps)
        except Exception:
            pass

    def _update_analytics(self):
        """Refresh bar chart, type breakdown, and analytics page from DB."""
        try:
            logs = self.db.get_all_logs()
            # Hourly distribution for bar chart
            hour_counter = Counter()
            type_counter = Counter()
            mac_counter = Counter()
            for log in logs:
                ts = log[1]
                try:
                    hour = int(ts.split(" ")[1].split(":")[0])
                    hour_counter[hour] += 1
                except (IndexError, ValueError):
                    pass
                atype = log[5] if len(log) > 5 and log[5] else "deauth"
                type_counter[atype] += 1
                src_mac = log[2] if len(log) > 2 else ""
                if src_mac:
                    mac_counter[src_mac] += 1

            # Build bar chart data (24 hours)
            max_h = max(hour_counter.values()) if hour_counter else 1
            bar_data = []
            for h in range(24):
                count = hour_counter.get(h, 0)
                if count == 0:
                    color = "#2b3b4a"  # Deep blue-gray for zero-value baseline
                elif count > max_h * 0.7:
                    color = "#ff3355"
                elif count > max_h * 0.3:
                    color = "#ffaa00"
                else:
                    color = "#00ff88"
                bar_data.append((count, color))
            self._dashboard.bar_chart.set_data(bar_data)

            # Type breakdown
            total = max(len(logs), 1)
            type_colors = {"deauth": "#ff3355", "evil_twin": "#ffaa00", "pmkid": "#bf5af2",
                           "probe_flood": "#00d4ff", "beacon_flood": "#00d4ff", "targeted_deauth": "#ff3355"}
            type_data = []
            for atype, count in type_counter.most_common():
                pct = round(count / total * 100)
                col = type_colors.get(atype, "#5a5a5a")
                type_data.append((atype.replace("_", " "), pct, col))
            self._dashboard.update_type_breakdown(type_data)

            # ── Feed analytics page ──
            # Top attackers
            flagged_set = {f[0] for f in self.db.get_flagged_threats()}
            top_attackers = mac_counter.most_common(10)
            self._analytics_page.load_top_attackers(top_attackers, flagged_set)
            # Type breakdown (analytics page)
            self._analytics_page.update_type_breakdown(type_data)
        except Exception:
            pass

    # ── Log filters ──────────────────────────────────────────────

    def _apply_log_filters(self, _=None):
        lp = self._logs_page
        search = lp.log_search.text().lower().strip()
        type_sel = lp.type_filter.currentText()
        sev_sel = lp.severity_filter.currentText()
        for row in range(lp.table.rowCount()):
            show = True
            if type_sel != "All":
                item = lp.table.item(row, 1)
                if item and item.text().lower() != type_sel.lower(): show = False
            if show and sev_sel != "All":
                item = lp.table.item(row, 6)
                if item and item.text().lower() != sev_sel.lower(): show = False
            if show and search:
                row_text = " ".join(
                    (lp.table.item(row, c).text() if lp.table.item(row, c) else "")
                    for c in range(lp.table.columnCount())).lower()
                if search not in row_text: show = False
            lp.table.setRowHidden(row, not show)

    def _clear_log_filters(self):
        lp = self._logs_page
        lp.log_search.clear(); lp.type_filter.setCurrentIndex(0); lp.severity_filter.setCurrentIndex(0)
        for row in range(lp.table.rowCount()): lp.table.setRowHidden(row, False)

    # ── Threat flagging ──────────────────────────────────────────

    def _logs_context_menu(self, pos):
        t = self._logs_page.table
        row = t.rowAt(pos.y())
        if row < 0: return
        src_item = t.item(row, 2)
        if not src_item: return
        mac = src_item.text().replace("⚠️ ", "").strip()
        menu = QMenu(self)
        if self.db.is_flagged(mac):
            a = QAction(f"✅ Unflag {mac}", self); a.triggered.connect(lambda: self._unflag_mac(mac))
        else:
            a = QAction(f"🚩 Flag {mac}", self); a.triggered.connect(lambda: self._flag_mac(mac))
        menu.addAction(a); menu.exec_(t.viewport().mapToGlobal(pos))

    def _flag_mac(self, mac):
        label, ok = QInputDialog.getText(self, "Flag Threat", f"Label for {mac}:")
        if ok:
            self.db.flag_threat(mac, label)
            QMessageBox.information(self, "Flagged", f"⚠️ {mac} flagged.")
            self._highlight_flagged_rows()

    def _unflag_mac(self, mac):
        self.db.unflag_threat(mac)
        QMessageBox.information(self, "Unflagged", f"✅ {mac} removed.")
        self._highlight_flagged_rows()

    def _highlight_flagged_rows(self):
        flagged = {f[0] for f in self.db.get_flagged_threats()}
        t = self._logs_page.table
        for row in range(t.rowCount()):
            src_item = t.item(row, 2)
            if not src_item: continue
            mac = src_item.text().replace("⚠️ ", "").strip().upper()
            if mac in flagged:
                if not src_item.text().startswith("⚠️"): src_item.setText(f"⚠️ {src_item.text()}")
                for col in range(t.columnCount()):
                    item = t.item(row, col)
                    if item and col != 6:
                        item.setBackground(QColor(180, 30, 30)); item.setForeground(QColor(255, 255, 255))

    # ── Export ───────────────────────────────────────────────────

    def export_logs(self):
        csv_path = os.path.join(log_dir, "attack_logs.csv")
        self.db.export_to_csv(csv_path)
        QMessageBox.information(self, "Success", f"Exported to {csv_path}")

    def export_pdf(self):
        logs = self.db.get_all_logs()
        if not logs: QMessageBox.warning(self, "No Data", "No logs."); return
        ts = time.strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(log_dir, f"attack_report_{ts}.pdf")
        html = f"<html><head><style>body{{font-family:sans-serif}}table{{width:100%;border-collapse:collapse}}th{{background:#0f3460;color:white;padding:6px}}td{{padding:4px;border-bottom:1px solid #ddd}}</style></head><body>"
        html += f"<h1>wifiwatch report</h1><p>Generated: {time.strftime('%Y-%m-%d %H:%M:%S')} | User: {self.username}</p><table><tr><th>Time</th><th>Type</th><th>Src</th><th>Dst</th><th>SSID</th><th>Sev</th></tr>"
        for log in logs:
            sev = log[6] if len(log) > 6 else "medium"
            html += f"<tr><td>{log[1]}</td><td>{log[5]}</td><td>{log[2]}</td><td>{log[3]}</td><td>{log[4]}</td><td>{sev}</td></tr>"
        html += "</table></body></html>"
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat); printer.setOutputFileName(pdf_path)
        doc = QTextDocument(); doc.setHtml(html); doc.print_(printer)
        QMessageBox.information(self, "PDF Exported", f"Saved to {pdf_path}")

    def upload_to_drive(self):
        if not self.drive_uploader: QMessageBox.warning(self, "Error", "No drive uploader."); return
        if self.drive_uploader.upload_logs(self.username, log_dir):
            QMessageBox.information(self, "Success", "Uploaded to Google Drive!")
        else:
            QMessageBox.warning(self, "Error", "Upload failed.")

    # ── Settings actions ─────────────────────────────────────────

    def change_interface(self):
        iface = self._settings_page.interface_combo.currentText()
        if self.detector:
            self.detector.set_interface(iface)
            QMessageBox.information(self, "Success", f"Interface set to {iface}")

    def change_username(self):
        new = self._settings_page.new_username.text().strip()
        if new and self.db.update_username(self.username, new):
            self.username = new; self._user_lbl.setText(f"user: {new}")
            QMessageBox.information(self, "Success", "Username updated.")
            self._settings_page.new_username.clear()

    def change_password(self):
        new = self._settings_page.new_password.text().strip()
        if new and self.db.update_password(self.username, new):
            QMessageBox.information(self, "Success", "Password updated.")
            self._settings_page.new_password.clear()

    def update_email_config(self):
        email = self._settings_page.receiver_email.text().strip()
        if email and self.db.update_email_config(self.username, None, None, email, 'smtp.gmail.com', 587):
            QMessageBox.information(self, "Success", "Email updated.")
            self._settings_page.receiver_email.clear()

    def connect_drive(self):
        if self.drive_uploader and self.drive_uploader.authenticate(self.username):
            QMessageBox.information(self, "Success", "Connected to Google Drive!")
            self.start_auto_backup()

    def disconnect_drive(self):
        if self.drive_uploader:
            self.drive_uploader.disconnect(self.username)
            if hasattr(self, 'backup_timer'): self.backup_timer.stop()
            QMessageBox.information(self, "Success", "Disconnected.")

    def update_threshold(self):
        sp = self._settings_page
        count, window = sp.threshold_count.value(), sp.threshold_window.value()
        if self.detector:
            self.detector.set_threshold(count, window)
            QMessageBox.information(self, "Success", f"Threshold: {count} packets / {window}s")

    def _toggle_email(self, state):
        if self.detector:
            if state:
                cfg = self.db.get_email_config(self.username)
                self.detector.notifier.receiver_email = cfg[3] if cfg else None
            else:
                self.detector.notifier.receiver_email = None

    def _toggle_telegram(self, state):
        if self.detector: self.detector.telegram.enabled = bool(state)

    def _toggle_ntfy(self, state):
        if self.detector: self.detector.ntfy.enabled = bool(state)

    def _toggle_twilio(self, state):
        if self.detector: self.detector.twilio.enabled = bool(state)

    def logout(self):
        reply = QMessageBox.question(self, "Confirm", "Log out?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.drive_uploader: self.drive_uploader.upload_logs(self.username, log_dir)
            self.close()
            from auth import LoginDialog
            app = QApplication.instance()
            login = LoginDialog()
            if login.exec_():
                new_win = WiFiMonitorGUI(self.detector, login.username, self.drive_uploader)
                new_win.show(); app.exec_()

    # ── System tray ──────────────────────────────────────────────

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        self._tray = QSystemTrayIcon(self)
        px = QPixmap(16, 16); px.fill(Qt.transparent)
        qp = QPainter(px); qp.setRenderHint(QPainter.Antialiasing)
        qp.setBrush(QBrush(QColor(78, 201, 148))); qp.setPen(Qt.NoPen)
        qp.drawEllipse(2, 2, 12, 12); qp.end()
        self._tray.setIcon(QIcon(px)); self._tray.setToolTip("wifiwatch")
        menu = QMenu()
        menu.addAction(QAction("open", self, triggered=self.show))
        menu.addAction(QAction("toggle monitoring", self, triggered=self.toggle_monitoring))
        menu.addSeparator()
        menu.addAction(QAction("quit", self, triggered=self._quit_app))
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(lambda r: self.show() if r == QSystemTrayIcon.DoubleClick else None)
        self._tray.show()

    def show_tray_notification(self, title, message, severity="medium"):
        if hasattr(self, '_tray'):
            icon = {
                "high": QSystemTrayIcon.Critical, "crit": QSystemTrayIcon.Critical,
                "medium": QSystemTrayIcon.Warning, "low": QSystemTrayIcon.Information,
            }.get(severity, QSystemTrayIcon.Information)
            self._tray.showMessage(title, message, icon, 5000)

    def closeEvent(self, e):
        if self._quit_from_tray:
            e.accept()
        elif hasattr(self, '_tray'):
            e.ignore(); self.hide()
            self._tray.showMessage("wifiwatch", "running in background", QSystemTrayIcon.Information, 2000)
        else:
            e.accept()

    def _quit_app(self):
        self._quit_from_tray = True
        if self.detector:
            try: self.detector.stop_monitoring()
            except Exception: pass
        if hasattr(self, '_tray'): self._tray.hide()
        QApplication.quit()

    def notify_attack(self, attack):
        sev = attack.get("severity", "")
        msg = f"{sev} — {attack.get('attack_type','')} from {attack.get('src_mac','')} ({attack.get('ssid','')})"
        if sev in ("crit", "high"):
            self._dashboard.alert.set_text(msg)
        self.show_tray_notification("wifiwatch attack detected", msg, sev)
        self._poll_db()

    def start_auto_backup(self):
        self.backup_timer = QTimer()
        self.backup_timer.timeout.connect(lambda: self.drive_uploader.upload_logs(self.username, log_dir))
        self.backup_timer.start(3600000)


# ── Entry point ─────────────────────────────────────────────────────────────────

def launch_gui(detector=None, db=None):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("wifiwatch")
    win = WiFiMonitorGUI(detector=detector)
    win.show()
    return app, win


if __name__ == "__main__":
    app, win = launch_gui()
    sys.exit(app.exec_())


