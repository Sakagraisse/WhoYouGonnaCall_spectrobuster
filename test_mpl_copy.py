import matplotlib.path
import copy
import sys

print(f"Python version: {sys.version}")
print(f"Matplotlib file: {matplotlib.path.__file__}")

try:
    p = matplotlib.path.Path([(0, 0), (1, 1)])
    print("Created Path object")
    p2 = copy.deepcopy(p)
    print("Deepcopied Path object successfully")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
