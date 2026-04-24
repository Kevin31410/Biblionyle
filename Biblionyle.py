import sys
import os
import cv2
from pyzbar.pyzbar import decode
import requests
import io
import sqlite3
import base64
import re
import csv
import time
from PIL import Image

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QTabWidget,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QTextEdit, QLineEdit, QFileDialog, QMessageBox,
                             QDialog, QFrame, QAbstractItemView)
from PyQt6.QtCore import QTimer, Qt, QMarginsF
from PyQt6.QtGui import QImage, QPixmap, QFont, QColor, QCursor, QIcon, QTextDocument, QPdfWriter, QPageSize

# --- ICÔNE DE L'APP EN BASE64 ---
APP_ICON_B64 = b"iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABmJLR0QA/wD/AP+gvaeTAAAAqklEQVQ4je2QvQ2DMBCFz00UjEAFjMEGjMEoNEiNo2QC2AA01GzAAMiIp1BwkkP4IykSpU5yL1+/p3v3CQf/UFXNMcZgjHlhjDFUVXN4v0RRFG6M2SKl9EEpZTPGvCiKwvkI0HWeZyul1MEYA2MMTqndPM9WIcTG6z/wBnzf54gIfN+HaZpYlgXGGCilYIwhIgjDQO/Kz+B1XV/Xdf33wN+Bv+C+B94DdwIvk9Y39K15qFEAAAAASUVORK5CYII="


class VinylScannerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VinylScan")

        icon_pixmap = QPixmap()
        icon_pixmap.loadFromData(base64.b64decode(APP_ICON_B64))
        self.setWindowIcon(QIcon(icon_pixmap))

        self.resize(1200, 800)

        # --- CONFIGURATION ---
        self.token_discogs = "Token"
        dossier_utilisateur = os.path.expanduser("~")  # Pointe vers C:\Users\VotreNom\
        dossier_app = os.path.join(dossier_utilisateur, "VinylScan_Data")
        if not os.path.exists(dossier_app):
            os.makedirs(dossier_app)

        self.db_name = os.path.join(dossier_app, "bibliotheque_vinyles.db")
        self.current_vinyl_data = None
        self.bubble = None

        self.init_database()

        self.setStyleSheet("""
            QMainWindow { background-color: #1e272e; }
            QTabWidget::pane { border: 1px solid #485460; background: #2d3436; border-radius: 5px; }
            QTabBar::tab { background: #485460; color: white; padding: 10px 20px; border-top-left-radius: 5px; border-top-right-radius: 5px; }
            QTabBar::tab:selected { background: #0fb9b1; color: black; font-weight: bold; }
            QLabel { color: white; }
            QPushButton { padding: 10px; border-radius: 5px; font-weight: bold; color: white; background-color: #485460; }
            QPushButton:hover { background-color: #576574; }
            QPushButton:disabled { background-color: #353b48; color: #a4b0be; }
            QTableWidget { background-color: #2f3640; color: white; gridline-color: #485460; selection-background-color: #0fb9b1; selection-color: black; }
            QHeaderView::section { background-color: #1e272e; color: white; padding: 5px; border: 1px solid #353b48; font-weight: bold; }
            QLineEdit, QTextEdit { background-color: #353b48; color: white; padding: 5px; border: 1px solid #485460; border-radius: 3px; }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        self.tabs.currentChanged.connect(self.hide_bubble)

        self.tab_scan = QWidget()
        self.tab_library = QWidget()
        self.tabs.addTab(self.tab_scan, "📸 Scanner un Vinyle")
        self.tabs.addTab(self.tab_library, "📚 Ma Bibliothèque")

        self.setup_scan_tab()
        self.setup_library_tab()

        self.cap = cv2.VideoCapture(0)
        self.last_barcode = None

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_scanner_background)
        self.timer.start(30)

    # ==========================================
    # INITIALISATION DES ONGLETS
    # ==========================================
    def setup_scan_tab(self):
        # Le layout principal de l'onglet devient vertical (Haut / Bas)
        main_scan_layout = QVBoxLayout(self.tab_scan)

        # --- 1. BARRE DU HAUT (RECHERCHE & CRÉATION) ---
        top_bar_layout = QHBoxLayout()

        self.input_manual = QLineEdit()
        self.input_manual.setPlaceholderText("Pas de code-barres ? Tapez Artiste - Titre...")
        self.input_manual.setStyleSheet("font-size: 14px; padding: 8px;")

        self.btn_manual = QPushButton("🔍 Chercher")
        self.btn_manual.setStyleSheet("background-color: #3498db; color: white; padding: 8px 20px; font-size: 14px;")
        self.btn_manual.clicked.connect(self.manual_search)

        self.btn_create_manual = QPushButton("✍️ Créer un vinyle (Hors Discogs)")
        self.btn_create_manual.setStyleSheet(
            "background-color: #8e44ad; color: white; padding: 8px 20px; font-weight: bold; font-size: 14px;")
        self.btn_create_manual.clicked.connect(self.open_create_window)

        top_bar_layout.addWidget(self.input_manual)
        top_bar_layout.addWidget(self.btn_manual)
        top_bar_layout.addSpacing(30)
        top_bar_layout.addWidget(self.btn_create_manual)

        main_scan_layout.addLayout(top_bar_layout)

        # Séparateur horizontal
        separator_top = QFrame()
        separator_top.setFrameShape(QFrame.Shape.HLine)
        separator_top.setStyleSheet("background-color: #485460; max-height: 1px; margin: 10px 0px;")
        main_scan_layout.addWidget(separator_top)

        # --- 2. ZONE CENTRALE (SCAN & RÉSULTATS) ---
        content_layout = QHBoxLayout()

        # COLONNE GAUCHE (CONTRÔLE & VIDÉO)
        left_panel = QWidget()
        left_panel.setFixedWidth(400)
        left_panel.setStyleSheet("background-color: #2c3e50; border-radius: 15px;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.lbl_logo = QLabel("💿 VinylScan")
        self.lbl_logo.setFont(QFont("Arial", 26, QFont.Weight.Bold))
        self.lbl_logo.setStyleSheet("color: #0fb9b1; border: none; background: transparent;")
        left_layout.addWidget(self.lbl_logo, alignment=Qt.AlignmentFlag.AlignHCenter)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: #485460; max-height: 1px; margin: 0 20px;")
        left_layout.addWidget(separator)
        left_layout.addSpacing(15)

        self.lbl_video = QLabel("Démarrage caméra...")
        self.lbl_video.setFixedSize(360, 270)
        self.lbl_video.setStyleSheet(
            "background-color: black; border: 2px solid #0fb9b1; border-radius: 5px; color: white;")
        self.lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.lbl_video, alignment=Qt.AlignmentFlag.AlignHCenter)
        left_layout.addSpacing(20)

        self.lbl_indicator = QLabel()
        self.lbl_indicator.setFixedSize(60, 60)
        self.lbl_indicator_text = QLabel("PRÊT")
        self.lbl_indicator_text.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.set_indicator("orange", "PRÊT")

        indicator_layout = QHBoxLayout()
        indicator_layout.addStretch()
        indicator_layout.addWidget(self.lbl_indicator)
        indicator_layout.addWidget(self.lbl_indicator_text)
        indicator_layout.addStretch()
        left_layout.addLayout(indicator_layout)

        content_layout.addWidget(left_panel)

        # COLONNE DROITE (RÉSULTATS)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        self.lbl_cover = QLabel("La pochette s'affichera ici")
        self.lbl_cover.setFixedSize(300, 300)
        self.lbl_cover.setStyleSheet(
            "background-color: #2d3436; border: 1px dashed #485460; border-radius: 10px; color: white;")
        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.lbl_cover, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.lbl_status = QLabel("En attente d'un scan...")
        self.lbl_status.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.lbl_status.setStyleSheet("color: white;")
        right_layout.addWidget(self.lbl_status)

        self.text_info = QTextEdit()
        self.text_info.setReadOnly(True)
        self.text_info.setFont(QFont("Arial", 11))
        right_layout.addWidget(self.text_info)

        # Boutons de sauvegarde / annulation
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("✅ SAUVEGARDER")
        self.btn_save.setStyleSheet("background-color: #20bf6b; color: black; font-size: 14px;")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self.confirm_save)

        self.btn_cancel = QPushButton("❌ ANNULER")
        self.btn_cancel.setStyleSheet("background-color: #eb3b5a; color: white; font-size: 14px;")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.reset_scanner)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        right_layout.addLayout(btn_layout)

        content_layout.addWidget(right_panel)
        main_scan_layout.addLayout(content_layout)

    def setup_library_tab(self):
        layout = QVBoxLayout(self.tab_library)

        toolbar = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 Rafraîchir")
        self.btn_refresh.clicked.connect(self.load_library_data)

        self.btn_edit = QPushButton("✏️ Modifier")
        self.btn_edit.setEnabled(False)
        self.btn_edit.clicked.connect(self.open_edit_window)

        self.btn_delete = QPushButton("🗑️ Supprimer")
        self.btn_delete.setStyleSheet("background-color: #eb3b5a; color: white;")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self.delete_selected_vinyl)

        self.btn_export_csv = QPushButton("📊 Exporter Excel")
        self.btn_export_csv.setStyleSheet("background-color: #27ae60; color: white;")
        self.btn_export_csv.clicked.connect(self.export_to_csv)

        self.btn_export_pdf = QPushButton("📄 Exporter PDF")
        self.btn_export_pdf.setStyleSheet("background-color: #e1b12c; color: black;")
        self.btn_export_pdf.clicked.connect(self.export_to_pdf)

        toolbar.addWidget(self.btn_refresh)
        toolbar.addWidget(self.btn_edit)
        toolbar.addWidget(self.btn_delete)
        toolbar.addWidget(self.btn_export_csv)
        toolbar.addWidget(self.btn_export_pdf)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID Discogs", "Artiste", "Titre", "Année", "Format", "Prix"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 100)

        self.table.itemSelectionChanged.connect(self.on_table_select)
        layout.addWidget(self.table)

        self.lbl_total = QLabel("Valeur totale estimée : 0.00 €")
        self.lbl_total.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.lbl_total.setStyleSheet("color: white;")
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.lbl_total)

        self.load_library_data()

    # ==========================================
    # UTILITAIRES & IHM
    # ==========================================
    def set_indicator(self, color, text):
        colors = {"orange": "#fa8231", "green": "#20bf6b", "red": "#eb3b5a"}
        hex_color = colors.get(color, "#fa8231")
        self.lbl_indicator.setStyleSheet(
            f"background-color: {hex_color}; border-radius: 30px; border: 3px solid #1e272e;")
        self.lbl_indicator_text.setText(text)
        self.lbl_indicator_text.setStyleSheet("color: white;")
        QApplication.processEvents()

    def get_image_bytes(self, url_or_b64):
        if not url_or_b64: return None
        if url_or_b64.startswith("base64:"):
            return base64.b64decode(url_or_b64.split("base64:")[1])
        elif url_or_b64.startswith("http"):
            headers = {"User-Agent": "VinylScannerAppQt/1.0", "Authorization": f"Discogs token={self.token_discogs}"}
            try:
                resp = requests.get(url_or_b64, headers=headers, verify=False, timeout=5)
                if resp.status_code == 200: return resp.content
            except:
                pass
        return None

    def get_qpixmap_from_bytes(self, img_bytes, width, height):
        if not img_bytes: return None
        image = QImage()
        image.loadFromData(img_bytes)
        if image.isNull(): return None

        square_img = QImage(width, height, QImage.Format.Format_ARGB32)
        square_img.fill(QColor("#34495e"))
        scaled_img = image.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)

        from PyQt6.QtGui import QPainter
        painter = QPainter(square_img)
        x = (width - scaled_img.width()) // 2
        y = (height - scaled_img.height()) // 2
        painter.drawImage(x, y, scaled_img)
        painter.end()
        return QPixmap.fromImage(square_img)

    # ==========================================
    # LOGIQUE BDD
    # ==========================================
    def init_database(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS vinyles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                barcode TEXT UNIQUE, discogs_id INTEGER, artiste TEXT, titre TEXT,
                annee TEXT, pays TEXT, genres TEXT, styles TEXT, labels TEXT,
                formats TEXT, tracklist TEXT, prix_bas TEXT, cover_url TEXT,
                date_ajout TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        conn.close()

    def save_to_database(self, **kwargs):
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute('''INSERT OR REPLACE INTO vinyles 
                (barcode, discogs_id, artiste, titre, annee, pays, genres, styles, labels, formats, tracklist, prix_bas, cover_url)
                VALUES (:barcode, :discogs_id, :artists, :title, :year, :country, :genres, :styles, :labels, :formats, :tracks_str, :prix_actuel, :cover_url)
            ''', kwargs)
            conn.commit()
            conn.close()
            self.load_library_data()
            return True
        except sqlite3.Error as e:
            print(f"Erreur SQLite : {e}")
            return False

    def load_library_data(self):
        self.table.setRowCount(0)
        total_valeur = 0.0
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("SELECT discogs_id, artiste, titre, annee, formats, prix_bas FROM vinyles ORDER BY id DESC")
            lignes = cursor.fetchall()

            for row_idx, ligne in enumerate(lignes):
                self.table.insertRow(row_idx)
                for col_idx, data in enumerate(ligne):
                    item = QTableWidgetItem(str(data))
                    if col_idx in [0, 3, 5]:
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignCenter if col_idx != 5 else Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table.setItem(row_idx, col_idx, item)

                match = re.search(r"(\d+(?:[\.,]\d+)?)", str(ligne[5]))
                if match:
                    total_valeur += float(match.group(1).replace(',', '.'))
            conn.close()
            self.lbl_total.setText(f"Valeur totale estimée : {total_valeur:.2f} €")
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
            self.hide_bubble()
        except sqlite3.Error as e:
            print(f"Erreur chargement : {e}")

    # ==========================================
    # ACTIONS DE LA BIBLIOTHÈQUE ET EXPORT
    # ==========================================
    def delete_selected_vinyl(self):
        selected = self.table.selectedItems()
        if not selected: return
        row = selected[0].row()
        discogs_id = self.table.item(row, 0).text()
        titre = self.table.item(row, 2).text()

        rep = QMessageBox.question(self, "Confirmer", f"Supprimer '{titre}' ?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if rep == QMessageBox.StandardButton.Yes:
            self.hide_bubble()
            conn = sqlite3.connect(self.db_name)
            conn.execute("DELETE FROM vinyles WHERE discogs_id=?", (discogs_id,))
            conn.commit()
            conn.close()
            self.load_library_data()

    def open_edit_window(self):
        selected = self.table.selectedItems()
        if not selected: return
        self.hide_bubble()
        row = selected[0].row()
        discogs_id = self.table.item(row, 0).text()

        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT artiste, titre, annee, formats, prix_bas, tracklist, cover_url FROM vinyles WHERE discogs_id=?",
            (discogs_id,))
        res = cursor.fetchone()
        conn.close()
        if not res: return

        dlg = QDialog(self)
        dlg.setWindowTitle("Éditer le vinyle")
        dlg.resize(450, 750)
        dlg.setStyleSheet(
            "QDialog { background-color: #1e272e; color: white; } QLabel { color: white; } QLineEdit, QTextEdit { background-color: #353b48; color: white; border: 1px solid #485460; }")
        layout = QVBoxLayout(dlg)

        dlg.new_cover_data = res[6]

        lbl_preview = QLabel("Chargement...")
        lbl_preview.setFixedSize(150, 150)
        lbl_preview.setStyleSheet("background-color: #34495e; border-radius: 5px; color: white;")
        lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_preview, alignment=Qt.AlignmentFlag.AlignHCenter)

        def update_preview(url_data):
            pixmap = self.get_qpixmap_from_bytes(self.get_image_bytes(url_data), 150, 150)
            if pixmap:
                lbl_preview.setPixmap(pixmap)
            else:
                lbl_preview.setText("Aucune image")

        QTimer.singleShot(10, lambda: update_preview(dlg.new_cover_data))

        entries = {}
        fields = [("Artiste", res[0]), ("Titre", res[1]), ("Année", res[2]), ("Format", res[3]), ("Prix", res[4])]
        for label, val in fields:
            layout.addWidget(QLabel(f"{label} :"))
            line = QLineEdit(str(val))
            entries[label] = line
            layout.addWidget(line)

        layout.addWidget(QLabel("Tracklist :"))
        txt_tracklist = QTextEdit()
        txt_tracklist.setPlainText(str(res[5]) if res[5] else "")
        layout.addWidget(txt_tracklist)

        def choose_image():
            filepath, _ = QFileDialog.getOpenFileName(dlg, "Sélectionner une pochette", "",
                                                      "Images (*.png *.jpg *.jpeg)")
            if filepath:
                try:
                    with Image.open(filepath) as img:
                        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                        img.thumbnail((600, 600), Image.Resampling.LANCZOS)
                        img_byte_arr = io.BytesIO()
                        img.save(img_byte_arr, format='JPEG', quality=85)
                        encoded_string = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")
                        dlg.new_cover_data = f"base64:{encoded_string}"
                    update_preview(dlg.new_cover_data)
                except Exception as e:
                    QMessageBox.critical(dlg, "Erreur", f"Impossible de lire l'image : {e}")

        btn_img = QPushButton("🖼️ Changer la pochette (Fichier Local)")
        btn_img.setStyleSheet("background-color: #485460; color: white; padding: 8px; border-radius: 5px;")
        btn_img.clicked.connect(choose_image)
        layout.addWidget(btn_img)

        def save_edits():
            conn = sqlite3.connect(self.db_name)
            conn.execute(
                """UPDATE vinyles SET artiste=?, titre=?, annee=?, formats=?, prix_bas=?, tracklist=?, cover_url=? WHERE discogs_id=?""",
                (entries["Artiste"].text(), entries["Titre"].text(), entries["Année"].text(), entries["Format"].text(),
                 entries["Prix"].text(), txt_tracklist.toPlainText().strip(), dlg.new_cover_data, discogs_id))
            conn.commit()
            conn.close()
            dlg.accept()
            self.load_library_data()

        btn_save = QPushButton("💾 Enregistrer les modifications")
        btn_save.setStyleSheet(
            "background-color: #0fb9b1; color: black; padding: 8px; border-radius: 5px; font-weight: bold;")
        btn_save.clicked.connect(save_edits)
        layout.addWidget(btn_save)

        dlg.exec()

    def export_to_csv(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Sauvegarder Excel", "Ma_Bibliotheque.csv", "CSV (*.csv)")
        if not filepath: return
        try:
            conn = sqlite3.connect(self.db_name)
            lignes = conn.execute(
                "SELECT discogs_id, artiste, titre, annee, formats, prix_bas, tracklist FROM vinyles ORDER BY artiste ASC").fetchall()
            conn.close()
            with open(filepath, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["ID Discogs", "Artiste", "Titre", "Année", "Format", "Prix bas estimé", "Tracklist"])
                writer.writerows(lignes)
            QMessageBox.information(self, "Succès", f"Export Excel réussi !\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur export : {e}")

    def export_to_pdf(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Sauvegarder PDF", "Ma_Bibliotheque.pdf", "PDF (*.pdf)")
        if not filepath: return
        try:
            conn = sqlite3.connect(self.db_name)
            lignes = conn.execute(
                "SELECT artiste, titre, annee, formats, prix_bas, tracklist FROM vinyles ORDER BY artiste ASC").fetchall()
            conn.close()

            html = """
            <html>
            <head>
                <style>
                    table { border-collapse: collapse; width: 100%; }
                    th { background-color: #34495e; color: white; padding: 8px; text-align: left; }
                    td { border: 1px solid #bdc3c7; padding: 6px; vertical-align: top; font-size: 10pt; }
                    .tracklist { font-size: 8pt; color: #2c3e50; }
                </style>
            </head>
            <body>
                <h1 style='color:#2c3e50; text-align:center;'>Ma Bibliothèque de Vinyles</h1>
                <table>
                    <tr>
                        <th>Artiste / Titre</th>
                        <th>Année</th>
                        <th>Format</th>
                        <th>Prix</th>
                        <th>Tracklist</th>
                    </tr>
            """
            for l in lignes:
                tracks_formatted = str(l[5]).replace('\n', '<br>') if l[5] else "N/A"
                html += f"<tr><td><b>{l[0]}</b><br>{l[1]}</td><td>{l[2]}</td><td>{l[3]}</td><td>{l[4]}</td><td class='tracklist'>{tracks_formatted}</td></tr>"

            html += "</table></body></html>"

            doc = QTextDocument()
            doc.setHtml(html)
            writer = QPdfWriter(filepath)
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            writer.setPageMargins(QMarginsF(10, 10, 10, 10))
            writer.setResolution(300)
            doc.print(writer)
            QMessageBox.information(self, "Succès", f"Export PDF réussi !\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur export : {e}")

    # ==========================================
    # CRÉATION MANUELLE D'UN VINYLE
    # ==========================================
    def open_create_window(self):
        self.hide_bubble()

        dlg = QDialog(self)
        dlg.setWindowTitle("Créer un Vinyle (Hors Discogs)")
        dlg.resize(450, 750)
        dlg.setStyleSheet(
            "QDialog { background-color: #1e272e; color: white; } QLabel { color: white; } QLineEdit, QTextEdit { background-color: #353b48; color: white; border: 1px solid #485460; }")
        layout = QVBoxLayout(dlg)

        dlg.new_cover_data = ""

        lbl_preview = QLabel("Aucune image")
        lbl_preview.setFixedSize(150, 150)
        lbl_preview.setStyleSheet("background-color: #34495e; border-radius: 5px; color: white;")
        lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_preview, alignment=Qt.AlignmentFlag.AlignHCenter)

        def update_preview(url_data):
            pixmap = self.get_qpixmap_from_bytes(self.get_image_bytes(url_data), 150, 150)
            if pixmap:
                lbl_preview.setPixmap(pixmap)
            else:
                lbl_preview.setText("Aucune image")

        entries = {}
        fields = ["Artiste", "Titre", "Année", "Format", "Prix"]
        for label in fields:
            layout.addWidget(QLabel(f"{label} :"))
            line = QLineEdit()
            entries[label] = line
            layout.addWidget(line)

        layout.addWidget(QLabel("Tracklist :"))
        txt_tracklist = QTextEdit()
        layout.addWidget(txt_tracklist)

        def choose_image():
            filepath, _ = QFileDialog.getOpenFileName(dlg, "Sélectionner une pochette", "",
                                                      "Images (*.png *.jpg *.jpeg)")
            if filepath:
                try:
                    with Image.open(filepath) as img:
                        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                        img.thumbnail((600, 600), Image.Resampling.LANCZOS)
                        img_byte_arr = io.BytesIO()
                        img.save(img_byte_arr, format='JPEG', quality=85)
                        encoded_string = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")
                        dlg.new_cover_data = f"base64:{encoded_string}"
                    update_preview(dlg.new_cover_data)
                except Exception as e:
                    QMessageBox.critical(dlg, "Erreur", f"Impossible de lire l'image : {e}")

        btn_img = QPushButton("🖼️ Ajouter une pochette")
        btn_img.setStyleSheet("background-color: #485460; color: white; padding: 8px; border-radius: 5px;")
        btn_img.clicked.connect(choose_image)
        layout.addWidget(btn_img)

        def save_new_vinyl():
            artiste = entries["Artiste"].text().strip() or "Inconnu"
            titre = entries["Titre"].text().strip() or "Sans titre"

            custom_id = int(time.time() * 1000) & 0x7FFFFFFF
            faux_code_barres = f"CUSTOM_{custom_id}"

            saved = self.save_to_database(
                barcode=faux_code_barres,
                discogs_id=custom_id,
                artists=artiste,
                title=titre,
                year=entries["Année"].text().strip(),
                country="N/A",
                genres="Personnalisé",
                styles="Personnalisé",
                labels="Indépendant / Hors Discogs",
                formats=entries["Format"].text().strip(),
                tracks_str=txt_tracklist.toPlainText().strip(),
                prix_actuel=entries["Prix"].text().strip(),
                cover_url=dlg.new_cover_data
            )

            if saved:
                QMessageBox.information(dlg, "Succès", "Vinyle personnalisé ajouté !")
                dlg.accept()
                self.tabs.setCurrentIndex(1)

        btn_save = QPushButton("💾 Créer et Sauvegarder")
        btn_save.setStyleSheet(
            "background-color: #0fb9b1; color: black; padding: 8px; border-radius: 5px; font-weight: bold;")
        btn_save.clicked.connect(save_new_vinyl)
        layout.addWidget(btn_save)

        dlg.exec()

    # ==========================================
    # BULLE CONTEXTUELLE
    # ==========================================
    def on_table_select(self):
        selected = self.table.selectedItems()
        if not selected:
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
            self.hide_bubble()
            return

        self.btn_edit.setEnabled(True)
        self.btn_delete.setEnabled(True)

        row = selected[0].row()
        discogs_id = self.table.item(row, 0).text()

        conn = sqlite3.connect(self.db_name)
        res = conn.execute("SELECT titre, cover_url, tracklist FROM vinyles WHERE discogs_id=?",
                           (discogs_id,)).fetchone()
        conn.close()

        if res: self.show_contextual_bubble(res[0], res[1], res[2])

    def show_contextual_bubble(self, titre, cover_url, tracklist):
        self.hide_bubble()

        self.bubble = QWidget(self)
        self.bubble.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.bubble.setStyleSheet("background-color: #2c3e50; border: 2px solid #f39c12; border-radius: 5px;")

        layout = QVBoxLayout(self.bubble)

        header_layout = QHBoxLayout()
        lbl_title = QLabel(titre)
        lbl_title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet("border: none; color: white;")

        btn_close = QPushButton("✖")
        btn_close.setFixedSize(25, 25)
        btn_close.setStyleSheet("background-color: transparent; color: #e74c3c; border: none; font-weight: bold;")
        btn_close.clicked.connect(self.hide_bubble)

        header_layout.addWidget(lbl_title, stretch=1)
        header_layout.addWidget(btn_close)
        layout.addLayout(header_layout)

        self.lbl_bubble_img = QLabel("Chargement...")
        self.lbl_bubble_img.setFixedSize(150, 150)
        self.lbl_bubble_img.setStyleSheet("background-color: #34495e; border: none; color: white;")
        self.lbl_bubble_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_bubble_img, alignment=Qt.AlignmentFlag.AlignHCenter)

        txt_track = QTextEdit()
        txt_track.setPlainText(str(tracklist) if tracklist else "Tracklist indisponible.")
        txt_track.setReadOnly(True)
        txt_track.setFixedSize(250, 150)
        txt_track.setStyleSheet("background-color: #1e272e; border: none; color: white;")
        layout.addWidget(txt_track)

        cursor_pos = QCursor.pos()
        self.bubble.move(cursor_pos.x() + 15, cursor_pos.y() + 15)
        self.bubble.show()

        if cover_url:
            QTimer.singleShot(10, lambda: self.load_bubble_image(cover_url))

    def load_bubble_image(self, url):
        pixmap = self.get_qpixmap_from_bytes(self.get_image_bytes(url), 150, 150)
        if self.bubble and self.bubble.isVisible():
            if pixmap:
                self.lbl_bubble_img.setPixmap(pixmap)
            else:
                self.lbl_bubble_img.setText("Erreur Image")

    def hide_bubble(self):
        if self.bubble:
            self.bubble.close()
            self.bubble = None

    # ==========================================
    # BOUCLE DE SCAN WEBCAM & API
    # ==========================================
    def update_scanner_background(self):
        if self.tabs.currentIndex() != 0 or self.last_barcode is not None:
            return

        ret, frame = self.cap.read()
        if ret:
            if self.last_barcode is None:
                barcodes = decode(frame)
                if barcodes:
                    barcode_data = barcodes[0].data.decode("utf-8")
                    self.last_barcode = barcode_data
                    self.lbl_status.setText(f"Code : {barcode_data}\nInterrogation API...")
                    self.set_indicator("orange", "RECHERCHE...")
                    self.fetch_full_metadata(barcode_data)

            frame_display = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame_display, cv2.COLOR_BGR2RGB)

            if self.last_barcode is None:
                h, w, _ = rgb_frame.shape
                cv2.rectangle(rgb_frame, (w // 4, h // 4), (3 * w // 4, 3 * h // 4), (15, 185, 177), 2)

            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image).scaled(self.lbl_video.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                        Qt.TransformationMode.SmoothTransformation)
            self.lbl_video.setPixmap(pixmap)

    def manual_search(self):
        query = self.input_manual.text().strip()
        if not query: return

        self.last_barcode = "MANUAL_SEARCH"
        self.lbl_status.setText(f"Recherche : {query}\nInterrogation API...")
        self.set_indicator("orange", "RECHERCHE...")
        QApplication.processEvents()

        if self.token_discogs == "Token" or self.token_discogs == "":
            QMessageBox.warning(self, "Token", "Veuillez ajouter votre Token d'API Discogs.")
            self.set_indicator("red", "ERREUR TOKEN")
            QTimer.singleShot(3000, self.reset_scanner)
            return

        headers = {"User-Agent": "VinylScannerAppQt/1.0"}
        api_url = "https://api.discogs.com/database/search"
        parametres = {"q": query, "type": "release", "token": self.token_discogs}

        try:
            resp = requests.get(api_url, params=parametres, headers=headers, verify=False)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    release_id = results[0]["id"]
                    cover_url = results[0].get("cover_image")

                    self.lbl_status.setText(f"Disque trouvé (ID: {release_id}).\nRécupération...")
                    QApplication.processEvents()

                    r_resp = requests.get(f"https://api.discogs.com/releases/{release_id}?token={self.token_discogs}",
                                          headers=headers, verify=False)
                    s_resp = requests.get(
                        f"https://api.discogs.com/marketplace/stats/{release_id}?token={self.token_discogs}",
                        headers=headers, verify=False)

                    if r_resp.status_code == 200:
                        full_data = r_resp.json()
                        stats_data = s_resp.json() if s_resp.status_code == 200 else {}

                        if full_data.get("images"):
                            primary = [i for i in full_data["images"] if i.get("type") == "primary"]
                            cover_url = primary[0].get("resource_url") if primary else full_data["images"][0].get(
                                "resource_url")

                        self.set_indicator("green", "EN ATTENTE")
                        faux_code_barres = f"MANUAL_ID_{release_id}"
                        self.process_found_vinyl(faux_code_barres, release_id, full_data, stats_data, cover_url)
                        return
                    else:
                        self.set_indicator("red", "ERREUR API")
                else:
                    self.lbl_status.setText("Aucun résultat trouvé sur Discogs.")
                    self.set_indicator("red", "INTROUVABLE")
            else:
                self.set_indicator("red", f"ERREUR {resp.status_code}")
        except Exception as e:
            self.set_indicator("red", "ERREUR RÉSEAU")
            print(e)

        QTimer.singleShot(4000, self.reset_scanner)

    def fetch_full_metadata(self, barcode):
        if self.token_discogs == "Token" or self.token_discogs == "":
            QMessageBox.warning(self, "Token", "Veuillez ajouter votre Token d'API Discogs.")
            self.set_indicator("red", "ERREUR TOKEN")
            QTimer.singleShot(3000, self.reset_scanner)
            return

        headers = {"User-Agent": "VinylScannerAppQt/1.0"}
        search_url = f"https://api.discogs.com/database/search?barcode={barcode}&token={self.token_discogs}"

        try:
            resp = requests.get(search_url, headers=headers, verify=False)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    release_id = results[0]["id"]
                    cover_url = results[0].get("cover_image")

                    self.lbl_status.setText(f"Disque trouvé (ID: {release_id}).\nRécupération...")
                    QApplication.processEvents()

                    r_resp = requests.get(f"https://api.discogs.com/releases/{release_id}?token={self.token_discogs}",
                                          headers=headers, verify=False)
                    s_resp = requests.get(
                        f"https://api.discogs.com/marketplace/stats/{release_id}?token={self.token_discogs}",
                        headers=headers, verify=False)

                    if r_resp.status_code == 200:
                        full_data = r_resp.json()
                        stats_data = s_resp.json() if s_resp.status_code == 200 else {}

                        if full_data.get("images"):
                            primary = [i for i in full_data["images"] if i.get("type") == "primary"]
                            cover_url = primary[0].get("resource_url") if primary else full_data["images"][0].get(
                                "resource_url")

                        self.set_indicator("green", "EN ATTENTE")
                        self.process_found_vinyl(barcode, release_id, full_data, stats_data, cover_url)
                        return
                    else:
                        self.set_indicator("red", "ERREUR API")
                else:
                    self.lbl_status.setText("Code-barres introuvable.")
                    self.set_indicator("red", "INTROUVABLE")
            else:
                self.set_indicator("red", f"ERREUR {resp.status_code}")
        except Exception as e:
            self.set_indicator("red", "ERREUR RÉSEAU")
            print(e)

        QTimer.singleShot(4000, self.reset_scanner)

    def process_found_vinyl(self, barcode, discogs_id, data, stats, cover_url):
        title = data.get("title", "Inconnu")
        artists = ", ".join([a.get("name", "Inconnu") for a in data.get("artists", [])])
        year = str(data.get("year", "Année inconnue"))
        country = data.get("country", "Pays inconnu")
        genres = ", ".join(data.get("genres", []))
        styles = ", ".join(data.get("styles", []))
        labels = ", ".join([f"{l.get('name')} (Cat: {l.get('catno', 'N/A')})" for l in data.get("labels", [])])

        formats_list = data.get("formats", [])
        formats_str = f"{formats_list[0].get('name', '')} - " + ", ".join(
            formats_list[0].get('descriptions', [])) if formats_list else ""

        stats_lp = stats.get("lowest_price")
        prix_actuel = f"{stats_lp.get('value')} {stats_lp.get('currency')}" if stats_lp and not stats.get(
            "blocked_from_sale") else "Aucune offre"

        tracks_str = "\n".join(
            [f"   {t.get('position', '')} - {t.get('title', 'Sans titre')}" for t in data.get("tracklist", [])])

        self.current_vinyl_data = {
            "barcode": barcode, "discogs_id": discogs_id, "artists": artists, "title": title,
            "year": year, "country": country, "genres": genres, "styles": styles, "labels": labels,
            "formats": formats_str, "tracks_str": tracks_str, "prix_actuel": prix_actuel, "cover_url": cover_url
        }

        pixmap = self.get_qpixmap_from_bytes(self.get_image_bytes(cover_url), 300, 300)
        if pixmap:
            self.lbl_cover.setPixmap(pixmap)
        else:
            self.lbl_cover.setText("Erreur image")

        self.btn_save.setEnabled(True)
        self.btn_cancel.setEnabled(True)

        affichage = f"🎵 ARTISTE : {artists}\n💿 TITRE : {title}\n📅 ANNÉE : {year} ({country})\n"
        affichage += f"🏷️ LABEL(S) : {labels}\n📀 FORMAT : {formats_str}\n"
        affichage += "-" * 40 + "\n📋 TRACKLIST :\n" + tracks_str + "\n" + "-" * 40 + "\n"
        affichage += f"📈 MARCHÉ ACTUEL : {stats.get('num_for_sale', 0)} en vente. Prix bas : {prix_actuel}"

        self.lbl_status.setText("Vinyle prêt. Veuillez valider ou ignorer.")
        self.text_info.setPlainText(affichage)

    def confirm_save(self):
        if self.current_vinyl_data and self.save_to_database(**self.current_vinyl_data):
            QMessageBox.information(self, "Succès", "Vinyle ajouté à votre bibliothèque !")
            self.reset_scanner()

    def reset_scanner(self):
        self.current_vinyl_data = None
        self.btn_save.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.last_barcode = None
        self.input_manual.clear()
        self.set_indicator("orange", "PRÊT À SCANNER")
        self.lbl_cover.clear()
        self.lbl_cover.setText("Pochette\n(Après scan)")
        self.lbl_status.setText("En attente d'un scan...")
        self.text_info.clear()

    def closeEvent(self, event):
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
        event.accept()


if __name__ == "__main__":
    import urllib3

    urllib3.disable_warnings()

    app = QApplication(sys.argv)
    window = VinylScannerApp()
    window.show()
    sys.exit(app.exec())
