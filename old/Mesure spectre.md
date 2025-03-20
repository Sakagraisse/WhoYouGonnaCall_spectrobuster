# Mesure de Lumière avec ArgyllCMS

## Procédure 1 : Mesurer une lumière avec `spotread` (Mode Spot, diffuseur requis)

### 1. Préparer l'instrument
- Fixer le **diffuseur blanc** sur la lentille du i1 Studio.
- Placer l'instrument face à la source lumineuse ou devant une surface blanche réfléchissant la lumière.
- S'assurer qu'il n'y a pas d'autres sources lumineuses parasites.

### 2. Calibrer l'instrument
- Vérifier que l'instrument est bien détecté :
  ```sh
    which spotread
  ```
- Afficher l'aide pour connaître les options disponibles :
  ```sh
    spotread -?
  ```
- Lancer la calibration pour garantir des mesures précises :
  ```sh
  spotread -c
  ```
- Suivre les instructions (placer l'instrument sur sa base de calibration).

### 3. Effectuer la mesure
- Lancer la commande suivante :
  ```sh
  spotread -s -H
  ```
  - `-s` : Active la mesure spectrale.
  - `-H` : Affiche les détails de la mesure.
- Attendre la fin de la mesure (quelques secondes).

### 4. Enregistrer et analyser les résultats
- Sauvegarder les données dans un fichier :
  ```sh
  spotread -s -H > lumiere.sp
  ```
- Visualiser le spectre mesuré :
  ```sh
  specplot lumiere.sp
  ```
- Convertir en valeurs CIE XYZ :
  ```sh
  spec2cie lumiere.sp
  ```

---

## Procédure 2 : Mesurer une lumière avec `dispread` (Mode Émissif, sans diffuseur)

### 1. Préparer l'instrument
- **Retirer le diffuseur** de l'i1 Studio.
- Placer l'instrument face à la source lumineuse directe (ex. LED, écran, lampe de modélisation).

### 2. Lancer la mesure en mode émissif
- Exécuter la commande suivante :
  ```sh
  dispread -H -Y A test_lumiere
  ```
  - `-H` : Mode détaillé.
  - `-Y A` : Mode émissif générique.
  - `test_lumiere` : Nom du fichier de sortie.

### 3. Analyser les résultats
- Visualiser le spectre mesuré :
  ```sh
  specplot test_lumiere.sp
  ```
- Convertir en valeurs XYZ/Lab :
  ```sh
  spec2cie test_lumiere.sp
  ```

---

Ces deux méthodes permettent d'obtenir des données spectrales précises en fonction du type de source lumineuse à analyser.

