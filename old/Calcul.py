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

def plot_spectrum(file_path):
    # Load data
    with open(file_path, 'r') as file:
        data = file.readlines()
        longueur_onde = data[13]
        intensité = data[18]

    longueur_onde = longueur_onde.split()
    intensité = intensité.split()
    longueur_onde = [i.replace('SPEC_', '') for i in longueur_onde]
    longueur_onde = np.array(longueur_onde, dtype=float)
    intensité = np.array(intensité, dtype=float)

    # Create the plot with a 3:2 aspect ratio and higher resolution
    fig, ax = plt.subplots(figsize=(15, 10), dpi=200)

    # Add color patches for each wavelength interval
    for i in range(len(longueur_onde) - 1):
        color = wavelength_to_rgb(longueur_onde[i])
        rect = patches.Rectangle((longueur_onde[i], 0), longueur_onde[i+1] - longueur_onde[i], max(intensité), color=color, alpha=0.3)
        ax.add_patch(rect)

    # Plot the data
    ax.plot(longueur_onde, intensité, color='black')

    # Set labels and title with larger font size
    ax.set_xlabel('Longueur d\'onde (nm)', fontsize=20)
    ax.set_ylabel('Intensité', fontsize=20)
    # Get the file name without the path
    file_name = os.path.basename(file_path)
    # Set the title with the file name
    ax.set_title(f'Spectre : {file_name}', fontsize=24)

    # Increase tick parameters
    ax.tick_params(axis='both', which='major', labelsize=16)

    return fig, ax

def save_spectrum_plot(file_path):
    fig, ax = plot_spectrum(file_path)
    # Save the plot as an image file in the current working directory
    output_file = os.path.join(os.getcwd(), 'spectrum_plot.png')
    fig.savefig(output_file)
    plt.close(fig)
    print(f'Plot saved as {output_file}')

plot_spectrum('../Filament.sp')
save_spectrum_plot('../Filament.sp')