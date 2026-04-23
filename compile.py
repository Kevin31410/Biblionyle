import PyInstaller.__main__
import os

# --- CONFIGURATION ---
fichier_principal = "Biblionyle.py"  # Remplacez par le nom exact de votre script si différent
nom_application = "VinylScan"

print(f"🚀 Début de la compilation de {nom_application}...")

options_compilation = [
    fichier_principal,
    f'--name={nom_application}',
    '--windowed',       # 🟢 TRÈS IMPORTANT : Masque la console noire Windows au lancement
    '--onefile',        # 🟢 Compile tout (PyQt6, OpenCV, etc.) dans UN SEUL gros fichier .exe
    '--clean',          # Nettoie le cache avant de compiler
    
    # --- DÉPENDANCES CACHÉES ---
    # Parfois PyInstaller "oublie" certaines bibliothèques complexes, on le force à les inclure :
    '--hidden-import=cv2',
    '--hidden-import=pyzbar',
    '--hidden-import=requests',
    '--hidden-import=PIL',
    '--hidden-import=PyQt6',
    
    # '--icon=logo.ico', # 💡 DÉCOMMENTEZ cette ligne si vous avez un fichier .ico pour l'icône de l'exe
]

# Lancement de la compilation
PyInstaller.__main__.run(options_compilation)

print("\n" + "="*50)
print("✅ COMPILATION TERMINÉE AVEC SUCCÈS !")
print("📁 Allez dans le nouveau dossier 'dist' qui vient d'être créé.")
print(f"💿 Vous y trouverez votre fichier '{nom_application}.exe' prêt à l'emploi.")
print("="*50)
