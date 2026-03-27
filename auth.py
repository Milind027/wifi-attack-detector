"""
Authentication dialog for WiFi Attack Detector.
Provides login and registration UI using PyQt5.
"""

import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QStackedWidget, QWidget, QFrame
)
from PyQt5.QtCore import Qt
from database import Database


class LoginDialog(QDialog):
    """Login / Register dialog. Sets self.username on successful login."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.username: str = ""
        self.db = Database()
        self.init_ui()

    def init_ui(self) -> None:
        self.setWindowTitle("WiFi Attack Detector — Login")
        self.setFixedSize(420, 380)
        self.setStyleSheet("""
            QDialog {
                background-color: #050a0e;
                font-family: 'IBM Plex Mono', 'Fira Code', 'Consolas', monospace;
            }
            QLabel {
                color: #b8c4ce; font-size: 12px; letter-spacing: 0.5px;
            }
            QLineEdit {
                background-color: #0a1118; color: #b8c4ce;
                border: 1px solid #0d2137; padding: 10px 12px;
                font-size: 13px; border-radius: 6px;
                font-family: 'IBM Plex Mono', monospace;
            }
            QLineEdit:focus { border: 1px solid #00ff88; }
            QPushButton {
                background-color: #0f1a24; color: #3d6070;
                border: 1px solid #0d2137; padding: 10px;
                font-size: 12px; border-radius: 6px;
                font-family: 'IBM Plex Mono', monospace;
                letter-spacing: 1px;
            }
            QPushButton:hover { border-color: #00ff88; color: #00ff88; }
            QPushButton#primary {
                background-color: #00ff88; color: #050a0e;
                font-weight: bold; border: none;
            }
            QPushButton#primary:hover { background-color: #00cc6a; }
            QPushButton#switch_btn {
                background-color: transparent; border: none;
                color: #00d4ff; font-size: 11px;
            }
            QPushButton#switch_btn:hover { color: #00ff88; }
        """)

        main_layout = QVBoxLayout(self)

        # Title
        title = QLabel("🛡️ WiFi Attack Detector")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        main_layout.addWidget(title)

        # Stacked widget for login / register pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self._create_login_page())
        self.stack.addWidget(self._create_register_page())
        main_layout.addWidget(self.stack)

    # ── Login Page ──────────────────────────────────────────────

    def _create_login_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        page_title = QLabel("Login")
        page_title.setAlignment(Qt.AlignCenter)
        page_title.setStyleSheet("font-size: 18px; font-weight: bold; padding-bottom: 5px;")
        layout.addWidget(page_title)

        layout.addWidget(QLabel("Username or Email:"))
        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText("Enter username or email")
        layout.addWidget(self.login_input)

        layout.addWidget(QLabel("Password:"))
        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.Password)
        self.login_password.setPlaceholderText("Enter password")
        layout.addWidget(self.login_password)

        login_btn = QPushButton("Login")
        login_btn.setObjectName("primary")
        login_btn.clicked.connect(self._handle_login)
        layout.addWidget(login_btn)

        switch_btn = QPushButton("Don't have an account? Register")
        switch_btn.setObjectName("switch_btn")
        switch_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        layout.addWidget(switch_btn)

        layout.addStretch()
        return page

    # ── Register Page ───────────────────────────────────────────

    def _create_register_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        page_title = QLabel("Register")
        page_title.setAlignment(Qt.AlignCenter)
        page_title.setStyleSheet("font-size: 18px; font-weight: bold; padding-bottom: 5px;")
        layout.addWidget(page_title)

        layout.addWidget(QLabel("Username:"))
        self.reg_username = QLineEdit()
        self.reg_username.setPlaceholderText("Choose a username")
        layout.addWidget(self.reg_username)

        layout.addWidget(QLabel("Email (for notifications):"))
        self.reg_email = QLineEdit()
        self.reg_email.setPlaceholderText("your@email.com")
        layout.addWidget(self.reg_email)

        layout.addWidget(QLabel("Password:"))
        self.reg_password = QLineEdit()
        self.reg_password.setEchoMode(QLineEdit.Password)
        self.reg_password.setPlaceholderText("Choose a password")
        layout.addWidget(self.reg_password)

        register_btn = QPushButton("Register")
        register_btn.setObjectName("primary")
        register_btn.clicked.connect(self._handle_register)
        layout.addWidget(register_btn)

        switch_btn = QPushButton("Already have an account? Login")
        switch_btn.setObjectName("switch_btn")
        switch_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        layout.addWidget(switch_btn)

        layout.addStretch()
        return page

    # ── Handlers ────────────────────────────────────────────────

    def _handle_login(self) -> None:
        login_input = self.login_input.text().strip()
        password = self.login_password.text().strip()

        if not login_input or not password:
            QMessageBox.warning(self, "Error", "Please fill in all fields.")
            return

        if self.db.verify_user(login_input, password):
            self.username = self.db.get_username_by_login(login_input)
            logging.info(f"User '{self.username}' logged in successfully")
            self.accept()
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid username/email or password.")
            logging.warning(f"Failed login attempt for: {login_input}")

    def _handle_register(self) -> None:
        username = self.reg_username.text().strip()
        email = self.reg_email.text().strip()
        password = self.reg_password.text().strip()

        if not username or not email or not password:
            QMessageBox.warning(self, "Error", "Please fill in all fields.")
            return

        if len(password) < 4:
            QMessageBox.warning(self, "Error", "Password must be at least 4 characters.")
            return

        if self.db.add_user(username, password, receiver_email=email):
            QMessageBox.information(self, "Success", "Account created! You can now login.")
            logging.info(f"New user registered: {username}")
            # Switch to login page
            self.login_input.setText(username)
            self.login_password.clear()
            self.stack.setCurrentIndex(0)
        else:
            QMessageBox.warning(self, "Error", "Username or email already exists.")
            logging.warning(f"Failed registration: {username} / {email}")

    def closeEvent(self, event) -> None:
        """Clean up database connection on close."""
        self.db.close()
        super().closeEvent(event)
