try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

from DooAnimKit.core.temp_control import TempControlManager
from DooAnimKit.core.mirror import PoseMirrorEngine
from DooAnimKit.core.temp_aim import TempAimEngine
from DooAnimKit.core.temp_ik import TempIKManager
from DooAnimKit.core.motion_trail import MotionTrailManager
from DooAnimKit.core.tween_engine import TweenEngine
from DooAnimKit.core.euler_filter import SmartEulerFilter
from DooAnimKit.core.action_registry import ActionRegistry
from DooAnimKit.ui.canvas_widget import SpatialActionCanvas


class DooAnimKitHubWindow(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    """Main single-window Hub for DooAnimKit with responsive proportional scaling."""

    UI_NAME = "DooAnimKitHubWindow"

    def __init__(self, parent=None):
        super(DooAnimKitHubWindow, self).__init__(parent=parent)
        self.setObjectName(self.UI_NAME)
        self.setWindowTitle("DooAnimKit — Spatial Hub")

        # Engines
        self.temp_ctrl_mgr = TempControlManager()
        self.pose_mirror_engine = PoseMirrorEngine()
        self.temp_aim_engine = TempAimEngine()
        self.temp_ik_mgr = TempIKManager(self)
        self.trail_mgr = MotionTrailManager()
        self.tween_engine = TweenEngine()
        self.euler_filter = SmartEulerFilter()

        # Action Registry & HUD Reference
        self.action_registry = ActionRegistry(self)
        self.aim_window = None

        self._is_resizing = False
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Quick Toolbar
        top_bar = QtWidgets.QHBoxLayout()
        btn_paste = QtWidgets.QPushButton("📋 Paste Screenshot (Win+Shift+S)")
        btn_paste.setFixedHeight(28)
        btn_paste.setStyleSheet("background-color: #00796B; color: white; font-weight: bold; border-radius: 4px;")

        btn_clear = QtWidgets.QPushButton("🧹 Clear Hub")
        btn_clear.setFixedHeight(28)
        btn_clear.setStyleSheet("background-color: #455A64; color: white; border-radius: 4px;")

        top_bar.addWidget(btn_paste)
        top_bar.addWidget(btn_clear)
        layout.addLayout(top_bar)

        # Offset Active Banner
        self.offset_banner = QtWidgets.QLabel("⚠️ TIMELINE OFFSET IS ACTIVE (Curves will shift dynamically)")
        self.offset_banner.setFixedHeight(24)
        self.offset_banner.setAlignment(QtCore.Qt.AlignCenter)
        self.offset_banner.setStyleSheet(
            "background-color: #E65100; color: white; font-weight: bold; font-size: 11px; border-radius: 3px;"
        )
        self.offset_banner.setVisible(False)
        layout.addWidget(self.offset_banner)

        # Interactive Canvas
        self.canvas = SpatialActionCanvas(self)
        btn_paste.clicked.connect(self.canvas.paste_image_from_clipboard)
        btn_clear.clicked.connect(self.canvas.clear_all)
        layout.addWidget(self.canvas)

        # Tip Footer
        tip = QtWidgets.QLabel("RMB: Menu / Tools | Ctrl + Left Drag: Move Button/Pin")
        tip.setStyleSheet("color: #888888; font-size: 10px;")
        tip.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(tip)

    def sync_ui_state(self):
        is_offset_on = getattr(self.temp_ctrl_mgr, "offset_active", False)
        self.offset_banner.setVisible(is_offset_on)
        self.canvas.update()