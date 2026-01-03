import sys
import os
import copy
import subprocess
import pty

from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QWidget, QFileDialog, QLabel, QComboBox, QTextEdit, QGroupBox, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, QSocketNotifier

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
except ImportError:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import re
import numpy as np
import colour

def wavelength_to_rgb(wavelength):
    gamma = 0.8
    intensity_max = 255
    factor = 0.0
    R = G = B = 0

    if 380 <= wavelength < 440:
        R = -(wavelength - 440) / (440 - 380)
        G = 0.0
        B = 1.0
    elif 440 <= wavelength < 490:
        R = 0.0
        G = (wavelength - 440) / (490 - 440)
        B = 1.0
    elif 490 <= wavelength < 510:
        R = 0.0
        G = 1.0
        B = -(wavelength - 510) / (510 - 490)
    elif 510 <= wavelength < 580:
        R = (wavelength - 510) / (580 - 510)
        G = 1.0
        B = 0.0
    elif 580 <= wavelength < 645:
        R = 1.0
        G = -(wavelength - 645) / (645 - 580)
        B = 0.0
    elif 645 <= wavelength < 780:
        R = 1.0
        G = 0.0
        B = 0.0
    else:
        R = G = B = 0.0

    if 380 <= wavelength < 420:
        factor = 0.3 + 0.7 * (wavelength - 380) / (420 - 380)
    elif 420 <= wavelength < 645:
        factor = 1.0
    elif 645 <= wavelength < 780:
        factor = 0.3 + 0.7 * (780 - wavelength) / (780 - 645)
    else:
        factor = 0.0

    R = int(intensity_max * ((R * factor) ** gamma))
    G = int(intensity_max * ((G * factor) ** gamma))
    B = int(intensity_max * ((B * factor) ** gamma))

    return (R / 255.0, G / 255.0, B / 255.0)

def xyz_to_rgb(X, Y, Z):
    # Normalize assuming X, Y, Z are in 0-100 range (common in Argyll output)
    var_X = float(X) / 100.0
    var_Y = float(Y) / 100.0
    var_Z = float(Z) / 100.0

    var_R = var_X *  3.2406 + var_Y * -1.5372 + var_Z * -0.4986
    var_G = var_X * -0.9689 + var_Y *  1.8758 + var_Z *  0.0415
    var_B = var_X *  0.0557 + var_Y * -0.2040 + var_Z *  1.0570

    def gamma_correct(v):
        if v > 0.0031308:
            return 1.055 * (v ** (1 / 2.4)) - 0.055
        else:
            return 12.92 * v

    R = gamma_correct(var_R) * 255
    G = gamma_correct(var_G) * 255
    B = gamma_correct(var_B) * 255

    return int(np.clip(R, 0, 255)), int(np.clip(G, 0, 255)), int(np.clip(B, 0, 255))

def yxy_to_xyz(Y, x, y):
    if y == 0:
        return 0.0, 0.0, 0.0
    X = x * (Y / y)
    Z = (1 - x - y) * (Y / y)
    return X, Y, Z

