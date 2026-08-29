"""
Kimodo AI Motion Generator UI & Maya Reference Loader.
Floating tool window that calls an external background worker (QThread + subprocess)
and references the generated skeleton into the Maya scene.
"""

import os
import tempfile
import maya.cmds as cmds

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

from DooAnimKit.core.kimodo_worker import KimodoWorker


class KimodoMotionDialog(QtWidgets.QWidget):
    """Floating window for Kimodo text-to-motion generation."""

    def __init__(self, main_window=None, parent=None):
        super(KimodoMotionDialog, self).__init__(parent=parent)
        self.main_window = main_window
        self.worker = None

        self.setWindowTitle("NVIDIA Kimodo — Text-to-Motion")
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint)
        self.resize(380, 280)

        # 1. Шлях до інтерпретатора у вашому створеному оточенні kimodo_env
        self.python_exe = r"C:\Users\wpupp\miniconda3\envs\kimodo_env\python.exe"

        # 2. Автоматичне визначення шляху до скрипта-генератора
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.generator_script = os.path.join(base_dir, "core", "kimodo_generator.py")

        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Prompt Input
        lbl_prompt = QtWidgets.QLabel("📝 Motion Prompt:")
        lbl_prompt.setStyleSheet("font-weight: bold; color: #00E5FF;")
        layout.addWidget(lbl_prompt)

        self.txt_prompt = QtWidgets.QTextEdit()
        self.txt_prompt.setPlaceholderText("e.g. fast run forward, jump, idle...")
        self.txt_prompt.setFixedHeight(65)
        layout.addWidget(self.txt_prompt)

        # Timing Parameters
        grp_time = QtWidgets.QGroupBox("⏱️ Timing")
        time_lay = QtWidgets.QHBoxLayout(grp_time)

        time_lay.addWidget(QtWidgets.QLabel("Frames:"))
        self.spn_frames = QtWidgets.QSpinBox()
        self.spn_frames.setRange(24, 2400)
        self.spn_frames.setValue(120)
        time_lay.addWidget(self.spn_frames)

        time_lay.addWidget(QtWidgets.QLabel("FPS:"))
        self.cmb_fps = QtWidgets.QComboBox()
        self.cmb_fps.addItems(["24 fps", "30 fps", "60 fps"])
        self.cmb_fps.setCurrentIndex(1)
        time_lay.addWidget(self.cmb_fps)
        layout.addWidget(grp_time)

        # Progress Bar (активується під час роботи воркера)
        self.prog_bar = QtWidgets.QProgressBar()
        self.prog_bar.setFixedHeight(14)
        self.prog_bar.setVisible(False)
        layout.addWidget(self.prog_bar)

        # Action Button
        self.btn_gen = QtWidgets.QPushButton("🚀 Generate & Reference Skeleton")
        self.btn_gen.setFixedHeight(34)
        self.btn_gen.setStyleSheet("""
            QPushButton {
                background-color: #2E7D32;
                color: white;
                font-weight: bold;
                font-size: 12px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #388E3C; }
            QPushButton:disabled { background-color: #555555; color: #888888; }
        """)
        self.btn_gen.clicked.connect(self._on_start_generation)
        layout.addWidget(self.btn_gen)

    def _on_start_generation(self):
        prompt = self.txt_prompt.toPlainText().strip()
        if not prompt:
            cmds.warning("Please enter a motion prompt first!")
            return

        frames = self.spn_frames.value()
        fps = int(self.cmb_fps.currentText().split()[0])

        # Шлях до тимчасового файлу Maya ASCII
        out_file = os.path.join(tempfile.gettempdir(), "kimodo_motion_out.ma")
        if os.path.exists(out_file):
            try:
                os.remove(out_file)
            except Exception:
                pass

        params = {
            "prompt": prompt,
            "frames": frames,
            "fps": fps,
            "output_path": out_file
        }

        self.btn_gen.setEnabled(False)
        self.prog_bar.setValue(0)
        self.prog_bar.setVisible(True)

        # Запуск фонового процесу без блокування інтерфейсу
        self.worker = KimodoWorker(self.python_exe, self.generator_script, params)
        self.worker.progress.connect(self.prog_bar.setValue)
        self.worker.finished.connect(self._on_success)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_success(self, file_path):
        self.btn_gen.setEnabled(True)
        self.prog_bar.setVisible(False)
        self._reference_motion_to_scene(file_path)

    def _on_failed(self, err_msg):
        self.btn_gen.setEnabled(True)
        self.prog_bar.setVisible(False)
        cmds.warning(f"Kimodo generation failed: {err_msg}")

    def _reference_motion_to_scene(self, file_path):
        """Creates a Reference in Maya under 'Kimodo_Motion' namespace."""
        if not os.path.exists(file_path):
            cmds.warning("Generated motion file does not exist!")
            return

        namespace = "Kimodo_Motion"

        # Видаляємо попередній референс, якщо він уже був у сцені
        existing_refs = cmds.file(query=True, reference=True) or []
        for ref_node in existing_refs:
            if namespace in ref_node:
                try:
                    cmds.file(ref_node, removeReference=True)
                except Exception:
                    pass

        try:
            cmds.file(
                file_path,
                reference=True,
                type="mayaAscii",
                ignoreVersion=True,
                namespace=namespace
            )
            cmds.inViewMessage(
                amg=f"<hl style='color:#00E676;'>✓ Motion Referenced!</hl> Namespace: <b>{namespace}</b>",
                pos="topCenter", fade=True
            )
            print(f"// [Kimodo] Successfully referenced motion from: {file_path}")
        except Exception as e:
            cmds.warning(f"Failed to reference Maya file: {e}")