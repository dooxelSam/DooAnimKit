import os
import json

try:
    from PySide6 import QtWidgets, QtGui, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtGui, QtCore

import maya.cmds as cmds


class CharacterPickerWidget(QtWidgets.QWidget):
    """Interactive 2D character picker canvas with persistent storage and marquee selection."""

    PIN_RADIUS = 7

    def __init__(self, parent=None):
        super(CharacterPickerWidget, self).__init__(parent=parent)
        self.setMinimumSize(220, 260)

        self.pixmap = None
        self.pins = []  # List of dicts: [{'name': 'L_Hand_CTRL', 'u': 0.35, 'v': 0.42}]

        # Marquee / Box Selection State
        self.is_dragging = False
        self.drag_start = QtCore.QPoint()
        self.drag_current = QtCore.QPoint()

        # Storage paths inside AnimKit project directory
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.presets_dir = os.path.join(base_dir, "presets")
        self.img_path = os.path.join(self.presets_dir, "picker_img.png")
        self.data_path = os.path.join(self.presets_dir, "picker_pins.json")

        self._ensure_storage_dir()
        self._load_saved_data()

    def _ensure_storage_dir(self):
        """Creates presets directory if it doesn't exist."""
        if not os.path.exists(self.presets_dir):
            try:
                os.makedirs(self.presets_dir)
            except Exception:
                pass

    # --- PERSISTENCE: SAVE / LOAD ---
    def _save_data(self):
        """Saves current image and pins to project presets directory."""
        self._ensure_storage_dir()

        # 1. Save Image
        if self.pixmap and not self.pixmap.isNull():
            self.pixmap.save(self.img_path, "PNG")
        elif os.path.exists(self.img_path):
            try:
                os.remove(self.img_path)
            except Exception:
                pass

        # 2. Save Pins JSON
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.pins, f, indent=4)
        except Exception as e:
            print(f"Failed to save picker data: {e}")

    def _load_saved_data(self):
        """Loads saved image and pins on startup."""
        # 1. Load Image
        if os.path.exists(self.img_path):
            self.pixmap = QtGui.QPixmap(self.img_path)

        # 2. Load Pins JSON
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    self.pins = json.load(f)
            except Exception as e:
                print(f"Failed to load picker data: {e}")
                self.pins = []

    def paste_from_clipboard(self):
        """Fetches screenshot from system clipboard and saves state."""
        clipboard = QtWidgets.QApplication.clipboard()
        mime = clipboard.mimeData()

        if mime.hasImage():
            self.pixmap = clipboard.pixmap()
            self._save_data()
            self.update()
            return True
        else:
            cmds.warning("No image found in clipboard! Use Win + Shift + S first.")
            return False

    def clear_pins(self):
        """Clears all hotspots, image, and removes saved cache."""
        self.pins.clear()
        self.pixmap = None
        self._save_data()
        self.update()

    def _get_image_rect(self):
        """Calculates scaled image rectangle preserving aspect ratio."""
        if not self.pixmap or self.pixmap.isNull():
            return QtCore.QRect()

        scaled = self.pixmap.scaled(
            self.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        return QtCore.QRect(x, y, scaled.width(), scaled.height())

    # --- PAINT EVENT ---
    def paintEvent(self, event):
        """Renders background image, pin hotspots, and drag-selection marquee."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        img_rect = self._get_image_rect()

        if self.pixmap and not self.pixmap.isNull():
            painter.drawPixmap(img_rect, self.pixmap)
        else:
            painter.setPen(QtGui.QColor(120, 120, 120))
            painter.drawText(
                self.rect(),
                QtCore.Qt.AlignCenter,
                "Win + Shift + S ➔ Click 'Paste Image'\nRight-Click on character to add Pin"
            )

        # Draw Pins
        if not img_rect.isEmpty():
            for pin in self.pins:
                px = img_rect.x() + int(pin['u'] * img_rect.width())
                py = img_rect.y() + int(pin['v'] * img_rect.height())

                # Color coding
                name = pin['name'].lower()
                if name.startswith('l_') or name.endswith('_l') or 'left' in name:
                    brush_color = QtGui.QColor(33, 150, 243, 220)   # Blue (Left)
                elif name.startswith('r_') or name.endswith('_r') or 'right' in name:
                    brush_color = QtGui.QColor(244, 67, 54, 220)    # Red (Right)
                else:
                    brush_color = QtGui.QColor(255, 193, 7, 220)    # Yellow (Center)

                painter.setBrush(QtGui.QBrush(brush_color))
                painter.setPen(QtGui.QPen(QtCore.Qt.white, 1.5))
                painter.drawEllipse(QtCore.QPoint(px, py), self.PIN_RADIUS, self.PIN_RADIUS)

        # Draw Marquee Selection Box
        if self.is_dragging:
            box_rect = QtCore.QRect(self.drag_start, self.drag_current).normalized()
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255), 1.5, QtCore.Qt.DashLine))
            painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 229, 255, 45)))
            painter.drawRect(box_rect)

    # --- MOUSE EVENTS ---
    def mousePressEvent(self, event):
        img_rect = self._get_image_rect()
        if img_rect.isEmpty() or not img_rect.contains(event.pos()):
            return

        # RIGHT CLICK: Add new Pin
        if event.button() == QtCore.Qt.RightButton:
            sel = cmds.ls(selection=True, type="transform")
            if not sel:
                cmds.warning("Select a Maya controller first before placing a Pin!")
                return

            norm_u = (event.pos().x() - img_rect.x()) / float(img_rect.width())
            norm_v = (event.pos().y() - img_rect.y()) / float(img_rect.height())

            ctrl_name = sel[0]
            self.pins.append({'name': ctrl_name, 'u': norm_u, 'v': norm_v})
            self._save_data()
            self.update()
            cmds.inViewMessage(amg=f"Pin created for: <hl>{ctrl_name}</hl>", pos="topCenter", fade=True)

        # LEFT CLICK: Start selection / drag
        elif event.button() == QtCore.Qt.LeftButton:
            self.is_dragging = True
            self.drag_start = event.pos()
            self.drag_current = event.pos()

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            self.drag_current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton or not self.is_dragging:
            return

        self.is_dragging = False
        img_rect = self._get_image_rect()
        if img_rect.isEmpty():
            self.update()
            return

        box_rect = QtCore.QRect(self.drag_start, self.drag_current).normalized()
        add_to_sel = bool(event.modifiers() & QtCore.Qt.ShiftModifier)

        # Single Click (no significant drag)
        if box_rect.width() < 5 and box_rect.height() < 5:
            clicked_pin = None
            for pin in reversed(self.pins):
                px = img_rect.x() + int(pin['u'] * img_rect.width())
                py = img_rect.y() + int(pin['v'] * img_rect.height())
                dist = ((event.pos().x() - px) ** 2 + (event.pos().y() - py) ** 2) ** 0.5
                if dist <= self.PIN_RADIUS + 3:
                    clicked_pin = pin
                    break

            if clicked_pin:
                ctrl = clicked_pin['name']
                if cmds.objExists(ctrl):
                    cmds.select(ctrl, add=add_to_sel)
        else:
            # Box / Marquee Selection
            selected_ctrls = []
            for pin in self.pins:
                px = img_rect.x() + int(pin['u'] * img_rect.width())
                py = img_rect.y() + int(pin['v'] * img_rect.height())
                if box_rect.contains(QtCore.QPoint(px, py)):
                    if cmds.objExists(pin['name']) and pin['name'] not in selected_ctrls:
                        selected_ctrls.append(pin['name'])

            if selected_ctrls:
                if add_to_sel:
                    cmds.select(selected_ctrls, add=True)
                else:
                    cmds.select(selected_ctrls, replace=True)

        self.update()