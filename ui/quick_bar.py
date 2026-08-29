import os
import json
try:
    from PySide6 import QtWidgets, QtGui, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtGui, QtCore

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
import maya.cmds as cmds


class QuickBarSliderWidget(QtWidgets.QWidget):
    """AnimBot-style compact interactive slider item."""

    TICK_OFFSETS = [
        (-0.85, 50.0, "-50%"),
        (-0.58, 20.0, "-20%"),
        (-0.30, 5.0, "-5%"),
        (0.30, 5.0, "+5%"),
        (0.58, 20.0, "+20%"),
        (0.85, 50.0, "+50%")
    ]

    def __init__(self, slider_data, parent_bar, parent=None):
        super(QuickBarSliderWidget, self).__init__(parent=parent)
        self.slider_data = slider_data
        self.parent_bar = parent_bar
        self.setFixedHeight(26)
        self.setFixedWidth(190)  # Фіксована компактна ширина як в AnimBot
        self.val = 0.0
        self.active_drag = False
        self.cached_state = {}

    def _get_slider_center_rect(self):
        btn_w = 40
        track_w = self.width() - 4
        max_shift = (track_w // 2) - (btn_w // 2) - 2
        mid_x = (self.width() // 2) + int(self.val * max_shift)
        return QtCore.QRect(mid_x - btn_w // 2, 1, btn_w, self.height() - 2)

    def _get_tick_points(self):
        mid_x = self.width() // 2
        mid_y = self.height() // 2
        half_w = (self.width() // 2) - 6
        points = []
        for factor, pct, label in self.TICK_OFFSETS:
            tx = mid_x + int(factor * half_w)
            points.append((tx, mid_y, pct, label))
        return points

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        srect = QtCore.QRect(1, 1, self.width() - 2, self.height() - 2)
        mid_x = srect.center().x()

        # Track background
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#1e232b")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#37474f"), 1.0))
        painter.drawRoundedRect(srect, 4, 4)

        # Center line
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 35), 1, QtCore.Qt.DashLine))
        painter.drawLine(mid_x, srect.y() + 2, mid_x, srect.bottom() - 2)

        # Active fill bar
        if abs(self.val) > 0.02:
            handle_rect = self._get_slider_center_rect()
            hx = handle_rect.center().x()
            fill_rect = QtCore.QRect(min(mid_x, hx), srect.y() + 2, abs(hx - mid_x), srect.height() - 4)
            fill_color = QtGui.QColor("#EC407A") if self.val < 0 else QtGui.QColor("#AB47BC")
            painter.setBrush(QtGui.QBrush(fill_color))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(fill_rect, 2, 2)

        # Tick points
        for tx, ty, pct, label in self._get_tick_points():
            painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 160)))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(QtCore.QPoint(tx, ty), 2, 2)

        # Center Handle
        c_rect = self._get_slider_center_rect()
        col_color = QtGui.QColor(self.slider_data.get("color", "#00838f"))
        painter.setBrush(QtGui.QBrush(col_color))
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1))
        painter.drawRoundedRect(c_rect, 3, 3)

        # Text
        painter.setPen(QtCore.Qt.white)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(7)
        painter.setFont(font)

        if abs(self.val) > 0.04:
            painter.drawText(c_rect, QtCore.Qt.AlignCenter, f"{int(self.val * 100):+d}%")
        else:
            painter.drawText(c_rect, QtCore.Qt.AlignCenter, self.slider_data.get("label", "Tween"))

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            self.parent_bar._show_slider_menu(event.pos(), self)
            return

        if event.button() == QtCore.Qt.LeftButton:
            c_rect = self._get_slider_center_rect()
            if not c_rect.contains(event.pos()):
                for tx, ty, pct, label in self._get_tick_points():
                    if ((event.pos().x() - tx)**2 + (event.pos().y() - ty)**2)**0.5 <= 7:
                        direction = 1 if tx > (self.width() // 2) else -1
                        from DooAnimKit.core.tween_engine import TweenEngine
                        te = TweenEngine()
                        te.step_nudge(direction=direction, step_percent=pct)
                        self.update()
                        return

            self.active_drag = True
            from DooAnimKit.core.tween_engine import TweenEngine
            te = TweenEngine()
            self.cached_state = te.cache_current_tween_state()
            self._update_drag(event.pos().x())

    def mouseMoveEvent(self, event):
        if self.active_drag:
            self._update_drag(event.pos().x())

    def mouseReleaseEvent(self, event):
        if self.active_drag:
            self.val = 0.0
            self.active_drag = False
            self.cached_state.clear()
            self.update()

    def _update_drag(self, mouse_x):
        btn_w = 40
        max_shift = float((self.width() // 2) - (btn_w // 2) - 2)
        offset_x = mouse_x - (self.width() // 2)
        self.val = max(-1.0, min(1.0, offset_x / max(1.0, max_shift)))

        if self.cached_state:
            from DooAnimKit.core.tween_engine import TweenEngine
            te = TweenEngine()
            te.tween_interactive_delta(self.cached_state, self.val)

        self.update()


class DooAnimKitQuickBar(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    """
    AnimBot-style compact toolbar with tight button grouping and no unwanted stretching.
    """

    UI_NAME = "DooAnimKitQuickBar"

    MENU_STYLE = """
        QMenu {
            background-color: #1e222b;
            color: #eceff1;
            border: 1px solid #37474f;
            border-radius: 6px;
            padding: 4px;
            font-size: 11px;
            font-weight: 500;
        }
        QMenu::item {
            padding: 5px 28px 5px 12px;
            border-radius: 4px;
            margin: 1px 2px;
        }
        QMenu::item:selected {
            background-color: #00838f;
            color: #ffffff;
        }
        QMenu::separator {
            height: 1px;
            background-color: #37474f;
            margin: 4px 6px;
        }
        QMenu::section {
            background-color: #263238;
            color: #00bcd4;
            padding: 4px 8px;
            font-size: 10px;
            font-weight: bold;
            border-radius: 3px;
        }
    """

    def __init__(self, parent=None):
        super(DooAnimKitQuickBar, self).__init__(parent=parent)
        self.setObjectName(self.UI_NAME)
        self.setWindowTitle("DooAnimKit — Toolbar")
        self.setFixedHeight(34)  # Компактна висота як в AnimBot
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.presets_dir = os.path.join(base_dir, "presets")
        self.icons_dir = os.path.join(base_dir, "icons")
        self.config_path = os.path.join(self.presets_dir, "quick_bar_data.json")

        if not os.path.exists(self.icons_dir):
            try:
                os.makedirs(self.icons_dir)
            except Exception:
                pass

        self.items_data = [
            {"item_type": "slider", "label": "Tween", "action_id": "tween_mid_50", "color": "#00838f"},
            {"item_type": "button", "label": "Space Switch", "action_id": "space_world", "type": "space", "icon": "", "color": "#00838f"},
            {"item_type": "button", "label": "Global Offset", "action_id": "temp_offset_toggle", "type": "offset", "icon": "", "color": "#e65100"},
            {"item_type": "button", "label": "Smart Temp", "action_id": "temp_smart", "type": "temp", "icon": "", "color": "#1976d2"},
            {"item_type": "button", "label": "Smart Mirror", "action_id": "mirror_pose", "type": "pose", "icon": "", "color": "#1e88e5"},
            {"item_type": "button", "label": "Euler Filter", "action_id": "smart_euler_filter", "type": "anim", "icon": "", "color": "#00acc1"},
            {"item_type": "button", "label": "Reset Pose", "action_id": "default_pose", "type": "pose", "icon": "", "color": "#004d40"},
            {"item_type": "button", "label": "Bake All", "action_id": "temp_bake_all", "type": "bake", "icon": "", "color": "#2e7d32"},
        ]

        self._load_config()
        self._build_ui()

    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "items" in data:
                        self.items_data = data["items"]
                    elif "buttons" in data:
                        self.items_data = data["buttons"]
                        for item in self.items_data:
                            item.setdefault("item_type", "button")
            except Exception:
                pass

    def _save_config(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"items": self.items_data}, f, indent=4)
        except Exception as e:
            print(f"Failed to save quick bar config: {e}")

    def _build_ui(self):
        # Горизонтальна компактна панель
        self.main_layout = QtWidgets.QHBoxLayout(self)
        self.main_layout.setContentsMargins(4, 2, 4, 2)
        self.main_layout.setSpacing(3)
        self.main_layout.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self._populate_items()

    def _populate_items(self):
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for idx, item_data in enumerate(self.items_data):
            if item_data.get("item_type") == "slider":
                slider = QuickBarSliderWidget(item_data, self)
                self.main_layout.addWidget(slider)
            else:
                btn = QtWidgets.QPushButton()
                btn.setFixedSize(26, 26)  # Акуратний розмір кнопок як в AnimBot
                btn.setToolTip(item_data.get("label", "Action"))

                icon_path = item_data.get("icon", "")
                if icon_path and os.path.exists(icon_path):
                    btn.setIcon(QtGui.QIcon(icon_path))
                    btn.setIconSize(QtCore.QSize(18, 18))
                else:
                    label_text = item_data.get("label", "A")
                    btn.setText(label_text[:2].upper())

                col_color = item_data.get("color", "#2b2b2b")
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {col_color};
                        border: 1px solid #3c3c3c;
                        border-radius: 4px;
                        color: #eceff1;
                        font-weight: bold;
                        font-size: 9px;
                    }}
                    QPushButton:hover {{
                        border: 1.2px solid #00e5ff;
                        background-color: #37474f;
                    }}
                    QPushButton:pressed {{
                        background-color: #00838f;
                    }}
                """)

                action_id = item_data.get("action_id")
                btn.clicked.connect(lambda checked=False, aid=action_id: self._execute_action(aid))
                btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                btn.customContextMenuRequested.connect(lambda pos, b=btn, i=idx: self._show_btn_menu(pos, b, i))

                self.main_layout.addWidget(btn)

        # Роздільник
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.VLine)
        sep.setStyleSheet("color: #37474f; margin: 4px 2px;")
        self.main_layout.addWidget(sep)

        # Кнопка додавання (+)
        add_btn = QtWidgets.QPushButton("+")
        add_btn.setFixedSize(24, 24)
        add_btn.setToolTip("Add Button or Slider")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e222b;
                color: #90a4ae;
                font-weight: bold;
                font-size: 13px;
                border: 1px dashed #546e7a;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #37474f;
                color: white;
                border: 1px solid #00e5ff;
            }
        """)
        add_btn.clicked.connect(self._add_item_dialog)
        self.main_layout.addWidget(add_btn)

        # Пружина праворуч, яка блокує розтягування кнопок по ширині
        self.main_layout.addStretch()

    def _execute_action(self, action_id):
        try:
            from DooAnimKit.core.action_registry import ActionRegistry
            from DooAnimKit.core.temp_control import TempControlManager
            from DooAnimKit.core.mirror import PoseMirrorEngine
            from DooAnimKit.core.temp_aim import TempAimEngine
            from DooAnimKit.core.motion_trail import MotionTrailManager
            from DooAnimKit.core.euler_filter import SmartEulerFilter
            from DooAnimKit.core.space_switch import SpaceSwitchEngine
            from DooAnimKit.core.tween_engine import TweenEngine

            dummy_win = type('Dummy', (object,), {
                'temp_ctrl_mgr': TempControlManager(),
                'pose_mirror_engine': PoseMirrorEngine(),
                'temp_aim_engine': TempAimEngine(),
                'trail_mgr': MotionTrailManager(),
                'euler_filter': SmartEulerFilter(),
                'space_engine': SpaceSwitchEngine(),
                'tween_engine': TweenEngine()
            })()
            registry = ActionRegistry(dummy_win)
            registry.execute(action_id)
        except Exception as e:
            cmds.warning(f"Could not execute action {action_id}: {e}")

    def _show_slider_menu(self, pos, slider_widget):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(self.MENU_STYLE)
        menu.addSection(f"Slider: {slider_widget.slider_data.get('label', 'Tween')}")

        action_rename = menu.addAction("✏️ Rename Slider...")
        action_color = menu.addAction("🎨 Pick Handle Color...")
        menu.addSeparator()
        action_delete = menu.addAction("🗑 Delete Slider")

        chosen = menu.exec_(slider_widget.mapToGlobal(pos))
        idx = self.items_data.index(slider_widget.slider_data) if slider_widget.slider_data in self.items_data else -1

        if chosen == action_rename and idx != -1:
            new_lbl, ok = QtWidgets.QInputDialog.getText(
                self, "Rename Slider", "Enter slider label:", text=slider_widget.slider_data.get("label", "")
            )
            if ok and new_lbl:
                self.items_data[idx]["label"] = new_lbl
                self._save_config()
                self._populate_items()
        elif chosen == action_color and idx != -1:
            col = QtWidgets.QColorDialog.getColor(
                QtGui.QColor(slider_widget.slider_data.get("color", "#00838f")), self, "Select Handle Color"
            )
            if col.isValid():
                self.items_data[idx]["color"] = col.name()
                self._save_config()
                self._populate_items()
        elif chosen == action_delete and idx != -1:
            self.items_data.pop(idx)
            self._save_config()
            self._populate_items()

    def _show_btn_menu(self, pos, btn_widget, index):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(self.MENU_STYLE)

        btn_info = self.items_data[index]
        btn_type = btn_info.get("type", "action")

        menu.addSection(f"{btn_info.get('label', 'Action')}")

        if btn_type == "space":
            space_menu = menu.addMenu("🌐 Space Targets")
            space_menu.setStyleSheet(self.MENU_STYLE)
            act_world = space_menu.addAction("🌍 World Space")
            act_hip = space_menu.addAction("🦴 Hips / Root")
            act_chest = space_menu.addAction("👕 Chest")
            act_custom = space_menu.addAction("🎯 Selected Target Object...")
            space_menu.addSeparator()
            act_bake_space = space_menu.addAction("🔥 Bake & Restore Space")

            from DooAnimKit.core.space_switch import SpaceSwitchEngine
            engine = SpaceSwitchEngine()

            act_world.triggered.connect(engine.switch_to_world)
            act_hip.triggered.connect(lambda: self._switch_to_smart_target("*Hip*", "*Pelvis*", "*Root*"))
            act_chest.triggered.connect(lambda: self._switch_to_smart_target("*Chest*", "*Spine*"))
            act_custom.triggered.connect(self._switch_to_custom_dialog)
            act_bake_space.triggered.connect(engine.bake_and_restore)

        elif btn_type == "offset":
            act_off_on = menu.addAction("⏱ Enable Offset")
            act_off_off = menu.addAction("⏹ Disable Offset")
            act_off_on.triggered.connect(lambda: self._set_offset_state(True))
            act_off_off.triggered.connect(lambda: self._set_offset_state(False))

        elif btn_type == "pose":
            menu.addAction("📋 Copy Pose").triggered.connect(lambda: self._execute_action("copy_pose"))
            menu.addAction("📌 Paste Pose").triggered.connect(lambda: self._execute_action("paste_pose"))
            menu.addAction("🪞 Smart Mirror / Flip").triggered.connect(lambda: self._execute_action("mirror_pose"))

        menu.addSeparator()
        icon_act = menu.addAction("🖼 Set Custom PNG Icon...")
        rename_act = menu.addAction("✏️ Rename Tooltip...")
        color_act = menu.addAction("🎨 Pick Background Color...")
        menu.addSeparator()
        del_act = menu.addAction("🗑 Delete Button")

        chosen = menu.exec_(btn_widget.mapToGlobal(pos))

        if chosen == icon_act:
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select Icon PNG", self.icons_dir, "Image Files (*.png *.jpg *.jpeg)"
            )
            if file_path:
                self.items_data[index]["icon"] = file_path
                self._save_config()
                self._populate_items()

        elif chosen == rename_act:
            current_label = btn_info.get("label", "")
            new_label, ok = QtWidgets.QInputDialog.getText(
                self, "Rename Button", "Enter new tooltip:", text=current_label
            )
            if ok and new_label:
                self.items_data[index]["label"] = new_label
                self._save_config()
                self._populate_items()

        elif chosen == color_act:
            col = QtWidgets.QColorDialog.getColor(QtGui.QColor(btn_info.get("color", "#2b2b2b")), self, "Select Color")
            if col.isValid():
                self.items_data[index]["color"] = col.name()
                self._save_config()
                self._populate_items()

        elif chosen == del_act:
            if 0 <= index < len(self.items_data):
                self.items_data.pop(index)
                self._save_config()
                self._populate_items()

    def _switch_to_smart_target(self, *patterns):
        from DooAnimKit.core.space_switch import SpaceSwitchEngine
        engine = SpaceSwitchEngine()
        for pat in patterns:
            found = cmds.ls(pat, type="transform") or []
            if found:
                engine.switch_to_custom(found[0])
                return
        cmds.warning(f"No target matching {patterns} found in scene!")

    def _switch_to_custom_dialog(self):
        from DooAnimKit.core.space_switch import SpaceSwitchEngine
        engine = SpaceSwitchEngine()
        target, ok = QtWidgets.QInputDialog.getText(self, "Custom Space", "Enter target object name:")
        if ok and target:
            engine.switch_to_custom(target.strip())

    def _set_offset_state(self, state):
        from DooAnimKit.core.temp_control import TempControlManager
        mgr = TempControlManager()
        mgr.set_offset_mode(state)

    def _add_item_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Add Item to Toolbar")
        dialog.setFixedWidth(280)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(QtWidgets.QLabel("Choose Item Type:"))

        type_combo = QtWidgets.QComboBox()
        type_combo.addItem("🎚 Interactive Slider", "slider")
        type_combo.addItem("🔘 Action / Space Button", "button")
        layout.addWidget(type_combo)

        layout.addWidget(QtWidgets.QLabel("Label / Name:"))
        label_input = QtWidgets.QLineEdit("Tween")
        layout.addWidget(label_input)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            item_type = type_combo.currentData()
            new_label = label_input.text().strip() or "Tween"

            if item_type == "slider":
                self.items_data.append({
                    "item_type": "slider",
                    "label": new_label,
                    "action_id": "tween_mid_50",
                    "color": "#00838f"
                })
            else:
                self.items_data.append({
                    "item_type": "button",
                    "label": new_label,
                    "action_id": "tween_mid_50",
                    "type": "action",
                    "icon": "",
                    "color": "#336699"
                })

            self._save_config()
            self._populate_items()