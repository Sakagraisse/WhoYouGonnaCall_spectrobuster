import colour
import numpy as np

print("colour version:", colour.__version__)

# Check for CRI function
if hasattr(colour.quality, 'colour_rendering_index'):
    print("Found colour.quality.colour_rendering_index")
    print(colour.quality.colour_rendering_index.__doc__)
else:
    print("colour.quality.colour_rendering_index not found")
    # Try to find it in other modules
    for module in dir(colour):
        if 'rendering' in module or 'quality' in module:
            print(f"Checking module: {module}")

# Create a dummy SpectralDistribution
wavelengths = np.arange(380, 781, 5)
values = np.random.rand(len(wavelengths))
data = dict(zip(wavelengths, values))
sd = colour.SpectralDistribution(data, name='Test')

print("\nSpectralDistribution created.")

# Try to calculate CRI
try:
    # It seems the function might be colour_rendering_index or similar
    # Let's look for it in colour.quality
    res = colour.colour_rendering_index(sd)
    print(f"Result of colour.colour_rendering_index: {type(res)}")
    print(res)
except Exception as e:
    print(f"Error calling colour_rendering_index: {e}")

