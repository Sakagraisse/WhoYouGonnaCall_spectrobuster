import sys
import os
import copy
import json
import subprocess
import time
import pty
import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QWidget, QFileDialog, QLabel, QComboBox, QTextEdit, QGroupBox, QMessageBox,
                             QLineEdit, QSizePolicy, QScrollArea, QFormLayout, QGridLayout, QCheckBox,
                             QFrame)
from PyQt6.QtCore import Qt, QTimer, QSocketNotifier, QThread, pyqtSignal

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
except ImportError:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.path as _mpath

# Workaround: matplotlib.path.Path.__deepcopy__ is broken on Python 3.14+
# (infinite recursion via copy.deepcopy(super(), memo)).
# Path is immutable — returning self is safe and breaks the recursion.
def _path_deepcopy_fix(self, memo):
    memo[id(self)] = self
    return self
_mpath.Path.__deepcopy__ = _path_deepcopy_fix

import re
import numpy as np
import colour
try:
    from .argyll import build_argyll_env, resolve_spotread_command
    from .domain.colorimetry import wavelength_to_rgb, xyz_to_rgb, yxy_to_xyz
except ImportError:
    from argyll import build_argyll_env, resolve_spotread_command
    from domain.colorimetry import wavelength_to_rgb, xyz_to_rgb, yxy_to_xyz


