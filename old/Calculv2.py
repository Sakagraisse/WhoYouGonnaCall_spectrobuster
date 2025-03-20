import matplotlib.pyplot as plt
import numpy as np

# charger la ligne 14 du document Filament.sp comme un long string
with open('../Filament.sp', 'r') as file:
    data = file.readlines()
    longueur_onde = data[13]
    intensité = data[18]

#utiliser les espace pour transformer le string en liste
longueur_onde = longueur_onde.split()
intensité = intensité.split()

#remove "SPEC_" from each entry on the list
longueur_onde = [i.replace('SPEC_', '') for i in longueur_onde]

#convert the list to a numpy array
longueur_onde = np.array(longueur_onde, dtype=float)
intensité = np.array(intensité, dtype=float)
print(longueur_onde)
print(intensité)

#create a plot
plt.plot(longueur_onde, intensité)
plt.xlabel('Longueur d\'onde (nm)')
plt.ylabel('Intensité')
plt.title('Spectre')
plt.show()