class SpectrumPlotter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Spectre Plotter & ArgyllCMS Interface')
        self.setGeometry(100, 100, 1200, 800)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Main Layout
        self.main_layout = QHBoxLayout(self.central_widget)

        # --- Left Panel: Controls & Console ---
        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)
        self.main_layout.addWidget(self.left_panel, 1)

        # ArgyllCMS Controls Group
        self.controls_group = QGroupBox("ArgyllCMS Controls")
        self.controls_layout = QVBoxLayout()
        self.controls_group.setLayout(self.controls_layout)

        # Instrument Selection
        self.controls_layout.addWidget(QLabel("Instrument:"))
        self.instrument_combo = QComboBox()
        self.instrument_combo.addItems(["1", "2", "3", "4", "5"]) # Simple selection
        self.instrument_combo.setEditable(True)
        self.controls_layout.addWidget(self.instrument_combo)

        # Mode Selection
        self.controls_layout.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Emission (Screen) [-e]", "-e")
        self.mode_combo.addItem("Ambient (Spot) [-a]", "-a")
        self.mode_combo.addItem("Projector [-p]", "-p")
        self.mode_combo.addItem("Spot (Reflectance) [Default]", "")
        self.controls_layout.addWidget(self.mode_combo)

        # Buttons
        self.start_btn = QPushButton("Démarrer Session (spotread)")
        self.start_btn.clicked.connect(self.start_session)
        self.controls_layout.addWidget(self.start_btn)

        self.calibrate_btn = QPushButton("Calibrer (Touche)")
        self.calibrate_btn.clicked.connect(self.trigger_calibration)
        self.calibrate_btn.setEnabled(False)
        self.controls_layout.addWidget(self.calibrate_btn)

        self.measure_btn = QPushButton("Mesurer (Espace)")
        self.measure_btn.clicked.connect(self.trigger_measurement)
        self.measure_btn.setEnabled(False)
        self.controls_layout.addWidget(self.measure_btn)

        self.stop_btn = QPushButton("Arrêter Session")
        self.stop_btn.clicked.connect(self.stop_session)
        self.stop_btn.setEnabled(False)
        self.controls_layout.addWidget(self.stop_btn)

        self.left_layout.addWidget(self.controls_group)

        # Console Output
        self.left_layout.addWidget(QLabel("Sortie Console:"))
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Monospace;")
        self.left_layout.addWidget(self.console_output)

        # Color Equivalence Group
        self.color_group = QGroupBox("Colorimétrie & CRI")
        self.color_layout = QVBoxLayout()
        self.color_group.setLayout(self.color_layout)

        self.color_patch = QLabel()
        self.color_patch.setFixedSize(100, 100)
        self.color_patch.setStyleSheet("background-color: gray; border: 1px solid black;")
        self.color_layout.addWidget(self.color_patch, alignment=Qt.AlignmentFlag.AlignCenter)

        self.color_values_label = QLabel("XYZ: - - -\nRGB: - - -\nLab: - - -")
        self.color_values_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.color_layout.addWidget(self.color_values_label)

        self.cri_label = QLabel("CRI (Ra): -")
        self.cri_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cri_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.color_layout.addWidget(self.cri_label)

        self.cri_details_label = QLabel("R9-R15:")
        self.color_layout.addWidget(self.cri_details_label)

        self.cri_details = QTextEdit()
        self.cri_details.setReadOnly(True)
        self.cri_details.setMaximumHeight(150)
        self.cri_details.setStyleSheet("font-family: Monospace; font-size: 10px;")
        self.color_layout.addWidget(self.cri_details)

        self.left_layout.addWidget(self.color_group)

        # --- Right Panel: Plot ---
        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)
        self.main_layout.addWidget(self.right_panel, 2)

        self.open_button = QPushButton('Choisir le fichier (Manuel)')
        self.open_button.clicked.connect(self.open_file)
        self.right_layout.addWidget(self.open_button)

        self.canvas = FigureCanvas(plt.Figure(figsize=(15, 10), dpi=100))
        self.right_layout.addWidget(self.canvas)

        self.save_button = QPushButton('Sauvegarder le graphique')
        self.save_button.clicked.connect(self.save_plot)
        self.right_layout.addWidget(self.save_button)

        self.ax = self.canvas.figure.subplots()

        # Process Handling
        self.subprocess = None
        self.master_fd = None
        self.notifier = None
        
        self.temp_file = "temp_measure.sp"

    def start_session(self):
        if self.subprocess and self.subprocess.poll() is None:
            return

        # Build command
        # spotread -v [mode] -x -S temp_measure.sp
        args = ["spotread", "-v"]
        
        # Mode
        mode_arg = self.mode_combo.currentData()
        if mode_arg:
            args.append(mode_arg)

        # Output format and file
        args.append("-x")
        args.extend(["-S", self.temp_file])
            
        self.console_output.append(f"Starting: {' '.join(args)}")
        
        # Use PTY to simulate a terminal
        self.master_fd, slave_fd = pty.openpty()
        
        try:
            self.subprocess = subprocess.Popen(
                args,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid,
                close_fds=True
            )
        except Exception as e:
            self.console_output.append(f"Failed to start: {e}")
            os.close(self.master_fd)
            os.close(slave_fd)
            return

        os.close(slave_fd) # Close slave in parent

        # Setup QSocketNotifier to read output asynchronously
        self.notifier = QSocketNotifier(self.master_fd, QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self.handle_output)
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.measure_btn.setEnabled(True)
        self.calibrate_btn.setEnabled(True)
        self.instrument_combo.setEnabled(False)
        self.mode_combo.setEnabled(False)

    def stop_session(self):
        if self.subprocess and self.subprocess.poll() is None:
            self.subprocess.terminate()
            QTimer.singleShot(1000, self.force_kill)
        else:
            self.process_finished()

    def force_kill(self):
        if self.subprocess and self.subprocess.poll() is None:
            self.subprocess.kill()
        self.process_finished()
        
    def trigger_calibration(self):
        if self.master_fd is not None:
            os.write(self.master_fd, b' ') # Send Space
            self.console_output.append(">> Sent SPACE (Calibrate)")

    def trigger_measurement(self):
        if self.master_fd is not None:
            os.write(self.master_fd, b' ') # Send Space
            self.console_output.append(">> Sent SPACE (Measure)")

    def handle_output(self):
        if self.master_fd is None: return
        try:
            # Read from PTY
            data_bytes = os.read(self.master_fd, 4096)
            if not data_bytes:
                self.process_finished()
                return
            
            data = data_bytes.decode('utf-8', errors='replace')
            self.console_output.insertPlainText(data)
            self.console_output.ensureCursorVisible()
            
            # Parse for XYZ
            match_xyz = re.search(r"Result is XYZ:\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)", data)
            if match_xyz:
                X, Y, Z = map(float, match_xyz.groups())
                self.update_color_display(X, Y, Z)
                self.plot_spectrum(self.temp_file)
                return

            # Parse for Yxy (if -x is used)
            match_yxy = re.search(r"Result is Yxy:\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)", data)
            if match_yxy:
                Y, x, y = map(float, match_yxy.groups())
                X, Y_val, Z = yxy_to_xyz(Y, x, y)
                self.update_color_display(X, Y_val, Z)
                self.plot_spectrum(self.temp_file)
                return
            
        except OSError:
            self.process_finished()

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
        
        self.console_output.append("Process Finished.")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.measure_btn.setEnabled(False)
        self.calibrate_btn.setEnabled(False)
        self.instrument_combo.setEnabled(True)
        self.mode_combo.setEnabled(True)

    def update_color_display(self, X, Y, Z):
        r, g, b = xyz_to_rgb(X, Y, Z)
        self.color_patch.setStyleSheet(f"background-color: rgb({r}, {g}, {b}); border: 1px solid black;")
        self.color_values_label.setText(f"XYZ: {X:.2f} {Y:.2f} {Z:.2f}\nRGB: {r} {g} {b}")

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Open File', '', 'Spectre Files (*.sp);;All Files (*)')
        if file_path:
            self.plot_spectrum(file_path)

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
                self.color_patch.setStyleSheet(f"background-color: rgb({R_disp}, {G_disp}, {B_disp}); border: 1px solid black;")
                self.color_values_label.setText(f"XYZ: {X:.2f} {Y:.2f} {Z:.2f}\n"
                                                f"RGB: {R_disp} {G_disp} {B_disp}\n"
                                                f"Lab: {L:.2f} {a:.2f} {b_val:.2f}")
                
                self.cri_label.setText(f"CRI (Ra): {Ra:.1f}")
                
                r_text = "--- General (Ra) ---\n"
                for i in range(1, 9):
                    r_text += f"R{i}: {r_values.get(i, 0):.1f}  "
                    if i == 4: r_text += "\n"
                r_text += "\n\n--- Special ---\n"
                for i in range(9, 16):
                    r_text += f"R{i}: {r_values.get(i, 0):.1f}  "
                    if i == 12: r_text += "\n"
                self.cri_details.setText(r_text)

            except Exception as e:
                self.console_output.append(f"Colorimetry Calc Error: {e}")
                # import traceback
                # traceback.print_exc()
            # -------------------------------

            self.ax.clear()

            # Add color patches for each wavelength interval
            for i in range(len(longueur_onde) - 1):
                color = wavelength_to_rgb(longueur_onde[i])
                rect = patches.Rectangle((longueur_onde[i], 0), longueur_onde[i + 1] - longueur_onde[i], max(intensité),
                                         color=color, alpha=0.3)
                self.ax.add_patch(rect)

            # Plot the data
            self.ax.plot(longueur_onde, intensité, color='black')

            # Set labels and title
            self.ax.set_xlabel('Longueur d\'onde (nm)', fontsize=10)
            self.ax.set_ylabel('Intensité', fontsize=10)
            file_name = os.path.basename(file_path)
            self.ax.set_title(f'Spectre : {file_name}', fontsize=12)
            self.ax.tick_params(axis='both', which='major', labelsize=6)
            self.canvas.figure.tight_layout()
            self.canvas.draw()
            
        except Exception as e:
            self.console_output.append(f"Error plotting: {e}")
            import traceback
            traceback.print_exc()

    def save_plot(self):
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save File', '', 'PNG Files (*.png);;All Files (*)')
        if file_path:
            original_size = self.canvas.figure.get_size_inches()
            original_dpi = self.canvas.figure.get_dpi()
            self.canvas.figure.set_size_inches(15, 10)
            self.ax.set_xlabel('Longueur d\'onde (nm)', fontsize=20)
            self.ax.set_ylabel('Intensité', fontsize=20)
            self.ax.title.set_fontsize(24)
            self.ax.tick_params(axis='both', which='major', labelsize=16)
            self.canvas.figure.savefig(file_path, dpi=300)
            self.canvas.figure.set_size_inches(original_size)
            self.canvas.figure.set_dpi(original_dpi)
            self.ax.set_xlabel('Longueur d\'onde (nm)', fontsize=10)
            self.ax.set_ylabel('Intensité', fontsize=10)
            self.ax.title.set_fontsize(12)
            self.ax.tick_params(axis='both', which='major', labelsize=6)
            self.canvas.draw()
            self.console_output.append(f'Plot saved as {file_path}')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SpectrumPlotter()
    window.show()
    sys.exit(app.exec())
