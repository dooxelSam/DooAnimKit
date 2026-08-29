"""
Background QThread worker for Nvidia Kimodo Motion Generator.
"""
import os
import subprocess
import time

try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore


class KimodoWorker(QtCore.QThread):
    progress = QtCore.Signal(int)
    finished = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(self, python_exe, script_path, params, parent=None):
        super(KimodoWorker, self).__init__(parent=parent)
        self.python_exe = python_exe
        self.script_path = script_path
        self.params = params

    def run(self):
        try:
            cmd = [
                self.python_exe,
                self.script_path,
                "--prompt", self.params["prompt"],
                "--frames", str(self.params["frames"]),
                "--fps", str(self.params["fps"]),
                "--output", self.params["output_path"]
            ]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Симуляція прогресу під час дифузії на GPU
            prog = 0
            while process.poll() is None:
                time.sleep(0.4)
                if prog < 90:
                    prog += 5
                    self.progress.emit(prog)

            stdout, stderr = process.communicate()

            if process.returncode == 0 and os.path.exists(self.params["output_path"]):
                self.progress.emit(100)
                self.finished.emit(self.params["output_path"])
            else:
                self.failed.emit(stderr or "Generation failed or output FBX not found.")

        except Exception as e:
            self.failed.emit(str(e))