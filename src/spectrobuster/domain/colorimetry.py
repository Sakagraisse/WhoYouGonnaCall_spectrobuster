import numpy as np


def wavelength_to_rgb(wavelength):
    gamma = 0.8
    intensity_max = 255
    factor = 0.0
    red = green = blue = 0

    if 380 <= wavelength < 440:
        red = -(wavelength - 440) / (440 - 380)
        green = 0.0
        blue = 1.0
    elif 440 <= wavelength < 490:
        red = 0.0
        green = (wavelength - 440) / (490 - 440)
        blue = 1.0
    elif 490 <= wavelength < 510:
        red = 0.0
        green = 1.0
        blue = -(wavelength - 510) / (510 - 490)
    elif 510 <= wavelength < 580:
        red = (wavelength - 510) / (580 - 510)
        green = 1.0
        blue = 0.0
    elif 580 <= wavelength < 645:
        red = 1.0
        green = -(wavelength - 645) / (645 - 580)
        blue = 0.0
    elif 645 <= wavelength < 780:
        red = 1.0
        green = 0.0
        blue = 0.0
    else:
        red = green = blue = 0.0

    if 380 <= wavelength < 420:
        factor = 0.3 + 0.7 * (wavelength - 380) / (420 - 380)
    elif 420 <= wavelength < 645:
        factor = 1.0
    elif 645 <= wavelength < 780:
        factor = 0.3 + 0.7 * (780 - wavelength) / (780 - 645)
    else:
        factor = 0.0

    red = int(intensity_max * ((red * factor) ** gamma))
    green = int(intensity_max * ((green * factor) ** gamma))
    blue = int(intensity_max * ((blue * factor) ** gamma))

    return (red / 255.0, green / 255.0, blue / 255.0)


def xyz_to_rgb(x_value, y_value, z_value):
    # Normalize assuming X, Y, Z are in 0-100 range (common in Argyll output)
    var_x = float(x_value) / 100.0
    var_y = float(y_value) / 100.0
    var_z = float(z_value) / 100.0

    var_r = var_x * 3.2406 + var_y * -1.5372 + var_z * -0.4986
    var_g = var_x * -0.9689 + var_y * 1.8758 + var_z * 0.0415
    var_b = var_x * 0.0557 + var_y * -0.2040 + var_z * 1.0570

    def gamma_correct(channel):
        if channel > 0.0031308:
            return 1.055 * (channel ** (1 / 2.4)) - 0.055
        return 12.92 * channel

    red = gamma_correct(var_r) * 255
    green = gamma_correct(var_g) * 255
    blue = gamma_correct(var_b) * 255

    return int(np.clip(red, 0, 255)), int(np.clip(green, 0, 255)), int(np.clip(blue, 0, 255))


def yxy_to_xyz(y_luma, x_chromaticity, y_chromaticity):
    if y_chromaticity == 0:
        return 0.0, 0.0, 0.0
    x_value = x_chromaticity * (y_luma / y_chromaticity)
    z_value = (1 - x_chromaticity - y_chromaticity) * (y_luma / y_chromaticity)
    return x_value, y_luma, z_value
