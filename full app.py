import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QPushButton, QWidget, QFileDialog, QLabel
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
import numpy as np
import os
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.patches as patches
import os

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

class SpectrumPlotter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Spectre Plotter')
        self.setGeometry(100, 100, 800, 600)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.layout = QVBoxLayout(self.central_widget)

        self.open_button = QPushButton('Choisir le fichier')
        self.open_button.clicked.connect(self.open_file)
        self.layout.addWidget(self.open_button)

        self.canvas = FigureCanvas(plt.Figure(figsize=(15, 10), dpi=200))
        self.layout.addWidget(self.canvas)

        self.save_button = QPushButton('Sauvegarder le graphique')
        self.save_button.clicked.connect(self.save_plot)
        self.layout.addWidget(self.save_button)

        self.ax = self.canvas.figure.subplots()

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Open File', '', 'Spectre Files (*.sp);;All Files (*)')
        if file_path:
            self.plot_spectrum(file_path)

    def plot_spectrum(self, file_path):
        with open(file_path, 'r') as file:
            data = file.readlines()
            longueur_onde = data[13].split()
            intensité = data[18].split()

        longueur_onde = [i.replace('SPEC_', '') for i in longueur_onde]
        longueur_onde = np.array(longueur_onde, dtype=float)
        intensité = np.array(intensité, dtype=float)

        self.ax.clear()

        # Add color patches for each wavelength interval
        for i in range(len(longueur_onde) - 1):
            color = wavelength_to_rgb(longueur_onde[i])
            rect = patches.Rectangle((longueur_onde[i], 0), longueur_onde[i + 1] - longueur_onde[i], max(intensité),
                                     color=color, alpha=0.3)
            self.ax.add_patch(rect)

        # Plot the data
        self.ax.plot(longueur_onde, intensité, color='black')

        # Set labels and title with larger font size
        self.ax.set_xlabel('Longueur d\'onde (nm)', fontsize=10)
        self.ax.set_ylabel('Intensité', fontsize=10)
        # Get the file name without the path
        file_name = os.path.basename(file_path)
        # Set the title with the file name
        self.ax.set_title(f'Spectre : {file_name}', fontsize=12)

        # Increase tick parameters
        self.ax.tick_params(axis='both', which='major', labelsize=6)
        self.canvas.figure.tight_layout()
        self.canvas.draw()

    def save_plot(self):
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save File', '', 'PNG Files (*.png);;All Files (*)')
        if file_path:
            # Store the original size and DPI
            original_size = self.canvas.figure.get_size_inches()
            original_dpi = self.canvas.figure.get_dpi()

            # Set the figure size to a 3:2 ratio and increase the DPI for better quality
            self.canvas.figure.set_size_inches(15, 10)  # 15 inches width, 10 inches height for 3:2 ratio

            # Set labels and title with larger font size
            self.ax.set_xlabel('Longueur d\'onde (nm)', fontsize=20)
            self.ax.set_ylabel('Intensité', fontsize=20)
            file_name = os.path.basename(file_path)
            self.ax.title.set_fontsize(24)
            self.ax.tick_params(axis='both', which='major', labelsize=16)

            # Save the figure
            self.canvas.figure.savefig(file_path, dpi=300)  # Increase DPI for better quality

            # Revert back to the original size and DPI
            self.canvas.figure.set_size_inches(original_size)
            self.canvas.figure.set_dpi(original_dpi)

            # Set labels and title with larger font size
            self.ax.set_xlabel('Longueur d\'onde (nm)', fontsize=10)
            self.ax.set_ylabel('Intensité', fontsize=10)
            file_name = os.path.basename(file_path)
            self.ax.title.set_fontsize(12)
            self.ax.tick_params(axis='both', which='major', labelsize=6)
            self.canvas.draw()

            print(f'Plot saved as {file_path}')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SpectrumPlotter()
    window.show()
    sys.exit(app.exec())