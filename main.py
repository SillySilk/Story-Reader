import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from reader_window import StoryReader

def main():
    # 1. Setup High DPI scaling (makes text sharp on modern screens)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    # 2. Start the Application
    app = QApplication(sys.argv)
    
    # 3. Create the Window
    print("Initializing Reader Window...")
    reader = StoryReader()
    
    # 4. SHOW the Window (This was missing!)
    print("Showing Window...")
    reader.showMaximized()
    
    # 5. Run the Event Loop
    print("Application Started.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()