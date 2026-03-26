import sys
import time
import logging
import csv
import os
from logging.handlers import RotatingFileHandler
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QTableWidget, QTableWidgetItem, 
                             QVBoxLayout, QHBoxLayout, QWidget, QLabel, QFrame, QSizePolicy, 
                             QStackedWidget, QLineEdit, QMessageBox, QComboBox, QSpinBox, QCheckBox,
                             QGroupBox, QSystemTrayIcon, QMenu, QAction, QInputDialog)
from PyQt5.QtCore import QTimer, Qt, QDateTime
from PyQt5.QtGui import QColor, QIcon, QPixmap, QPainter, QTextDocument
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtChart import QChart, QChartView, QLineSeries
from scapy.all import Dot11Deauth
from wifi_detector import WiFiDetector
from database import Database
from auth import LoginDialog
from oui_lookup import lookup_vendor

# Configure logging with size-based rotation
from config import PROJECT_DIR, LOG_PATH, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT, DEAUTH_THRESHOLD_COUNT, DEAUTH_THRESHOLD_WINDOW
log_dir = PROJECT_DIR
log_path = LOG_PATH
os.makedirs(log_dir, exist_ok=True)
logger = logging.getLogger()
if not logger.handlers:
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))
    handler = RotatingFileHandler(log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

class WiFiMonitorGUI(QMainWindow):
    def __init__(self, detector, username, drive_uploader):
        super().__init__()
        self.detector = detector
        self.db = Database()
        self.username = username
        self.drive_uploader = drive_uploader
        self.is_dark_mode = True
        self.last_logs = []
        self._quit_from_tray = False
        self.init_ui()
        self._init_tray()
        self.update_logs()
        self.update_stats()
        if self.detector:
            self.detector.sniff_thread.packet_signal.connect(self.update_logs_live)
            logging.debug("Signal connected to update_logs_live")
        # Check for existing Drive token and start auto-backup if present
        if self.drive_uploader.check_existing_token(self.username):
            self.start_auto_backup()

    def init_ui(self):
        self.showMaximized()
        self.setWindowTitle("WiFi Attack Detector")

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        sidebar = QFrame()
        sidebar.setFixedWidth(250)
        sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setAlignment(Qt.AlignTop)
        
        sidebar_label = QLabel("WiFi Monitor")
        sidebar_label.setStyleSheet("font-size: 20px; font-weight: bold; padding: 20px;")
        sidebar_layout.addWidget(sidebar_label)
        
        self.dashboard_btn = QPushButton("Dashboard")
        self.logs_btn = QPushButton("Logs")
        self.network_btn = QPushButton("Network Map")
        self.analytics_btn = QPushButton("Analytics")
        self.settings_btn = QPushButton("Settings")
        for btn in [self.dashboard_btn, self.logs_btn, self.network_btn, self.analytics_btn, self.settings_btn]:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet("padding: 15px; font-size: 16px;")
            sidebar_layout.addWidget(btn)
        sidebar_layout.addStretch()

        self.content_stack = QStackedWidget()
        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.content_stack, stretch=1)

        self.content_stack.addWidget(self.create_dashboard_page())
        self.content_stack.addWidget(self.create_logs_page())
        self.content_stack.addWidget(self.create_network_page())
        self.content_stack.addWidget(self.create_analytics_page())
        self.content_stack.addWidget(self.create_settings_page())

        self.dashboard_btn.clicked.connect(lambda: self.content_stack.setCurrentIndex(0))
        self.logs_btn.clicked.connect(lambda: self.content_stack.setCurrentIndex(1))
        self.network_btn.clicked.connect(lambda: self.content_stack.setCurrentIndex(2))
        self.analytics_btn.clicked.connect(lambda: self.content_stack.setCurrentIndex(3))
        self.settings_btn.clicked.connect(lambda: self.content_stack.setCurrentIndex(4))

        self.apply_theme()

        self.logs_timer = QTimer()
        self.logs_timer.timeout.connect(self.update_logs)
        self.logs_timer.start(5000)
        
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_stats)
        self.stats_timer.start(60000)

        self.network_timer = QTimer()
        self.network_timer.timeout.connect(self.update_network_map)
        self.network_timer.start(3000)

        self.analytics_timer = QTimer()
        self.analytics_timer.timeout.connect(self.update_analytics)
        self.analytics_timer.start(30000)

        logging.debug("GUI initialized")

    def _init_tray(self):
        """Set up system tray icon with context menu."""
        # Create a simple shield icon programmatically (no external file needed)
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QColor(0, 255, 136))  # green
        painter.setPen(Qt.NoPen)
        # Simple shield shape
        painter.drawEllipse(8, 8, 48, 48)
        painter.setBrush(QColor(26, 26, 46))  # dark center
        painter.drawEllipse(16, 16, 32, 32)
        painter.end()

        self.tray_icon = QSystemTrayIcon(QIcon(pixmap), self)
        self.tray_icon.setToolTip("WiFi Attack Detector")

        # Context menu
        tray_menu = QMenu()
        show_action = QAction("Show / Hide", self)
        show_action.triggered.connect(self._toggle_window)
        monitor_action = QAction("Start Monitoring", self)
        monitor_action.triggered.connect(self.toggle_monitoring)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_app)

        tray_menu.addAction(show_action)
        tray_menu.addAction(monitor_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()
        logging.debug("System tray icon initialized")

    def _toggle_window(self):
        if self.isVisible():
            self.hide()
        else:
            self.showMaximized()
            self.activateWindow()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._toggle_window()

    def closeEvent(self, event):
        """Minimize to tray instead of quitting."""
        if self._quit_from_tray:
            event.accept()
        else:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "WiFi Attack Detector",
                "Running in background. Right-click tray icon for options.",
                QSystemTrayIcon.Information,
                2000
            )

    def _quit_app(self):
        self._quit_from_tray = True
        if self.detector and self.detector.sniff_thread.isRunning():
            self.detector.stop_monitoring()
        self.tray_icon.hide()
        QApplication.quit()

    def show_tray_notification(self, title: str, message: str, severity: str = "medium"):
        """Show a tray balloon notification for an attack."""
        icon_type = {
            "high": QSystemTrayIcon.Critical,
            "medium": QSystemTrayIcon.Warning,
            "low": QSystemTrayIcon.Information,
        }.get(severity, QSystemTrayIcon.Information)
        self.tray_icon.showMessage(title, message, icon_type, 5000)

    def create_dashboard_page(self):
        dashboard = QWidget()
        content_layout = QVBoxLayout(dashboard)

        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_title = QLabel("Dashboard")
        header_title.setStyleSheet("font-size: 24px; font-weight: bold;")
        header_user = QLabel(f"User: {self.username}", objectName="header_user")
        self.theme_btn = QPushButton("Switch to Light Mode")
        self.theme_btn.clicked.connect(self.toggle_theme)
        header_layout.addWidget(header_title)
        header_layout.addStretch()
        header_layout.addWidget(header_user)
        header_layout.addWidget(self.theme_btn)

        stats_frame = QFrame()
        stats_layout = QHBoxLayout(stats_frame)
        self.total_attacks = QLabel("Total Attacks: 0")
        self.recent_attacks = QLabel("Recent Attacks (24h): 0")
        for stat in [self.total_attacks, self.recent_attacks]:
            stat.setStyleSheet("font-size: 18px; padding: 10px;")
            stats_layout.addWidget(stat)
        stats_layout.addStretch()

        self.live_logs = QTableWidget()
        self.live_logs.setColumnCount(6)
        self.live_logs.setHorizontalHeaderLabels(["Time", "Type", "Source MAC", "Target MAC", "SSID", "Severity"])
        self.live_logs.setSortingEnabled(True)
        self.live_logs.setEditTriggers(QTableWidget.NoEditTriggers)

        chart = QChart()
        self.chart_series = QLineSeries()
        chart.addSeries(self.chart_series)
        chart.createDefaultAxes()
        chart.setTitle("Attack Frequency")
        chart_view = QChartView(chart)
        chart_view.setMinimumHeight(200)

        self.start_stop_btn = QPushButton("Start Monitoring")
        self.start_stop_btn.clicked.connect(self.toggle_monitoring)
        self.start_stop_btn.setStyleSheet("font-size: 18px; padding: 15px; font-weight: bold;")

        content_layout.addWidget(header)
        content_layout.addWidget(stats_frame)
        content_layout.addWidget(chart_view)
        content_layout.addWidget(self.live_logs, stretch=1)
        content_layout.addWidget(self.start_stop_btn)
        logging.debug("Dashboard page created")
        return dashboard

    def create_logs_page(self):
        logs_page = QWidget()
        logs_layout = QVBoxLayout(logs_page)

        logs_title = QLabel("Attack Logs")
        logs_title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        logs_layout.addWidget(logs_title)

        # Search and filter bar
        filter_frame = QFrame()
        filter_layout = QHBoxLayout(filter_frame)

        filter_layout.addWidget(QLabel("🔍"))
        self.log_search = QLineEdit()
        self.log_search.setPlaceholderText("Search logs (MAC, SSID, type...)")
        self.log_search.textChanged.connect(self._apply_log_filters)
        filter_layout.addWidget(self.log_search, stretch=2)

        filter_layout.addWidget(QLabel("Type:"))
        self.type_filter = QComboBox()
        self.type_filter.addItems(["All", "deauth", "targeted_deauth", "evil_twin",
                                   "probe_flood", "beacon_flood", "pmkid"])
        self.type_filter.currentTextChanged.connect(self._apply_log_filters)
        filter_layout.addWidget(self.type_filter)

        filter_layout.addWidget(QLabel("Severity:"))
        self.severity_filter = QComboBox()
        self.severity_filter.addItems(["All", "high", "medium", "low"])
        self.severity_filter.currentTextChanged.connect(self._apply_log_filters)
        filter_layout.addWidget(self.severity_filter)

        clear_btn = QPushButton("Clear Filters")
        clear_btn.clicked.connect(self._clear_log_filters)
        filter_layout.addWidget(clear_btn)

        logs_layout.addWidget(filter_frame)

        self.all_logs = QTableWidget()
        self.all_logs.setColumnCount(7)
        self.all_logs.setHorizontalHeaderLabels(["Time", "Type", "Source MAC", "Target MAC", "SSID", "Attack Type", "Severity"])
        self.all_logs.setSortingEnabled(True)
        self.all_logs.setEditTriggers(QTableWidget.NoEditTriggers)
        self.all_logs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.all_logs.customContextMenuRequested.connect(self._logs_context_menu)
        logs_layout.addWidget(self.all_logs, stretch=1)

        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        refresh_btn = QPushButton("Refresh Logs")
        refresh_btn.clicked.connect(self.update_all_logs)
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self.export_logs)
        pdf_btn = QPushButton("Export PDF")
        pdf_btn.clicked.connect(self.export_pdf)
        upload_btn = QPushButton("Upload to Drive")
        upload_btn.clicked.connect(self.upload_to_drive)
        for btn in [refresh_btn, export_btn, pdf_btn, upload_btn]:
            btn.setStyleSheet("font-size: 16px; padding: 10px;")
            button_layout.addWidget(btn)
        logs_layout.addWidget(button_frame)

        self.update_all_logs()
        logging.debug("Logs page created")
        return logs_page

    def create_network_page(self):
        network_page = QWidget()
        network_layout = QVBoxLayout(network_page)

        header = QHBoxLayout()
        title = QLabel("Network Map — Nearby Access Points")
        title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        self.ap_count_label = QLabel("APs detected: 0")
        self.ap_count_label.setStyleSheet("font-size: 16px; padding: 10px;")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.ap_count_label)
        network_layout.addLayout(header)

        self.ap_table = QTableWidget()
        self.ap_table.setColumnCount(7)
        self.ap_table.setHorizontalHeaderLabels([
            "BSSID", "Vendor", "SSID", "Channel", "Signal (dBm)", "Encryption", "Last Seen"
        ])
        self.ap_table.setSortingEnabled(True)
        self.ap_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ap_table.setColumnWidth(0, 160)
        self.ap_table.setColumnWidth(1, 140)
        self.ap_table.setColumnWidth(2, 180)
        self.ap_table.setColumnWidth(3, 70)
        self.ap_table.setColumnWidth(4, 110)
        self.ap_table.setColumnWidth(5, 110)
        self.ap_table.setColumnWidth(6, 90)
        network_layout.addWidget(self.ap_table, stretch=1)

        logging.debug("Network page created")
        return network_page

    def create_analytics_page(self):
        analytics_page = QWidget()
        layout = QVBoxLayout(analytics_page)

        title = QLabel("📊 Attack Pattern Analysis")
        title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # --- Top Attackers ---
        top_group = QGroupBox("🏆 Top 10 Attackers")
        top_layout = QVBoxLayout(top_group)
        self.top_attackers_table = QTableWidget()
        self.top_attackers_table.setColumnCount(5)
        self.top_attackers_table.setHorizontalHeaderLabels(
            ["Source MAC", "Vendor", "Attacks", "Last Seen", "Flagged"]
        )
        self.top_attackers_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.top_attackers_table.setColumnWidth(0, 170)
        self.top_attackers_table.setColumnWidth(1, 140)
        self.top_attackers_table.setColumnWidth(2, 80)
        self.top_attackers_table.setColumnWidth(3, 160)
        self.top_attackers_table.setColumnWidth(4, 70)
        top_layout.addWidget(self.top_attackers_table)
        layout.addWidget(top_group)

        # --- Middle row: Attack Type + Hourly Distribution side-by-side ---
        mid_layout = QHBoxLayout()

        type_group = QGroupBox("🔬 Attack Type Breakdown")
        type_layout = QVBoxLayout(type_group)
        self.type_breakdown_table = QTableWidget()
        self.type_breakdown_table.setColumnCount(3)
        self.type_breakdown_table.setHorizontalHeaderLabels(["Attack Type", "Count", "Share"])
        self.type_breakdown_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.type_breakdown_table.setColumnWidth(0, 150)
        self.type_breakdown_table.setColumnWidth(1, 70)
        self.type_breakdown_table.setColumnWidth(2, 200)
        type_layout.addWidget(self.type_breakdown_table)
        mid_layout.addWidget(type_group)

        hour_group = QGroupBox("🕐 Hourly Attack Distribution")
        hour_layout = QVBoxLayout(hour_group)
        self.hourly_table = QTableWidget()
        self.hourly_table.setColumnCount(3)
        self.hourly_table.setHorizontalHeaderLabels(["Hour", "Attacks", "Bar"])
        self.hourly_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.hourly_table.setColumnWidth(0, 60)
        self.hourly_table.setColumnWidth(1, 70)
        self.hourly_table.setColumnWidth(2, 200)
        hour_layout.addWidget(self.hourly_table)
        mid_layout.addWidget(hour_group)

        layout.addLayout(mid_layout)

        self.update_analytics()
        logging.debug("Analytics page created")
        return analytics_page

    def update_analytics(self):
        """Refresh all analytics widgets from the database."""
        from collections import Counter
        logs = self.db.get_all_logs()

        # --- Top 10 Attackers ---
        mac_counter = Counter()
        mac_last_seen = {}
        for log in logs:
            src = log[2]
            mac_counter[src] += 1
            if src not in mac_last_seen:
                mac_last_seen[src] = log[1]

        top10 = mac_counter.most_common(10)
        self.top_attackers_table.setRowCount(len(top10))
        for row, (mac, count) in enumerate(top10):
            self.top_attackers_table.setItem(row, 0, QTableWidgetItem(mac))
            self.top_attackers_table.setItem(row, 1, QTableWidgetItem(lookup_vendor(mac)))
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.top_attackers_table.setItem(row, 2, count_item)
            self.top_attackers_table.setItem(row, 3, QTableWidgetItem(mac_last_seen.get(mac, "")))
            flagged = "⚠️ YES" if self.db.is_flagged(mac) else "—"
            flag_item = QTableWidgetItem(flagged)
            flag_item.setTextAlignment(Qt.AlignCenter)
            if self.db.is_flagged(mac):
                flag_item.setBackground(QColor(180, 30, 30))
                flag_item.setForeground(QColor(255, 255, 255))
            self.top_attackers_table.setItem(row, 4, flag_item)

        # --- Attack Type Breakdown ---
        type_counter = Counter()
        for log in logs:
            atype = log[5] if len(log) > 5 and log[5] else "deauth"
            type_counter[atype] += 1
        total = max(len(logs), 1)

        type_sorted = type_counter.most_common()
        self.type_breakdown_table.setRowCount(len(type_sorted))
        for row, (atype, count) in enumerate(type_sorted):
            self.type_breakdown_table.setItem(row, 0, QTableWidgetItem(atype))
            c_item = QTableWidgetItem(str(count))
            c_item.setTextAlignment(Qt.AlignCenter)
            self.type_breakdown_table.setItem(row, 1, c_item)
            pct = count / total * 100
            bar_len = int(pct / 5)  # ~20 chars max
            bar = "█" * bar_len + f"  {pct:.1f}%"
            self.type_breakdown_table.setItem(row, 2, QTableWidgetItem(bar))

        # --- Hourly Distribution ---
        hour_counter = Counter()
        for log in logs:
            ts = log[1]
            try:
                hour = int(ts.split(" ")[1].split(":")[0])
                hour_counter[hour] += 1
            except (IndexError, ValueError):
                pass

        max_hourly = max(hour_counter.values()) if hour_counter else 1
        self.hourly_table.setRowCount(24)
        for h in range(24):
            self.hourly_table.setItem(h, 0, QTableWidgetItem(f"{h:02d}:00"))
            count = hour_counter.get(h, 0)
            c_item = QTableWidgetItem(str(count))
            c_item.setTextAlignment(Qt.AlignCenter)
            self.hourly_table.setItem(h, 1, c_item)
            bar_len = int((count / max_hourly) * 20) if max_hourly else 0
            bar_item = QTableWidgetItem("█" * bar_len)
            # Color intensity by attack density
            if count > max_hourly * 0.7:
                bar_item.setForeground(QColor(220, 50, 50))   # red = hot
            elif count > max_hourly * 0.3:
                bar_item.setForeground(QColor(230, 150, 30))  # orange
            else:
                bar_item.setForeground(QColor(50, 180, 50))   # green = calm
            self.hourly_table.setItem(h, 2, bar_item)

        logging.debug("Analytics updated")

    def update_network_map(self):
        if not self.detector:
            return
        aps = self.detector.nearby_aps
        self.ap_count_label.setText(f"APs detected: {len(aps)}")

        # Sort by signal strength (strongest first)
        sorted_aps = sorted(aps.items(), key=lambda x: x[1].get("signal", -100), reverse=True)

        self.ap_table.setSortingEnabled(False)
        self.ap_table.setRowCount(len(sorted_aps))
        for row, (bssid, info) in enumerate(sorted_aps):
            self.ap_table.setItem(row, 0, QTableWidgetItem(bssid))
            self.ap_table.setItem(row, 1, QTableWidgetItem(lookup_vendor(bssid)))
            self.ap_table.setItem(row, 2, QTableWidgetItem(info.get("ssid", "Hidden")))
            self.ap_table.setItem(row, 3, QTableWidgetItem(str(info.get("channel", "?"))))

            # Signal with color coding
            signal = info.get("signal", -100)
            sig_item = QTableWidgetItem(str(signal))
            if signal > -50:
                sig_item.setBackground(QColor(50, 180, 50))      # green = strong
            elif signal > -70:
                sig_item.setBackground(QColor(230, 150, 30))     # orange = medium
            else:
                sig_item.setBackground(QColor(220, 50, 50))      # red = weak
            sig_item.setForeground(QColor(255, 255, 255))
            self.ap_table.setItem(row, 4, sig_item)

            self.ap_table.setItem(row, 5, QTableWidgetItem(info.get("encryption", "?")))
            self.ap_table.setItem(row, 6, QTableWidgetItem(info.get("last_seen", "")))
        self.ap_table.setSortingEnabled(True)

    def create_settings_page(self):
        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)

        settings_title = QLabel("Settings")
        settings_title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        settings_layout.addWidget(settings_title)

        interface_frame = QFrame()
        interface_layout = QHBoxLayout(interface_frame)
        self.interface_combo = QComboBox()
        self.interface_combo.addItems(self.detector.get_available_interfaces() if self.detector else ["wlan0"])
        change_interface_btn = QPushButton("Set Interface")
        change_interface_btn.clicked.connect(self.change_interface)
        interface_layout.addWidget(QLabel("WiFi Interface:"))
        interface_layout.addWidget(self.interface_combo)
        interface_layout.addWidget(change_interface_btn)

        username_frame = QFrame()
        username_layout = QHBoxLayout(username_frame)
        self.new_username = QLineEdit()
        change_username_btn = QPushButton("Change Username")
        change_username_btn.clicked.connect(self.change_username)
        username_layout.addWidget(QLabel("New Username:"))
        username_layout.addWidget(self.new_username)
        username_layout.addWidget(change_username_btn)

        password_frame = QFrame()
        password_layout = QHBoxLayout(password_frame)
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.Password)
        change_password_btn = QPushButton("Change Password")
        change_password_btn.clicked.connect(self.change_password)
        password_layout.addWidget(QLabel("New Password:"))
        password_layout.addWidget(self.new_password)
        password_layout.addWidget(change_password_btn)

        email_frame = QFrame()
        email_layout = QVBoxLayout(email_frame)
        self.receiver_email = QLineEdit()
        self.receiver_email.setToolTip("Enter the email address to receive notifications")
        update_email_btn = QPushButton("Update Notification Email")
        update_email_btn.clicked.connect(self.update_email_config)
        email_layout.addWidget(QLabel("Notification Email:"))
        email_layout.addWidget(self.receiver_email)
        email_layout.addWidget(update_email_btn)

        drive_frame = QFrame()
        drive_layout = QHBoxLayout(drive_frame)
        connect_drive_btn = QPushButton("Connect Google Drive")
        connect_drive_btn.clicked.connect(self.connect_drive)
        disconnect_drive_btn = QPushButton("Disconnect Google Drive")
        disconnect_drive_btn.clicked.connect(self.disconnect_drive)
        drive_layout.addWidget(connect_drive_btn)
        drive_layout.addWidget(disconnect_drive_btn)

        logout_btn = QPushButton("Log Out")
        logout_btn.clicked.connect(self.logout)
        logout_btn.setStyleSheet("font-size: 16px; padding: 10px;")
        settings_layout.addWidget(interface_frame)
        settings_layout.addWidget(username_frame)
        settings_layout.addWidget(password_frame)
        settings_layout.addWidget(email_frame)
        settings_layout.addWidget(drive_frame)

        # Threshold settings
        threshold_frame = QFrame()
        threshold_layout = QHBoxLayout(threshold_frame)
        threshold_layout.addWidget(QLabel("Deauth Threshold:"))
        self.threshold_count_spin = QSpinBox()
        self.threshold_count_spin.setRange(1, 1000)
        self.threshold_count_spin.setValue(DEAUTH_THRESHOLD_COUNT)
        self.threshold_count_spin.setToolTip("Number of deauth packets to trigger alert")
        threshold_layout.addWidget(self.threshold_count_spin)
        threshold_layout.addWidget(QLabel("packets in"))
        self.threshold_window_spin = QSpinBox()
        self.threshold_window_spin.setRange(1, 300)
        self.threshold_window_spin.setValue(DEAUTH_THRESHOLD_WINDOW)
        self.threshold_window_spin.setSuffix(" sec")
        self.threshold_window_spin.setToolTip("Time window in seconds")
        threshold_layout.addWidget(self.threshold_window_spin)
        update_threshold_btn = QPushButton("Apply Threshold")
        update_threshold_btn.clicked.connect(self.update_threshold)
        threshold_layout.addWidget(update_threshold_btn)
        settings_layout.addWidget(threshold_frame)

        # Alert channel toggles
        channels_group = QGroupBox("Alert Channels")
        channels_group.setStyleSheet("QGroupBox { font-size: 16px; font-weight: bold; padding-top: 15px; }")
        channels_layout = QVBoxLayout(channels_group)

        self.email_toggle = QCheckBox("📧  Email (Gmail SMTP)")
        self.email_toggle.setChecked(bool(self.detector and self.detector.notifier.receiver_email))
        self.email_toggle.setToolTip("Send attack alerts via email")
        self.email_toggle.stateChanged.connect(self._toggle_email)

        self.telegram_toggle = QCheckBox("💬  Telegram Bot")
        self.telegram_toggle.setChecked(bool(self.detector and self.detector.telegram.enabled))
        self.telegram_toggle.setToolTip("Send attack alerts via Telegram")
        self.telegram_toggle.stateChanged.connect(self._toggle_telegram)

        self.ntfy_toggle = QCheckBox("🔔  ntfy.sh Push Notifications")
        self.ntfy_toggle.setChecked(bool(self.detector and self.detector.ntfy.enabled))
        self.ntfy_toggle.setToolTip("Send attack alerts via ntfy.sh")
        self.ntfy_toggle.stateChanged.connect(self._toggle_ntfy)

        self.twilio_toggle = QCheckBox("📱  Twilio SMS")
        self.twilio_toggle.setChecked(bool(self.detector and self.detector.twilio.enabled))
        self.twilio_toggle.setToolTip("Send attack alerts via SMS")
        self.twilio_toggle.stateChanged.connect(self._toggle_twilio)

        for toggle in [self.email_toggle, self.telegram_toggle, self.ntfy_toggle, self.twilio_toggle]:
            toggle.setStyleSheet("QCheckBox { font-size: 14px; padding: 5px; }")
            channels_layout.addWidget(toggle)

        settings_layout.addWidget(channels_group)

        settings_layout.addWidget(logout_btn)
        settings_layout.addStretch()
        logging.debug("Settings page created")
        return settings_page

    def toggle_monitoring(self):
        if self.detector and self.detector.sniff_thread.isRunning():
            self.detector.stop_monitoring()
            self.start_stop_btn.setText("Start Monitoring")
            logging.info("Monitoring stopped")
        elif self.detector:
            self.detector.start_monitoring()
            self.start_stop_btn.setText("Stop Monitoring")
            logging.info("Monitoring started")

    # ── Threat flagging context menu ───────────────────────────

    def _logs_context_menu(self, pos):
        """Show right-click menu on the logs table."""
        row = self.all_logs.rowAt(pos.y())
        if row < 0:
            return
        src_item = self.all_logs.item(row, 2)  # Source MAC column
        if not src_item:
            return
        mac = src_item.text().replace("⚠️ ", "").strip()

        menu = QMenu(self)
        if self.db.is_flagged(mac):
            unflag_action = QAction(f"✅ Unflag {mac}", self)
            unflag_action.triggered.connect(lambda: self._unflag_mac(mac))
            menu.addAction(unflag_action)
        else:
            flag_action = QAction(f"🚩 Flag {mac} as Threat", self)
            flag_action.triggered.connect(lambda: self._flag_mac(mac))
            menu.addAction(flag_action)
        menu.exec_(self.all_logs.viewport().mapToGlobal(pos))

    def _flag_mac(self, mac):
        from PyQt5.QtWidgets import QInputDialog
        label, ok = QInputDialog.getText(self, "Flag Threat", f"Optional label for {mac}:")
        if ok:
            self.db.flag_threat(mac, label)
            QMessageBox.information(self, "Flagged", f"⚠️ {mac} flagged as threat.")
            self._highlight_flagged_rows()

    def _unflag_mac(self, mac):
        self.db.unflag_threat(mac)
        QMessageBox.information(self, "Unflagged", f"✅ {mac} removed from threat list.")
        self._highlight_flagged_rows()

    def _highlight_flagged_rows(self):
        """Highlight rows with flagged MACs in red across logs table."""
        flagged = {f[0] for f in self.db.get_flagged_threats()}
        threat_bg = QColor(180, 30, 30)
        threat_fg = QColor(255, 255, 255)

        for row in range(self.all_logs.rowCount()):
            src_item = self.all_logs.item(row, 2)
            if not src_item:
                continue
            mac = src_item.text().replace("⚠️ ", "").strip().upper()
            if mac in flagged:
                # Add warning prefix if not already there
                if not src_item.text().startswith("⚠️"):
                    src_item.setText(f"⚠️ {src_item.text()}")
                for col in range(self.all_logs.columnCount()):
                    item = self.all_logs.item(row, col)
                    if item and col != 6:  # don't override severity colors
                        item.setBackground(threat_bg)
                        item.setForeground(threat_fg)
            else:
                # Remove warning prefix if present
                if src_item.text().startswith("⚠️ "):
                    src_item.setText(src_item.text()[3:])


    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.theme_btn.setText("Switch to Light Mode" if self.is_dark_mode else "Switch to Dark Mode")
        self.apply_theme()
        logging.debug(f"Theme switched to {'dark' if self.is_dark_mode else 'light'}")

    def apply_theme(self):
        if self.is_dark_mode:
            self.setStyleSheet("""
                QMainWindow { background-color: #1a1a2e; color: #00ff88; }
                QFrame { background-color: #16213e; color: #00ff88; border-radius: 6px; }
                QTableWidget {
                    background-color: #0f3460; color: #e0e0e0;
                    border: 1px solid #1a5276; gridline-color: #1a5276;
                    selection-background-color: #1a5276;
                }
                QHeaderView::section {
                    background-color: #1a5276; color: #00ff88;
                    padding: 6px; border: 1px solid #0f3460; font-weight: bold;
                }
                QPushButton {
                    background-color: #0f3460; color: #00ff88;
                    border: 1px solid #1a5276; border-radius: 5px; padding: 8px;
                }
                QPushButton:hover { background-color: #1a5276; }
                QPushButton:pressed { background-color: #00b4d8; color: #000; }
                QLabel { color: #00ff88; }
                QLineEdit {
                    background-color: #16213e; color: #00ff88;
                    border: 1px solid #1a5276; border-radius: 4px; padding: 4px;
                }
                QComboBox {
                    background-color: #16213e; color: #00ff88;
                    border: 1px solid #1a5276; border-radius: 4px;
                }
                QSpinBox {
                    background-color: #16213e; color: #00ff88;
                    border: 1px solid #1a5276; border-radius: 4px;
                }
                QCheckBox { color: #e0e0e0; spacing: 8px; }
                QCheckBox::indicator { width: 18px; height: 18px; }
                QCheckBox::indicator:checked { background-color: #00ff88; border-radius: 3px; }
                QCheckBox::indicator:unchecked { background-color: #333; border: 1px solid #555; border-radius: 3px; }
                QGroupBox {
                    color: #00ff88; border: 1px solid #1a5276;
                    border-radius: 6px; margin-top: 10px; padding-top: 20px;
                }
                QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
                QScrollBar:vertical {
                    background: #16213e; width: 10px; border-radius: 5px;
                }
                QScrollBar::handle:vertical { background: #1a5276; border-radius: 5px; }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow { background-color: #f8f9fa; color: #212529; }
                QFrame { background-color: #ffffff; color: #212529; border-radius: 6px; }
                QTableWidget {
                    background-color: #ffffff; color: #212529;
                    border: 1px solid #dee2e6; gridline-color: #dee2e6;
                    selection-background-color: #e3f2fd;
                }
                QHeaderView::section {
                    background-color: #e9ecef; color: #212529;
                    padding: 6px; border: 1px solid #dee2e6; font-weight: bold;
                }
                QPushButton {
                    background-color: #e9ecef; color: #212529;
                    border: 1px solid #ced4da; border-radius: 5px; padding: 8px;
                }
                QPushButton:hover { background-color: #dee2e6; }
                QPushButton:pressed { background-color: #0d6efd; color: #fff; }
                QLabel { color: #212529; }
                QLineEdit {
                    background-color: #ffffff; color: #212529;
                    border: 1px solid #ced4da; border-radius: 4px; padding: 4px;
                }
                QComboBox {
                    background-color: #ffffff; color: #212529;
                    border: 1px solid #ced4da; border-radius: 4px;
                }
                QSpinBox {
                    background-color: #ffffff; color: #212529;
                    border: 1px solid #ced4da; border-radius: 4px;
                }
                QCheckBox { color: #212529; spacing: 8px; }
                QCheckBox::indicator { width: 18px; height: 18px; }
                QCheckBox::indicator:checked { background-color: #0d6efd; border-radius: 3px; }
                QCheckBox::indicator:unchecked { background-color: #fff; border: 1px solid #adb5bd; border-radius: 3px; }
                QGroupBox {
                    color: #212529; border: 1px solid #dee2e6;
                    border-radius: 6px; margin-top: 10px; padding-top: 20px;
                }
                QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
                QScrollBar:vertical {
                    background: #f8f9fa; width: 10px; border-radius: 5px;
                }
                QScrollBar::handle:vertical { background: #ced4da; border-radius: 5px; }
            """)
        logging.debug("Theme applied")

    def _severity_color(self, severity: str) -> QColor:
        """Return a background color for the given severity level."""
        colors = {
            "high": QColor(220, 50, 50),      # red
            "medium": QColor(230, 150, 30),    # orange
            "low": QColor(50, 180, 50),        # green
        }
        return colors.get(severity, QColor(100, 100, 100))

    def _make_severity_item(self, severity: str) -> QTableWidgetItem:
        """Create a colored QTableWidgetItem for severity."""
        item = QTableWidgetItem(severity.upper())
        item.setBackground(self._severity_color(severity))
        item.setForeground(QColor(255, 255, 255))
        return item

    # ── Alert channel toggles ──────────────────────────────────

    def _toggle_email(self, state):
        if self.detector:
            if state:
                # Re-read receiver email from DB
                cfg = self.db.get_email_config(self.username)
                self.detector.notifier.receiver_email = cfg[3] if cfg else None
            else:
                self.detector.notifier.receiver_email = None
            logging.info(f"Email alerts {'enabled' if state else 'disabled'}")

    def _toggle_telegram(self, state):
        if self.detector:
            self.detector.telegram.enabled = bool(state)
            logging.info(f"Telegram alerts {'enabled' if state else 'disabled'}")

    def _toggle_ntfy(self, state):
        if self.detector:
            self.detector.ntfy.enabled = bool(state)
            logging.info(f"ntfy alerts {'enabled' if state else 'disabled'}")

    def _toggle_twilio(self, state):
        if self.detector:
            self.detector.twilio.enabled = bool(state)
            logging.info(f"Twilio SMS alerts {'enabled' if state else 'disabled'}")

    def update_logs(self):
        logs = self.db.get_recent_logs()
        if logs != self.last_logs:
            self.live_logs.setRowCount(len(logs))
            for row, log in enumerate(logs):
                attack_type = log[5] if len(log) > 5 and log[5] else "deauth"
                severity = log[6] if len(log) > 6 and log[6] else "medium"
                self.live_logs.setItem(row, 0, QTableWidgetItem(log[1]))
                self.live_logs.setItem(row, 1, QTableWidgetItem(attack_type))
                self.live_logs.setItem(row, 2, QTableWidgetItem(log[2]))
                self.live_logs.setItem(row, 3, QTableWidgetItem(log[3]))
                self.live_logs.setItem(row, 4, QTableWidgetItem(log[4]))
                self.live_logs.setItem(row, 5, self._make_severity_item(severity))
            self.last_logs = logs
            self.update_chart()
            logging.debug("Updated recent logs")

    def update_all_logs(self):
        logs = self.db.get_all_logs()
        self.all_logs.setRowCount(len(logs))
        for row, log in enumerate(logs):
            attack_type = log[5] if len(log) > 5 and log[5] else "deauth"
            severity = log[6] if len(log) > 6 and log[6] else "medium"
            self.all_logs.setItem(row, 0, QTableWidgetItem(log[1]))
            self.all_logs.setItem(row, 1, QTableWidgetItem(attack_type))
            self.all_logs.setItem(row, 2, QTableWidgetItem(log[2]))
            self.all_logs.setItem(row, 3, QTableWidgetItem(log[3]))
            self.all_logs.setItem(row, 4, QTableWidgetItem(log[4]))
            self.all_logs.setItem(row, 5, QTableWidgetItem(attack_type))
            self.all_logs.setItem(row, 6, self._make_severity_item(severity))
        logging.debug("Updated all logs")
        self._apply_log_filters()
        self._highlight_flagged_rows()

    def _apply_log_filters(self, _=None):
        """Filter visible rows based on search text, type, and severity."""
        search = self.log_search.text().lower().strip()
        type_sel = self.type_filter.currentText()
        sev_sel = self.severity_filter.currentText()

        for row in range(self.all_logs.rowCount()):
            show = True
            # Attack type filter (column 1 or 5)
            if type_sel != "All":
                item = self.all_logs.item(row, 1)
                if item and item.text().lower() != type_sel.lower():
                    show = False
            # Severity filter (column 6)
            if show and sev_sel != "All":
                item = self.all_logs.item(row, 6)
                if item and item.text().lower() != sev_sel.lower():
                    show = False
            # Text search across all columns
            if show and search:
                row_text = " ".join(
                    (self.all_logs.item(row, c).text() if self.all_logs.item(row, c) else "")
                    for c in range(self.all_logs.columnCount())
                ).lower()
                if search not in row_text:
                    show = False
            self.all_logs.setRowHidden(row, not show)

    def _clear_log_filters(self):
        """Reset all filter controls and show all rows."""
        self.log_search.clear()
        self.type_filter.setCurrentIndex(0)
        self.severity_filter.setCurrentIndex(0)
        for row in range(self.all_logs.rowCount()):
            self.all_logs.setRowHidden(row, False)

    def update_logs_live(self, packet):
        if packet.haslayer(Dot11Deauth):
            src = packet.addr2
            dst = packet.addr1
            ssid = self.detector.ssid_map.get(src, "Unknown") if self.detector else "Unknown"
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

            # Classify attack
            attack_type, severity = "deauth", "medium"
            if self.detector:
                attack_type, severity = self.detector._classify_deauth(dst)

            attack = {
                "timestamp": timestamp,
                "src_mac": src,
                "dst_mac": dst,
                "ssid": ssid,
                "attack_type": attack_type,
                "severity": severity
            }
            self.db.log_attack(attack)

            # Update live logs table
            row = self.live_logs.rowCount()
            self.live_logs.insertRow(row)
            self.live_logs.setItem(row, 0, QTableWidgetItem(timestamp))
            self.live_logs.setItem(row, 1, QTableWidgetItem(attack_type))
            self.live_logs.setItem(row, 2, QTableWidgetItem(src))
            self.live_logs.setItem(row, 3, QTableWidgetItem(dst))
            self.live_logs.setItem(row, 4, QTableWidgetItem(ssid))
            self.live_logs.setItem(row, 5, self._make_severity_item(severity))

            # Update all logs table
            arow = self.all_logs.rowCount()
            self.all_logs.insertRow(arow)
            self.all_logs.setItem(arow, 0, QTableWidgetItem(timestamp))
            self.all_logs.setItem(arow, 1, QTableWidgetItem(attack_type))
            self.all_logs.setItem(arow, 2, QTableWidgetItem(src))
            self.all_logs.setItem(arow, 3, QTableWidgetItem(dst))
            self.all_logs.setItem(arow, 4, QTableWidgetItem(ssid))
            self.all_logs.setItem(arow, 5, QTableWidgetItem(attack_type))
            self.all_logs.setItem(arow, 6, self._make_severity_item(severity))

            self.update_chart()
            logging.debug(f"Live log: {attack_type} ({severity}) {src} -> {dst}")

    def update_chart(self):
        logs = self.db.get_recent_logs(100)
        self.chart_series.clear()
        for log in logs:
            timestamp = QDateTime.fromString(log[1], "yyyy-MM-dd hh:mm:ss")
            self.chart_series.append(timestamp.toMSecsSinceEpoch(), 1)
        logging.debug("Updated chart")

    def update_stats(self):
        total = self.db.cursor.execute("SELECT COUNT(*) FROM attacks").fetchone()[0]
        recent = self.db.cursor.execute(
            "SELECT COUNT(*) FROM attacks WHERE timestamp >= datetime('now', '-24 hours', 'localtime')").fetchone()[0]
        self.total_attacks.setText(f"Total Attacks: {total}")
        self.recent_attacks.setText(f"Recent Attacks (24h): {recent}")
        logging.debug(f"Updated stats: Total={total}, Recent={recent}")

    def update_threshold(self):
        count = self.threshold_count_spin.value()
        window = self.threshold_window_spin.value()
        if self.detector:
            self.detector.set_threshold(count, window)
            QMessageBox.information(self, "Success", f"Threshold set to {count} packets in {window} seconds.")
            logging.info(f"Threshold updated via GUI: {count} packets / {window}s")
        else:
            QMessageBox.warning(self, "Error", "No detector available.")
            logging.warning("Threshold update failed: No detector")

    def change_interface(self):
        interface = self.interface_combo.currentText()
        if self.detector:
            self.detector.set_interface(interface)
            QMessageBox.information(self, "Success", f"Interface set to {interface}")
            logging.info(f"Interface changed to {interface}")
        else:
            QMessageBox.warning(self, "Error", "No detector available")
            logging.warning("Failed to change interface: No detector")

    def change_username(self):
        new_username = self.new_username.text().strip()
        if new_username:
            reply = QMessageBox.question(self, "Confirm", "Are you sure you want to change your username?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes and self.db.update_username(self.username, new_username):
                self.username = new_username
                self.findChild(QLabel, "header_user").setText(f"User: {self.username}")
                QMessageBox.information(self, "Success", "Username updated successfully!")
                self.new_username.clear()
                logging.info(f"Username changed to {new_username}")
            else:
                QMessageBox.warning(self, "Error", "Failed to update username. It may already exist.")
                logging.warning(f"Failed to change username to {new_username}")
        else:
            QMessageBox.warning(self, "Error", "Username cannot be empty.")
            logging.warning("Username change failed: Empty input")

    def change_password(self):
        new_password = self.new_password.text().strip()
        if new_password:
            reply = QMessageBox.question(self, "Confirm", "Are you sure you want to change your password?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes and self.db.update_password(self.username, new_password):
                QMessageBox.information(self, "Success", "Password updated successfully!")
                self.new_password.clear()
                logging.info(f"Password changed for {self.username}")
            else:
                QMessageBox.warning(self, "Error", "Failed to update password.")
                logging.warning(f"Failed to change password for {self.username}")
        else:
            QMessageBox.warning(self, "Error", "Password cannot be empty.")
            logging.warning("Password change failed: Empty input")

    def update_email_config(self):
        receiver_email = self.receiver_email.text().strip()
        if receiver_email:
            reply = QMessageBox.question(self, "Confirm", "Are you sure you want to update your notification email?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                try:
                    if self.db.update_email_config(self.username, None, None, receiver_email, 'smtp.gmail.com', 587):
                        QMessageBox.information(self, "Success", "Notification email updated successfully!")
                        self.receiver_email.clear()
                        logging.info(f"Notification email updated for {self.username}")
                    else:
                        QMessageBox.warning(self, "Error", "Failed to update notification email.")
                        logging.warning(f"Failed to update email settings for {self.username}")
                except sqlite3.IntegrityError:
                    QMessageBox.warning(self, "Error", f"Email {receiver_email} already in use.")
                    logging.warning(f"Email {receiver_email} already in use")
        else:
            QMessageBox.warning(self, "Error", "Notification email must be filled.")
            logging.warning("Incomplete email config fields")

    def export_logs(self):
        csv_path = os.path.join(log_dir, "attack_logs.csv")
        self.db.export_to_csv(csv_path)
        QMessageBox.information(self, "Success", f"Logs exported to {csv_path}")
        logging.info("Logs exported to attack_logs.csv")

    def export_pdf(self):
        """Export attack logs as a styled PDF report using Qt's built-in QPrinter."""
        logs = self.db.get_all_logs()
        if not logs:
            QMessageBox.warning(self, "No Data", "No attack logs to export.")
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(log_dir, f"attack_report_{timestamp}.pdf")

        # Build HTML report
        severity_colors = {"high": "#dc3232", "medium": "#e6961e", "low": "#32b432"}
        total = len(logs)
        high_count = sum(1 for l in logs if l[6] == "high")
        medium_count = sum(1 for l in logs if l[6] == "medium")

        html = f"""
        <html><head><style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #222; }}
            h1 {{ color: #0f3460; border-bottom: 3px solid #00ff88; padding-bottom: 8px; }}
            .stats {{ background: #f0f4f8; padding: 12px; border-radius: 8px; margin: 10px 0; }}
            .stat-item {{ display: inline-block; margin-right: 30px; font-size: 14px; }}
            .stat-value {{ font-size: 22px; font-weight: bold; color: #0f3460; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 11px; }}
            th {{ background: #0f3460; color: white; padding: 8px; text-align: left; }}
            td {{ padding: 6px 8px; border-bottom: 1px solid #ddd; }}
            tr:nth-child(even) {{ background: #f8f9fa; }}
            .severity-high {{ color: white; background: #dc3232; padding: 2px 8px; border-radius: 4px; }}
            .severity-medium {{ color: white; background: #e6961e; padding: 2px 8px; border-radius: 4px; }}
            .severity-low {{ color: white; background: #32b432; padding: 2px 8px; border-radius: 4px; }}
        </style></head><body>
        <h1>🛡️ WiFi Attack Detector — Report</h1>
        <p><b>Generated:</b> {time.strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp;
           <b>User:</b> {self.username}</p>
        <div class="stats">
            <span class="stat-item"><span class="stat-value">{total}</span> Total Attacks</span>
            <span class="stat-item"><span class="stat-value" style="color:#dc3232">{high_count}</span> High</span>
            <span class="stat-item"><span class="stat-value" style="color:#e6961e">{medium_count}</span> Medium</span>
            <span class="stat-item"><span class="stat-value" style="color:#32b432">{total - high_count - medium_count}</span> Low</span>
        </div>
        <table>
        <tr><th>Time</th><th>Attack Type</th><th>Source MAC</th><th>Target MAC</th><th>SSID</th><th>Severity</th></tr>
        """

        for log in logs:
            ts, src, dst, ssid, atype = log[1], log[2], log[3], log[4], log[5]
            sev = log[6] if len(log) > 6 else "medium"
            sev_class = f"severity-{sev}"
            html += f'<tr><td>{ts}</td><td>{atype}</td><td>{src}</td><td>{dst}</td><td>{ssid}</td>'
            html += f'<td><span class="{sev_class}">{sev.upper()}</span></td></tr>\n'

        html += "</table></body></html>"

        # Render to PDF
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(pdf_path)
        printer.setPageSize(QPrinter.A4)

        doc = QTextDocument()
        doc.setHtml(html)
        doc.print_(printer)

        QMessageBox.information(self, "PDF Exported", f"Report saved to:\n{pdf_path}")
        logging.info(f"PDF report exported to {pdf_path}")

    def upload_to_drive(self):
        if self.drive_uploader.upload_logs(self.username, log_dir):
            QMessageBox.information(self, "Success", "Logs uploaded to Google Drive!")
            logging.info(f"Manual upload triggered by {self.username}")
        else:
            QMessageBox.warning(self, "Error", "Failed to upload logs. Please connect Google Drive.")
            logging.warning(f"Manual upload failed for {self.username}")

    def connect_drive(self):
        if self.drive_uploader.authenticate(self.username):
            QMessageBox.information(self, "Success", "Connected to Google Drive!")
            logging.info(f"Drive connected for {self.username}")
            self.start_auto_backup()
        else:
            QMessageBox.warning(self, "Error", "Failed to connect to Google Drive.")
            logging.error(f"Drive connection failed for {self.username}")

    def disconnect_drive(self):
        reply = QMessageBox.question(self, "Confirm", "Are you sure you want to disconnect Google Drive?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.drive_uploader.disconnect(self.username)
            if hasattr(self, 'backup_timer'):
                self.backup_timer.stop()
            QMessageBox.information(self, "Success", "Disconnected from Google Drive.")
            logging.info(f"Disconnected Drive for {self.username}")

    def logout(self):
        reply = QMessageBox.question(self, "Confirm Logout", "Are you sure you want to log out?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.drive_uploader.upload_logs(self.username, log_dir)
            self.close()
            app = QApplication.instance()
            login = LoginDialog()
            if login.exec_():
                new_window = WiFiMonitorGUI(self.detector, login.username, self.drive_uploader)
                new_window.show()
                logging.info(f"User {self.username} logged out, new session started")
                app.exec_()
            else:
                logging.info(f"User {self.username} logged out without new login")

    def start_auto_backup(self):
        self.backup_timer = QTimer()
        self.backup_timer.timeout.connect(lambda: self.drive_uploader.upload_logs(self.username, log_dir))
        self.backup_timer.start(3600000)
        logging.info(f"Auto-backup started for {self.username}")
