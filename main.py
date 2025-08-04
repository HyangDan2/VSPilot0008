import sys, time, cv2
import numpy as np
from queue import Queue, Empty, Full
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QFileDialog, QSizePolicy
)
from PySide6.QtGui import QPixmap, QImage, QAction

# ────────────────────────────────────────
# Decoder Thread
# ────────────────────────────────────────
class VideoDecoder(QThread):
    frame_ready = Signal(np.ndarray)

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.running = True

    def run(self):
        cap = cv2.VideoCapture(self.path)
        fps = cap.get(cv2.CAP_PROP_FPS)

        while self.running and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                cap.open(self.path)
                ret, frame = cap.read()
                print(f"Restart : {self.path}")
                continue
            
            self.frame_ready.emit(frame)
            time.sleep(1/fps)
        cap.release()

    def stop(self):
        self.running = False
        self.quit()
        self.wait()

# ────────────────────────────────────────
# Mixer Thread
# ────────────────────────────────────────
class MixingThread(QThread):
    mixed_frame_ready = Signal(QImage)

    def __init__(self, queue1: Queue, queue2: Queue):
        super().__init__()
        self.q1 = queue1
        self.q2 = queue2
        self.running = True

    def run(self):
        while self.running:
            try:
                f1 = self.q1.get(timeout=1)
                f2 = self.q2.get(timeout=1)
                if f1.shape != f2.shape:
                    continue
                mixed = self.mix_columns(f1, f2)
                h, w, ch = mixed.shape
                rgb = cv2.cvtColor(mixed, cv2.COLOR_BGR2RGB)
                qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
                self.mixed_frame_ready.emit(qimg)
            except Empty:
                continue

    def stop(self):
        self.running = False
        self.quit()
        self.wait()

    def mix_columns(self, f1, f2):
        result = f1.copy()
        result[:, ::2] = f2[:, ::2]  # even columns from f2
        return result


# ────────────────────────────────────────
# Main GUI
# ────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Column Video Mixer: Odd/Even Columns")
        self.resize(1280, 720)

        # Queues for frames
        self.q1 = Queue(maxsize=10)
        self.q2 = Queue(maxsize=10)

        # UI Elements
        self.label = QLabel("🔲 Mixed Output")
        self.label.setStyleSheet("background-color: black; color: white;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.setCentralWidget(self.label)
        self.build_menu()

        # Variables
        self.path1 = ""
        self.path2 = ""
        self.decoder1 = None
        self.decoder2 = None
        self.mixer = None

    def build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        action_video1 = QAction("Video 1 (Odd)", self)
        action_video2 = QAction("Video 2 (Even)", self)
        action_video1.triggered.connect(self.select_video1)
        action_video2.triggered.connect(self.select_video2)
        file_menu.addAction(action_video1)
        file_menu.addAction(action_video2)

        play_menu = menubar.addMenu("Play")
        action_play = QAction("Play", self)
        action_stop = QAction("Stop", self)
        action_play.triggered.connect(self.start_mixing)
        action_stop.triggered.connect(self.stop_all)
        play_menu.addAction(action_play)
        play_menu.addAction(action_stop)


    def select_video1(self):
        path, _ = QFileDialog.getOpenFileName(self, "Video 1 (Odd Columns)")
        if path:
            self.path1 = path

    def select_video2(self):
        path, _ = QFileDialog.getOpenFileName(self, "Video 2 (Even Columns)")
        if path:
            self.path2 = path

    def start_mixing(self):
        if not self.path1 or not self.path2:
            return

        # 중복 실행 방지
        self.stop_all()

        # Decoder threads
        self.decoder1 = VideoDecoder(self.path1)
        self.decoder1.setParent(self)
        self.decoder2 = VideoDecoder(self.path2)
        self.decoder2.setParent(self)
        self.decoder1.frame_ready.connect(lambda f: self.safe_put(self.q1, f))
        self.decoder2.frame_ready.connect(lambda f: self.safe_put(self.q2, f))
        self.decoder1.start()
        self.decoder2.start()

        # Mixer thread
        self.mixer = MixingThread(self.q1, self.q2)
        self.mixer.mixed_frame_ready.connect(self.update_display)
        self.mixer.start()

    def safe_put(self, q: Queue, f: np.ndarray):
        try:
            q.put_nowait(f)
        except Full:
            pass # Frame pass

    def stop_all(self):
        if self.decoder1:
            self.decoder1.stop()
            self.decoder1.deleteLater()
            self.decoder1 = None
        if self.decoder2:
            self.decoder2.stop()
            self.decoder2.deleteLater()
            self.decoder2 = None
        if self.mixer:
            self.mixer.stop()
            self.mixer = None
        
    def toggle_fullscreen(self):
        if self.isFullScreen() == True :
            self.showNormal()
            self.menuBar().show()
        else:
            self.showFullScreen()
            self.menuBar().hide()

    def update_display(self, qimg: QImage):
        pix = QPixmap.fromImage(qimg).scaled(
            self.label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.label.setPixmap(pix)
        

    def closeEvent(self, event):
        self.stop_all()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.toggle_fullscreen()
        if event.key() == Qt.Key.Key_1:
            self.select_video1()
        if event.key() == Qt.Key.Key_2:
            self.select_video2()
        if event.key() == Qt.Key.Key_3:
            self.start_mixing()


# ────────────────────────────────────────
# Entry Point
# ────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
