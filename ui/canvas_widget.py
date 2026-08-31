import os
import json
import math

try:
    from PySide6 import QtWidgets, QtGui, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtGui, QtCore

import maya.cmds as cmds
import maya.mel as mel
from DooAnimKit.core.auto_capture import AutoCaptureEngine
from DooAnimKit.core.rig_builder import RigBuilderEngine


class SpatialActionCanvas(QtWidgets.QWidget):
    """
    Dual-mode canvas:
    1. Animation Mode: Live rig control pickers, AnimBot slim sliders, HIK mirror badges.
    2. Auto-Rig Mode: 3-View synchronized 3D guides, Live Rebuild, Shape Mirroring, and Finalize.
    """

    PIN_RADIUS = 9

    TICK_OFFSETS = [
        (-0.84, 25.0, "-25%"),
        (-0.58, 15.0, "-15%"),
        (-0.32, 5.0, "-5%"),
        (0.32, 5.0, "+5%"),
        (0.58, 15.0, "+15%"),
        (0.84, 25.0, "+25%")
    ]

    HIK_TAGS_MAP = {
        "Root & Pelvis": ["Main_Root", "Hips"],
        "Spine & Head": ["Spine1", "Spine2", "Spine3", "Spine4", "Spine5", "Spine6", "Chest", "Neck", "Head"],
        "Left Arm": ["LeftClavicle", "LeftShoulder", "LeftElbow", "LeftWrist", "LeftFingers", "LeftThumb"],
        "Right Arm": ["RightClavicle", "RightShoulder", "RightElbow", "RightWrist", "RightFingers", "RightThumb"],
        "Left Leg": ["LeftUpLeg", "LeftKnee", "LeftFoot", "LeftToes"],
        "Right Leg": ["RightUpLeg", "RightKnee", "RightFoot", "RightToes"],
        "Wings & Extra": ["LeftWing_Root", "LeftWing_Tip", "RightWing_Root", "RightWing_Tip", "Tail_1", "Tail_2", "Tail_3", "Prop_Main"]
    }

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
            padding: 6px 42px 6px 14px;
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

    def __init__(self, main_window, parent=None):
        super(SpatialActionCanvas, self).__init__(parent=parent)
        self.setMinimumSize(280, 280)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.main_window = main_window
        self.action_registry = main_window.action_registry

        self.canvas_mode = "anim"
        self.current_view = "front"
        self.view_pixmaps = {"front": None, "side": None, "top": None}
        self.capture_meta = None
        self.mirror_mode = True

        self.pins = []
        self.rig_guides = []
        self.buttons = []
        self.sliders = []

        self.selected_guide = None
        self.is_box_selecting = False
        self.box_start = QtCore.QPoint()
        self.box_current = QtCore.QPoint()

        self.dragged_button = None
        self.dragged_pin = None
        self.dragged_guide = None
        self.dragged_slider = None
        self.active_slider_handle = None
        self.slider_cached_state = {}
        self.is_handle_dragging = False
        self.drag_offset = QtCore.QPoint()
        self._undo_opened = False

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.presets_dir = os.path.join(base_dir, "presets")
        self.icons_dir = os.path.join(base_dir, "icons")
        self.img_path = os.path.join(self.presets_dir, "picker_img.png")
        self.data_path = os.path.join(self.presets_dir, "picker_data.json")

        self.capture_engine = AutoCaptureEngine()
        self.rig_builder = RigBuilderEngine()

        self._ensure_storage_dir()
        self._load_saved_data()

    def _ensure_storage_dir(self):
        os.makedirs(self.presets_dir, exist_ok=True)

    def set_canvas_mode(self, mode):
        self.canvas_mode = mode
        self.updateGeometry()
        self.update()

    def set_active_view(self, view_name):
        if view_name in ("front", "side", "top"):
            self.current_view = view_name
            self.updateGeometry()
            self.update()

    def toggle_mirror_mode(self):
        self.mirror_mode = not self.mirror_mode
        self.save_state()
        self.update()

    def run_auto_capture(self):
        sel = cmds.ls(selection=True)
        if not sel:
            cmds.warning("Будь ласка, виділіть геометрію персонажа в Maya!")
            return

        data = self.capture_engine.capture_all_projections()
        if data:
            self.capture_meta = data
            for v_name in ("front", "side", "top"):
                img = data["views"][v_name]["image"]
                if os.path.exists(img):
                    self.view_pixmaps[v_name] = QtGui.QPixmap(img)
            self.canvas_mode = "rig"
            self.save_state()
            self.updateGeometry()
            self.update()

    def live_rebuild_rig(self):
        res = self.rig_builder.build_skeleton_and_rig(self.rig_guides)
        if res:
            cmds.inViewMessage(amg="Auto-Rig: <hl>Skeleton & Controls successfully rebuilt in Maya!</hl>", pos="topCenter", fade=True)
        self.update()

    def finalize_rig_and_go_anim(self):
        exported_pins = self.rig_builder.build_skeleton_and_rig(self.rig_guides)
        if exported_pins:
            new_pins = []
            for p in exported_pins:
                pos3d = p.get("pos3d", [0, 0, 0])
                u, v = AutoCaptureEngine.world_to_uv(pos3d, "front", self.capture_meta)
                p["u"] = u
                p["v"] = v
                p["shape"] = "Circle"
                new_pins.append(p)

            self.pins = new_pins
            self.canvas_mode = "anim"
            self.save_state()
            self.updateGeometry()
            self.update()
            cmds.inViewMessage(amg="Auto-Rig: <hl>Rig Finalized! Switched to Animation Mode.</hl>", pos="topCenter", fade=True)

    def save_state(self):
        self._ensure_storage_dir()
        pix = self.view_pixmaps.get("front")
        if pix and not pix.isNull():
            pix.save(self.img_path, "PNG")

        data = {
            "pins": self.pins,
            "rig_guides": self.rig_guides,
            "buttons": self.buttons,
            "sliders": self.sliders,
            "capture_meta": self.capture_meta,
            "canvas_mode": self.canvas_mode,
            "mirror_mode": self.mirror_mode
        }
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    def _load_saved_data(self):
        if os.path.exists(self.img_path):
            self.view_pixmaps["front"] = QtGui.QPixmap(self.img_path)

        cap_dir = os.path.join(self.presets_dir, "captures")
        for v in ("side", "top"):
            cap_img = os.path.join(cap_dir, f"rig_view_{v}.png")
            if os.path.exists(cap_img):
                self.view_pixmaps[v] = QtGui.QPixmap(cap_img)

        meta_file = os.path.join(cap_dir, "capture_metadata.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    self.capture_meta = json.load(f)
            except Exception:
                pass

        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.pins = data.get("pins", [])
                    self.rig_guides = data.get("rig_guides", [])
                    self.buttons = data.get("buttons", [])
                    self.sliders = data.get("sliders", [])
                    self.canvas_mode = data.get("canvas_mode", "anim")
                    self.mirror_mode = data.get("mirror_mode", True)
            except Exception:
                pass

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
            self.view_pixmaps["front"] = cb.pixmap()
            self.canvas_mode = "anim"
            self.save_state()
            self.updateGeometry()
            self.update()
            return True
        cmds.warning("No image in clipboard! Press Win + Shift + S first.")
        return False

    def clear_all(self):
        self.pins.clear()
        self.rig_guides.clear()
        self.buttons.clear()
        self.sliders.clear()
        self.view_pixmaps = {"front": None, "side": None, "top": None}
        self.capture_meta = None
        self.save_state()
        self.updateGeometry()
        self.update()

    def _get_image_rect(self):
        pix = self.view_pixmaps.get(self.current_view if self.canvas_mode == "rig" else "front")
        if not pix or pix.isNull():
            return QtCore.QRect()

        pix_w = pix.width()
        pix_h = pix.height()
        if pix_w <= 0 or pix_h <= 0:
            return QtCore.QRect()

        aspect = float(pix_w) / float(pix_h)
        canvas_w = self.width()
        canvas_h = self.height() - (70 if self.canvas_mode == "rig" else 0)

        if canvas_w / float(canvas_h) > aspect:
            draw_h = canvas_h
            draw_w = int(draw_h * aspect)
        else:
            draw_w = canvas_w
            draw_h = int(draw_w / aspect)

        draw_x = (canvas_w - draw_w) // 2
        draw_y = ((canvas_h - draw_h) // 2) + (68 if self.canvas_mode == "rig" else 0)

        return QtCore.QRect(draw_x, draw_y, max(1, draw_w), max(1, draw_h))

    # --- Header Toolbars ---
    def _get_mode_toggle_rect(self):
        return QtCore.QRect(10, 8, 105, 24)

    def _get_capture_btn_rect(self):
        return QtCore.QRect(120, 8, 65, 24)

    def _get_mirror_toggle_rect(self):
        return QtCore.QRect(190, 8, 65, 24)

    def _get_view_tab_rect(self, index):
        start_x = 260
        tab_w = 42
        return QtCore.QRect(start_x + index * (tab_w + 3), 8, tab_w, 24)

    def _get_rebuild_btn_rect(self):
        return QtCore.QRect(10, 36, 95, 24)

    def _get_mirror_shapes_btn_rect(self):
        return QtCore.QRect(110, 36, 140, 24)

    def _get_finalize_btn_rect(self):
        return QtCore.QRect(255, 36, 120, 24)

    def _get_slider_rect(self, sld, img_rect):
        sx = img_rect.x() + int(sld["u"] * img_rect.width())
        sy = img_rect.y() + int(sld["v"] * img_rect.height())
        sw = max(235, sld.get("w", 235))
        return QtCore.QRect(sx, sy, sw, 24)

    def _get_slider_center_btn_rect(self, sld_rect, val=0.0):
        btn_w = 40
        btn_h = 20
        track_w = sld_rect.width() - 4
        max_shift = (track_w // 2) - (btn_w // 2) - 2
        mid_x = sld_rect.center().x() + int(val * max_shift)
        mid_y = sld_rect.center().y()
        return QtCore.QRect(mid_x - btn_w // 2, mid_y - btn_h // 2, btn_w, btn_h)

    def _get_tick_points(self, sld_rect):
        mid_x = sld_rect.center().x()
        mid_y = sld_rect.center().y()
        half_w = (sld_rect.width() // 2) - 8
        points = []
        for factor, pct, label in self.TICK_OFFSETS:
            tx = mid_x + int(factor * half_w)
            points.append((tx, mid_y, pct, label))
        return points

    def _get_symmetry_center_x(self):
        if self.capture_meta and "center" in self.capture_meta:
            return self.capture_meta["center"][0]
        return 0.0

    def _find_mirrored_guide(self, guide):
        gid = guide.get("id")
        pair_id = guide.get("pair_id")
        if not pair_id:
            return None
        for g in self.rig_guides:
            if g.get("id") == pair_id or g.get("pair_id") == gid:
                return g
        return None

    def _get_mirrored_tag(self, tag):
        if tag.startswith("Left"):
            return tag.replace("Left", "Right", 1)
        elif tag.startswith("Right"):
            return tag.replace("Right", "Left", 1)
        return tag

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        img_rect = self._get_image_rect()

        pix = self.view_pixmaps.get(self.current_view if self.canvas_mode == "rig" else "front")
        if pix and not pix.isNull():
            painter.drawPixmap(img_rect, pix)
        else:
            painter.setPen(QtGui.QColor(130, 130, 130))
            if self.canvas_mode == "rig":
                painter.drawText(
                    self.rect(), QtCore.Qt.AlignCenter,
                    "🦴 AUTO-RIG MODE\n\n"
                    "1. Click '📸 Capture' above\n"
                    "2. Right-Click or Click to Add Guide Points\n"
                    "3. Click '🔄 Rebuild' to live-update skeleton in Maya\n"
                    "4. Click '🪞 Mirror Shapes' & '✨ Finalize Rig'"
                )
            else:
                painter.drawText(
                    self.rect(), QtCore.Qt.AlignCenter,
                    "⚡ ANIMATION MODE\n\n"
                    "1. Switch to 'Auto-Rig Mode' to build rig\n"
                    "2. Click pins to select controls & animate\n"
                    "3. Sliders: Tween & Time Offset ready"
                )

        if self.canvas_mode == "rig":
            painter.setPen(QtGui.QPen(QtGui.QColor("#FF9100"), 2.0, QtCore.Qt.SolidLine))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 6, 6)

        # 1. Mode Toggle
        mode_rect = self._get_mode_toggle_rect()
        mode_bg = QtGui.QColor("#E65100") if self.canvas_mode == "rig" else QtGui.QColor("#1976D2")
        painter.setBrush(QtGui.QBrush(mode_bg))
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1.2))
        painter.drawRoundedRect(mode_rect, 4, 4)
        painter.setPen(QtCore.Qt.white)
        f = painter.font()
        f.setBold(True)
        f.setPointSize(8)
        painter.setFont(f)
        painter.drawText(mode_rect, QtCore.Qt.AlignCenter, "🦴 Auto-Rig" if self.canvas_mode == "rig" else "⚡ Anim Mode")

        # 2. On-Screen Auto-Rig Toolbars
        if self.canvas_mode == "rig":
            cap_rect = self._get_capture_btn_rect()
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#2e7d32")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#81c784"), 1.2))
            painter.drawRoundedRect(cap_rect, 4, 4)
            painter.drawText(cap_rect, QtCore.Qt.AlignCenter, "📸 Capture")

            mir_rect = self._get_mirror_toggle_rect()
            mir_bg = QtGui.QColor("#6A1B9A") if self.mirror_mode else QtGui.QColor("#263238")
            mir_border = QtGui.QColor("#BA68C8") if self.mirror_mode else QtGui.QColor("#455A64")
            painter.setBrush(QtGui.QBrush(mir_bg))
            painter.setPen(QtGui.QPen(mir_border, 1.2))
            painter.drawRoundedRect(mir_rect, 4, 4)
            painter.drawText(mir_rect, QtCore.Qt.AlignCenter, "🪞 Mirror" if self.mirror_mode else "🪞 Off")

            tabs = [("front", "Front"), ("side", "Side"), ("top", "Top")]
            for i, (v_key, v_label) in enumerate(tabs):
                t_rect = self._get_view_tab_rect(i)
                is_active = (self.current_view == v_key)
                t_bg = QtGui.QColor("#00838f") if is_active else QtGui.QColor("#1e222b")
                painter.setBrush(QtGui.QBrush(t_bg))
                painter.setPen(QtGui.QPen(QtGui.QColor("#37474f"), 1))
                painter.drawRoundedRect(t_rect, 4, 4)
                painter.setPen(QtCore.Qt.white if is_active else QtGui.QColor("#90a4ae"))
                painter.drawText(t_rect, QtCore.Qt.AlignCenter, v_label)

            reb_rect = self._get_rebuild_btn_rect()
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#0277BD")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#4FC3F7"), 1.2))
            painter.drawRoundedRect(reb_rect, 4, 4)
            painter.setPen(QtCore.Qt.white)
            painter.drawText(reb_rect, QtCore.Qt.AlignCenter, "🔄 Rebuild")

            ms_rect = self._get_mirror_shapes_btn_rect()
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#4527A0")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#B388FF"), 1.2))
            painter.drawRoundedRect(ms_rect, 4, 4)
            painter.setPen(QtCore.Qt.white)
            painter.drawText(ms_rect, QtCore.Qt.AlignCenter, "🪞 Mirror Shapes (L->R)")

            fin_rect = self._get_finalize_btn_rect()
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#2E7D32")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#A5D6A7"), 1.2))
            painter.drawRoundedRect(fin_rect, 4, 4)
            painter.setPen(QtCore.Qt.white)
            painter.drawText(fin_rect, QtCore.Qt.AlignCenter, "✨ Finalize Rig")

        if img_rect.isEmpty():
            return

        # 3. Symmetry Axis Line
        if self.canvas_mode == "rig" and self.mirror_mode and self.current_view in ("front", "top"):
            cx = self._get_symmetry_center_x()
            u_center, _ = AutoCaptureEngine.world_to_uv([cx, 0.0, 0.0], self.current_view, self.capture_meta)
            line_x = img_rect.x() + int(u_center * img_rect.width())
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, 90), 1.0, QtCore.Qt.DashLine))
            painter.drawLine(line_x, img_rect.top(), line_x, img_rect.bottom())

        # 4. Guides Rendering
        if self.canvas_mode == "rig":
            for guide in self.rig_guides:
                pos3d = guide.get("pos3d", [0.0, 0.0, 0.0])
                u, v = AutoCaptureEngine.world_to_uv(pos3d, self.current_view, self.capture_meta)
                gx = img_rect.x() + int(u * img_rect.width())
                gy = img_rect.y() + int(v * img_rect.height())

                is_sel = (guide == self.selected_guide)
                tag = guide.get("hik_tag", "None")

                if is_sel:
                    painter.setBrush(QtCore.Qt.NoBrush)
                    painter.setPen(QtGui.QPen(QtGui.QColor("#00E5FF"), 2.2, QtCore.Qt.DashLine))
                    painter.drawEllipse(QtCore.QPoint(gx, gy), self.PIN_RADIUS + 6, self.PIN_RADIUS + 6)

                g_col = QtGui.QColor("#FF9100") if tag == "None" else QtGui.QColor("#00E676")
                painter.setBrush(QtGui.QBrush(g_col))
                painter.setPen(QtGui.QPen(QtCore.Qt.white, 1.8))
                painter.drawEllipse(QtCore.QPoint(gx, gy), self.PIN_RADIUS, self.PIN_RADIUS)

                lbl = tag if tag != "None" else guide.get("name", "guide")
                font = painter.font()
                font.setPointSize(7)
                font.setBold(True)
                painter.setFont(font)
                metrics = QtGui.QFontMetrics(font)
                tw = metrics.horizontalAdvance(lbl) if hasattr(metrics, 'horizontalAdvance') else metrics.width(lbl)
                label_rect = QtCore.QRect(gx - (tw // 2) - 4, gy - 22, tw + 8, 14)

                painter.setBrush(QtGui.QBrush(QtGui.QColor(24, 27, 34, 210)))
                painter.setPen(QtGui.QPen(QtGui.QColor(55, 71, 79, 180), 1))
                painter.drawRoundedRect(label_rect, 3, 3)

                painter.setPen(QtCore.Qt.white)
                painter.drawText(label_rect, QtCore.Qt.AlignCenter, lbl)
            return

        # 5. Animation Mode Pins
        for sld in self.sliders:
            srect = self._get_slider_rect(sld, img_rect)
            val = sld.get("val", 0.0)
            mid_x = srect.center().x()
            mid_y = srect.center().y()

            track_h = 10
            track_rect = QtCore.QRect(srect.x() + 4, mid_y - track_h // 2, srect.width() - 8, track_h)
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#181b22")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#2d3340"), 1.0))
            painter.drawRoundedRect(track_rect, 5.0, 5.0)

            if abs(val) > 0.02:
                handle_rect = self._get_slider_center_btn_rect(srect, val)
                hx = handle_rect.center().x()
                fill_rect = QtCore.QRect(min(mid_x, hx), mid_y - track_h // 2, abs(hx - mid_x), track_h)
                fill_color = QtGui.QColor("#EC407A") if val < 0 else QtGui.QColor("#AB47BC")
                painter.setBrush(QtGui.QBrush(fill_color))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRoundedRect(fill_rect, 5.0, 5.0)

            for tx, ty, pct, label in self._get_tick_points(srect):
                painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 190)))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawEllipse(QtCore.QPointF(tx, ty), 1.3, 1.3)

            c_rect = self._get_slider_center_btn_rect(srect, val)
            painter.setBrush(QtGui.QBrush(QtGui.QColor(sld.get("color", "#00838f"))))
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 210), 1))
            painter.drawRoundedRect(c_rect, 3, 3)

            painter.setPen(QtCore.Qt.white)
            f = painter.font()
            f.setBold(True)
            f.setPointSize(7)
            painter.setFont(f)
            mode = sld.get("mode", "Tween")
            if abs(val) > 0.04:
                shift_val = f"{int(round(val * 10)):+d}f" if mode == "Offset" else f"{int(val * 100):+d}%"
                painter.drawText(c_rect, QtCore.Qt.AlignCenter, shift_val)
            else:
                painter.drawText(c_rect, QtCore.Qt.AlignCenter, sld.get("label", "Tween"))

        for pin in self.pins:
            px = img_rect.x() + int(pin["u"] * img_rect.width())
            py = img_rect.y() + int(pin["v"] * img_rect.height())
            brush_col = QtGui.QColor(pin.get("color", "#2196F3"))
            painter.setBrush(QtGui.QBrush(brush_col))
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 220), 1.5))
            painter.drawEllipse(QtCore.QPoint(px, py), self.PIN_RADIUS, self.PIN_RADIUS)

            tag = pin.get("hik_tag", "")
            if tag and tag != "None":
                painter.setPen(QtGui.QColor(255, 255, 255, 200))
                f_p = painter.font()
                f_p.setPointSize(6)
                f_p.setBold(True)
                painter.setFont(f_p)
                painter.drawText(QtCore.QRect(px - 35, py + self.PIN_RADIUS + 1, 70, 12), QtCore.Qt.AlignCenter, tag)

        if self.is_box_selecting:
            box_rect = QtCore.QRect(self.box_start, self.box_current).normalized()
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 229, 255, 230), 1.5, QtCore.Qt.DashLine))
            painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 229, 255, 45)))
            painter.drawRect(box_rect)

    def mousePressEvent(self, event):
        # 1. Mode Toggle
        if self._get_mode_toggle_rect().contains(event.pos()):
            new_mode = "anim" if self.canvas_mode == "rig" else "rig"
            self.set_canvas_mode(new_mode)
            return

        # 2. Top Toolbar Clicks (Auto-Rig Mode)
        if self.canvas_mode == "rig":
            if self._get_capture_btn_rect().contains(event.pos()):
                self.run_auto_capture()
                return

            if self._get_mirror_toggle_rect().contains(event.pos()):
                self.toggle_mirror_mode()
                return

            tabs = [("front", "Front"), ("side", "Side"), ("top", "Top")]
            for i, (v_key, _) in enumerate(tabs):
                if self._get_view_tab_rect(i).contains(event.pos()):
                    self.set_active_view(v_key)
                    return

            if self._get_rebuild_btn_rect().contains(event.pos()):
                self.live_rebuild_rig()
                return

            if self._get_mirror_shapes_btn_rect().contains(event.pos()):
                cx = self._get_symmetry_center_x()
                self.rig_builder.mirror_control_shapes(source_side="Left", center_x=cx)
                return

            if self._get_finalize_btn_rect().contains(event.pos()):
                self.finalize_rig_and_go_anim()
                return

        img_rect = self._get_image_rect()
        if img_rect.isEmpty():
            return

        # 3. Context Menu on RMB
        if event.button() == QtCore.Qt.RightButton:
            self._show_context_menu(event.pos(), img_rect)
            return

        # 4. Guide Selection & Dragging (LMB)
        if event.button() == QtCore.Qt.LeftButton and self.canvas_mode == "rig":
            for guide in reversed(self.rig_guides):
                pos3d = guide.get("pos3d", [0.0, 0.0, 0.0])
                u, v = AutoCaptureEngine.world_to_uv(pos3d, self.current_view, self.capture_meta)
                gx = img_rect.x() + int(u * img_rect.width())
                gy = img_rect.y() + int(v * img_rect.height())
                if ((event.pos().x() - gx)**2 + (event.pos().y() - gy)**2)**0.5 <= self.PIN_RADIUS + 5:
                    self.selected_guide = guide
                    self.dragged_guide = guide
                    self.drag_offset = event.pos() - QtCore.QPoint(gx, gy)
                    self.update()
                    return

            self.selected_guide = None
            self.update()
            return

        # 5. Animation Mode Interactions
        for sld in reversed(self.sliders):
            srect = self._get_slider_rect(sld, img_rect)
            if srect.contains(event.pos()):
                if event.modifiers() & QtCore.Qt.ControlModifier:
                    self.dragged_slider = sld
                    self.drag_offset = event.pos() - srect.topLeft()
                    return

                c_rect = self._get_slider_center_btn_rect(srect, sld.get("val", 0.0))
                mode = sld.get("mode", "Tween")

                if not c_rect.contains(event.pos()):
                    for tx, ty, pct, label in self._get_tick_points(srect):
                        if ((event.pos().x() - tx)**2 + (event.pos().y() - ty)**2)**0.5 <= 9:
                            direction = 1 if tx > srect.center().x() else -1
                            if mode == "Offset":
                                from DooAnimKit.core.time_offset_engine import TimeOffsetEngine
                                toe = TimeOffsetEngine()
                                step_frames = 1 if pct <= 5.0 else (2 if pct <= 15.0 else 5)
                                toe.step_shift(direction * step_frames)
                            else:
                                if hasattr(self.main_window, "tween_engine"):
                                    self.main_window.tween_engine.step_nudge(direction=direction, step_percent=pct)
                            self.update()
                            return

                self.active_slider_handle = sld
                self.is_handle_dragging = True
                cmds.undoInfo(openChunk=True)
                self._undo_opened = True

                if mode == "Offset":
                    from DooAnimKit.core.time_offset_engine import TimeOffsetEngine
                    toe = TimeOffsetEngine()
                    self.slider_cached_state = toe.cache_time_state()
                else:
                    if hasattr(self.main_window, "tween_engine"):
                        self.slider_cached_state = self.main_window.tween_engine.cache_current_tween_state()
                self._update_slider_drag(sld, event.pos(), srect)
                return

        for pin in reversed(self.pins):
            px = img_rect.x() + int(pin["u"] * img_rect.width())
            py = img_rect.y() + int(pin["v"] * img_rect.height())
            if ((event.pos().x() - px)**2 + (event.pos().y() - py)**2)**0.5 <= self.PIN_RADIUS + 4:
                add_mode = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
                if "name" in pin and cmds.objExists(pin["name"]):
                    cmds.select(pin["name"], add=add_mode)
                return

        self.is_box_selecting = True
        self.box_start = event.pos()
        self.box_current = event.pos()
        self.update()

    def _update_slider_drag(self, sld, pos, srect):
        btn_w = 40
        max_shift = float((srect.width() // 2) - (btn_w // 2) - 2)
        offset_x = pos.x() - srect.center().x()
        val = max(-1.0, min(1.0, offset_x / max(1.0, max_shift)))
        sld["val"] = val

        mode = sld.get("mode", "Tween")
        if self.slider_cached_state:
            if mode == "Offset":
                from DooAnimKit.core.time_offset_engine import TimeOffsetEngine
                toe = TimeOffsetEngine()
                shift_frames = val * 10.0
                toe.offset_interactive_delta(self.slider_cached_state, shift_frames)
            else:
                if hasattr(self.main_window, "tween_engine"):
                    self.main_window.tween_engine.tween_interactive_delta(self.slider_cached_state, val)
        self.update()

    def mouseMoveEvent(self, event):
        img_rect = self._get_image_rect()
        if img_rect.isEmpty():
            return

        if self.dragged_guide and self.canvas_mode == "rig":
            new_pos = event.pos() - self.drag_offset
            u = max(0.0, min(1.0, (new_pos.x() - img_rect.x()) / float(img_rect.width())))
            v = max(0.0, min(1.0, (new_pos.y() - img_rect.y()) / float(img_rect.height())))
            curr_pos3d = self.dragged_guide.get("pos3d", [0.0, 0.0, 0.0])
            new_pos3d = AutoCaptureEngine.uv_to_world(u, v, self.current_view, self.capture_meta, curr_pos3d)
            self.dragged_guide["pos3d"] = new_pos3d

            if self.mirror_mode:
                mir_guide = self._find_mirrored_guide(self.dragged_guide)
                if mir_guide:
                    cx = self._get_symmetry_center_x()
                    mir_x = cx - (new_pos3d[0] - cx)
                    mir_guide["pos3d"] = [mir_x, new_pos3d[1], new_pos3d[2]]

            self.update()
            return

        if self.active_slider_handle:
            srect = self._get_slider_rect(self.active_slider_handle, img_rect)
            self._update_slider_drag(self.active_slider_handle, event.pos(), srect)
            return

        if self.dragged_pin and self.canvas_mode == "anim":
            new_center = event.pos() - self.drag_offset
            self.dragged_pin["u"] = max(0.0, min(1.0, (new_center.x() - img_rect.x()) / float(img_rect.width())))
            self.dragged_pin["v"] = max(0.0, min(1.0, (new_center.y() - img_rect.y()) / float(img_rect.height())))
            self.update()
        elif self.is_box_selecting:
            self.box_current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.dragged_guide:
            self.dragged_guide = None
            self.save_state()
            self.update()
            return

        if self.active_slider_handle:
            self.active_slider_handle["val"] = 0.0
            self.active_slider_handle = None
            self.is_handle_dragging = False
            self.slider_cached_state.clear()
            if self._undo_opened:
                cmds.undoInfo(closeChunk=True)
                self._undo_opened = False
            self.update()
            return

        if self.dragged_slider or self.dragged_button or self.dragged_pin:
            self.dragged_slider = None
            self.dragged_button = None
            self.dragged_pin = None
            self.save_state()
            self.update()

        if event.button() == QtCore.Qt.LeftButton and self.is_box_selecting:
            self.is_box_selecting = False
            img_rect = self._get_image_rect()
            if not img_rect.isEmpty():
                box = QtCore.QRect(self.box_start, self.box_current).normalized()
                add_mode = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
                sel_nodes = []
                for p in self.pins:
                    px = img_rect.x() + int(p["u"] * img_rect.width())
                    py = img_rect.y() + int(p["v"] * img_rect.height())
                    if box.contains(QtCore.QPoint(px, py)) and "name" in p and cmds.objExists(p["name"]):
                        sel_nodes.append(p["name"])
                if sel_nodes:
                    cmds.select(sel_nodes, add=add_mode)

        self.save_state()
        self.update()

    def _show_context_menu(self, pos, img_rect):
        norm_u = (pos.x() - img_rect.x()) / float(img_rect.width())
        norm_v = (pos.y() - img_rect.y()) / float(img_rect.height())

        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(self.MENU_STYLE)

        # 1. RMB Context Menu in Auto-Rig Mode
        if self.canvas_mode == "rig":
            clicked_guide = None
            for guide in self.rig_guides:
                pos3d = guide.get("pos3d", [0.0, 0.0, 0.0])
                u, v = AutoCaptureEngine.world_to_uv(pos3d, self.current_view, self.capture_meta)
                gx = img_rect.x() + int(u * img_rect.width())
                gy = img_rect.y() + int(v * img_rect.height())
                if ((pos.x() - gx)**2 + (pos.y() - gy)**2)**0.5 <= self.PIN_RADIUS + 5:
                    clicked_guide = guide
                    break

            if clicked_guide:
                current_tag = clicked_guide.get("hik_tag", "None")
                menu.addSection(f"🦴 Guide: {clicked_guide.get('name')} [{current_tag}]")
                hik_menu = menu.addMenu("🏷 Assign Anatomy Tag")
                hik_menu.setStyleSheet(self.MENU_STYLE)
                tag_actions = {}
                clear_tag_act = hik_menu.addAction("Clear (None)")
                tag_actions[clear_tag_act] = "None"
                hik_menu.addSeparator()

                for cat_name, tag_list in self.HIK_TAGS_MAP.items():
                    cat_sub = hik_menu.addMenu(cat_name)
                    cat_sub.setStyleSheet(self.MENU_STYLE)
                    for t in tag_list:
                        act = cat_sub.addAction(t)
                        tag_actions[act] = t

                delete_act = menu.addAction("🗑 Delete Guide")
                chosen = menu.exec_(self.mapToGlobal(pos))

                if chosen in tag_actions:
                    new_tag = tag_actions[chosen]
                    clicked_guide["hik_tag"] = new_tag
                    if self.mirror_mode:
                        mir_g = self._find_mirrored_guide(clicked_guide)
                        if mir_g:
                            mir_g["hik_tag"] = self._get_mirrored_tag(new_tag)
                    self.save_state()
                    self.update()

                elif chosen == delete_act:
                    mir_g = self._find_mirrored_guide(clicked_guide)
                    if clicked_guide in self.rig_guides:
                        self.rig_guides.remove(clicked_guide)
                    if mir_g and mir_g in self.rig_guides:
                        self.rig_guides.remove(mir_g)
                    self.selected_guide = None
                    self.save_state()
                    self.update()
                return

            menu.addSection("🦴 Auto-Rig Guides")
            act_add_guide = menu.addAction("📍 Add 3D Guide Point")
            act_mirror_now = menu.addAction("🔄 Mirror Left -> Right Now")
            menu.addSeparator()
            act_clear_guides = menu.addAction("🗑 Clear All Guides")

            chosen = menu.exec_(self.mapToGlobal(pos))

            if chosen == act_add_guide:
                base_center = self.capture_meta.get("center", [0.0, 0.0, 0.0]) if self.capture_meta else [0.0, 0.0, 0.0]
                pos3d = AutoCaptureEngine.uv_to_world(norm_u, norm_v, self.current_view, self.capture_meta, base_center)
                guide_count = len(self.rig_guides) + 1
                g_id = f"guide_id_{guide_count}_{int(cmds.currentTime(q=True))}"

                new_guide = {
                    "id": g_id,
                    "name": f"guide_{guide_count}",
                    "hik_tag": "None",
                    "pos3d": pos3d,
                    "pair_id": None
                }
                self.rig_guides.append(new_guide)

                if self.mirror_mode:
                    cx = self._get_symmetry_center_x()
                    mir_x = cx - (pos3d[0] - cx)
                    if abs(pos3d[0] - cx) > 0.05:
                        mir_id = f"guide_id_{guide_count + 1}_mir"
                        mir_guide = {
                            "id": mir_id,
                            "name": f"guide_{guide_count + 1}_R",
                            "hik_tag": "None",
                            "pos3d": [mir_x, pos3d[1], pos3d[2]],
                            "pair_id": g_id
                        }
                        new_guide["pair_id"] = mir_id
                        self.rig_guides.append(mir_guide)

                self.selected_guide = new_guide
                self.save_state()
                self.update()

            elif chosen == act_mirror_now:
                self._mirror_all_left_to_right()

            elif chosen == act_clear_guides:
                self.rig_guides.clear()
                self.selected_guide = None
                self.save_state()
                self.update()
            return

        # 2. RMB Context Menu in Animation Mode
        menu.addSection("⚡ Animation Hub")
        act_add_pin = menu.addAction("📍 Add Pin (From Selection)")
        act_add_tween = menu.addAction("🎚 Add Tween Slider")
        act_add_offset = menu.addAction("⏱️ Add Time Offset Slider")
        menu.addSeparator()
        act_switch_rig = menu.addAction("🦴 Switch to Auto-Rig Mode")

        chosen = menu.exec_(self.mapToGlobal(pos))
        if chosen == act_add_pin:
            sel = cmds.ls(selection=True, type="transform")
            if sel:
                self.pins.append({"name": sel[0], "u": norm_u, "v": norm_v, "shape": "Circle"})
                self.save_state()
                self.update()
        elif chosen == act_add_tween:
            self.sliders.append({
                "label": "Tween", "mode": "Tween", "action_id": "tween_mid_50",
                "u": norm_u, "v": norm_v, "w": 235, "h": 24, "val": 0.0, "color": "#00838f"
            })
            self.save_state()
            self.update()
        elif chosen == act_add_offset:
            self.sliders.append({
                "label": "Offset", "mode": "Offset", "action_id": "time_offset",
                "u": norm_u, "v": norm_v, "w": 235, "h": 24, "val": 0.0, "color": "#00695c"
            })
            self.save_state()
            self.update()
        elif chosen == act_switch_rig:
            self.set_canvas_mode("rig")

    def _mirror_all_left_to_right(self):
        cx = self._get_symmetry_center_x()
        left_guides = [g for g in self.rig_guides if g.get("pos3d", [0,0,0])[0] < cx - 0.05]
        new_list = [g for g in self.rig_guides if g.get("pos3d", [0,0,0])[0] <= cx + 0.05]

        for lg in left_guides:
            pos3d = lg["pos3d"]
            mir_x = cx - (pos3d[0] - cx)
            mir_id = f"{lg.get('id', 'g')}_mir"
            lg["pair_id"] = mir_id

            mir_guide = {
                "id": mir_id,
                "name": f"{lg.get('name')}_R",
                "hik_tag": self._get_mirrored_tag(lg.get("hik_tag", "None")),
                "pos3d": [mir_x, pos3d[1], pos3d[2]],
                "pair_id": lg.get("id")
            }
            new_list.append(mir_guide)

        self.rig_guides = new_list
        self.save_state()
        self.update()
        cmds.inViewMessage(amg="Auto-Rig: <hl>All Left guides mirrored to Right!</hl>", pos="topCenter", fade=True)