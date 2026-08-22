import os
import json
import math

try:
    from PySide6 import QtWidgets, QtGui, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtGui, QtCore

import maya.cmds as cmds
import maya.mel as mel


class SpatialActionCanvas(QtWidgets.QWidget):
    """Interactive canvas with background character screenshot, customizable pins, and movable action buttons."""

    PIN_RADIUS = 9

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
            padding: 5px 22px 5px 10px;
            border-radius: 4px;
            margin: 1px 2px;
        }
        QMenu::item:selected {
            background-color: #00838f;
            color: #ffffff;
        }
        QMenu::item:disabled {
            color: #546e7a;
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
        QMenu::right-arrow {
            margin-right: 6px;
        }
    """

    def __init__(self, main_window, parent=None):
        super(SpatialActionCanvas, self).__init__(parent=parent)
        self.setMinimumSize(400, 500)
        self.main_window = main_window
        self.action_registry = main_window.action_registry

        self.pixmap = None
        self.pins = []
        self.buttons = []

        self.is_box_selecting = False
        self.box_start = QtCore.QPoint()
        self.box_current = QtCore.QPoint()

        # Drag States (Ctrl + Drag)
        self.dragged_button = None
        self.dragged_pin = None
        self.drag_offset = QtCore.QPoint()

        # Context menu spawn click cache
        self.last_menu_pos_norm = (0.5, 0.5)

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.presets_dir = os.path.join(base_dir, "presets")
        self.img_path = os.path.join(self.presets_dir, "picker_img.png")
        self.data_path = os.path.join(self.presets_dir, "picker_data.json")

        self._ensure_storage_dir()
        self._load_saved_data()

    def _ensure_storage_dir(self):
        if not os.path.exists(self.presets_dir):
            try:
                os.makedirs(self.presets_dir)
            except Exception:
                pass

    def save_state(self):
        self._ensure_storage_dir()
        if self.pixmap and not self.pixmap.isNull():
            self.pixmap.save(self.img_path, "PNG")
        elif os.path.exists(self.img_path):
            try:
                os.remove(self.img_path)
            except Exception:
                pass

        data = {"pins": self.pins, "buttons": self.buttons}
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving DooAnimKit state: {e}")

    def _load_saved_data(self):
        if os.path.exists(self.img_path):
            self.pixmap = QtGui.QPixmap(self.img_path)
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.pins = data.get("pins", [])
                    self.buttons = data.get("buttons", [])
            except Exception:
                self.pins, self.buttons = [], []

    def paste_image_from_clipboard(self):
        cb = QtWidgets.QApplication.clipboard()
        mime = cb.mimeData()
        if mime.hasImage():
            self.pixmap = cb.pixmap()
            self.save_state()
            self.update()
            return True
        cmds.warning("No image found in clipboard! Press Win + Shift + S first.")
        return False

    def clear_all(self):
        self.pins.clear()
        self.buttons.clear()
        self.pixmap = None
        self.save_state()
        self.update()

    def save_preset_to_file(self):
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Preset", self.presets_dir, "JSON Files (*.json)"
        )
        if file_path:
            if not file_path.endswith(".json"):
                file_path += ".json"
            data = {"pins": self.pins, "buttons": self.buttons}
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                img_file = file_path.replace(".json", "_img.png")
                if self.pixmap and not self.pixmap.isNull():
                    self.pixmap.save(img_file, "PNG")
                elif os.path.exists(img_file):
                    os.remove(img_file)
                cmds.inViewMessage(amg="Preset saved successfully!", pos="topCenter", fade=True)
            except Exception as e:
                cmds.warning(f"Failed to save preset: {e}")

    def open_preset_from_file(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Preset", self.presets_dir, "JSON Files (*.json)"
        )
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.pins = data.get("pins", [])
                    self.buttons = data.get("buttons", [])
                img_file = file_path.replace(".json", "_img.png")
                self.pixmap = QtGui.QPixmap(img_file) if os.path.exists(img_file) else None
                self.save_state()
                self.update()
                cmds.inViewMessage(amg="Preset loaded successfully!", pos="topCenter", fade=True)
            except Exception as e:
                cmds.warning(f"Failed to load preset: {e}")

    # --- AUTO HOTKEY REGISTRATION ---

    def register_action_to_maya_hotkeys(self, action_id, label="Action"):
        api_map = {
            "tween_step_left": "tween_step_left",
            "tween_step_right": "tween_step_right",
            "tween_snap_left": "tween_snap_left",
            "tween_snap_right": "tween_snap_right",
            "tween_mid_50": "tween_breakdown_50",
            "temp_smart": "create_smart",
            "temp_offset_toggle": "toggle_offset_mode",
            "temp_aim_create": "create_temp_aim",
            "temp_set_pivot": "create_pivot_locator",
            "temp_bake_pivot": "apply_pivot_locator",
            "copy_pose": "copy_pose",
            "paste_pose": "paste_pose",
            "mirror_pose": "mirror_pose",
            "copy_anim": "copy_animation",
            "paste_anim": "paste_animation",
            "mirror_anim": "mirror_animation",
            "bake_selected": "bake_selected",
            "temp_bake_all": "bake_all",
            "toggle_sampling": "toggle_bake_sampling",
            "trail_toggle": "toggle_motion_trail",
            "scan_rig": "scan_rig",
            "default_pose": "reset_default_pose"
        }

        func_name = api_map.get(action_id, action_id)
        cmd_name = f"DooAnim_{func_name}"
        name_cmd_name = f"{cmd_name}NameCommand"
        python_code = f"import DooAnimKit; DooAnimKit.api.{func_name}()"

        if cmds.runTimeCommand(cmd_name, exists=True):
            cmds.runTimeCommand(cmd_name, edit=True, delete=True)

        cmds.runTimeCommand(
            cmd_name,
            category="DooAnimKit",
            commandLanguage="python",
            command=python_code,
            annotation=f"DooAnimKit: {label}"
        )

        cmds.nameCommand(
            name_cmd_name,
            annotation=f"DooAnimKit: {label}",
            command=cmd_name
        )

        try:
            mel.eval("HotkeyPreferencesWindow;")
        except Exception:
            try:
                mel.eval("hotkeyEditor;")
            except Exception as e:
                cmds.warning(f"Could not open Hotkey Editor automatically: {e}")

        cmds.inViewMessage(
            amg=f"Command <hl>{cmd_name}</hl> ready! Assign key in Category: <hl>'DooAnimKit'</hl>.",
            pos="topCenter", fade=True
        )

    def _get_image_rect(self):
        if not self.pixmap or self.pixmap.isNull():
            return QtCore.QRect()
        scaled = self.pixmap.scaled(self.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        return QtCore.QRect(
            (self.width() - scaled.width()) // 2,
            (self.height() - scaled.height()) // 2,
            scaled.width(),
            scaled.height()
        )

    def _get_btn_rect(self, btn, img_rect):
        bx = img_rect.x() + int(btn["u"] * img_rect.width())
        by = img_rect.y() + int(btn["v"] * img_rect.height())
        return QtCore.QRect(bx, by, btn.get("w", 110), btn.get("h", 26))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        img_rect = self._get_image_rect()

        if self.pixmap and not self.pixmap.isNull():
            painter.drawPixmap(img_rect, self.pixmap)
        else:
            painter.setPen(QtGui.QColor(130, 130, 130))
            painter.drawText(
                self.rect(), QtCore.Qt.AlignCenter,
                "1. Take screenshot (Win + Shift + S)\n"
                "2. Click 'Paste Screenshot'\n"
                "3. RMB: Tools / Add Pin / Save / Open\n"
                "4. Menu click: Run Action | Ctrl + Menu Click: Spawn Button\n"
                "5. Ctrl + Left Drag: Move Buttons / Pins\n"
                "6. RMB on Button: Save to Hotkeys / Delete"
            )

        if img_rect.isEmpty():
            return

        is_offset_on = getattr(self.main_window.temp_ctrl_mgr, "offset_active", False)
        bake_keys_only = getattr(self.main_window.temp_ctrl_mgr, "bake_keys_only", True)

        # Draw Buttons
        for btn in self.buttons:
            brect = self._get_btn_rect(btn, img_rect)
            action_id = btn.get("action_id")

            if action_id == "temp_offset_toggle" and is_offset_on:
                bg_col = QtGui.QColor("#E65100")
                border_pen = QtGui.QPen(QtGui.QColor("#FFCC80"), 2.5)
                display_label = f"⏱ [ON] {btn.get('label', 'Offset')}"
            elif action_id == "toggle_sampling":
                bg_col = QtGui.QColor("#FB8C00") if bake_keys_only else QtGui.QColor("#455A64")
                border_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 180), 1)
                display_label = "🎯 Keys Only" if bake_keys_only else "🎯 Every Frame"
            else:
                bg_col = QtGui.QColor(btn.get("color", "#336699"))
                border_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 180), 1)
                display_label = btn.get("label", "Action")

            painter.setBrush(QtGui.QBrush(bg_col))
            painter.setPen(border_pen)
            painter.drawRoundedRect(brect, 5, 5)

            painter.setPen(QtCore.Qt.white)
            font = painter.font()
            font.setBold(True)
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(brect, QtCore.Qt.AlignCenter, display_label)

        # Draw Pins
        for pin in self.pins:
            px = img_rect.x() + int(pin["u"] * img_rect.width())
            py = img_rect.y() + int(pin["v"] * img_rect.height())

            if "color" in pin and pin["color"]:
                brush_col = QtGui.QColor(pin["color"])
            else:
                name = pin["name"].lower()
                if name.startswith(("l_", "left_")) or name.endswith(("_l", "_left")):
                    brush_col = QtGui.QColor(33, 150, 243, 230)
                elif name.startswith(("r_", "right_")) or name.endswith(("_r", "_right")):
                    brush_col = QtGui.QColor(244, 67, 54, 230)
                else:
                    brush_col = QtGui.QColor(255, 193, 7, 230)

            painter.setBrush(QtGui.QBrush(brush_col))
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 1.5))

            shape = pin.get("shape", "Circle")
            r = self.PIN_RADIUS

            if shape == "Square":
                painter.drawRect(QtCore.QRectF(px - r, py - r, r * 2, r * 2))
            elif shape == "Triangle":
                polygon = QtGui.QPolygonF([
                    QtCore.QPointF(px, py - r - 2),
                    QtCore.QPointF(px - r - 1, py + r),
                    QtCore.QPointF(px + r + 1, py + r)
                ])
                painter.drawPolygon(polygon)
            elif shape == "Diamond":
                polygon = QtGui.QPolygonF([
                    QtCore.QPointF(px, py - r - 2),
                    QtCore.QPointF(px + r + 1, py),
                    QtCore.QPointF(px, py + r + 2),
                    QtCore.QPointF(px - r - 1, py)
                ])
                painter.drawPolygon(polygon)
            elif shape == "Star":
                path = QtGui.QPainterPath()
                points = 5
                outer_r = r + 2
                inner_r = r * 0.4
                for i in range(2 * points):
                    angle = i * math.pi / points - math.pi / 2
                    curr_r = outer_r if i % 2 == 0 else inner_r
                    x = px + curr_r * math.cos(angle)
                    y = py + curr_r * math.sin(angle)
                    if i == 0:
                        path.moveTo(x, y)
                    else:
                        path.lineTo(x, y)
                path.closeSubpath()
                painter.drawPath(path)
            else:
                painter.drawEllipse(QtCore.QPoint(px, py), r, r)

        # Draw Marquee Box
        if self.is_box_selecting:
            box_rect = QtCore.QRect(self.box_start, self.box_current).normalized()
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255), 1.5, QtCore.Qt.DashLine))
            painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 229, 255, 40)))
            painter.drawRect(box_rect)

    def mousePressEvent(self, event):
        img_rect = self._get_image_rect()
        if img_rect.isEmpty():
            return

        if event.button() == QtCore.Qt.RightButton:
            self._show_context_menu(event.pos(), img_rect)
            return

        if event.button() == QtCore.Qt.LeftButton:
            for btn in reversed(self.buttons):
                brect = self._get_btn_rect(btn, img_rect)
                if brect.contains(event.pos()):
                    if event.modifiers() & QtCore.Qt.ControlModifier:
                        self.dragged_button = btn
                        self.drag_offset = event.pos() - brect.topLeft()
                    else:
                        self.action_registry.execute(btn["action_id"])
                        self.main_window.sync_ui_state()
                        self.update()
                    return

            for pin in reversed(self.pins):
                px = img_rect.x() + int(pin["u"] * img_rect.width())
                py = img_rect.y() + int(pin["v"] * img_rect.height())
                if ((event.pos().x() - px)**2 + (event.pos().y() - py)**2)**0.5 <= self.PIN_RADIUS + 4:
                    if event.modifiers() & QtCore.Qt.ControlModifier:
                        self.dragged_pin = pin
                        self.drag_offset = event.pos() - QtCore.QPoint(px, py)
                    else:
                        add_mode = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
                        if cmds.objExists(pin["name"]):
                            cmds.select(pin["name"], add=add_mode)
                    return

            self.is_box_selecting = True
            self.box_start = event.pos()
            self.box_current = event.pos()

    def mouseMoveEvent(self, event):
        img_rect = self._get_image_rect()
        if self.dragged_button and not img_rect.isEmpty():
            new_top_left = event.pos() - self.drag_offset
            u_coord = (new_top_left.x() - img_rect.x()) / float(img_rect.width())
            v_coord = (new_top_left.y() - img_rect.y()) / float(img_rect.height())
            self.dragged_button["u"] = max(0.0, min(0.95, u_coord))
            self.dragged_button["v"] = max(0.0, min(0.95, v_coord))
            self.update()
        elif self.dragged_pin and not img_rect.isEmpty():
            new_center = event.pos() - self.drag_offset
            u_coord = (new_center.x() - img_rect.x()) / float(img_rect.width())
            v_coord = (new_center.y() - img_rect.y()) / float(img_rect.height())
            self.dragged_pin["u"] = max(0.0, min(1.0, u_coord))
            self.dragged_pin["v"] = max(0.0, min(1.0, v_coord))
            self.update()
        elif self.is_box_selecting:
            self.box_current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.dragged_button:
            self.dragged_button = None
            self.save_state()
            return

        if self.dragged_pin:
            self.dragged_pin = None
            self.save_state()
            return

        if event.button() == QtCore.Qt.LeftButton and self.is_box_selecting:
            self.is_box_selecting = False
            img_rect = self._get_image_rect()
            if img_rect.isEmpty():
                return

            box = QtCore.QRect(self.box_start, self.box_current).normalized()
            add_mode = bool(event.modifiers() & QtCore.Qt.ShiftModifier)

            selected = []
            for pin in self.pins:
                px = img_rect.x() + int(pin["u"] * img_rect.width())
                py = img_rect.y() + int(pin["v"] * img_rect.height())
                if box.contains(QtCore.QPoint(px, py)) and cmds.objExists(pin["name"]):
                    selected.append(pin["name"])
            if selected:
                cmds.select(selected, add=add_mode)

            self.update()

    def _handle_action_trigger(self, act):
        ctrl_held = bool(QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ControlModifier)
        norm_u, norm_v = self.last_menu_pos_norm

        if ctrl_held:
            label, ok = QtWidgets.QInputDialog.getText(
                self, "Button Label", "Enter button label:", text=act.get("name", "Action")
            )
            if ok and label:
                self.buttons.append({
                    "label": label,
                    "action_id": act["id"],
                    "u": norm_u,
                    "v": norm_v,
                    "w": max(100, len(label) * 8),
                    "h": 26,
                    "color": act.get("color", "#336699")
                })
                self.save_state()
                self.update()
        else:
            self.action_registry.execute(act["id"])
            self.main_window.sync_ui_state()
            self.update()

    def _show_context_menu(self, pos, img_rect):
        norm_u = (pos.x() - img_rect.x()) / float(img_rect.width())
        norm_v = (pos.y() - img_rect.y()) / float(img_rect.height())
        self.last_menu_pos_norm = (norm_u, norm_v)

        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(self.MENU_STYLE)

        clicked_btn = None
        for btn in reversed(self.buttons):
            if self._get_btn_rect(btn, img_rect).contains(pos):
                clicked_btn = btn
                break

        if clicked_btn:
            menu.addSection(f"Button: {clicked_btn.get('label', 'Action')}")
            action_save_hotkey = menu.addAction("⌨️ Save to Hotkeys...")
            menu.addSeparator()
            action_delete_btn = menu.addAction("🗑 Delete Button")

            chosen = menu.exec_(self.mapToGlobal(pos))
            if chosen == action_save_hotkey:
                self.register_action_to_maya_hotkeys(
                    clicked_btn.get("action_id"), clicked_btn.get("label")
                )
            elif chosen == action_delete_btn:
                self.buttons.remove(clicked_btn)
                self.save_state()
                self.update()
            return

        clicked_pin = None
        for pin in self.pins:
            px = img_rect.x() + int(pin["u"] * img_rect.width())
            py = img_rect.y() + int(pin["v"] * img_rect.height())
            if ((pos.x() - px)**2 + (pos.y() - py)**2)**0.5 <= self.PIN_RADIUS + 5:
                clicked_pin = pin
                break

        if clicked_pin:
            menu.addSection(f"Pin: {clicked_pin['name']}")
            shape_menu = menu.addMenu("🔷 Change Shape")
            shape_menu.setStyleSheet(self.MENU_STYLE)
            shapes_list = ["Circle", "Square", "Triangle", "Diamond", "Star"]
            shape_actions = {shape_menu.addAction(s): s for s in shapes_list}

            color_action = menu.addAction("🎨 Pick Custom Color")
            reset_color_action = menu.addAction("🔄 Reset Default Color")
            menu.addSeparator()
            delete_pin_action = menu.addAction("🗑 Delete Pin")

            chosen = menu.exec_(self.mapToGlobal(pos))
            if chosen in shape_actions:
                clicked_pin["shape"] = shape_actions[chosen]
                self.save_state()
                self.update()
            elif chosen == color_action:
                col = QtWidgets.QColorDialog.getColor(QtGui.QColor(clicked_pin.get("color", "#2196F3")), self, "Select Pin Color")
                if col.isValid():
                    clicked_pin["color"] = col.name()
                    self.save_state()
                    self.update()
            elif chosen == reset_color_action:
                if "color" in clicked_pin:
                    del clicked_pin["color"]
                self.save_state()
                self.update()
            elif chosen == delete_pin_action:
                self.pins.remove(clicked_pin)
                self.save_state()
                self.update()
            return

        # Canvas General Context Menu
        action_add_pin = menu.addAction("📍 Add Pin")
        menu.addSeparator()

        tools_menu = menu.addMenu("🛠 Tools")
        tools_menu.setStyleSheet(self.MENU_STYLE)
        all_actions = self.action_registry.get_action_list()

        categories_map = {
            "Tween": tools_menu.addMenu("⚖️ Tween"),
            "Temp Controls": tools_menu.addMenu("⚡ Temp Controls"),
            "Pose": tools_menu.addMenu("🧘 Pose"),
            "Animation": tools_menu.addMenu("🎬 Animation"),
            "Bake": tools_menu.addMenu("🎯 Bake")
        }

        for sub in categories_map.values():
            sub.setStyleSheet(self.MENU_STYLE)

        for act in all_actions:
            cat = act.get("category")
            if cat in categories_map:
                item = categories_map[cat].addAction(act["name"])
                item.triggered.connect(lambda checked=False, a=act: self._handle_action_trigger(a))

        tools_menu.addSeparator()
        for direct_id, direct_title in [("temp_offset_toggle", "⏱ Offset"), ("trail_toggle", "🎨 Motion Trail")]:
            act = next((a for a in all_actions if a["id"] == direct_id), None)
            if act:
                item = tools_menu.addAction(direct_title)
                item.triggered.connect(lambda checked=False, a=act: self._handle_action_trigger(a))

        tools_menu.addSeparator()
        for direct_id, direct_title in [("scan_rig", "🔍 Scan Rig"), ("default_pose", "🔄 Default Pose")]:
            act = next((a for a in all_actions if a["id"] == direct_id), None)
            if act:
                item = tools_menu.addAction(direct_title)
                item.triggered.connect(lambda checked=False, a=act: self._handle_action_trigger(a))

        menu.addSeparator()
        action_save_preset = menu.addAction("💾 Save Preset")
        action_open_preset = menu.addAction("📂 Open Preset")

        chosen = menu.exec_(self.mapToGlobal(pos))

        if chosen == action_add_pin:
            sel = cmds.ls(selection=True, type="transform")
            if not sel:
                cmds.warning("Please select a controller in Maya before creating a Pin!")
                return
            self.pins.append({"name": sel[0], "u": norm_u, "v": norm_v, "shape": "Circle"})
            self.save_state()
            self.update()

        elif chosen == action_save_preset:
            self.save_preset_to_file()

        elif chosen == action_open_preset:
            self.open_preset_from_file()