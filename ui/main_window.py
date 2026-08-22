try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

from DooAnimKit.core.temp_control import TempControlManager
from DooAnimKit.core.mirror import PoseMirrorEngine
from DooAnimKit.core.temp_aim import TempAimEngine
from DooAnimKit.core.motion_trail import MotionTrailManager
from DooAnimKit.core.tween_engine import TweenEngine
from DooAnimKit.core.action_registry import ActionRegistry
from DooAnimKit.ui.canvas_widget import SpatialActionCanvas


class DooAnimKitHubWindow(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    """Main single-window Hub for DooAnimKit."""

    UI_NAME = "DooAnimKitHubWindow"

    def __init__(self, parent=None):
        super(DooAnimKitHubWindow, self).__init__(parent=parent)
        self.setObjectName(self.UI_NAME)
        self.setWindowTitle("DooAnimKit — Spatial Hub")

        # Core Engines
        self.temp_ctrl_mgr = TempControlManager()
        self.temp_aim_engine = TempAimEngine(main_window=self)
        self.pose_mirror_engine = PoseMirrorEngine()
        self.trail_mgr = MotionTrailManager()
        self.tween_engine = TweenEngine()

        # Action Registry
        self.action_registry = ActionRegistry(self)

        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Quick Toolbar
        top_bar = QtWidgets.QHBoxLayout()
        btn_paste = QtWidgets.QPushButton("📋 Paste Screenshot (Win+Shift+S)")
        btn_paste.setFixedHeight(28)
        btn_paste.setStyleSheet("background-color: #00796B; color: white; font-weight: bold;")

        btn_clear = QtWidgets.QPushButton("🧹 Clear Hub")
        btn_clear.setFixedHeight(28)
        btn_clear.setStyleSheet("background-color: #455A64; color: white;")

        top_bar.addWidget(btn_paste)
        top_bar.addWidget(btn_clear)
        layout.addLayout(top_bar)

        # 2. Canvas Widget
        self.canvas = SpatialActionCanvas(self)
        btn_paste.clicked.connect(self.canvas.paste_image_from_clipboard)
        btn_clear.clicked.connect(self.canvas.clear_all)
        layout.addWidget(self.canvas)

        # 3. Helper Footer
        tip = QtWidgets.QLabel("RMB: Tools Menu | Ctrl + Click on Tool: Add Button | Ctrl + Drag: Move")
        tip.setStyleSheet("color: #888888; font-size: 10px;")
        tip.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(tip)

    def sync_ui_state(self):
        self.canvas.update()