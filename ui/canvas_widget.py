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
    """
    Interactive canvas with AnimBot-style interactive Sliders
    and 6 clearly distributed step dots: -50%, -20%, -5% | +5%, +20%, +50%.
    """

    PIN_RADIUS = 9

    # Точки розміщені симетрично на вільному просторі з кожного боку треку
    TICK_OFFSETS = [
        (-0.85, 50.0, "-50%"),
        (-0.58, 20.0, "-20%"),
        (-0.30, 5.0, "-5%"),
        (0.30, 5.0, "+5%"),
        (0.58, 20.0, "+20%"),
        (0.85, 50.0, "+50%")
    ]

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
        self.setMinimumSize(250, 250)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.main_window = main_window
        self.action_registry = main_window.action_registry

        self.pixmap = None
        self.pins = []
        self.buttons = []
        self.sliders = []  # [{'label': 'Tween', 'mode': 'Tween', 'action_id': 'tween_mid_50', 'u': 0.5, 'v': 0.8, 'w': 210, 'h': 24, 'val': 0.0}]

        self.is_box_selecting = False
        self.box_start = QtCore.QPoint()
        self.box_current = QtCore.QPoint()

        # Drag States (Ctrl + Drag)
        self.dragged_button = None
        self.dragged_pin = None
        self.dragged_slider = None
        self.active_slider_handle = None
        self.slider_cached_state = {}
        self.is_handle_dragging = False
        self.drag_offset = QtCore.QPoint()

        self.last_menu_pos_norm = (0.5, 0.5)

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.presets_dir = os.path.join(base_dir, "presets")
        self.img_path = os.path.join(self.presets_dir, "picker_img.png")
        self.data_path = os.path.join(self.presets_dir, "picker_data.json")

        self._ensure_storage_dir()
        self._load_saved_data()

    def hasHeightForWidth(self):
        return self.pixmap is not None and not self.pixmap.isNull()

    def heightForWidth(self, width):
        if self.pixmap and not self.pixmap.isNull() and self.pixmap.width() > 0:
            return int(width * (self.pixmap.height() / float(self.pixmap.width())))
        return width

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

        data = {"pins": self.pins, "buttons": self.buttons, "sliders": self.sliders}
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
                    self.sliders = data.get("sliders", [])
                    for b in self.buttons:
                        b["w"] = self._calc_button_width(b.get("label", "Action"))
                    for s in self.sliders:
                        if s.get("w", 0) < 210:
                            s["w"] = 210
            except Exception:
                self.pins, self.buttons, self.sliders = [], [], []

    def _calc_button_width(self, text):
        font = QtGui.QFont()
        font.setPointSize(8)
        font.setBold(True)
        metrics = QtGui.QFontMetrics(font)
        text_w = metrics.horizontalAdvance(text) if hasattr(metrics, 'horizontalAdvance') else metrics.width(text)
        return max(36, text_w + 14)

    def paste_image_from_clipboard(self):
        cb = QtWidgets.QApplication.clipboard()
        mime = cb.mimeData()
        if mime.hasImage():
            self.pixmap = cb.pixmap()
            self.save_state()
            self.updateGeometry()
            self.update()
            return True
        cmds.warning("No image found in clipboard! Press Win + Shift + S first.")
        return False

    def clear_all(self):
        self.pins.clear()
        self.buttons.clear()
        self.sliders.clear()
        self.pixmap = None
        self.save_state()
        self.updateGeometry()
        self.update()

    def save_preset_to_file(self):
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Preset", self.presets_dir, "JSON Files (*.json)"
        )
        if file_path:
            if not file_path.endswith(".json"):
                file_path += ".json"
            data = {"pins": self.pins, "buttons": self.buttons, "sliders": self.sliders}
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
                    self.sliders = data.get("sliders", [])
                    for b in self.buttons:
                        b["w"] = self._calc_button_width(b.get("label", "Action"))
                    for s in self.sliders:
                        if s.get("w", 0) < 210:
                            s["w"] = 210
                img_file = file_path.replace(".json", "_img.png")
                self.pixmap = QtGui.QPixmap(img_file) if os.path.exists(img_file) else None
                self.save_state()
                self.updateGeometry()
                self.update()
                cmds.inViewMessage(amg="Preset loaded successfully!", pos="topCenter", fade=True)
            except Exception as e:
                cmds.warning(f"Failed to load preset: {e}")

    def register_action_to_maya_hotkeys(self, action_id, label="Action"):
        cmd_name = f"DooAnim_{action_id}"
        name_cmd_name = f"{cmd_name}NameCommand"
        python_code = f"import DooAnimKit; DooAnimKit.api.{action_id}()"

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

        pix_w = self.pixmap.width()
        pix_h = self.pixmap.height()
        if pix_w <= 0 or pix_h <= 0:
            return QtCore.QRect()

        aspect = float(pix_w) / float(pix_h)
        canvas_w = self.width()
        canvas_h = self.height()

        if canvas_w / float(canvas_h) > aspect:
            draw_h = canvas_h
            draw_w = int(draw_h * aspect)
        else:
            draw_w = canvas_w
            draw_h = int(draw_w / aspect)

        draw_x = (canvas_w - draw_w) // 2
        draw_y = (canvas_h - draw_h) // 2

        return QtCore.QRect(draw_x, draw_y, max(1, draw_w), max(1, draw_h))

    def _get_btn_rect(self, btn, img_rect):
        bx = img_rect.x() + int(btn["u"] * img_rect.width())
        by = img_rect.y() + int(btn["v"] * img_rect.height())
        bw = btn.get("w", self._calc_button_width(btn.get("label", "Action")))
        return QtCore.QRect(bx, by, bw, btn.get("h", 24))

    def _get_slider_rect(self, sld, img_rect):
        sx = img_rect.x() + int(sld["u"] * img_rect.width())
        sy = img_rect.y() + int(sld["v"] * img_rect.height())
        sw = max(210, sld.get("w", 210))
        sh = sld.get("h", 24)
        return QtCore.QRect(sx, sy, sw, sh)

    def _get_slider_center_btn_rect(self, sld_rect, val=0.0):
        btn_w = 32
        max_shift = (sld_rect.width() // 2) - (btn_w // 2) - 3
        mid_x = sld_rect.center().x() + int(val * max_shift)
        return QtCore.QRect(mid_x - btn_w // 2, sld_rect.y(), btn_w, sld_rect.height())

    def _get_tick_points(self, sld_rect):
        mid_x = sld_rect.center().x()
        mid_y = sld_rect.center().y()
        half_w = (sld_rect.width() // 2) - 4

        points = []
        for factor, pct, label in self.TICK_OFFSETS:
            tx = mid_x + int(factor * half_w)
            points.append((tx, mid_y, pct, label))
        return points

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        img_rect = self._get_image_rect()

        if self.pixmap and not self.pixmap.isNull():
            painter.drawPixmap(img_rect, self.pixmap)
        else:
            painter.setPen(QtGui.QColor(130, 130, 130))
            painter.drawText(
                self.rect(), QtCore.Qt.AlignCenter,
                "1. Take screenshot (Win + Shift + S)\n"
                "2. Click 'Paste Screenshot'\n"
                "3. RMB: Add Pin / Create Slider / Tools\n"
                "4. Drag Center Handle left/right (-100% to +100%)\n"
                "5. Click Step Dots: -50%, -20%, -5% | +5%, +20%, +50%\n"
                "6. Ctrl + Left Drag: Move Sliders / Buttons / Pins"
            )

        if img_rect.isEmpty():
            return

        is_offset_on = getattr(self.main_window.temp_ctrl_mgr, "offset_active", False)
        bake_keys_only = getattr(self.main_window.temp_ctrl_mgr, "bake_keys_only", True)

        # 1. Draw Sliders
        for sld in self.sliders:
            srect = self._get_slider_rect(sld, img_rect)
            val = sld.get("val", 0.0)

            # Base Track
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#1a1e26")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#37474f"), 1.2))
            painter.drawRoundedRect(srect, 4, 4)

            # Center Indicator Line
            mid_x = srect.center().x()
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 40), 1, QtCore.Qt.DashLine))
            painter.drawLine(mid_x, srect.y() + 3, mid_x, srect.bottom() - 3)

            # Interactive Active Fill Bar
            if abs(val) > 0.02:
                handle_rect = self._get_slider_center_btn_rect(srect, val)
                hx = handle_rect.center().x()
                fill_rect = QtCore.QRect(min(mid_x, hx), srect.y() + 2, abs(hx - mid_x), srect.height() - 4)
                fill_color = QtGui.QColor("#EC407A") if val < 0 else QtGui.QColor("#AB47BC")
                painter.setBrush(QtGui.QBrush(fill_color))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRoundedRect(fill_rect, 2, 2)

            # Step Tick Dots
            for tx, ty, pct, label in self._get_tick_points(srect):
                painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 200)))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawEllipse(QtCore.QPoint(tx, ty), 2, 2)

            # Center Handle
            c_rect = self._get_slider_center_btn_rect(srect, val)
            action_id = sld.get("action_id", "tween_mid_50")

            if action_id == "temp_offset_toggle" and is_offset_on:
                c_col = QtGui.QColor("#E65100")
            else:
                c_col = QtGui.QColor(sld.get("color", "#00838f"))

            painter.setBrush(QtGui.QBrush(c_col))
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 220), 1))
            painter.drawRoundedRect(c_rect, 4, 4)

            painter.setPen(QtCore.Qt.white)
            font = painter.font()
            font.setBold(True)
            font.setPointSize(7)
            painter.setFont(font)

            if abs(val) > 0.04:
                painter.drawText(c_rect, QtCore.Qt.AlignCenter, f"{int(val * 100):+d}%")
            else:
                painter.drawText(c_rect, QtCore.Qt.AlignCenter, sld.get("label", "Tween"))

        # 2. Draw Action Buttons
        for btn in self.buttons:
            brect = self._get_btn_rect(btn, img_rect)
            action_id = btn.get("action_id")

            if action_id == "temp_offset_toggle" and is_offset_on:
                bg_col = QtGui.QColor("#E65100")
                border_pen = QtGui.QPen(QtGui.QColor("#FFCC80"), 2.0)
                display_label = f"⏱ [ON] {btn.get('label', 'Offset')}"
            elif action_id == "toggle_sampling":
                bg_col = QtGui.QColor("#FB8C00") if bake_keys_only else QtGui.QColor("#455A64")
                border_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 180), 1)
                display_label = "🎯 Keys" if bake_keys_only else "🎯 All"
            else:
                bg_col = QtGui.QColor(btn.get("color", "#336699"))
                border_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 180), 1)
                display_label = btn.get("label", "Action")

            painter.setBrush(QtGui.QBrush(bg_col))
            painter.setPen(border_pen)
            painter.drawRoundedRect(brect, 4, 4)

            painter.setPen(QtCore.Qt.white)
            font = painter.font()
            font.setBold(True)
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(brect, QtCore.Qt.AlignCenter, display_label)

        # 3. Draw Pins
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

        # 4. Marquee Box
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
            # 1. Перевірка натискання на Слайдери
            for sld in reversed(self.sliders):
                srect = self._get_slider_rect(sld, img_rect)
                if srect.contains(event.pos()):
                    if event.modifiers() & QtCore.Qt.ControlModifier:
                        self.dragged_slider = sld
                        self.drag_offset = event.pos() - srect.topLeft()
                        return

                    c_rect = self._get_slider_center_btn_rect(srect, sld.get("val", 0.0))

                    # Точки (Dots)
                    if not c_rect.contains(event.pos()):
                        for tx, ty, pct, label in self._get_tick_points(srect):
                            if ((event.pos().x() - tx)**2 + (event.pos().y() - ty)**2)**0.5 <= 7:
                                direction = 1 if tx > srect.center().x() else -1
                                mode = sld.get("mode", "Tween")

                                if mode == "Tween" and hasattr(self.main_window, "tween_engine"):
                                    self.main_window.tween_engine.step_nudge(direction=direction, step_percent=pct)
                                elif mode == "Time Shift" and hasattr(self.main_window, "time_shift_engine"):
                                    offset_f = int(round(pct / 50.0 * 2.0)) or (1 if direction > 0 else -1)
                                    self.main_window.time_shift_engine.shift_selected(frame_offset=offset_f)
                                elif mode == "Cascade" and hasattr(self.main_window, "time_shift_engine"):
                                    step_f = 1 if pct <= 20 else 2
                                    self.main_window.time_shift_engine.cascade_shift(step=step_f, reverse=(direction < 0))

                                self.update()
                                return

                    # Центральна ручка (початок перетягування)
                    self.active_slider_handle = sld
                    self.is_handle_dragging = False
                    if hasattr(self.main_window, "tween_engine"):
                        self.slider_cached_state = self.main_window.tween_engine.cache_current_tween_state()
                    return

            # 2. Кнопки
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

            # 3. Піни
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

    def _update_slider_drag(self, sld, pos, srect):
        btn_w = 32
        max_shift = float((srect.width() // 2) - (btn_w // 2) - 3)
        offset_x = pos.x() - srect.center().x()
        val = max(-1.0, min(1.0, offset_x / max(1.0, max_shift)))
        sld["val"] = val

        if abs(val) > 0.04:
            self.is_handle_dragging = True

        mode = sld.get("mode", "Tween")
        if mode == "Tween" and hasattr(self.main_window, "tween_engine"):
            self.main_window.tween_engine.tween_interactive_delta(self.slider_cached_state, val)
        self.update()

    def mouseMoveEvent(self, event):
        img_rect = self._get_image_rect()
        if self.active_slider_handle and not img_rect.isEmpty():
            srect = self._get_slider_rect(self.active_slider_handle, img_rect)
            self._update_slider_drag(self.active_slider_handle, event.pos(), srect)
            return

        if self.dragged_slider and not img_rect.isEmpty():
            new_top_left = event.pos() - self.drag_offset
            u_coord = (new_top_left.x() - img_rect.x()) / float(img_rect.width())
            v_coord = (new_top_left.y() - img_rect.y()) / float(img_rect.height())
            self.dragged_slider["u"] = max(0.0, min(0.95, u_coord))
            self.dragged_slider["v"] = max(0.0, min(0.95, v_coord))
            self.update()
        elif self.dragged_button and not img_rect.isEmpty():
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
        if self.active_slider_handle:
            # Клік по центру без тягання -> 50% Breakdown
            if not self.is_handle_dragging:
                self.action_registry.execute(self.active_slider_handle.get("action_id", "tween_mid_50"))
                self.main_window.sync_ui_state()

            # Пружне повернення в центр
            self.active_slider_handle["val"] = 0.0
            self.active_slider_handle = None
            self.is_handle_dragging = False
            self.slider_cached_state.clear()
            self.update()
            return

        if self.dragged_slider:
            self.dragged_slider = None
            self.save_state()
            return

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
                    "w": self._calc_button_width(label),
                    "h": 24,
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

        # 1. Slider Under Cursor
        clicked_sld = None
        for sld in reversed(self.sliders):
            if self._get_slider_rect(sld, img_rect).contains(pos):
                clicked_sld = sld
                break

        if clicked_sld:
            menu.addSection(f"Slider: {clicked_sld.get('label', 'Tween')}")
            
            mode_menu = menu.addMenu("🎯 Slider Mode / Center Action")
            mode_menu.setStyleSheet(self.MENU_STYLE)
            modes = [
                ("Tween: 50% Breakdown", "Tween", "tween_mid_50"),
                ("Time Shift: Toggle Global Offset", "Time Shift", "temp_offset_toggle"),
                ("Cascade: +1f Forward", "Cascade", "cascade_fwd_1"),
                ("Pose: Snap Left (100%)", "Tween", "tween_snap_left"),
                ("Pose: Snap Right (100%)", "Tween", "tween_snap_right"),
            ]
            mode_actions = {}
            for title, mode_type, act_id in modes:
                act = mode_menu.addAction(title)
                mode_actions[act] = (title, mode_type, act_id)

            action_rename_sld = menu.addAction("✏️ Rename Slider...")
            action_color_sld = menu.addAction("🎨 Pick Center Color...")
            menu.addSeparator()
            action_delete_sld = menu.addAction("🗑 Delete Slider")

            chosen = menu.exec_(self.mapToGlobal(pos))
            if chosen in mode_actions:
                title, mode_type, act_id = mode_actions[chosen]
                clicked_sld["mode"] = mode_type
                clicked_sld["action_id"] = act_id
                clicked_sld["label"] = title.split(":")[0]
                self.save_state()
                self.update()
            elif chosen == action_rename_sld:
                new_lbl, ok = QtWidgets.QInputDialog.getText(
                    self, "Rename Slider", "Enter slider label:", text=clicked_sld.get("label", "")
                )
                if ok and new_lbl:
                    clicked_sld["label"] = new_lbl
                    self.save_state()
                    self.update()
            elif chosen == action_color_sld:
                col = QtWidgets.QColorDialog.getColor(QtGui.QColor(clicked_sld.get("color", "#00838f")), self, "Select Color")
                if col.isValid():
                    clicked_sld["color"] = col.name()
                    self.save_state()
                    self.update()
            elif chosen == action_delete_sld:
                self.sliders.remove(clicked_sld)
                self.save_state()
                self.update()
            return

        # 2. Button Under Cursor
        clicked_btn = None
        for btn in reversed(self.buttons):
            if self._get_btn_rect(btn, img_rect).contains(pos):
                clicked_btn = btn
                break

        if clicked_btn:
            menu.addSection(f"Button: {clicked_btn.get('label', 'Action')}")
            action_rename_btn = menu.addAction("✏️ Rename Button...")
            action_color_btn = menu.addAction("🎨 Pick Custom Color...")
            action_reset_color_btn = menu.addAction("🔄 Reset Default Color")
            menu.addSeparator()
            action_save_hotkey = menu.addAction("⌨️ Save to Hotkeys...")
            menu.addSeparator()
            action_delete_btn = menu.addAction("🗑 Delete Button")

            chosen = menu.exec_(self.mapToGlobal(pos))
            if chosen == action_rename_btn:
                new_label, ok = QtWidgets.QInputDialog.getText(
                    self, "Rename Button", "Enter new button label:", text=clicked_btn.get("label", "")
                )
                if ok and new_label:
                    clicked_btn["label"] = new_label
                    clicked_btn["w"] = self._calc_button_width(new_label)
                    self.save_state()
                    self.update()
            elif chosen == action_color_btn:
                current_color = clicked_btn.get("color", "#336699")
                col = QtWidgets.QColorDialog.getColor(QtGui.QColor(current_color), self, "Select Button Color")
                if col.isValid():
                    clicked_btn["color"] = col.name()
                    self.save_state()
                    self.update()
            elif chosen == action_reset_color_btn:
                all_actions = self.action_registry.get_action_list()
                original_act = next((a for a in all_actions if a["id"] == clicked_btn.get("action_id")), None)
                clicked_btn["color"] = original_act.get("color", "#336699") if original_act else "#336699"
                self.save_state()
                self.update()
            elif chosen == action_save_hotkey:
                self.register_action_to_maya_hotkeys(
                    clicked_btn.get("action_id"), clicked_btn.get("label")
                )
            elif chosen == action_delete_btn:
                self.buttons.remove(clicked_btn)
                self.save_state()
                self.update()
            return

        # 3. Pin Under Cursor
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

        # 4. Canvas Context Menu
        action_add_pin = menu.addAction("📍 Add Pin")
        action_add_slider = menu.addAction("🎚 Create Slider...")
        menu.addSeparator()

        tools_menu = menu.addMenu("🛠 Tools")
        tools_menu.setStyleSheet(self.MENU_STYLE)
        all_actions = self.action_registry.get_action_list()

        categories_map = {
            "Tween": tools_menu.addMenu("⚖️ Tween"),
            "Time Shift": tools_menu.addMenu("⏱ Time Shift & Cascade"),
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
        for direct_id, direct_title in [("temp_offset_toggle", "⏱ Global Offset"), ("trail_toggle", "🎨 Motion Trail")]:
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

        elif chosen == action_add_slider:
            label, ok = QtWidgets.QInputDialog.getText(self, "Create Slider", "Enter Slider Name:", text="Tween")
            if ok and label:
                self.sliders.append({
                    "label": label,
                    "mode": "Tween",
                    "action_id": "tween_mid_50",
                    "u": norm_u,
                    "v": norm_v,
                    "w": 210,
                    "h": 24,
                    "val": 0.0,
                    "color": "#00838f"
                })
                self.save_state()
                self.update()

        elif chosen == action_save_preset:
            self.save_preset_to_file()

        elif chosen == action_open_preset:
            self.open_preset_from_file()