class InstrumentEnumeratorThread(QThread):
    """Runs `spotread -?` and parses the instrument list."""
    instruments_found = pyqtSignal(dict)  # {index(int): name(str)}
    debug_output      = pyqtSignal(str)   # raw spotread output for debugging

    def __init__(self, timeout_s=8):
        super().__init__()
        self.timeout_s = timeout_s

    def run(self):
        instruments = {}
        raw = ""
        started_at = time.perf_counter()

        try:
            env = build_argyll_env()
            spotread_cmd = resolve_spotread_command()

            proc = subprocess.run(
                [spotread_cmd, "-?"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # merge stderr so we catch either stream
                stdin=subprocess.DEVNULL,
                env=env,
                timeout=self.timeout_s,
            )
            raw = proc.stdout.decode("utf-8", errors="replace")

        except subprocess.TimeoutExpired as e:
            # Keep partial output if spotread takes too long.
            raw = e.stdout.decode("utf-8", errors="replace") if e.stdout else ""
            if not raw:
                raw = "[spotread -? a expiré sans produire de sortie — vérifiez ArgyllCMS]"
        except FileNotFoundError:
            raw = "[spotread non trouvé — ArgyllCMS installé et dans le PATH ?]"
        except Exception as e:
            raw = f"[Erreur énumération: {e}]"

        # Parse all instrument lines globally. Accept single quote, double quote, or plain text.
        for m in re.finditer(r"(?m)^\s*(\d+)\s*=\s*'([^']+)'\s*$", raw):
            instruments[int(m.group(1))] = m.group(2)
        for m in re.finditer(r'(?m)^\s*(\d+)\s*=\s*"([^"]+)"\s*$', raw):
            instruments[int(m.group(1))] = m.group(2)
        for m in re.finditer(r"(?m)^\s*(\d+)\s*=\s*([^\r\n]+)$", raw):
            instruments[int(m.group(1))] = m.group(2).strip().strip("'\"")

        elapsed_s = time.perf_counter() - started_at
        self.debug_output.emit(f"[scan instruments en {elapsed_s:.2f}s]\n" + raw)
        self.instruments_found.emit(instruments)


class SpotreadOneShotThread(QThread):
    """Runs a one-shot spotread command outside the UI thread."""
    output_ready = pyqtSignal(str, bool, float)  # raw output, calibration_only, elapsed_s

    def __init__(self, args, env, timeout_s=120, calibration_only=False):
        super().__init__()
        self.args = args
        self.env = env
        self.timeout_s = timeout_s
        self.calibration_only = calibration_only

    def run(self):
        started_at = time.perf_counter()
        try:
            proc = subprocess.run(
                self.args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=self.env,
                timeout=self.timeout_s,
            )
            raw = proc.stdout.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired as e:
            raw = e.stdout.decode("utf-8", errors="replace") if e.stdout else ""
            raw += "\n[Erreur: spotread a expiré]"
        except Exception as e:
            raw = f"[Erreur spotread one-shot: {e}]"

        elapsed_s = time.perf_counter() - started_at
        self.output_ready.emit(raw, self.calibration_only, elapsed_s)


class SpectrumPlotter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Spectre Plotter & ArgyllCMS Interface')
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #dfe4ea, stop:0.45 #d7dde5, stop:1 #e5eaef);
            }
            QWidget#mainSurface {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #dfe4ea, stop:0.45 #d7dde5, stop:1 #e5eaef);
            }
            QWidget {
                font-size: 12px;
                color: #1f2933;
            }
            QGroupBox {
                font-weight: 600;
                border: 1px solid #d8e1ec;
                border-radius: 10px;
                margin-top: 10px;
                padding: 10px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: #334e68;
            }
            QPushButton {
                background-color: #2f6fda;
                color: white;
                border: none;
                padding: 7px 12px;
                border-radius: 8px;
                min-height: 32px;
                min-width: 80px;
                font-weight: 600;
            }
            QPushButton:disabled {
                background-color: #aabfe8;
            }
            QPushButton:hover:!disabled {
                background-color: #245fc3;
            }
            QPushButton#secondaryButton {
                background-color: #edf2f9;
                color: #243b53;
                border: 1px solid #c8d5e6;
            }
            QPushButton#secondaryButton:hover:!disabled {
                background-color: #e0e9f5;
            }
            QLineEdit, QComboBox {
                background-color: #ffffff;
                border: 1px solid #d3dce6;
                border-radius: 8px;
                padding: 6px;
                min-height: 30px;
            }
            QTextEdit {
                background-color: #ffffff;
                border: 1px solid #d3dce6;
                border-radius: 8px;
                padding: 6px;
            }
            QScrollArea {
                border: none;
            }
            QGroupBox#argyllControlsGroup {
                border: 1px solid #d8e1ec;
                border-radius: 10px;
                background-color: #ffffff;
                padding: 10px;
                margin-top: 10px;
            }
            QGroupBox#argyllControlsGroup::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: #334e68;
            }
        """)

        self.central_widget = QWidget()
        self.central_widget.setObjectName("mainSurface")
        self.setCentralWidget(self.central_widget)

        # Main Layout
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(14, 14, 14, 14)
        self.main_layout.setSpacing(14)

        # --- Left Panel: Controls & Console ---
        self.left_panel = QWidget()
        self.left_panel.setMinimumWidth(320)
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(10)
        self.main_layout.addWidget(self.left_panel, 1)

        # ArgyllCMS Controls Group
        self.controls_group = QGroupBox("ArgyllCMS Controls")
        self.controls_group.setObjectName("argyllControlsGroup")
        self.controls_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        controls_outer = QVBoxLayout()
        controls_outer.setSpacing(8)
        self.controls_group.setLayout(controls_outer)

        # --- Form: Instrument / Mode / Nom ---
        form = QFormLayout()
        form.setSpacing(5)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        instr_row_widget = QWidget()
        instr_row_layout = QHBoxLayout(instr_row_widget)
        instr_row_layout.setContentsMargins(0, 0, 0, 0)
        instr_row_layout.setSpacing(4)
        self.instrument_combo = QComboBox()
        self.instrument_combo.setMinimumWidth(140)
        self.instrument_combo.addItem("-- Recherche... --", None)
        instr_row_layout.addWidget(self.instrument_combo, 1)
        self.refresh_instr_btn = QPushButton("\U0001f504")
        self.refresh_instr_btn.setObjectName("secondaryButton")
        self.refresh_instr_btn.setFixedSize(34, 34)
        self.refresh_instr_btn.setToolTip("Actualiser la liste des instruments")
        self.refresh_instr_btn.clicked.connect(self.enumerate_instruments)
        instr_row_layout.addWidget(self.refresh_instr_btn)
        form.addRow("Instrument :", instr_row_widget)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Emission (Screen) [-e]", "-e")
        self.mode_combo.addItem("Ambient (Spot) [-a]", "-a")
        self.mode_combo.addItem("Projector [-p]", "-p")
        self.mode_combo.addItem("Spot (Reflectance) [Default]", "")
        form.addRow("Mode :", self.mode_combo)

        self.exec_mode_combo = QComboBox()
        self.exec_mode_combo.addItem("Appel unique (-O) [recommandé]", "oneshot")
        self.exec_mode_combo.addItem("Session interactive (PTY)", "interactive")
        self.exec_mode_combo.setCurrentIndex(0)
        self.exec_mode_combo.setVisible(False)

        self.measurement_name_input = QLineEdit()
        self.measurement_name_input.setPlaceholderText("ex: Lampe-01")
        form.addRow("Nom mesure :", self.measurement_name_input)

        controls_outer.addLayout(form)

        self.skip_calibration_checkbox = QCheckBox("Réutiliser calibration si possible (-N)")
        self.skip_calibration_checkbox.setChecked(True)
        controls_outer.addWidget(self.skip_calibration_checkbox)

        self.mode_help_label = QLabel("")
        self.mode_help_label.setWordWrap(True)
        self.mode_help_label.setStyleSheet("color: #444; font-size: 11px; padding: 2px;")
        controls_outer.addWidget(self.mode_help_label)

        self.session_status_label = QLabel("État : prêt")
        self.session_status_label.setWordWrap(True)
        self.session_status_label.setStyleSheet(
            "background-color: #eef4ff; color: #1f4ea3; border: 1px solid #c9daf9; "
            "border-radius: 6px; padding: 6px;"
        )
        controls_outer.addWidget(self.session_status_label)

        # --- Dossier de sauvegarde (inline) ---
        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self.save_folder_input = QLineEdit()
        self.save_folder_input.setReadOnly(True)
        self.save_folder_input.setPlaceholderText("Dossier de sauvegarde...")
        folder_row.addWidget(self.save_folder_input, 1)
        self.change_folder_btn = QPushButton("Parcourir")
        self.change_folder_btn.setObjectName("secondaryButton")
        self.change_folder_btn.setFixedWidth(80)
        self.change_folder_btn.clicked.connect(self.select_save_folder)
        folder_row.addWidget(self.change_folder_btn)
        controls_outer.addLayout(folder_row)

        # --- Action Buttons (grid) ---
        btn_grid = QGridLayout()
        btn_grid.setSpacing(6)

        self.start_btn = QPushButton("▶  Démarrer Session")
        self.start_btn.clicked.connect(self.start_session)
        self.start_btn.setStyleSheet(
            "QPushButton { background-color: #27ae60; min-height: 34px; font-weight: bold; }"
            "QPushButton:hover:!disabled { background-color: #1e8449; }"
            "QPushButton:disabled { background-color: #a9dfbf; }"
        )
        self.start_btn.setVisible(False)

        self.calibrate_btn = QPushButton("⚙  Calibrer")
        self.calibrate_btn.clicked.connect(self.trigger_calibration)
        self.calibrate_btn.setEnabled(True)
        self.calibrate_btn.setMinimumHeight(34)
        btn_grid.addWidget(self.calibrate_btn, 0, 0)

        self.measure_btn = QPushButton("◉  Mesurer")
        self.measure_btn.clicked.connect(self.trigger_measurement)
        self.measure_btn.setEnabled(True)
        self.measure_btn.setMinimumHeight(34)
        btn_grid.addWidget(self.measure_btn, 0, 1)

        self.stop_btn = QPushButton("■  Arrêter Session")
        self.stop_btn.clicked.connect(self.stop_session)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(
            "QPushButton { background-color: #c0392b; min-height: 34px; font-weight: bold; }"
            "QPushButton:hover:!disabled { background-color: #a93226; }"
            "QPushButton:disabled { background-color: #f1948a; }"
        )
        self.stop_btn.setVisible(False)

        controls_outer.addLayout(btn_grid)

        # Calibration status indicator
        self.calib_status_label = QLabel("🔴  Non calibré")
        self.calib_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.calib_status_label.setStyleSheet("color: #c0392b; font-weight: bold; padding: 4px;")
        controls_outer.addWidget(self.calib_status_label)

        self.left_layout.addWidget(self.controls_group)

        self.mode_combo.currentIndexChanged.connect(self._update_mode_guidance)
        self._oneshot_thread = None
        self._oneshot_busy = False
        self._action_in_progress = False
        self._current_action = None
        self._update_mode_guidance()
        self._update_execution_mode_ui()

        # Console Output (collapsible)
        self.console_group = QGroupBox("Sortie Console")
        self.console_group.setCheckable(False)
        console_layout = QVBoxLayout()
        console_layout.setSpacing(6)
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setMinimumHeight(140)
        self.console_output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self.console_output.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: 'Menlo', 'Courier New', monospace;")
        console_layout.addWidget(self.console_output)
        clear_console_btn = QPushButton("Effacer console")
        clear_console_btn.setObjectName("secondaryButton")
        clear_console_btn.clicked.connect(self.console_output.clear)
        console_layout.addWidget(clear_console_btn)
        self.console_group.setLayout(console_layout)
        self.left_layout.addStretch(1)
        self.left_layout.addWidget(self.console_group)

        # Color Equivalence Group
        self.color_group = QGroupBox("Colorimétrie & CRI")
        self.color_layout = QVBoxLayout()
        self.color_layout.setSpacing(4)
        self.color_group.setLayout(self.color_layout)
        self.color_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.color_patch = QLabel()
        self.color_patch.setFixedHeight(18)
        self.color_patch.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.color_patch.setStyleSheet("background-color: gray; border: 1px solid #9aa5b1; border-radius: 5px;")
        self.color_layout.addWidget(self.color_patch)

        self.color_values_label = QLabel("XYZ: - - -\nRGB: - - -\nLab: - - -")
        self.color_values_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.color_values_label.setStyleSheet("font-size: 11px;")
        self.color_values_label.setVisible(False)
        self.color_layout.addWidget(self.color_values_label)

        self.cri_label = QLabel("CRI (Ra): -")
        self.cri_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cri_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.cri_label.setVisible(False)
        self.color_layout.addWidget(self.cri_label)

        self.cri_details_label = QLabel("R9-R15:")
        self.cri_details_label.setStyleSheet("font-size: 11px;")
        self.cri_details_label.setVisible(False)
        self.color_layout.addWidget(self.cri_details_label)

        self.cri_details = QTextEdit()
        self.cri_details.setReadOnly(True)
        self.cri_details.setMaximumHeight(120)
        self.cri_details.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.cri_details.setStyleSheet("font-family: 'Menlo', 'Courier New', monospace; font-size: 10px;")
        self.cri_details.setPlainText("XYZ: -\nRGB: -\nLab: -\nCRI (Ra): -")
        self.color_layout.addWidget(self.cri_details)
        self.color_group.setMaximumHeight(180)

        # --- Right Panel: Spectre + CIE + Historique ---
        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setSpacing(8)
        self.right_layout.setContentsMargins(2, 2, 2, 2)
        self.main_layout.addWidget(self.right_panel, 3)

        self.analysis_row = QHBoxLayout()
        self.analysis_row.setSpacing(6)

        self.spectrum_group = QGroupBox("Spectre")
        spectrum_layout = QVBoxLayout(self.spectrum_group)
        spectrum_layout.setContentsMargins(2, 2, 2, 2)
        self.canvas = FigureCanvas(plt.Figure(figsize=(6.2, 6.2), dpi=100))
        self.canvas.setMinimumSize(440, 440)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        spectrum_layout.addWidget(self.canvas)
        self.analysis_row.addWidget(self.spectrum_group, 5)

        self.cie_group = QGroupBox("CIE 1931 xy")
        cie_layout = QVBoxLayout(self.cie_group)
        cie_layout.setContentsMargins(3, 3, 3, 3)
        self.cie_canvas = FigureCanvas(plt.Figure(figsize=(4.2, 4.2), dpi=100))
        self.cie_canvas.setMinimumSize(240, 240)
        self.cie_canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        cie_layout.addWidget(self.cie_canvas)

        self.cie_value_label = QLabel("x: -   y: -")
        self.cie_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cie_value_label.setStyleSheet("font-weight: 600; color: #334e68;")
        cie_layout.addWidget(self.cie_value_label)
        self.cie_group.setMaximumHeight(330)

        self.right_info_col = QWidget()
        self.right_info_layout = QVBoxLayout(self.right_info_col)
        self.right_info_layout.setContentsMargins(0, 0, 0, 0)
        self.right_info_layout.setSpacing(6)
        self.right_info_layout.addWidget(self.cie_group, 2)
        self.right_info_layout.addWidget(self.color_group, 2)

        self.analysis_row.addWidget(self.right_info_col, 2)

        self.right_layout.addLayout(self.analysis_row, 1)

        self.recent_group = QGroupBox("Mémoire: 6 dernières mesures")
        recent_layout = QVBoxLayout(self.recent_group)
        recent_layout.setContentsMargins(8, 8, 8, 8)
        recent_layout.setSpacing(6)

        recent_header = QHBoxLayout()
        recent_header.setSpacing(6)
        self.recent_hint_label = QLabel("Clique une mesure pour recharger")
        self.recent_hint_label.setStyleSheet("color: #486581;")
        recent_header.addWidget(self.recent_hint_label, 1)
        recent_layout.addLayout(recent_header)

        self.recent_body = QHBoxLayout()
        self.recent_body.setSpacing(8)

        self.recent_actions_col = QVBoxLayout()
        self.recent_actions_col.setSpacing(6)
        self.open_button = QPushButton('Recharger fichier')
        self.open_button.setObjectName("secondaryButton")
        self.open_button.clicked.connect(self.open_file)
        self.recent_actions_col.addWidget(self.open_button)

        self.save_button = QPushButton('Sauvegarder graphe')
        self.save_button.setObjectName("secondaryButton")
        self.save_button.clicked.connect(self.save_plot)
        self.recent_actions_col.addWidget(self.save_button)
        self.recent_actions_col.addStretch(1)
        self.recent_body.addLayout(self.recent_actions_col)

        self.recent_scroll = QScrollArea()
        self.recent_scroll.setWidgetResizable(True)
        self.recent_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.recent_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.recent_scroll.setMinimumHeight(110)

        self.recent_container = QWidget()
        self.recent_row = QHBoxLayout(self.recent_container)
        self.recent_row.setContentsMargins(4, 4, 4, 4)
        self.recent_row.setSpacing(8)
        self.recent_scroll.setWidget(self.recent_container)
        self.recent_body.addWidget(self.recent_scroll, 1)
        recent_layout.addLayout(self.recent_body)
        self.right_layout.addWidget(self.recent_group)

        self.ax = self.canvas.figure.subplots()
        self.cie_ax = self.cie_canvas.figure.subplots()

        # Process Handling
        self.subprocess = None
        self.master_fd = None
        self.notifier = None
        
        self.temp_file = "temp_measure.sp"
        self.base_save_dir = Path.cwd() / "mesures"
        self.base_save_dir.mkdir(parents=True, exist_ok=True)
        self.save_folder_input.setText(str(self.base_save_dir))
        self.last_saved_mtime = None
        self.recent_history_file = self.base_save_dir / "recent_measurements.json"
        self.instrument_cache_file = self.base_save_dir / "instrument_cache.json"
        self.recent_measurements = []
        self._cie_point_artist = None

        # --- Session state ---
        self._calibrated = False
        self._stdout_buf = ""
        self._pending_result = False
        self._last_xyz = (0.0, 0.0, 0.0)
        self._instr_thread = None
        self._current_scan_deep = False
        self._instrument_cache = {}
        self._pending_issue_popups = []
        self._last_popup_ts = {}
        self._use_hybrid_backend = False
        self._action_in_progress = False
        self._current_action = None
        self._action_deadline_ms = 45000
        self._action_request_id = 0
        self._pending_result_request_id = 0
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setSingleShot(True)
        self._watchdog_timer.timeout.connect(self._on_action_timeout)
        self._last_scan_finished_at = 0.0
        self._session_start_pending = False
        self._pending_interactive_action = None
        self._interactive_retry_count = 0
        self._max_interactive_retries = 2
        self._oneshot_retries_left = 0

        # Enumerate instruments at startup
        self._init_cie_plot()
        self._load_recent_measurements()
        self._refresh_recent_carousel()
        self._load_instrument_cache()
        if self._instrument_cache:
            self._apply_instruments_to_combo(self._instrument_cache, "cache")
            self.console_output.append("Instruments chargés depuis le cache (pas de scan auto).")
        else:
            self.enumerate_instruments()
        self._update_status_banner()

    def _init_cie_plot(self):
        self.cie_ax.clear()
        self.cie_ax.set_title("Diagramme CIE 1931", fontsize=10)
        self.cie_ax.set_xlabel("x", fontsize=9)
        self.cie_ax.set_ylabel("y", fontsize=9)
        self.cie_ax.set_xlim(0.0, 0.8)
        self.cie_ax.set_ylim(0.0, 0.9)
        self.cie_ax.set_aspect('equal', adjustable='box')
        self.cie_ax.set_box_aspect(1)
        self.cie_ax.grid(True, alpha=0.25)

        try:
            cmfs = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"].copy()
            cmfs = cmfs.align(colour.SpectralShape(380, 780, 5))
            locus_xy = colour.XYZ_to_xy(cmfs.values)
            self.cie_ax.plot(locus_xy[..., 0], locus_xy[..., 1], color="#334e68", linewidth=1.2)
            if len(locus_xy) > 0:
                self.cie_ax.plot([locus_xy[-1, 0], locus_xy[0, 0]], [locus_xy[-1, 1], locus_xy[0, 1]], color="#334e68", linewidth=1.2)
        except Exception as exc:
            self.console_output.append(f"Erreur tracé CIE: {exc}")

        self._cie_point_artist = self.cie_ax.scatter([0.33], [0.33], s=65, color="#2f6fda", edgecolors="black", zorder=5)
        self.cie_canvas.figure.subplots_adjust(left=0.10, right=0.98, bottom=0.10, top=0.93)
        self.cie_canvas.draw_idle()

    def _update_cie_point(self, X: float, Y: float, Z: float):
        total = X + Y + Z
        if total <= 0:
            self.cie_value_label.setText("x: -   y: -")
            return

        x = X / total
        y = Y / total
        x = float(np.clip(x, 0.0, 0.8))
        y = float(np.clip(y, 0.0, 0.9))

        r, g, b = xyz_to_rgb(X, Y, Z)
        marker_color = (r / 255.0, g / 255.0, b / 255.0)
        if self._cie_point_artist is None:
            self._cie_point_artist = self.cie_ax.scatter([x], [y], s=65, color=marker_color, edgecolors="black", zorder=5)
        else:
            self._cie_point_artist.set_offsets(np.array([[x, y]]))
            self._cie_point_artist.set_color([marker_color])

        self.cie_value_label.setText(f"x: {x:.4f}   y: {y:.4f}")
        self.cie_canvas.draw_idle()

    def _load_recent_measurements(self):
        self.recent_measurements = []
        if not self.recent_history_file.exists():
            return

        try:
            with open(self.recent_history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                cleaned = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    path = item.get("path", "")
                    if path and Path(path).exists():
                        cleaned.append(item)
                self.recent_measurements = cleaned[:6]
        except Exception as exc:
            self.console_output.append(f"Erreur chargement historique: {exc}")

    def _save_recent_measurements(self):
        try:
            self.base_save_dir.mkdir(parents=True, exist_ok=True)
            with open(self.recent_history_file, "w", encoding="utf-8") as f:
                json.dump(self.recent_measurements[:6], f, indent=2, ensure_ascii=False)
        except Exception as exc:
            self.console_output.append(f"Erreur sauvegarde historique: {exc}")

    def _add_recent_measurement(self, path: Path, xyz=None):
        p = str(path)
        self.recent_measurements = [item for item in self.recent_measurements if item.get("path") != p]

        x = y = None
        if xyz is not None:
            X, Y, Z = xyz
            total = X + Y + Z
            if total > 0:
                x = float(X / total)
                y = float(Y / total)

        entry = {
            "name": path.stem,
            "path": p,
            "timestamp": datetime.now().strftime("%d/%m %H:%M"),
            "x": x,
            "y": y,
        }
        self.recent_measurements.insert(0, entry)
        self.recent_measurements = self.recent_measurements[:6]
        self._save_recent_measurements()
        self._refresh_recent_carousel()

    def _reload_measurement_from_history(self, path_str: str):
        path = Path(path_str)
        if not path.exists():
            QMessageBox.warning(self, "Mesure introuvable", f"Fichier absent:\n{path}")
            self.recent_measurements = [item for item in self.recent_measurements if item.get("path") != path_str]
            self._save_recent_measurements()
            self._refresh_recent_carousel()
            return

        self.plot_spectrum(str(path))
        self.console_output.append(f"Mesure rechargée: {path}")

    def _refresh_recent_carousel(self):
        while self.recent_row.count():
            item = self.recent_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self.recent_measurements:
            empty_label = QLabel("Aucune mesure mémorisée pour le moment.")
            empty_label.setStyleSheet("color: #829ab1; padding: 8px;")
            self.recent_row.addWidget(empty_label)
            self.recent_row.addStretch(1)
            return

        for item in self.recent_measurements[:6]:
            card = QFrame()
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card.setStyleSheet("QFrame { background: #f7f9fc; border: 1px solid #d8e1ec; border-radius: 8px; }")
            card.setFixedWidth(180)

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)
            card_layout.setSpacing(6)

            patch = QLabel()
            patch.setFixedHeight(20)
            patch_color = "#cbd2d9"
            if item.get("x") is not None and item.get("y") is not None:
                try:
                    x = float(item["x"])
                    y = float(item["y"])
                    if y > 0:
                        X = x / y
                        Y = 1.0
                        Z = (1.0 - x - y) / y
                        rr, gg, bb = xyz_to_rgb(X * 100.0, Y * 100.0, Z * 100.0)
                        patch_color = f"rgb({rr}, {gg}, {bb})"
                except Exception:
                    patch_color = "#cbd2d9"
            patch.setStyleSheet(f"background: {patch_color}; border-radius: 4px;")
            card_layout.addWidget(patch)

            name_label = QLabel(item.get("name", "mesure"))
            name_label.setStyleSheet("font-weight: 600; color: #243b53;")
            card_layout.addWidget(name_label)

            meta_label = QLabel(item.get("timestamp", ""))
            meta_label.setStyleSheet("color: #627d98; font-size: 11px;")
            card_layout.addWidget(meta_label)

            xy_txt = "xy: -"
            if item.get("x") is not None and item.get("y") is not None:
                xy_txt = f"xy: {item['x']:.3f}, {item['y']:.3f}"
            xy_label = QLabel(xy_txt)
            xy_label.setStyleSheet("color: #486581; font-size: 11px;")
            card_layout.addWidget(xy_label)

            reload_btn = QPushButton("Recharger")
            reload_btn.setObjectName("secondaryButton")
            reload_btn.clicked.connect(lambda _, p=item.get("path", ""): self._reload_measurement_from_history(p))
            card_layout.addWidget(reload_btn)

            self.recent_row.addWidget(card)

        self.recent_row.addStretch(1)

    def _load_instrument_cache(self):
        self._instrument_cache = {}
        if not self.instrument_cache_file.exists():
            return
        try:
            with open(self.instrument_cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if isinstance(cached, dict):
                cleaned = {}
                for key, value in cached.items():
                    try:
                        index = int(key)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(value, str) and value.strip():
                        cleaned[index] = value.strip()
                self._instrument_cache = cleaned
        except Exception as exc:
            self.console_output.append(f"Erreur cache instruments: {exc}")

    def _save_instrument_cache(self):
        try:
            self.base_save_dir.mkdir(parents=True, exist_ok=True)
            serializable = {str(idx): name for idx, name in sorted(self._instrument_cache.items())}
            with open(self.instrument_cache_file, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            self.console_output.append(f"Erreur sauvegarde cache instruments: {exc}")

    def _apply_instruments_to_combo(self, instruments: dict, source: str):
        self.instrument_combo.clear()
        if instruments:
            for idx, name in sorted(instruments.items()):
                self.instrument_combo.addItem(f"{idx}: {name}", idx)
            self.console_output.append(f"Instruments ({source}): {len(instruments)}")
        else:
            self.instrument_combo.addItem("(aucun instrument détecté)", None)
            self.console_output.append(
                "Aucun instrument détecté — vérifiez la connexion USB et qu'ArgyllCMS est installé.")

    def _spotread_issue_flags(self, raw: str):
        raw_lower = raw.lower()
        calibration_ok = re.search(r"calibration\s+(successful|complete|ok)|calibrated\s+ok", raw_lower) is not None

        calibration_needed = False
        if not calibration_ok:
            calibration_needed = re.search(
                r"(needs?\s+calibration|calibration\s+required|not\s+calibrated|"
                r"place\s+.*calibration|set\s+.*calibration|calibrate\s+the\s+instrument)",
                raw_lower,
            ) is not None

        wrong_direction = re.search(
            r"(wrong\s+position|sensor\s+should\s+be|aim\s+the\s+(sensor|instrument)|"
            r"point\s+the\s+(sensor|instrument)|reposition\s+the\s+(sensor|instrument))",
            raw_lower,
        ) is not None

        return {
            "calibration_needed": calibration_needed,
            "wrong_direction": wrong_direction,
        }

    def _should_show_popup(self, key: str, cooldown_s: float = 6.0):
        now = time.time()
        last = self._last_popup_ts.get(key, 0.0)
        if now - last < cooldown_s:
            return False
        self._last_popup_ts[key] = now
        return True

    def _direction_guidance_text(self):
        mode_arg = self.mode_combo.currentData()
        if mode_arg == "-e":
            return "Place la sonde à plat contre l'écran, orientée vers la lumière émise, puis relance Mesurer."
        if mode_arg == "-a":
            return "Passe en mode ambiant (diffuseur/accessoire), oriente la sonde vers la source et relance Mesurer."
        if mode_arg == "-p":
            return "Oriente la sonde vers le projecteur (axe optique), garde une visée stable, puis relance Mesurer."
        return "Vérifie l'orientation de la sonde par rapport à la surface/source, puis relance Mesurer."

    def _show_pending_issue_popups(self):
        if not self._pending_issue_popups:
            return

        issues = set(self._pending_issue_popups)
        self._pending_issue_popups = []

        if "calibration_needed" in issues and self._should_show_popup("calibration_needed"):
            answer = QMessageBox.question(
                self,
                "Calibration requise",
                "La sonde semble ne pas être en mode calibration.\n\nLancer la calibration maintenant ?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Ok,
            )
            if answer == QMessageBox.StandardButton.Ok:
                self.trigger_calibration()

        if "wrong_direction" in issues and self._should_show_popup("wrong_direction"):
            QMessageBox.information(
                self,
                "Orientation sonde",
                "La sonde semble mal orientée pour cette mesure.\n\n"
                + self._direction_guidance_text(),
            )

    def _is_interactive_running(self):
        return self.subprocess is not None and self.subprocess.poll() is None

    def _begin_action(self, action: str):
        self._action_in_progress = True
        self._current_action = action
        self._action_request_id += 1
        self._watchdog_timer.start(self._action_deadline_ms)
        self._update_execution_mode_ui()

    def _finish_action(self):
        self._action_in_progress = False
        self._current_action = None
        if self._watchdog_timer.isActive():
            self._watchdog_timer.stop()
        self._update_execution_mode_ui()

    def _fallback_to_oneshot(self, action: str, reason: str):
        self.console_output.append(f"Fallback one-shot ({action}): {reason}")
        if self._is_interactive_running():
            self.stop_session()
            QTimer.singleShot(
                1200,
                lambda a=action: self._run_spotread_oneshot(calibration_only=(a == "calibration")),
            )
        else:
            self._run_spotread_oneshot(calibration_only=(action == "calibration"))

    def _dispatch_action(self, action: str):
        if self._oneshot_busy or self._action_in_progress:
            self.console_output.append("Une opération est déjà en cours.")
            return

        self._oneshot_retries_left = 1

        if self._instr_thread is not None and self._instr_thread.isRunning():
            if not self._session_start_pending:
                self._session_start_pending = True
                self.console_output.append("Scan instruments en cours: mesure one-shot différée…")
            QTimer.singleShot(350, lambda a=action: self._dispatch_action(a))
            return

        cooldown_s = 6.0 - (time.time() - self._last_scan_finished_at)
        if cooldown_s > 0:
            if not self._session_start_pending:
                self._session_start_pending = True
                self.console_output.append("Attente courte de libération USB avant mesure one-shot…")
            wait_ms = int(cooldown_s * 1000)
            QTimer.singleShot(max(wait_ms, 120), lambda a=action: self._dispatch_action(a))
            return

        self._session_start_pending = False

        self._run_spotread_oneshot(calibration_only=(action == "calibration"))

    def _on_action_timeout(self):
        if not self._action_in_progress:
            return
        action = self._current_action or "measurement"
        self._finish_action()
        if self._interactive_retry_count < self._max_interactive_retries:
            self.console_output.append("Timeout interactif, relance session…")
            self._pending_interactive_action = action
            self._interactive_retry_count += 1
            self.stop_session()
            QTimer.singleShot(900, self._retry_pending_interactive_action)
            return
        self._fallback_to_oneshot(action, "timeout interactif")

    def _is_comm_failure_output(self, raw: str):
        txt = raw.lower()
        return (
            "failed to initialise communications with instrument" in txt
            or "communications failure" in txt
            or "device being used" in txt
            or "failed to initialise" in txt
            or "wrong instrument or bad configuration" in txt
        )

    def _dispatch_action_after_start(self, action: str):
        if self._oneshot_busy or self._action_in_progress:
            return
        if self._session_start_pending:
            QTimer.singleShot(350, lambda a=action: self._dispatch_action_after_start(a))
            return
        if self._is_interactive_running() and self.master_fd is not None:
            try:
                self._begin_action(action)
                os.write(self.master_fd, b' ')
                self.console_output.append(
                    ">> Calibration interactive envoyée (SPACE)"
                    if action == "calibration"
                    else ">> Mesure interactive envoyée (SPACE)"
                )
                return
            except OSError as exc:
                self.console_output.append(f"Échec envoi action interactive: {exc}")
        self._fallback_to_oneshot(action, "session interactive indisponible")

    def _retry_pending_interactive_action(self):
        action = self._pending_interactive_action
        self._pending_interactive_action = None
        if action is None:
            return
        self.start_session()
        QTimer.singleShot(550, lambda a=action: self._dispatch_action_after_start(a))

    def _retry_start_session(self):
        self._session_start_pending = False
        self.start_session()

    def start_session(self):
        self.console_output.append("Mode standard one-shot actif: pas de session interactive.")
        self._update_status_banner()

    def stop_session(self):
        self.console_output.append("Mode standard one-shot actif: aucune session à arrêter.")
        self._update_status_banner()

    def force_kill(self):
        if self.subprocess and self.subprocess.poll() is None:
            self.subprocess.kill()
        self.process_finished()

    def _spotread_env(self):
        return build_argyll_env()

    def _build_spotread_args(self, interactive: bool, calibration_only: bool = False):
        args = [resolve_spotread_command(), "-v"]

        instr_idx = self.instrument_combo.currentIndex()
        instr_data = self.instrument_combo.itemData(instr_idx)
        if instr_data is not None:
            args.extend(["-c", str(instr_data)])

        mode_arg = self.mode_combo.currentData()
        if mode_arg:
            args.append(mode_arg)

        if interactive:
            args.extend(["-s", self.temp_file])
            if self.skip_calibration_checkbox.isChecked():
                args.append("-N")
        else:
            if calibration_only:
                args.append("-O")
            else:
                args.extend(["-s", "-O", self.temp_file])
                if self.skip_calibration_checkbox.isChecked():
                    args.append("-N")

        return args

    def _set_oneshot_busy(self, busy: bool, action_label: str = ""):
        self._oneshot_busy = busy
        if busy and action_label:
            self.console_output.append(f"{action_label} en cours…")
        self._update_execution_mode_ui()

    def _set_calibrated_ui(self):
        self._calibrated = True
        self.calib_status_label.setText("✅  Calibré")
        self.calib_status_label.setStyleSheet("color: #27ae60; font-weight: bold; padding: 4px;")

    def _run_spotread_oneshot(self, calibration_only: bool = False):
        args = self._build_spotread_args(interactive=False, calibration_only=calibration_only)
        self.console_output.append(f"Starting (one-shot): {' '.join(args)}")

        if not calibration_only and os.path.exists(self.temp_file):
            try:
                os.remove(self.temp_file)
            except OSError:
                pass

        self._set_oneshot_busy(True, "Calibration" if calibration_only else "Mesure")
        self._oneshot_thread = SpotreadOneShotThread(
            args=args,
            env=self._spotread_env(),
            timeout_s=300,
            calibration_only=calibration_only,
        )
        self._oneshot_thread.output_ready.connect(self._on_oneshot_output_ready)
        self._oneshot_thread.finished.connect(self._on_oneshot_finished)
        self._oneshot_thread.finished.connect(self._oneshot_thread.deleteLater)
        self._oneshot_thread.start()

    def _on_oneshot_finished(self):
        self._oneshot_thread = None
        self._set_oneshot_busy(False)
        self._show_pending_issue_popups()

    def _on_oneshot_output_ready(self, raw: str, calibration_only: bool, elapsed_s: float):
        self.console_output.append(f"[durée one-shot: {elapsed_s:.2f}s]")
        self.console_output.append(raw)
        self._stdout_buf = raw

        if self._is_comm_failure_output(raw):
            if self._oneshot_retries_left > 0:
                self._oneshot_retries_left -= 1
                self.console_output.append("⚠ Communication USB occupée: nouvelle tentative one-shot dans 4s…")
                self._last_scan_finished_at = time.time()
                QTimer.singleShot(
                    4000,
                    lambda c=calibration_only: self._run_spotread_oneshot(calibration_only=c),
                )
                return
            self.console_output.append("❌ Échec communication instrument persistant. Évitez un scan juste avant la calibration/mesure.")
            return

        flags = self._spotread_issue_flags(raw)
        raw_lower = raw.lower()
        if re.search(r"calibration\s+(successful|complete|ok)|calibrated\s+ok", raw_lower):
            self._set_calibrated_ui()
            self.console_output.append(">> Sonde calibrée ✅")

        if flags["wrong_direction"]:
            self.console_output.append(
                "⚠ Position capteur incorrecte: en mode écran/projo, mettez le capteur sur la surface à mesurer avant \"Mesurer\".")

        if calibration_only:
            return

        if flags["calibration_needed"]:
            self.console_output.append("⚠ Calibration requise détectée.")
            self._pending_issue_popups.append("calibration_needed")
        if flags["wrong_direction"]:
            self._pending_issue_popups.append("wrong_direction")

        match_xyz = re.search(
            r"Result is XYZ:\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", raw)
        match_yxy = re.search(
            r"Result is Yxy:\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", raw)

        xyz = None

        if match_xyz:
            xyz = tuple(map(float, match_xyz.groups()))
        elif match_yxy:
            Yv, x, y = map(float, match_yxy.groups())
            xyz = yxy_to_xyz(Yv, x, y)

        measurement_saved = False
        if os.path.exists(self.temp_file):
            self.plot_spectrum(self.temp_file)
            saved_path = self.save_measurement_file()
            if saved_path:
                self._add_recent_measurement(saved_path, xyz=xyz)
                measurement_saved = True
        else:
            spec_written = self._write_spectrum_from_buffer()
            if spec_written:
                self.plot_spectrum(self.temp_file)
                saved_path = self.save_measurement_file()
                if saved_path:
                    self._add_recent_measurement(saved_path, xyz=xyz)
                    measurement_saved = True

        if not measurement_saved and xyz is not None:
            self.update_color_display(*xyz)

        if not measurement_saved and xyz is None:
            self.console_output.append("⚠ Mesure incomplète: aucune donnée exploitable reçue de spotread.")

    def _update_mode_guidance(self):
        mode_arg = self.mode_combo.currentData()
        if mode_arg == "-e":
            txt = "Emission (-e): mesure écran/lumière directe. Capteur en position surface contre l'écran."
        elif mode_arg == "-a":
            txt = "Ambient (-a): mesure lumière ambiante. Utilisez l'accessoire/diffuseur ambiant de la sonde si nécessaire."
        elif mode_arg == "-p":
            txt = "Projector (-p): mode téléphoto si supporté (ColorMunki/i1Pro). Sinon préférez Emission (-e)."
        else:
            txt = "Spot (réflectance): mesure de surface réfléchissante."
        self.mode_help_label.setText(txt)

    def _update_execution_mode_ui(self):
        subprocess_obj = getattr(self, "subprocess", None)
        session_running = subprocess_obj is not None and subprocess_obj.poll() is None
        busy = getattr(self, "_oneshot_busy", False) or self._action_in_progress

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.calibrate_btn.setEnabled(not busy)
        self.measure_btn.setEnabled(not busy)

        self.refresh_instr_btn.setEnabled(not session_running and not busy)
        self.instrument_combo.setEnabled(not session_running and not busy)
        self.mode_combo.setEnabled(not session_running and not busy)
        self.exec_mode_combo.setEnabled(False)
        self.change_folder_btn.setEnabled(not busy)
        if hasattr(self, "open_button"):
            self.open_button.setEnabled(not busy)
        if hasattr(self, "save_button"):
            self.save_button.setEnabled(not busy)
        self._update_status_banner()

    def _update_status_banner(self):
        instr = self.instrument_combo.currentText() or "-"
        mode = self.mode_combo.currentText().split("[")[0].strip() if self.mode_combo.count() else "-"
        process_obj = getattr(self, "subprocess", None)
        interactive_running = process_obj is not None and process_obj.poll() is None

        if self._oneshot_busy:
            run_state = "Exécution one-shot…"
        elif self._action_in_progress:
            run_state = "Calibration…" if self._current_action == "calibration" else "Mesure…"
        elif interactive_running:
            run_state = "Session rapide prête"
        else:
            run_state = "Prêt"

        calib_txt = "calibré" if getattr(self, "_calibrated", False) else "non calibré"
        self.session_status_label.setText(
            f"État: {run_state} | Mode: {mode} | Exécution: appel unique | Calib: {calib_txt} | Instrument: {instr}"
        )

    def trigger_calibration(self):
        """Send space to spotread to trigger calibration."""
        self._dispatch_action("calibration")

    def trigger_measurement(self):
        """Send space to spotread to take a measurement."""
        self._dispatch_action("measurement")

    # ------------------------------------------------------------------
    # PTY output handler
    # ------------------------------------------------------------------
    def handle_output(self):
        if self.master_fd is None:
            return
        try:
            data_bytes = os.read(self.master_fd, 4096)
            if not data_bytes:
                self.process_finished()
                return

            data = data_bytes.decode('utf-8', errors='replace')
            self.console_output.insertPlainText(data)
            self.console_output.ensureCursorVisible()

            if self._is_comm_failure_output(data):
                failed_action = self._current_action or "measurement"
                self.console_output.append("⚠ Erreur communication instrument détectée en interactif.")
                self._finish_action()
                if self._interactive_retry_count < self._max_interactive_retries:
                    self._interactive_retry_count += 1
                    self._pending_interactive_action = failed_action
                    self.console_output.append(
                        f"Relance session interactive (tentative {self._interactive_retry_count}/{self._max_interactive_retries})…"
                    )
                    self.stop_session()
                    QTimer.singleShot(1200, self._retry_pending_interactive_action)
                else:
                    self.console_output.append("Échec interactif persistant, bascule one-shot.")
                    self._interactive_retry_count = 0
                    self._fallback_to_oneshot(failed_action, "communications failure")
                return

            flags = self._spotread_issue_flags(data)
            if flags["calibration_needed"] and self._current_action == "measurement":
                self._pending_issue_popups.append("calibration_needed")
                self.console_output.append("⚠ Calibration requise détectée (interactif).")
            if flags["wrong_direction"] and self._current_action == "measurement":
                self._pending_issue_popups.append("wrong_direction")
                self.console_output.append("⚠ Orientation capteur incorrecte détectée (interactif).")

            # Accumulate buffer for multi-line spectral parsing
            self._stdout_buf += data
            # Trim to last 32 KB to avoid unbounded growth
            if len(self._stdout_buf) > 32768:
                self._stdout_buf = self._stdout_buf[-32768:]

            # --- Calibration state detection ---
            buf_lower = self._stdout_buf.lower()
            if (not self._calibrated and
                    re.search(r"calibration\s+(successful|complete|ok)|calibrated\s+ok",
                               buf_lower)):
                self._calibrated = True
                self.calib_status_label.setText("\U00002705  Calibr\u00e9")
                self.calib_status_label.setStyleSheet(
                    "color: #27ae60; font-weight: bold; padding: 4px;")
                self.console_output.append(">> Sonde calibr\u00e9e \u2705")
                self._interactive_retry_count = 0
                if self._current_action == "calibration":
                    self._finish_action()

            # --- Detect result in this chunk ---
            match_xyz = re.search(
                r"Result is XYZ:\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)", data)
            match_yxy = re.search(
                r"Result is Yxy:\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)", data)

            if match_xyz:
                X, Y, Z = map(float, match_xyz.groups())
                self._last_xyz = (X, Y, Z)
                self._pending_result = True
                self._pending_result_request_id = self._action_request_id
                # Give PTY 300 ms to flush the spectral block before parsing
                QTimer.singleShot(300, lambda rid=self._pending_result_request_id: self._process_pending_result(rid))
            elif match_yxy:
                Yv, x, y = map(float, match_yxy.groups())
                self._last_xyz = yxy_to_xyz(Yv, x, y)
                self._pending_result = True
                self._pending_result_request_id = self._action_request_id
                QTimer.singleShot(300, lambda rid=self._pending_result_request_id: self._process_pending_result(rid))

        except OSError:
            self.process_finished()

    def _process_pending_result(self, request_id=None):
        """Called 300 ms after a 'Result is' line to give the spectrum time to arrive."""
        if request_id is not None and request_id != self._action_request_id:
            return
        if not self._pending_result:
            return
        self._pending_result = False

        X, Y, Z = self._last_xyz
        self.update_color_display(X, Y, Z)

        spec_written = self._write_spectrum_from_buffer()
        if spec_written:
            self.plot_spectrum(self.temp_file)
            saved_path = self.save_measurement_file()
            if saved_path:
                self._add_recent_measurement(saved_path, xyz=(X, Y, Z))
        else:
            self.console_output.append(
                "(Pas de donn\u00e9es spectrales dans la sortie — v\u00e9rifiez que l'instrument supporte le mode spectral)")

        self._finish_action()
        self._interactive_retry_count = 0
        self._show_pending_issue_popups()

    def _write_spectrum_from_buffer(self):
        """
        Parse a spectral block from the accumulated stdout buffer and write
        a minimal CGATS .sp file so plot_spectrum() can display it.

        spotread prints (when the device supports it):
          Radiometric spectrum, 380 nm to 730 nm at 10 nm increments, 36 values:
             0.083   0.099  ...
        """
        m = re.search(
            r"[Rr]adiometric\s+spectrum[^,]*,\s*(\d+)\s*nm\s+to\s+(\d+)\s*nm"
            r"\s+at\s+(\d+)\s*nm\s+increments[^:]*:\s*\n([\d\.\s]+)",
            self._stdout_buf
        )
        if not m:
            return False

        start_nm = int(m.group(1))
        end_nm   = int(m.group(2))
        step_nm  = int(m.group(3))
        raw_vals = m.group(4).split()

        wavelengths = list(range(start_nm, end_nm + step_nm, step_nm))
        values = []
        for v in raw_vals:
            try:
                values.append(float(v))
            except ValueError:
                pass
            if len(values) == len(wavelengths):
                break

        if not values or len(values) != len(wavelengths):
            return False

        header   = " ".join(f"NM_{wl}" for wl in wavelengths)
        data_row = " ".join(f"{v:.6f}" for v in values)
        cgats = (
            f"CGATS.17\n"
            f"ORIGINATOR \"spotread\"\n"
            f"NUMBER_OF_FIELDS {len(wavelengths)}\n"
            f"BEGIN_DATA_FORMAT\n{header}\nEND_DATA_FORMAT\n"
            f"NUMBER_OF_SETS 1\n"
            f"BEGIN_DATA\n{data_row}\nEND_DATA\n"
        )
        try:
            with open(self.temp_file, 'w') as f:
                f.write(cgats)
            return True
        except Exception as e:
            self.console_output.append(f"Erreur \u00e9criture spectre: {e}")
            return False

    def process_finished(self):
        if self.notifier:
            self.notifier.setEnabled(False)
            self.notifier = None

        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

        self.subprocess = None
        self._pending_result = False
        self._stdout_buf = ""
        self._pending_result_request_id = 0
        if self._watchdog_timer.isActive():
            self._watchdog_timer.stop()
        self._action_in_progress = False
        self._current_action = None

        self.console_output.append("Process Finished.")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.measure_btn.setEnabled(True)
        self.calibrate_btn.setEnabled(True)
        self.refresh_instr_btn.setEnabled(True)
        self.instrument_combo.setEnabled(True)
        self.mode_combo.setEnabled(True)
        self.exec_mode_combo.setEnabled(False)
        # Reset calibration indicator
        self._calibrated = False
        self.calib_status_label.setText("\U0001f534  Non calibr\u00e9")
        self.calib_status_label.setStyleSheet("color: #c0392b; font-weight: bold; padding: 4px;")
        self._update_execution_mode_ui()

    # ------------------------------------------------------------------
    # Instrument enumeration
    # ------------------------------------------------------------------
    def enumerate_instruments(self, deep_scan=False):
        """Launch InstrumentEnumeratorThread to populate the instrument combo."""
        # Avoid stacking scans when one is already in progress
        if self._instr_thread is not None and self._instr_thread.isRunning():
            self.console_output.append("Scan instruments déjà en cours…")
            return

        self._current_scan_deep = deep_scan

        # Show cached list immediately for responsiveness
        if self._instrument_cache:
            self._apply_instruments_to_combo(self._instrument_cache, "cache")

        self.instrument_combo.setEnabled(False)
        self.refresh_instr_btn.setEnabled(False)
        if not self._instrument_cache:
            self.instrument_combo.clear()
            self.instrument_combo.addItem("Recherche...", None)
        timeout_s = 22 if deep_scan else 8
        self._instr_thread = InstrumentEnumeratorThread(timeout_s=timeout_s)  # no parent — lives in its own thread
        self._instr_thread.debug_output.connect(
            lambda txt: self.console_output.append("[spotread -?]\n" + txt[:500]))
        self._instr_thread.instruments_found.connect(self.on_instruments_found)
        self._instr_thread.start()

    def on_instruments_found(self, instruments: dict):
        """Populate instrument combo from enumeration results."""
        self._last_scan_finished_at = time.time()
        if instruments:
            self._instrument_cache = dict(instruments)
            self._save_instrument_cache()
            self._apply_instruments_to_combo(instruments, "scan")
        else:
            if not self._instrument_cache:
                self._apply_instruments_to_combo({}, "scan")
            else:
                self.console_output.append("Scan vide: conservation de la liste cache.")
        # Only re-enable these controls when no measurement session is active
        session_idle = (
            (self.subprocess is None or self.subprocess.poll() is not None)
            and not self._oneshot_busy
            and not self._action_in_progress
        )
        self.instrument_combo.setEnabled(session_idle)
        self.refresh_instr_btn.setEnabled(session_idle)
        self._update_status_banner()

    def select_save_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choisir le dossier de sauvegarde")
        if folder:
            self.base_save_dir = Path(folder)
            self.base_save_dir.mkdir(parents=True, exist_ok=True)
            self.recent_history_file = self.base_save_dir / "recent_measurements.json"
            self.save_folder_input.setText(str(self.base_save_dir))
            self.console_output.append(f"Dossier de sauvegarde: {self.base_save_dir}")
            self._load_recent_measurements()
            self._refresh_recent_carousel()

    def sanitize_measurement_name(self, name):
        cleaned = re.sub(r"[^\w\-]+", "_", name.strip())
        return cleaned.strip("_") or "mesure"

    def resolve_unique_path(self, folder, base_name, suffix):
        candidate = folder / f"{base_name}{suffix}"
        if not candidate.exists():
            return candidate
        index = 1
        while True:
            candidate = folder / f"{base_name}_{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    def save_measurement_file(self):
        if not os.path.exists(self.temp_file):
            return None

        try:
            mtime = os.path.getmtime(self.temp_file)
        except OSError:
            return None

        if self.last_saved_mtime is not None and mtime <= self.last_saved_mtime:
            return None

        date_folder = self.base_save_dir / datetime.now().strftime("%Y-%m-%d")
        date_folder.mkdir(parents=True, exist_ok=True)
        base_name = self.sanitize_measurement_name(self.measurement_name_input.text())
        destination = self.resolve_unique_path(date_folder, base_name, ".sp")

        try:
            shutil.move(self.temp_file, destination)
            self.last_saved_mtime = mtime
            self.console_output.append(f"Mesure sauvegardée: {destination}")
            return destination
        except Exception as exc:
            self.console_output.append(f"Erreur sauvegarde mesure: {exc}")
            return None

    def update_color_display(self, X, Y, Z):
        r, g, b = xyz_to_rgb(X, Y, Z)
        self.color_patch.setStyleSheet(f"background-color: rgb({r}, {g}, {b}); border: 1px solid #9aa5b1; border-radius: 5px;")
        self.color_values_label.setText(f"XYZ: {X:.2f} {Y:.2f} {Z:.2f}\nRGB: {r} {g} {b}")
        details = (
            f"XYZ: {X:.2f} {Y:.2f} {Z:.2f}\n"
            f"RGB: {r} {g} {b}\n"
            f"Lab: -\n"
            f"CRI (Ra): -\n"
            f"R1-R15: -"
        )
        self.cri_details.setPlainText(details)
        self._update_cie_point(X, Y, Z)

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Open File', '', 'Spectre Files (*.sp);;All Files (*)')
        if file_path:
            self.plot_spectrum(file_path)
            self._add_recent_measurement(Path(file_path))

    def plot_spectrum(self, file_path):
        if not os.path.exists(file_path):
            return
            
        try:
            with open(file_path, 'r') as file:
                lines = file.readlines()
            
            # Robust CGATS Parser
            header_fields = []
            data_values = []
            
            in_format = False
            in_data = False
            
            # Check for simple tabular format (Reading X Y Z ... 380.000 ...)
            is_simple_tabular = False
            header_index = -1
            
            # Find the header line (contains many wavelengths)
            # We look for the LAST header in the file, in case multiple measurements are appended
            for i, line in enumerate(lines):
                parts = line.strip().split()
                wl_count = 0
                for part in parts:
                    try:
                        val = float(part)
                        if 300 <= val <= 830:
                            wl_count += 1
                    except ValueError:
                        pass
                
                if wl_count > 10:
                    is_simple_tabular = True
                    header_index = i
                    header_fields = parts
            
            if is_simple_tabular:
                # Find the last data line after the header
                # We search backwards from the end of the file
                # But we must ensure it's after the header_index
                for line in reversed(lines[header_index+1:]):
                    if line.strip():
                        data_values = line.strip().split()
                        break

            if not is_simple_tabular:
                # Standard CGATS parsing
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    if line == "BEGIN_DATA_FORMAT":
                        in_format = True
                        continue
                    if line == "END_DATA_FORMAT":
                        in_format = False
                        continue
                        
                    if line == "BEGIN_DATA":
                        in_data = True
                        continue
                    if line == "END_DATA":
                        in_data = False
                        continue
                        
                    if in_format:
                        header_fields.extend(line.split())
                    
                    if in_data:
                        # Handle comments or empty lines if any
                        if line.startswith('#'): continue
                        data_values.extend(line.split())

            longueur_onde = []
            intensité = []

            # Strategy 0: Simple Tabular (Header has wavelengths)
            if is_simple_tabular:
                self.console_output.append(f"Debug: Detected Simple Tabular format. Header cols: {len(header_fields)}, Data cols: {len(data_values)}")
                
                if not data_values:
                    self.console_output.append("Error: Header found but no data line found.")
                    return

                for idx, field in enumerate(header_fields):
                    try:
                        wl = float(field)
                        # Filter out non-wavelength numbers (like '1' if it was in header, though unlikely for 'Reading')
                        # And ensure we have corresponding data
                        if 300 <= wl <= 830 and idx < len(data_values):
                            val = float(data_values[idx])
                            longueur_onde.append(wl)
                            intensité.append(val)
                    except ValueError:
                        pass
                self.console_output.append(f"Debug: Extracted {len(longueur_onde)} spectral points.")
                
                # If we found a tabular format, we trust it. If extraction failed, don't try other strategies.
                if not longueur_onde:
                     self.console_output.append("Error: Could not extract spectral data from tabular format.")
                     return

            # Strategy 1: Wide Format (SPEC_xxx or NM_xxx)
            # Check if headers contain spectral bands
            spec_indices = []
            if not longueur_onde and not is_simple_tabular:
                for idx, field in enumerate(header_fields):
                    if field.startswith("SPEC_") or field.startswith("NM_"):
                        try:
                            wl = float(field.replace("SPEC_", "").replace("NM_", ""))
                            spec_indices.append((idx, wl))
                        except ValueError:
                            pass
            
            if spec_indices:
                # It is Wide Format
                # We assume data_values contains one or more sets. We take the first set.
                # The number of values per set should equal len(header_fields)
                num_fields = len(header_fields)
                if len(data_values) >= num_fields:
                    # Take the first row/set
                    first_set = data_values[:num_fields]
                    
                    for idx, wl in spec_indices:
                        if idx < len(first_set):
                            try:
                                val = float(first_set[idx])
                                longueur_onde.append(wl)
                                intensité.append(val)
                            except ValueError:
                                pass
            elif not longueur_onde and not is_simple_tabular:
                # Strategy 2: Tall Format (Columns)
                # Look for 'Wavelength' and 'Spectral'/'Value' columns
                # Or just assume 2 columns if not specified
                wl_col = -1
                val_col = -1
                
                # Try to find columns by name
                for idx, field in enumerate(header_fields):
                    f_lower = field.lower()
                    if "wavelength" in f_lower or "nm" in f_lower:
                        wl_col = idx
                    elif "spectral" in f_lower or "value" in f_lower or "emission" in f_lower or "reflectance" in f_lower:
                        val_col = idx
                
                # Default to 0 and 1 if not found and we have at least 2 columns
                if wl_col == -1 and len(header_fields) >= 2:
                    wl_col = 0
                    val_col = 1
                
                if wl_col != -1 and val_col != -1:
                    num_cols = len(header_fields)
                    # Iterate through data in chunks of num_cols
                    # Note: data_values is a flat list of all tokens in BEGIN_DATA block
                    
                    # If num_cols is 0 (e.g. no format specified?), assume 2
                    if num_cols == 0: num_cols = 2
                    
                    for i in range(0, len(data_values), num_cols):
                        if i + max(wl_col, val_col) < len(data_values):
                            try:
                                wl = float(data_values[i + wl_col])
                                val = float(data_values[i + val_col])
                                longueur_onde.append(wl)
                                intensité.append(val)
                            except ValueError:
                                pass

            # Fallback for legacy/simple files (just numbers)
            if not longueur_onde and not header_fields:
                 # Try parsing pairs from all lines
                 for line in lines:
                     parts = line.split()
                     if len(parts) == 2:
                         try:
                             wl = float(parts[0])
                             val = float(parts[1])
                             longueur_onde.append(wl)
                             intensité.append(val)
                         except ValueError:
                             pass

            longueur_onde = np.array(longueur_onde, dtype=float)
            intensité = np.array(intensité, dtype=float)

            if len(longueur_onde) == 0 or len(intensité) == 0:
                self.console_output.append("Error: No spectral data found in file.")
                return

            # --- Colorimetry Calculations ---
            try:
                # Create Spectral Distribution
                # Ensure wavelengths are sorted
                sorted_indices = np.argsort(longueur_onde)
                wl_sorted = longueur_onde[sorted_indices]
                int_sorted = intensité[sorted_indices]
                
                data = dict(zip(wl_sorted, int_sorted))
                sd = colour.SpectralDistribution(data, name='Sample')

                # Interpolate to standard 1nm interval for colour-science
                # This fixes the "measurement interval" error for irregular data (e.g. 3.3nm from i1Pro)
                sd.interpolate(colour.SpectralShape(sd.shape.start, sd.shape.end, 1))

                # Calculate XYZ (CIE 1931 2 Degree Standard Observer)
                XYZ = colour.sd_to_XYZ(sd)
                X, Y, Z = XYZ
                
                # Calculate Lab (using D65 as reference)
                # colour.XYZ_to_Lab expects XYZ in domain [0, 1] usually (relative to reference white Y=1)
                Lab = colour.XYZ_to_Lab(XYZ / 100.0)
                L, a, b_val = Lab
                
                # Calculate sRGB
                # XYZ_to_sRGB expects XYZ in domain [0, 1] usually.
                RGB = colour.XYZ_to_sRGB(XYZ / 100.0)
                R, G, B = RGB
                R_disp = int(np.clip(R, 0, 1) * 255)
                G_disp = int(np.clip(G, 0, 1) * 255)
                B_disp = int(np.clip(B, 0, 1) * 255)
                
                # Calculate CRI
                cri_res = colour.quality.colour_rendering_index(sd, additional_data=True)
                Ra = cri_res.Q_a
                r_values = {k: v.Q_a for k, v in cri_res.Q_as.items()}
                
                # Update UI
                self.color_patch.setStyleSheet(f"background-color: rgb({R_disp}, {G_disp}, {B_disp}); border: 1px solid #9aa5b1; border-radius: 5px;")
                self.color_values_label.setText(f"XYZ: {X:.2f} {Y:.2f} {Z:.2f}\n"
                                                f"RGB: {R_disp} {G_disp} {B_disp}\n"
                                                f"Lab: {L:.2f} {a:.2f} {b_val:.2f}")
                self._update_cie_point(X, Y, Z)
                
                self.cri_label.setText(f"CRI (Ra): {Ra:.1f}")

                full_lines = [
                    f"XYZ: {X:.2f} {Y:.2f} {Z:.2f}",
                    f"RGB: {R_disp} {G_disp} {B_disp}",
                    f"Lab: {L:.2f} {a:.2f} {b_val:.2f}",
                    f"CRI (Ra): {Ra:.1f}",
                    "",
                    "-- Indices CRI --",
                ]
                for i in range(1, 16):
                    full_lines.append(f"R{i}: {r_values.get(i, 0):.1f}")
                self.cri_details.setPlainText("\n".join(full_lines))

            except Exception as e:
                self.console_output.append(f"Colorimetry Calc Error: {e}")
                # import traceback
                # traceback.print_exc()
            # -------------------------------

            self.ax.clear()
            y_max = float(np.max(intensité)) if len(intensité) else 1.0
            y_max = max(y_max, 1e-9)

            # Continuous spectral gradient background (true gradient, not discrete patches)
            x_min = float(np.min(longueur_onde))
            x_max = float(np.max(longueur_onde))
            grad_wl = np.linspace(x_min, x_max, 512)
            grad_rgb = np.array([wavelength_to_rgb(wl) for wl in grad_wl], dtype=float)
            grad_img = np.repeat(grad_rgb[np.newaxis, :, :], 2, axis=0)
            self.ax.imshow(
                grad_img,
                extent=[x_min, x_max, 0.0, y_max],
                aspect='auto',
                origin='lower',
                alpha=0.35,
                zorder=0,
                interpolation='bicubic'
            )

            # Plot spectral curve with polished style
            self.ax.plot(longueur_onde, intensité, color='#102a43', linewidth=2.2, zorder=3)
            self.ax.fill_between(longueur_onde, intensité, 0, color='#486581', alpha=0.08, zorder=2)

            # Professional axes / typography
            self.ax.set_facecolor('#ffffff')
            self.ax.set_xlabel('Longueur d\'onde (nm)', fontsize=11, color='#243b53', labelpad=8)
            self.ax.set_ylabel('Intensité relative', fontsize=11, color='#243b53', labelpad=8)
            file_name = os.path.basename(file_path)
            self.ax.set_title(f'Spectre : {file_name}', fontsize=13, color='#102a43', pad=10, fontweight='600')
            self.ax.tick_params(axis='both', which='major', labelsize=9, colors='#334e68')
            self.ax.tick_params(axis='x', which='both', bottom=True, top=False, labelbottom=True)
            self.ax.grid(True, which='major', color='#d9e2ec', linewidth=0.8, alpha=0.7)
            self.ax.grid(True, which='minor', color='#e9eff5', linewidth=0.5, alpha=0.55)
            self.ax.minorticks_on()
            self.ax.set_xlim(x_min, x_max)
            self.ax.set_ylim(0.0, y_max * 1.05)
            self.ax.set_box_aspect(1)

            for spine in ['top', 'right']:
                self.ax.spines[spine].set_visible(False)
            for spine in ['left', 'bottom']:
                self.ax.spines[spine].set_color('#9fb3c8')
                self.ax.spines[spine].set_linewidth(1.0)

            self.canvas.figure.subplots_adjust(left=0.09, right=0.995, bottom=0.12, top=0.935)
            self.canvas.draw_idle()
            
        except Exception as e:
            self.console_output.append(f"Error plotting: {e}")
            import traceback
            traceback.print_exc()

    def save_plot(self):
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save File', '', 'PNG Files (*.png);;All Files (*)')
        if file_path:
            original_size = self.canvas.figure.get_size_inches()
            original_dpi = self.canvas.figure.get_dpi()
            self.canvas.figure.set_size_inches(10, 10)
            self.ax.set_xlabel('Longueur d\'onde (nm)', fontsize=18)
            self.ax.set_ylabel('Intensité relative', fontsize=18)
            self.ax.title.set_fontsize(22)
            self.ax.tick_params(axis='both', which='major', labelsize=14)
            self.canvas.figure.savefig(file_path, dpi=300)
            self.canvas.figure.set_size_inches(original_size)
            self.canvas.figure.set_dpi(original_dpi)
            self.ax.set_xlabel('Longueur d\'onde (nm)', fontsize=11)
            self.ax.set_ylabel('Intensité relative', fontsize=11)
            self.ax.title.set_fontsize(13)
            self.ax.tick_params(axis='both', which='major', labelsize=9)
            self.canvas.draw()
            self.console_output.append(f'Plot saved as {file_path}')

def run_app():
    app = QApplication(sys.argv)
    window = SpectrumPlotter()
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(run_app())
