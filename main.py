import sys
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import QSettings
from image_tab import ImageTab

class MainWindow(QMainWindow):
    def __init__(self):
       
        super().__init__()

       
        self.setWindowTitle("Генератор водяных знаков")

        self.settings = QSettings("MyCompany", "WatermarkApp")

        try:
            with open("style.qss", "r", encoding="utf-8") as f:
                style_sheet = f.read()
                self.setStyleSheet(style_sheet)
        except FileNotFoundError:
            print("Файл 'style.qss' не найден. Стили не будут применены.")

       
        self.image_tab = ImageTab(self.settings)

        
        self.setCentralWidget(self.image_tab)

       
        self.resize(1000, 700)



if __name__ == "__main__":
    
    app = QApplication(sys.argv)

    
    window = MainWindow()

    
    window.show()

    sys.exit(app.exec())
