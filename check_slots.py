import matplotlib.path
try:
    print(f"Path slots: {matplotlib.path.Path.__slots__}")
except AttributeError:
    print("Path has no __slots__")
