import sys, time, cv2
import numpy as np
from queue import Queue, Empty
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QWidget,
    QVBoxLayout, QHBoxLayout, QFileDialog, QSizePolicy
)
from PySide6.QtGui import QPixmap, QImage

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
        while self.running and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            self.frame_ready.emit(frame)
            time.sleep(1 / 30)
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
        self.q1 = Queue()
        self.q2 = Queue()

        # UI Elements
        self.label = QLabel("🔲 Mixed Output")
        self.label.setStyleSheet("background-color: black; color: white;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.btn1 = QPushButton("🎞 Video 1 (Odd)")
        self.btn2 = QPushButton("🎞 Video 2 (Even)")
        self.btn_play = QPushButton("▶ 재생")
        self.btn_stop = QPushButton("⏹ 중지")

        self.btn1.clicked.connect(self.select_video1)
        self.btn2.clicked.connect(self.select_video2)
        self.btn_play.clicked.connect(self.start_mixing)
        self.btn_stop.clicked.connect(self.stop_all)

        # Layout
        top = QHBoxLayout()
        top.addWidget(self.btn1)
        top.addWidget(self.btn2)
        top.addWidget(self.btn_play)
        top.addWidget(self.btn_stop)

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self.label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Variables
        self.path1 = ""
        self.path2 = ""
        self.decoder1 = None
        self.decoder2 = None
        self.mixer = None

    def select_video1(self):
        path, _ = QFileDialog.getOpenFileName(self, "Video 1 (Odd Columns)")
        if path:
            self.path1 = path
            self.btn1.setText(f"🎞 1: {path.split('/')[-1]}")

    def select_video2(self):
        path, _ = QFileDialog.getOpenFileName(self, "Video 2 (Even Columns)")
        if path:
            self.path2 = path
            self.btn2.setText(f"🎞 2: {path.split('/')[-1]}")

    def start_mixing(self):
        if not self.path1 or not self.path2:
            return

        # 중복 실행 방지
        self.stop_all()

        # Decoder threads
        self.decoder1 = VideoDecoder(self.path1)
        self.decoder2 = VideoDecoder(self.path2)
        self.decoder1.frame_ready.connect(lambda f: self.q1.put(f))
        self.decoder2.frame_ready.connect(lambda f: self.q2.put(f))
        self.decoder1.start()
        self.decoder2.start()

        # Mixer thread
        self.mixer = MixingThread(self.q1, self.q2)
        self.mixer.mixed_frame_ready.connect(self.update_display)
        self.mixer.start()

    def stop_all(self):
        if self.decoder1:
            self.decoder1.stop()
            self.decoder1 = None
        if self.decoder2:
            self.decoder2.stop()
            self.decoder2 = None
        if self.mixer:
            self.mixer.stop()
            self.mixer = None

    def update_display(self, qimg: QImage):
        pix = QPixmap.fromImage(qimg).scaled(
            self.label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.label.setPixmap(pix)

    def closeEvent(self, event):
        self.stop_all()
        event.accept()

# ────────────────────────────────────────
# Entry Point
# ────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
