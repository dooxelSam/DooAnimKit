"""
Auto Capture Engine for DooAnimKit Auto-Rig.
Captures clean, unselected, grid-free orthographic projections (Front, Side, Top)
with solid default shading and accurate 2D <-> 3D world space coordinate mapping.
"""

import os
import json
import maya.cmds as cmds

try:
    import maya.api.OpenMaya as om
    import maya.api.OpenMayaUI as omui
except ImportError:
    import maya.OpenMaya as om
    import maya.OpenMayaUI as omui

try:
    from PySide6 import QtGui
except ImportError:
    from PySide2 import QtGui


class AutoCaptureEngine:

    VIEWS = {
        "front": {
            "cam": "front",
            "pos_offset": (0, 0, 5000),
            "axes": ("x", "y"),
            "dim_indices": (0, 1)
        },
        "side": {
            "cam": "side",
            "pos_offset": (5000, 0, 0),
            "axes": ("z", "y"),
            "dim_indices": (2, 1)
        },
        "top": {
            "cam": "top",
            "pos_offset": (0, 5000, 0),
            "axes": ("x", "z"),
            "dim_indices": (0, 2)
        }
    }

    def __init__(self, output_dir=None):
        if not output_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(base_dir, "presets", "captures")
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def get_selection_bbox(self):
        sel = cmds.ls(selection=True, long=True) or []
        if not sel:
            cmds.warning("Будь ласка, виділіть геометрію або групу персонажа!")
            return None

        shapes = cmds.listRelatives(sel, allDescendents=True, type="mesh", fullPath=True) or []
        mesh_nodes = list(set(sel + shapes))
        if not mesh_nodes:
            cmds.warning("У виділеному об'єкті не знайдено полігональних мешів!")
            return None

        bbox = cmds.exactWorldBoundingBox(mesh_nodes)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox

        cx = (xmin + xmax) / 2.0
        cy = (ymin + ymax) / 2.0
        cz = (zmin + zmax) / 2.0

        w = max(0.01, xmax - xmin)
        h = max(0.01, ymax - ymin)
        d = max(0.01, zmax - zmin)

        return {
            "bbox": bbox,
            "center": (cx, cy, cz),
            "dimensions": (w, h, d),
            "nodes": sel
        }

    def _grab_view_buffer(self, file_path):
        """Captures clean viewport buffer directly from OpenGL."""
        try:
            view = omui.M3dView.active3dView()
            image = om.MImage()
            view.readColorBuffer(image, True)
            image.writeToFile(file_path, "png")
            return True
        except Exception:
            try:
                view = omui.M3dView.active3dView()
                hwnd = view.widget()
                pix = QtGui.QPixmap(hwnd.size())
                hwnd.render(pix)
                pix.save(file_path, "PNG")
                return True
            except Exception as e:
                print(f"Error capturing buffer: {e}")
                return False

    def capture_all_projections(self):
        saved_selection = cmds.ls(selection=True, long=True) or []
        bbox_data = self.get_selection_bbox()
        if not bbox_data:
            return None

        cx, cy, cz = bbox_data["center"]
        w, h, d = bbox_data["dimensions"]
        dims = (w, h, d)

        panel = cmds.getPanel(withFocus=True)
        if not panel or "modelPanel" not in panel:
            panels = cmds.getPanel(type="modelPanel") or []
            panel = panels[0] if panels else "modelPanel4"

        # Зберігаємо попередній стан панелі
        prev_cam = cmds.modelEditor(panel, query=True, camera=True) if cmds.modelPanel(panel, exists=True) else "persp"
        prev_grid = cmds.modelEditor(panel, query=True, grid=True)
        prev_joints = cmds.modelEditor(panel, query=True, joints=True)
        prev_curves = cmds.modelEditor(panel, query=True, nurbsCurves=True)
        prev_locators = cmds.modelEditor(panel, query=True, locators=True)
        prev_wos = cmds.modelEditor(panel, query=True, wireframeOnShaded=True)
        prev_sel_hl = cmds.modelEditor(panel, query=True, selectionHiliteDisplay=True)
        prev_lights = cmds.modelEditor(panel, query=True, displayLights=True)

        res_data = {
            "center": bbox_data["center"],
            "dimensions": bbox_data["dimensions"],
            "bbox": bbox_data["bbox"],
            "views": {}
        }

        try:
            # 1. Повністю скидаємо будь-яке виділення та підсвічування об'єктів
            cmds.select(clear=True)
            try:
                cmds.hilite(clear=True)
            except Exception:
                pass

            # 2. Налаштовуємо чистий шейдинг (стандартне світло, без зникнення текстур)
            cmds.modelEditor(
                panel, edit=True,
                grid=False,
                joints=False,
                nurbsCurves=False,
                locators=False,
                wireframeOnShaded=False,
                selectionHiliteDisplay=False,
                displayAppearance="smoothShaded",
                displayTextures=False,
                displayLights="default"
            )

            # Холостий рефреш, щоб Viewport 2.0 скинув зелений lead-selection буфер
            cmds.refresh(cv=True, force=True)

            view = omui.M3dView.active3dView()
            view_w = float(view.portWidth())
            view_h = float(view.portHeight())
            view_aspect = view_w / max(1.0, view_h)

            padding = 1.06

            for view_name, cfg in self.VIEWS.items():
                cam = cfg["cam"]
                cam_shape = cmds.listRelatives(cam, shapes=True)[0] if cmds.nodeType(cam) == "transform" else cam

                dim_x = dims[cfg["dim_indices"][0]]
                dim_y = dims[cfg["dim_indices"][1]]
                obj_aspect = dim_x / max(0.001, dim_y)

                if obj_aspect > view_aspect:
                    ortho_w = dim_x * padding
                else:
                    ortho_w = (dim_y * view_aspect) * padding

                cmds.setAttr(f"{cam}.translateX", cx + cfg["pos_offset"][0])
                cmds.setAttr(f"{cam}.translateY", cy + cfg["pos_offset"][1])
                cmds.setAttr(f"{cam}.translateZ", cz + cfg["pos_offset"][2])
                cmds.setAttr(f"{cam_shape}.orthographicWidth", ortho_w)

                cmds.modelEditor(panel, edit=True, camera=cam)
                cmds.refresh(cv=True, force=True)

                img_path = os.path.join(self.output_dir, f"rig_view_{view_name}.png").replace("\\", "/")
                self._grab_view_buffer(img_path)

                res_data["views"][view_name] = {
                    "image": img_path,
                    "ortho_width": ortho_w,
                    "center": (cx, cy, cz),
                    "aspect": view_aspect,
                    "axes": cfg["axes"]
                }

        finally:
            if cmds.modelPanel(panel, exists=True):
                cmds.modelEditor(
                    panel, edit=True,
                    camera=prev_cam,
                    grid=prev_grid,
                    joints=prev_joints,
                    nurbsCurves=prev_curves,
                    locators=prev_locators,
                    wireframeOnShaded=prev_wos,
                    selectionHiliteDisplay=prev_sel_hl,
                    displayLights=prev_lights
                )
            if saved_selection:
                cmds.select(saved_selection)
            cmds.refresh(cv=True, force=True)

        meta_file = os.path.join(self.output_dir, "capture_metadata.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(res_data, f, indent=4)

        cmds.inViewMessage(amg="AutoCapture: <hl>Front, Side & Top views успішно зняті чисто!</hl>", pos="topCenter", fade=True)
        return res_data

    @staticmethod
    def world_to_uv(pos3d, view_name, meta):
        if not meta or "views" not in meta or view_name not in meta["views"]:
            return 0.5, 0.5

        v_data = meta["views"][view_name]
        cx, cy, cz = v_data["center"]
        ortho_w = v_data["ortho_width"]
        aspect = v_data.get("aspect", 1.0)
        ortho_h = ortho_w / max(0.001, aspect)

        px, py, pz = pos3d

        if view_name == "front":
            u = 0.5 + ((px - cx) / ortho_w)
            v = 0.5 - ((py - cy) / ortho_h)
        elif view_name == "side":
            u = 0.5 - ((pz - cz) / ortho_w)
            v = 0.5 - ((py - cy) / ortho_h)
        elif view_name == "top":
            u = 0.5 + ((px - cx) / ortho_w)
            v = 0.5 + ((pz - cz) / ortho_h)
        else:
            return 0.5, 0.5

        return max(0.0, min(1.0, u)), max(0.0, min(1.0, v))

    @staticmethod
    def uv_to_world(u, v, view_name, meta, current_pos3d):
        if not meta or "views" not in meta or view_name not in meta["views"]:
            return current_pos3d

        v_data = meta["views"][view_name]
        cx, cy, cz = v_data["center"]
        ortho_w = v_data["ortho_width"]
        aspect = v_data.get("aspect", 1.0)
        ortho_h = ortho_w / max(0.001, aspect)

        x, y, z = list(current_pos3d)

        if view_name == "front":
            x = cx + (u - 0.5) * ortho_w
            y = cy - (v - 0.5) * ortho_h
        elif view_name == "side":
            z = cz - (u - 0.5) * ortho_w
            y = cy - (v - 0.5) * ortho_h
        elif view_name == "top":
            x = cx + (u - 0.5) * ortho_w
            z = cz + (v - 0.5) * ortho_h

        return [x, y, z]