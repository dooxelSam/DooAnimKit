try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui


class ViewportAimHUD(QtWidgets.QWidget):
    """Floating tool window with real-time sliders for Temp Aim setup."""

    def __init__(self, aim_engine, parent=None):
        super(ViewportAimHUD, self).__init__(parent=parent)
        self.aim_engine = aim_engine
        self.is_applied = False  # Flag to prevent discarding on successful apply

        self.setWindowTitle("Temp Aim Options")
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint)
        self.setFixedWidth(280)

        self._build_ui()
        self._on_values_changed()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 1. Aim Axis
        h_aim = QtWidgets.QHBoxLayout()
        h_aim.addWidget(QtWidgets.QLabel("Aim Axis:"))
        self.lbl_axis = QtWidgets.QLabel("+X")
        self.lbl_axis.setStyleSheet("font-weight: bold; color: #00BCD4; font-size: 12px;")
        h_aim.addWidget(self.lbl_axis)
        layout.addLayout(h_aim)

        self.sld_aim = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sld_aim.setRange(0, 5)
        self.sld_aim.setValue(0)
        self.sld_aim.valueChanged.connect(self._on_values_changed)
        layout.addWidget(self.sld_aim)

        # 2. Twist Roll
        h_twist = QtWidgets.QHBoxLayout()
        h_twist.addWidget(QtWidgets.QLabel("Twist Roll:"))
        self.lbl_twist = QtWidgets.QLabel("0°")
        self.lbl_twist.setStyleSheet("font-weight: bold; color: #00BCD4; font-size: 12px;")
        h_twist.addWidget(self.lbl_twist)
        layout.addLayout(h_twist)

        self.sld_twist = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sld_twist.setRange(0, 3)
        self.sld_twist.setValue(0)
        self.sld_twist.valueChanged.connect(self._on_values_changed)
        layout.addWidget(self.sld_twist)

        # 3. Distance
        h_dist = QtWidgets.QHBoxLayout()
        h_dist.addWidget(QtWidgets.QLabel("Distance:"))
        self.lbl_dist = QtWidgets.QLabel("30")
        self.lbl_dist.setStyleSheet("font-weight: bold; color: #00BCD4; font-size: 12px;")
        h_dist.addWidget(self.lbl_dist)
        layout.addLayout(h_dist)

        self.sld_dist = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sld_dist.setRange(5, 150)
        self.sld_dist.setValue(30)
        self.sld_dist.valueChanged.connect(self._on_values_changed)
        layout.addWidget(self.sld_dist)

        layout.addSpacing(6)

        # Buttons Box
        btn_box = QtWidgets.QHBoxLayout()
        btn_apply = QtWidgets.QPushButton("Apply (Zero Offset)")
        btn_apply.setFixedHeight(28)
        btn_apply.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold;")
        btn_apply.clicked.connect(self._on_apply)

        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.setFixedHeight(28)
        btn_cancel.setStyleSheet("background-color: #C62828; color: white; font-weight: bold;")
        btn_cancel.clicked.connect(self._on_cancel)

        btn_box.addWidget(btn_apply)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

    def _on_values_changed(self):
        aim_idx = self.sld_aim.value()
        twist_idx = self.sld_twist.value()
        dist = self.sld_dist.value()

        angles = ["0°", "90°", "180°", "270°"]
        self.lbl_axis.setText(self.aim_engine.AIM_AXES[aim_idx][0])
        self.lbl_twist.setText(angles[twist_idx])
        self.lbl_dist.setText(str(dist))

        self.aim_engine.update_preview(aim_idx, twist_idx, dist)

    def _on_apply(self):
        self.is_applied = True
        self.aim_engine.apply_aim(self.sld_aim.value(), self.sld_twist.value(), self.sld_dist.value())
        self.close()

    def _on_cancel(self):
        self.is_applied = False
        self.aim_engine.discard()
        self.close()

    def closeEvent(self, event):
        # Discard only if the user closed the window without clicking Apply
        if not self.is_applied:
            self.aim_engine.discard()
        event.accept()