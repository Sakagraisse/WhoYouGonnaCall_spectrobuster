# Calcul de l'IRC d'une Lumière à partir d'un Fichier .sp

## 📌 Calculer l’IRC (Indice de Rendu des Couleurs)
L’**IRC (CRI - Color Rendering Index)** évalue la capacité d’une source lumineuse à restituer fidèlement les couleurs par rapport à une source de référence (ex : lumière du jour).

### **1️⃣ Extraire les données spectrales**
Convertir le fichier `.sp` en valeurs utilisables (XYZ) :
```sh
spec2cie fichier.sp
```
Cela affichera les valeurs **XYZ** et **Lab**, mais pas encore l’IRC.

### **2️⃣ Exporter les données pour un calcul externe**
Si un calcul direct de l’IRC est nécessaire, convertir en format texte :
```sh
spec2cie -n fichier.sp > fichier_xyz.txt
```
Cela génère un fichier **CGATS** avec les valeurs **XYZ** exploitables.

### **3️⃣ Calculer l’IRC avec un outil externe**
#### 🖥 **Option 1 : Utiliser Python avec `colour-science`**
Si vous avez Python installé, utilisez ce script :
```python
import colour

# Charger le spectre depuis un fichier .sp
data = colour.SpectralDistribution.from_file("fichier.sp")

# Calculer l'IRC
cri = colour.colorimetry.colour_rendering_index(data)
print(f"IRC: {cri:.2f}")
```
#### 🌍 **Option 2 : Utiliser un calculateur en ligne**
Vous pouvez **copier-coller** les valeurs spectrales dans un **calculateur en ligne**, comme ceux de l’**IES** (Illuminating Engineering Society).

---
