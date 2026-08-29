try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
import maya.cmds as cmds

from DooAnimKit.core.temp_control import TempControlManager
from DooAnimKit.core.mirror import PoseMirrorEngine
from DooAnimKit.core.temp_aim import TempAimEngine
from DooAnimKit.core.motion_trail import MotionTrailManager
from DooAnimKit.core.euler_filter import SmartEulerFilter
from DooAnimKit.core.space_switch import SpaceSwitchEngine
from DooAnimKit.core.tween_engine import TweenEngine
from DooAnimKit.core.action_registry import ActionRegistry
from DooAnimKit.ui.canvas_widget import SpatialActionCanvas
from DooAnimKit.ui.quick_bar import DooAnimKitQuickBar


class DooAnimKitHubWindow(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    """Main single-window Hub for DooAnimKit with dedicated Quick Bar Toolbar."""

    UI_NAME = "DooAnimKitHubWindow"

    def __init__(self, parent=None):
        super(DooAnimKitHubWindow, self).__init__(parent=parent)
        self.setObjectName(self.UI_NAME)
        self.setWindowTitle("DooAnimKit — Spatial Hub")

        self.temp_ctrl_mgr = TempControlManager()
        self.pose_mirror_engine = PoseMirrorEngine()
        self.temp_aim_engine = TempAimEngine()
        self.trail_mgr = MotionTrailManager()
        self.euler_filter = SmartEulerFilter()
        self.space_engine = SpaceSwitchEngine()
        self.tween_engine = TweenEngine()

        self.action_registry = ActionRegistry(self)
        self.quick_bar_instance = None
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        top_bar = QtWidgets.QHBoxLayout()
        btn_paste = QtWidgets.QPushButton("📋 Paste Screenshot")
        btn_paste.setFixedHeight(28)
        btn_paste.setStyleSheet("background-color: #00796B; color: white; font-weight: bold; border-radius: 4px;")

        btn_toolbar = QtWidgets.QPushButton("⚡ Open Toolbar")
        btn_toolbar.setFixedHeight(28)
        btn_toolbar.setStyleSheet("background-color: #5E35B1; color: white; font-weight: bold; border-radius: 4px;")
        btn_toolbar.setToolTip("Відкрити виносний тулбар швидких кнопок (як в AnimBot)")
        btn_toolbar.clicked.connect(self.toggle_quick_bar)

        btn_clear = QtWidgets.QPushButton("🧹 Clear")
        btn_clear.setFixedHeight(28)
        btn_clear.setStyleSheet("background-color: #455A64; color: white; border-radius: 4px;")

        top_bar.addWidget(btn_paste)
        top_bar.addWidget(btn_toolbar)
        top_bar.addWidget(btn_clear)
        layout.addLayout(top_bar)

        self.canvas = SpatialActionCanvas(self)
        btn_paste.clicked.connect(self.canvas.paste_image_from_clipboard)
        btn_clear.clicked.connect(self.canvas.clear_all)
        layout.addWidget(self.canvas)

        tip = QtWidgets.QLabel("Drag Slider Center: Interactive Tween | RMB on Toolbar Icons: Submenu Options")
        tip.setStyleSheet("color: #888888; font-size: 10px;")
        tip.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(tip)

    def toggle_quick_bar(self):
        if self.quick_bar_instance is not None:
            try:
                self.quick_bar_instance.close()
                self.quick_bar_instance.deleteLater()
            except Exception:
                pass
            self.quick_bar_instance = None
            cmds.inViewMessage(amg="Toolbar closed.", pos="topCenter", fade=True)
            return

        ws_name = f"{DooAnimKitQuickBar.UI_NAME}WorkspaceControl"
        if cmds.workspaceControl(ws_name, exists=True):
            try:
                cmds.deleteUI(ws_name, control=True)
            except Exception:
                pass

        self.quick_bar_instance = DooAnimKitQuickBar(parent=self)
        self.quick_bar_instance.show(dockable=True)
        cmds.inViewMessage(amg="Toolbar opened!", pos="topCenter", fade=True)

    def sync_ui_state(self):
        self.canvas.update()