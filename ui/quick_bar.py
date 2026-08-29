import os
import json
try:
    from PySide6 import QtWidgets, QtGui, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtGui, QtCore

from maya.app.general.mayaMixin import MayaQWidgetDockableMixin
import maya.cmds as cmds
from DooAnimKit.core.mirror import PoseMirrorEngine


def tint_pixmap_blend(pixmap, color_hex="#00E676", alpha_ratio=0.50):
    """
    Subtly blends 50% tint color over original icon's non-transparent pixels,
    keeping original details while showing a distinct emerald glow.
    """
    if pixmap.isNull():
        return pixmap

    result = QtGui.QPixmap(pixmap.size())
    result.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(result)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

    # 1. Base icon
    painter.drawPixmap(0, 0, pixmap)

    # 2. 50% color overlay over alpha silhouette
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceAtop)
    tint_col = QtGui.QColor(color_hex)
    tint_col.setAlphaF(alpha_ratio)
    painter.fillRect(result.rect(), tint_col)

    painter.end()
    return result


class HoverIconButton(QtWidgets.QPushButton):
    """Clean PNG Icon button with 50% alpha-hover tinting."""

    def __init__(self, icon_path, parent=None):
        super(HoverIconButton, self).__init__(parent=parent)
        self.setFixedSize(24, 24)
        self.icon_path = icon_path

        self.normal_pix = QtGui.QPixmap(icon_path).scaled(
            18, 18, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
        )
        self.hover_pix = tint_pixmap_blend(self.normal_pix, color_hex="#00E676", alpha_ratio=0.50)

        self.setIcon(QtGui.QIcon(self.normal_pix))
        self.setIconSize(QtCore.QSize(18, 18))

        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: transparent;
                border: none;
            }
            QPushButton:pressed {
                background-color: transparent;
                border: none;
            }
        """)

    def enterEvent(self, event):
        self.setIcon(QtGui.QIcon(self.hover_pix))
        super(HoverIconButton, self).enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(QtGui.QIcon(self.normal_pix))
        super(HoverIconButton, self).leaveEvent(event)


class QuickBarSliderWidget(QtWidgets.QWidget):
    """AnimBot-style sleek slider with slim track and mode switching."""

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
        self.setFixedHeight(24)
        self.setFixedWidth(175)
        self.val = 0.0
        self.active_drag = False
        self.cached_state = {}

    def _get_slider_center_rect(self):
        btn_w = 36
        btn_h = 20
        track_w = self.width() - 4
        max_shift = (track_w // 2) - (btn_w // 2) - 2
        mid_x = (self.width() // 2) + int(self.val * max_shift)
        mid_y = self.height() // 2
        return QtCore.QRect(mid_x - btn_w // 2, mid_y - btn_h // 2, btn_w, btn_h)

    def _get_tick_points(self):
        mid_x = self.width() // 2
        mid_y = self.height() // 2
        half_w = (self.width() // 2) - 8
        points = []
        for factor, pct, label in self.TICK_OFFSETS:
            tx = mid_x + int(factor * half_w)
            points.append((tx, mid_y, pct, label))
        return points

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        mid_x = self.width() // 2
        mid_y = self.height() // 2

        # Slim Track (5px)
        track_h = 5
        track_rect = QtCore.QRect(4, mid_y - track_h // 2, self.width() - 8, track_h)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#181b22")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#323846"), 1.0))
        painter.drawRoundedRect(track_rect, 2.5, 2.5)

        # Active Fill
        if abs(self.val) > 0.02:
            handle_rect = self._get_slider_center_rect()
            hx = handle_rect.center().x()
            fill_rect = QtCore.QRect(min(mid_x, hx), mid_y - track_h // 2, abs(hx - mid_x), track_h)
            fill_color = QtGui.QColor("#EC407A") if self.val < 0 else QtGui.QColor("#AB47BC")
            painter.setBrush(QtGui.QBrush(fill_color))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(fill_rect, 2, 2)

        # Ticks
        for tx, ty, pct, label in self._get_tick_points():
            painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 170)))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(QtCore.QPoint(tx, ty), 1.5, 1.5)

        # Center Handle
        c_rect = self._get_slider_center_rect()
        col_color = QtGui.QColor(self.slider_data.get("color", "#00838f"))
        painter.setBrush(QtGui.QBrush(col_color))
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 210), 1))
        painter.drawRoundedRect(c_rect, 3, 3)

        painter.setPen(QtCore.Qt.white)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(7)
        painter.setFont(font)

        mode = self.slider_data.get("mode", "Tween")
        if abs(self.val) > 0.04:
            if mode == "Offset":
                shift_val = int(round(self.val * 10))
                painter.drawText(c_rect, QtCore.Qt.AlignCenter, f"{shift_val:+d}f")
            else:
                painter.drawText(c_rect, QtCore.Qt.AlignCenter, f"{int(self.val * 100):+d}%")
        else:
            painter.drawText(c_rect, QtCore.Qt.AlignCenter, self.slider_data.get("label", "Tween"))

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            self.parent_bar._show_slider_menu(event.pos(), self)
            return

        if event.button() == QtCore.Qt.LeftButton:
            c_rect = self._get_slider_center_rect()
            mode = self.slider_data.get("mode", "Tween")

            if not c_rect.contains(event.pos()):
                for tx, ty, pct, label in self._get_tick_points():
                    if ((event.pos().x() - tx)**2 + (event.pos().y() - ty)**2)**0.5 <= 7:
                        direction = 1 if tx > (self.width() // 2) else -1
                        if mode == "Offset":
                            from DooAnimKit.core.time_offset_engine import TimeOffsetEngine
                            toe = TimeOffsetEngine()
                            step_frames = 1 if pct <= 5.0 else (2 if pct <= 20.0 else 5)
                            toe.step_shift(direction * step_frames)
                        else:
                            from DooAnimKit.core.tween_engine import TweenEngine
                            te = TweenEngine()
                            te.step_nudge(direction=direction, step_percent=pct)
                        self.update()
                        return

            self.active_drag = True
            if mode == "Offset":
                from DooAnimKit.core.time_offset_engine import TimeOffsetEngine
                toe = TimeOffsetEngine()
                self.cached_state = toe.cache_time_state()
            else:
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
        btn_w = 36
        max_shift = float((self.width() // 2) - (btn_w // 2) - 2)
        offset_x = mouse_x - (self.width() // 2)
        self.val = max(-1.0, min(1.0, offset_x / max(1.0, max_shift)))

        mode = self.slider_data.get("mode", "Tween")
        if self.cached_state:
            if mode == "Offset":
                from DooAnimKit.core.time_offset_engine import TimeOffsetEngine
                toe = TimeOffsetEngine()
                shift_frames = self.val * 10.0
                toe.offset_interactive_delta(self.cached_state, shift_frames)
            else:
                from DooAnimKit.core.tween_engine import TweenEngine
                te = TweenEngine()
                te.tween_interactive_delta(self.cached_state, self.val)

        self.update()


class DooAnimKitQuickBar(MayaQWidgetDockableMixin, QtWidgets.QWidget):
    """
    AnimBot-style compact toolbar synchronized with DooAnimKitHubWindow.
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
        self.setFixedHeight(32)
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

        scan_icon = os.path.join(self.icons_dir, "scanCh.png")

        self.items_data = [
            {"item_type": "slider", "label": "Tween", "mode": "Tween", "action_id": "tween_mid_50", "color": "#00838f"},
            {"item_type": "slider", "label": "Offset", "mode": "Offset", "action_id": "time_offset", "color": "#00695c"},
            {"item_type": "button", "label": "Scan / Default Pose", "action_id": "default_pose", "type": "scan", "icon": scan_icon if os.path.exists(scan_icon) else "", "color": "#5e35b1"},
            {"item_type": "button", "label": "Space Switch", "action_id": "space_world", "type": "space", "icon": "", "color": "#00838f"},
            {"item_type": "button", "label": "Global Offset", "action_id": "temp_offset_toggle", "type": "offset", "icon": "", "color": "#e65100"},
            {"item_type": "button", "label": "Smart Temp", "action_id": "temp_smart", "type": "temp", "icon": "", "color": "#1976d2"},
            {"item_type": "button", "label": "Smart Mirror", "action_id": "mirror_pose", "type": "pose", "icon": "", "color": "#1e88e5"},
            {"item_type": "button", "label": "Euler Filter", "action_id": "smart_euler_filter", "type": "anim", "icon": "", "color": "#00acc1"},
            {"item_type": "button", "label": "Bake All", "action_id": "temp_bake_all", "type": "bake", "icon": "", "color": "#2e7d32"},
        ]

        self._load_config()
        self._build_ui()

    def _load_config(self):
        scan_icon = os.path.join(self.icons_dir, "scanCh.png")
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "items" in data:
                        self.items_data = data["items"]
                        for item in self.items_data:
                            if item.get("action_id") in ("scan_rig", "default_pose") and os.path.exists(scan_icon):
                                item["icon"] = scan_icon
                            if item.get("item_type") == "slider":
                                item.setdefault("mode", "Tween")
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

        from DooAnimKit.core.temp_control import TempControlManager
        temp_mgr = TempControlManager()
        is_offset_on = getattr(temp_mgr, "offset_active", False)

        for idx, item_data in enumerate(self.items_data):
            if item_data.get("item_type") == "slider":
                slider = QuickBarSliderWidget(item_data, self)
                self.main_layout.addWidget(slider)
            else:
                action_id = item_data.get("action_id")
                is_offset_btn = (action_id == "temp_offset_toggle")
                icon_path = item_data.get("icon", "")

                if icon_path and os.path.exists(icon_path):
                    btn = HoverIconButton(icon_path, parent=self)
                    btn.setToolTip(item_data.get("label", "Action"))
                else:
                    btn = QtWidgets.QPushButton()
                    btn.setFixedSize(24, 24)
                    btn.setToolTip(item_data.get("label", "Action"))
                    label_text = item_data.get("label", "A")
                    btn.setText(label_text[:2].upper())

                    if is_offset_btn and is_offset_on:
                        col_color = "#E65100"
                        border_style = "2px solid #FFCC80"
                    else:
                        col_color = item_data.get("color", "#2b2b2b")
                        border_style = "1px solid #3c3c3c"

                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {col_color};
                            border: {border_style};
                            border-radius: 4px;
                            color: #eceff1;
                            font-weight: bold;
                            font-size: 9px;
                        }}
                        QPushButton:hover {{
                            background-color: {col_color};
                            border: {border_style};
                        }}
                        QPushButton:pressed {{
                            background-color: #00838f;
                        }}
                    """)

                btn.clicked.connect(lambda checked=False, aid=action_id: self._execute_action(aid))
                btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                btn.customContextMenuRequested.connect(lambda pos, b=btn, i=idx: self._show_btn_menu(pos, b, i))

                self.main_layout.addWidget(btn)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.VLine)
        sep.setStyleSheet("color: #37474f; margin: 4px 2px;")
        self.main_layout.addWidget(sep)

        add_btn = QtWidgets.QPushButton("+")
        add_btn.setFixedSize(22, 22)
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
                background-color: #1e222b;
                color: #ffffff;
                border: 1px dashed #00e5ff;
            }
            QPushButton:pressed {
                background-color: #37474f;
            }
        """)
        add_btn.clicked.connect(lambda: self._show_tools_add_menu(add_btn.mapToGlobal(QtCore.QPoint(0, add_btn.height()))))
        self.main_layout.addWidget(add_btn)

        self.main_layout.addStretch()

    def _execute_action(self, action_id):
        try:
            if action_id == "scan_rig":
                engine = PoseMirrorEngine()
                engine.scan_selected_rig()
            elif action_id == "default_pose":
                engine = PoseMirrorEngine()
                engine.reset_to_default_pose()
            else:
                from DooAnimKit.core.action_registry import ActionRegistry
                from DooAnimKit.core.temp_control import TempControlManager
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

            try:
                import DooAnimKit
                if getattr(DooAnimKit, "_hub_instance", None) is not None:
                    DooAnimKit._hub_instance.sync_ui_state()
            except Exception:
                pass

            self._populate_items()
        except Exception as e:
            cmds.warning(f"Could not execute action {action_id}: {e}")

    def _show_btn_menu(self, pos, btn_widget, index):
        btn_info = self.items_data[index]
        icon_path = btn_info.get("icon", "")

        # Зберігаємо 50% зелений відтінок під час відкритого меню
        if icon_path and os.path.exists(icon_path):
            norm_pix = QtGui.QPixmap(icon_path).scaled(18, 18, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            tinted_pix = tint_pixmap_blend(norm_pix, "#00E676", alpha_ratio=0.50)
            btn_widget.setIcon(QtGui.QIcon(tinted_pix))

        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(self.MENU_STYLE)
        btn_type = btn_info.get("type", "action")

        menu.addSection(f"{btn_info.get('label', 'Action')}")

        if btn_type == "scan":
            act_scan = menu.addAction("🔍 Scan Rig (Set Neutral Pose)")
            act_reset = menu.addAction("🧘 Reset to Default Pose")

            chosen = menu.exec_(btn_widget.mapToGlobal(pos))
            if chosen == act_scan:
                self._execute_action("scan_rig")
            elif chosen == act_reset:
                self._execute_action("default_pose")
            else:
                self._populate_items()
            return

        elif btn_type == "space":
            space_menu = menu.addMenu("Space Targets")
            space_menu.setStyleSheet(self.MENU_STYLE)
            act_world = space_menu.addAction("World Space")
            act_hip = space_menu.addAction("Hips / Root")
            act_chest = space_menu.addAction("Chest")
            act_custom = space_menu.addAction("Selected Target Object...")
            space_menu.addSeparator()
            act_bake_space = space_menu.addAction("Bake & Restore Space")

            from DooAnimKit.core.space_switch import SpaceSwitchEngine
            engine = SpaceSwitchEngine()

            act_world.triggered.connect(engine.switch_to_world)
            act_hip.triggered.connect(lambda: self._switch_to_smart_target("*Hip*", "*Pelvis*", "*Root*"))
            act_chest.triggered.connect(lambda: self._switch_to_smart_target("*Chest*", "*Spine*"))
            act_custom.triggered.connect(self._switch_to_custom_dialog)
            act_bake_space.triggered.connect(engine.bake_and_restore)

        elif btn_type == "offset":
            act_off_on = menu.addAction("Enable Offset")
            act_off_off = menu.addAction("Disable Offset")
            act_off_on.triggered.connect(lambda: self._set_offset_state(True))
            act_off_off.triggered.connect(lambda: self._set_offset_state(False))

        elif btn_type == "pose":
            menu.addAction("Copy Pose").triggered.connect(lambda: self._execute_action("copy_pose"))
            menu.addAction("Paste Pose").triggered.connect(lambda: self._execute_action("paste_pose"))
            menu.addAction("Smart Mirror / Flip").triggered.connect(lambda: self._execute_action("mirror_pose"))

        menu.addSeparator()
        icon_act = menu.addAction("Set Custom PNG Icon...")
        rename_act = menu.addAction("Rename Tooltip...")
        color_act = menu.addAction("Pick Background Color...")
        menu.addSeparator()
        del_act = menu.addAction("Delete Button")

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
        else:
            self._populate_items()

    def _show_slider_menu(self, pos, slider_widget):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(self.MENU_STYLE)
        menu.addSection(f"Slider: {slider_widget.slider_data.get('label', 'Slider')}")

        mode_menu = menu.addMenu("🔄 Switch Slider Mode")
        mode_menu.setStyleSheet(self.MENU_STYLE)
        act_mode_tween = mode_menu.addAction("⚖️ Tween Mode (Breakdown)")
        act_mode_offset = mode_menu.addAction("⏱️ Loop Time Offset (Range)")

        action_rename = menu.addAction("✏️ Rename Label...")
        action_color = menu.addAction("🎨 Pick Handle Color...")
        menu.addSeparator()
        action_delete = menu.addAction("🗑 Delete Slider")

        chosen = menu.exec_(slider_widget.mapToGlobal(pos))
        idx = self.items_data.index(slider_widget.slider_data) if slider_widget.slider_data in self.items_data else -1
        if idx == -1:
            return

        if chosen == act_mode_tween:
            self.items_data[idx]["mode"] = "Tween"
            self.items_data[idx]["label"] = "Tween"
            self.items_data[idx]["action_id"] = "tween_mid_50"
            self.items_data[idx]["color"] = "#00838f"
            self._save_config()
            self._populate_items()
        elif chosen == act_mode_offset:
            self.items_data[idx]["mode"] = "Offset"
            self.items_data[idx]["label"] = "Offset"
            self.items_data[idx]["action_id"] = "time_offset"
            self.items_data[idx]["color"] = "#00695c"
            self._save_config()
            self._populate_items()
        elif chosen == action_rename:
            new_lbl, ok = QtWidgets.QInputDialog.getText(
                self, "Rename Slider", "Enter slider label:", text=slider_widget.slider_data.get("label", "")
            )
            if ok and new_lbl:
                self.items_data[idx]["label"] = new_lbl
                self._save_config()
                self._populate_items()
        elif chosen == action_color:
            col = QtWidgets.QColorDialog.getColor(
                QtGui.QColor(slider_widget.slider_data.get("color", "#00838f")), self, "Select Handle Color"
            )
            if col.isValid():
                self.items_data[idx]["color"] = col.name()
                self._save_config()
                self._populate_items()
        elif chosen == action_delete:
            self.items_data.pop(idx)
            self._save_config()
            self._populate_items()

    def _show_tools_add_menu(self, global_pos):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(self.MENU_STYLE)

        act_add_tween_slider = menu.addAction("🎚 Add Tween Slider")
        act_add_offset_slider = menu.addAction("⏱️ Add Time Offset Slider (Range)")
        menu.addSeparator()

        all_actions = self._get_registry_action_list()

        categories_map = {
            "Tween": menu.addMenu("Tween"),
            "Temp Controls": menu.addMenu("Temp Controls"),
            "Pose": menu.addMenu("Pose"),
            "Animation": menu.addMenu("Animation"),
            "Bake": menu.addMenu("Bake")
        }

        for sub in categories_map.values():
            sub.setStyleSheet(self.MENU_STYLE)

        for act in all_actions:
            cat = act.get("category")
            if cat in categories_map:
                item = categories_map[cat].addAction(act["name"])
                item.setData(act)

        menu.addSeparator()
        for direct_id, direct_title in [("temp_offset_toggle", "Global Offset"), ("trail_toggle", "Motion Trail")]:
            act = next((a for a in all_actions if a["id"] == direct_id), None)
            if act:
                item = menu.addAction(direct_title)
                item.setData(act)

        menu.addSeparator()
        for direct_id, direct_title in [("scan_rig", "Scan Rig (Validate Skeleton)"), ("default_pose", "Reset to Default Pose")]:
            act = next((a for a in all_actions if a["id"] == direct_id), None)
            if act:
                item = menu.addAction(direct_title)
                item.setData(act)

        chosen = menu.exec_(global_pos)
        ctrl_held = bool(QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ControlModifier)

        if chosen == act_add_tween_slider:
            self.items_data.append({
                "item_type": "slider",
                "label": "Tween",
                "mode": "Tween",
                "action_id": "tween_mid_50",
                "color": "#00838f"
            })
            self._save_config()
            self._populate_items()

        elif chosen == act_add_offset_slider:
            self.items_data.append({
                "item_type": "slider",
                "label": "Offset",
                "mode": "Offset",
                "action_id": "time_offset",
                "color": "#00695c"
            })
            self._save_config()
            self._populate_items()

        elif chosen and chosen.data():
            act_data = chosen.data()
            scan_icon = os.path.join(self.icons_dir, "scanCh.png")
            btn_icon = scan_icon if (act_data["id"] in ("scan_rig", "default_pose") and os.path.exists(scan_icon)) else ""
            btn_type = "scan" if act_data["id"] in ("scan_rig", "default_pose") else "action"

            if ctrl_held:
                label, ok = QtWidgets.QInputDialog.getText(
                    self, "Button Name", "Enter button label for Toolbar:", text=act_data.get("name", "Action")
                )
                if ok and label:
                    self.items_data.append({
                        "item_type": "button",
                        "label": label,
                        "action_id": act_data["id"],
                        "type": btn_type,
                        "icon": btn_icon,
                        "color": act_data.get("color", "#336699")
                    })
                    self._save_config()
                    self._populate_items()
            else:
                self._execute_action(act_data["id"])

    def _get_registry_action_list(self):
        try:
            from DooAnimKit.core.action_registry import ActionRegistry
            from DooAnimKit.core.temp_control import TempControlManager
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
            return registry.get_action_list()
        except Exception:
            return []

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
        self._populate_items()