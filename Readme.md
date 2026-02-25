# Mesure de Lumière avec ArgyllCMS avec i1 Studio/Colormunki Photo/Colorchecker Studio

## Mesurer une lumière avec `illumread` (Mode Spot, diffuseur parfois requis)

### 0. Prérequis
- Installer ArgyllCMS
- Brancher l'appareil de mesure (i1 Studio, Colormunki Photo, Colorchecker Studio)
- Ouvrir un terminal

### 1. Préparer l'instrument
- Faire pivoter l'appareil en position de calibration

### 2. Lancer la mesure en mode illumread
- Afficher l'aide pour connaître les options disponibles :
  ```sh
    spotread -?
  ```
- Copier la commande dans votre terminal et appuyer sur "entrer" :
  ```sh
  illumread -v -H -T "path/file.sp"
  ```
    - `-v` : Mode verbose.
    - `-H` : Mode haute precision
    - `-T` : Mode experimental pour le stockage du spectre dans un fichier
    - `"path/file.sp"` : Nom du fichier de sortie.

- Attendre l'apparition des 7 options disponibles (bien attendre)
  - Appuyer sur la touche 1 pour mesure le spectre d'une lumiere
  - Appuyer sur la touche 2 pour mesurer en mode telephoto (sans diffuseur)
- L'interface demande de calibrer, appuyer sur "entrer" pour continuer
- Faire tourner l'appareil pour mesurer la lumiere en position de diffuseur si option 1 ou videoprojecteur pour option 2
- Positionner l'appareil en face de la source lumineuse et maintenir la position en cliquant de la touche du spectro ou une touche clavier
- Attendre la fin de la mesure (quelques secondes).

### 3. Astuce 
- La commande `illumread` avec option -T écrase chaque nouvelle mesure, mais recalibrer à chaque fois prend du temps. Vous pouvez renommer le fichier créer et ainsi continuer à faire des mesures sans perdre de temps !

### 4. Analyser le spectre, methode ArgyllCMS

- Avantage >>> calcul des valeurs utiles comme le CRI, CCT, etc.
- Désavantage >>> pas de stockage du spectre (screenshot possible)
- Lancer la commande suivante :
  ```sh
  specplot "path/fichier.sp"
  ```
- Un spectre s'affiche, plus d'autres valeurs :

- Voici une liste des mesures et leur utilité dans votre fichier de données spectrales (B2.sp) :
  - Abs. Y – Luminosité absolue en candela par mètre carré (cd/m²), une mesure de l'intensité lumineuse.
  - CCT (Correlated Color Temperature) – Température de couleur en Kelvin, indiquant si la source lumineuse tend vers le bleu (froid) ou le rouge (chaud).
  - VCT (Visual Color Temperature) – Température de couleur perçue par l’œil humain.
  - CDT (Correlated Daylight Temperature) – Température de couleur corrélée en fonction d’une source lumineuse de type lumière du jour.
  - CRI (Color Rendering Index) – Indice de rendu des couleurs, qui mesure la capacité d’une source lumineuse à restituer fidèlement les couleurs par rapport à une source de référence.
  - R9 – Valeur spécifique du rendu du rouge saturé dans le calcul du CRI.
  - TLCI (Television Lighting Consistency Index) – Indice de qualité des couleurs utilisé en production télévisuelle.
  - CIEDE2000 Delta E – Différence de couleur par rapport à une référence, une mesure de la précision de la reproduction des couleurs.

### 5. App Python

- Avantage >>> stockage et visualisation du spectre
- Désavantage >>> pas de calcul des valeurs utiles / installation requise (app autonome bientot fournies)
- Voir en bas pour l'installation de l'app Python

- Lancer la commande suivante (nouvel entrypoint) :
  ```sh
  python3 "path/main.py"
  ```
- L'ancien lancement reste compatible temporairement :
  ```sh
  python3 "path/full app.py"
  ```
- ou alors lancer la via votre IDE favori
- Bouton du haut pour choisir le fichier .sp, milieu pour visualiser, bas pour sauvegarder

### 6. Installation de l'app Python

- Installer Python 3.10 ou plus récent

- Installer les dépendances :
  ```sh
  pip3 install numpy matplotlib PyQt6
  ```
  
- c'est bon !