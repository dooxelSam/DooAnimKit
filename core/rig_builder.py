"""
Rig Builder Engine for DooAnimKit.
Dynamic Spine Solver, Direct CV Vertex Shape Preservation (selectCurveCV compatible),
World-Space Curve Shape Mirroring, and Animation Canvas bridge.
"""

import os
import json
import maya.cmds as cmds
import maya.api.OpenMaya as om
from DooAnimKit.core.context import UndoContext


class RigBuilderEngine:

    HIERARCHY_RULES = {
        # Arm Chains
        "LeftShoulder": "LeftClavicle",
        "LeftElbow": "LeftShoulder",
        "LeftWrist": "LeftElbow",
        "LeftFingers": "LeftWrist",
        "LeftThumb": "LeftWrist",

        "RightShoulder": "RightClavicle",
        "RightElbow": "RightShoulder",
        "RightWrist": "RightElbow",
        "RightFingers": "RightWrist",
        "RightThumb": "RightWrist",

        # Head Chain
        "Head": "Neck",

        # Leg Chains
        "LeftUpLeg": "Hips",
        "LeftKnee": "LeftUpLeg",
        "LeftFoot": "LeftKnee",
        "LeftToes": "LeftFoot",

        "RightUpLeg": "Hips",
        "RightKnee": "RightUpLeg",
        "RightFoot": "RightKnee",
        "RightToes": "RightFoot"
    }

    def __init__(self, shapes_dir=None):
        if not shapes_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            shapes_dir = os.path.join(base_dir, "presets")
        self.shapes_file = os.path.join(shapes_dir, "control_shapes.json")

    def _create_circle_ctrl(self, name, radius=2.5, axis=(1, 0, 0), color="yellow", cached_shapes=None):
        """Creates styled curve control and forces saved CV vertex transforms."""
        ctrl_name = f"CTRL_{name}"
        if cmds.objExists(ctrl_name):
            try:
                cmds.delete(ctrl_name)
            except Exception:
                pass

        if cached_shapes is None:
            cached_shapes = self.load_saved_shapes()

        shape_data = cached_shapes.get(name)

        # 1. Створюємо базове коло в Maya
        circ = cmds.circle(name=ctrl_name, normal=axis, radius=radius, ch=False)[0]

        # 2. Якщо користувач крутив/скейлив вертекси (через selectCurveCV) — примусово ставимо їх на місце
        if shape_data and shape_data.get("cvs"):
            shapes = cmds.listRelatives(circ, shapes=True, fullPath=True) or []
            if shapes:
                shape = shapes[0]
                cv_points = shape_data["cvs"]
                num_cvs = cmds.getAttr(f"{shape}.spans") + cmds.getAttr(f"{shape}.degree")

                if len(cv_points) == num_cvs:
                    for i, pt in enumerate(cv_points):
                        cmds.xform(f"{shape}.cv[{i}]", objectSpace=True, translation=pt)

        # 3. Колір кривої
        shapes = cmds.listRelatives(circ, shapes=True, fullPath=True) or []
        if shapes:
            shape = shapes[0]
            cmds.setAttr(f"{shape}.overrideEnabled", 1)
            col_idx = 17
            if color == "blue":
                col_idx = 6
            elif color == "red":
                col_idx = 13
            elif color == "green":
                col_idx = 14
            cmds.setAttr(f"{shape}.overrideColor", col_idx)

        return circ

    def save_control_shapes(self):
        """Scans all CTRL_ shapes in scene and caches their exact CV positions."""
        ctrls = cmds.ls("CTRL_*", type="transform") or []
        if not ctrls:
            return False

        data = self.load_saved_shapes()
        for c in ctrls:
            shapes = cmds.listRelatives(c, shapes=True, type="nurbsCurve") or []
            if not shapes:
                continue
            shape = shapes[0]
            tag = c.replace("CTRL_", "", 1)
            try:
                num_cvs = cmds.getAttr(f"{shape}.spans") + cmds.getAttr(f"{shape}.degree")
                cv_points = []
                for i in range(num_cvs):
                    # Зчитуємо чисті локальні координати вертексів у просторі самого контролера
                    pt = cmds.xform(f"{shape}.cv[{i}]", query=True, objectSpace=True, translation=True)
                    cv_points.append(pt)

                if cv_points:
                    data[tag] = {
                        "degree": cmds.getAttr(f"{shape}.degree"),
                        "periodic": bool(cmds.getAttr(f"{shape}.form") == 2),
                        "cvs": cv_points
                    }
            except Exception as e:
                print(f"Error caching control CVs for {c}: {e}")

        if data:
            try:
                os.makedirs(os.path.dirname(self.shapes_file), exist_ok=True)
                with open(self.shapes_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                return True
            except Exception:
                pass
        return False

    def load_saved_shapes(self):
        """Loads cached control shapes from disk."""
        if os.path.exists(self.shapes_file):
            try:
                with open(self.shapes_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def mirror_control_shapes(self, source_side="Left", center_x=0.0):
        """
        True World-Space Curve Mirroring (Position + Rotation + Shape).
        Works seamlessly with selectCurveCV('all') vertex edits.
        """
        target_side = "Right" if source_side == "Left" else "Left"
        source_ctrls = cmds.ls(f"CTRL_{source_side}*", type="transform") or []
        if not source_ctrls:
            cmds.warning(f"No CTRL_{source_side}* controls found to mirror!")
            return False

        mirrored_count = 0
        with UndoContext("MirrorControlShapesWorld"):
            for s_ctrl in source_ctrls:
                t_ctrl = s_ctrl.replace(f"CTRL_{source_side}", f"CTRL_{target_side}", 1)
                if not cmds.objExists(t_ctrl):
                    continue

                s_shapes = cmds.listRelatives(s_ctrl, shapes=True, type="nurbsCurve") or []
                t_shapes = cmds.listRelatives(t_ctrl, shapes=True, type="nurbsCurve") or []
                if not s_shapes or not t_shapes:
                    continue

                s_shape, t_shape = s_shapes[0], t_shapes[0]
                num_cvs = cmds.getAttr(f"{s_shape}.spans") + cmds.getAttr(f"{s_shape}.degree")

                t_matrix_list = cmds.getAttr(f"{t_ctrl}.worldInverseMatrix[0]")
                t_inv_mat = om.MMatrix(t_matrix_list)

                for i in range(num_cvs):
                    ws_pt = cmds.pointPosition(f"{s_shape}.cv[{i}]", world=True)
                    mir_ws_x = center_x - (ws_pt[0] - center_x)
                    mir_ws_pt = om.MPoint(mir_ws_x, ws_pt[1], ws_pt[2], 1.0)
                    local_pt = mir_ws_pt * t_inv_mat
                    cmds.xform(f"{t_shape}.cv[{i}]", objectSpace=True, translation=[local_pt.x, local_pt.y, local_pt.z])

                mirrored_count += 1

        self.save_control_shapes()
        cmds.inViewMessage(amg=f"Control Shapes Mirrored: <hl>{mirrored_count} controls ({source_side} -> {target_side})</hl>", pos="topCenter", fade=True)
        return True

    def build_skeleton_and_rig(self, guides):
        """Builds skeleton and FK controls, rigorously preserving all CV vertex edits."""
        if not guides:
            cmds.warning("No guide points provided!")
            return None

        guide_map = {}
        for g in guides:
            tag = g.get("hik_tag", "None")
            if tag != "None":
                guide_map[tag] = g.get("pos3d", [0, 0, 0])

        if "Hips" not in guide_map:
            cmds.warning("Missing 'Hips' root guide! Please assign 'Hips' tag.")
            return None

        # 1. Автоматично зчитуємо та зберігаємо повернуті вертекси кривих перед видаленням
        self.save_control_shapes()
        cached_shapes = self.load_saved_shapes()

        # 2. Динамічний пошук та сортування хребта
        spine_tags = [t for t in guide_map.keys() if t.startswith("Spine") or t == "Chest"]

        def spine_sort_key(name):
            if name.startswith("Spine"):
                try:
                    return int(name.replace("Spine", ""))
                except Exception:
                    return 99
            return 98 if name == "Chest" else 100

        sorted_spines = sorted(spine_tags, key=spine_sort_key)
        top_spine_tag = sorted_spines[-1] if sorted_spines else "Hips"

        created_pins = []

        with UndoContext("BuildDooRig"):
            master_grp = "DooRig_Character_GRP"
            if cmds.objExists(master_grp):
                cmds.delete(master_grp)
            master_grp = cmds.group(empty=True, name=master_grp)

            joints_grp = cmds.group(empty=True, name="DooRig_Skeleton_GRP", parent=master_grp)
            controls_grp = cmds.group(empty=True, name="DooRig_Controls_GRP", parent=master_grp)

            created_joints = {}
            created_ctrls = {}
            created_zero_grps = {}

            # Створення кісток
            for tag, pos in guide_map.items():
                jnt_name = f"JNT_{tag}"
                cmds.select(clear=True)
                jnt = cmds.joint(name=jnt_name, position=pos, radius=1.2)
                created_joints[tag] = jnt

            # Зв'язування Spine ланцюжка
            prev_spine = "Hips"
            for s_tag in sorted_spines:
                if s_tag in created_joints and prev_spine in created_joints:
                    cmds.parent(created_joints[s_tag], created_joints[prev_spine])
                prev_spine = s_tag

            # Зв'язування кінцівок до кісток
            for child_tag, jnt in created_joints.items():
                if child_tag in sorted_spines:
                    continue

                if child_tag == "Hips":
                    cmds.parent(jnt, joints_grp)
                    continue

                if child_tag in ("LeftClavicle", "RightClavicle", "Neck", "LeftShoulder", "RightShoulder"):
                    if child_tag in ("LeftClavicle", "RightClavicle", "Neck"):
                        parent_tag = top_spine_tag
                    else:
                        clav = "LeftClavicle" if child_tag.startswith("Left") else "RightClavicle"
                        parent_tag = clav if clav in created_joints else top_spine_tag
                else:
                    parent_tag = self.HIERARCHY_RULES.get(child_tag)

                if parent_tag and parent_tag in created_joints:
                    cmds.parent(jnt, created_joints[parent_tag])

            # Орієнтація кісток
            for tag, jnt in created_joints.items():
                children = cmds.listRelatives(jnt, type="joint") or []
                if children:
                    cmds.joint(jnt, edit=True, oj="xyz", sao="yup", zso=True)
                else:
                    cmds.joint(jnt, edit=True, oj="none", zso=True)

            # 3. Створення контролерів із примусовим застосуванням повернених CV вертексів
            for tag, jnt in created_joints.items():
                col = "yellow"
                if tag.startswith("Left"):
                    col = "blue"
                elif tag.startswith("Right"):
                    col = "red"

                axis = (1, 0, 0)
                if "Foot" in tag or "Toes" in tag:
                    axis = (0, 1, 0)
                elif "Hips" in tag or "Spine" in tag or "Chest" in tag:
                    axis = (0, 1, 0)

                ctrl = self._create_circle_ctrl(tag, radius=2.5, axis=axis, color=col, cached_shapes=cached_shapes)
                zero_grp = cmds.group(ctrl, name=f"GRP_ZERO_{tag}")
                created_ctrls[tag] = ctrl
                created_zero_grps[tag] = zero_grp

                cmds.matchTransform(zero_grp, jnt, pos=True, rot=True)
                cmds.parentConstraint(ctrl, jnt, maintainOffset=True)

                created_pins.append({
                    "name": ctrl,
                    "hik_tag": tag,
                    "color": "#2196F3" if col == "blue" else ("#F44336" if col == "red" else "#FFC107"),
                    "pos3d": guide_map[tag]
                })

            # 4. Ієрархія контролерів
            prev_ctrl_spine = "Hips"
            for s_tag in sorted_spines:
                if s_tag in created_zero_grps and prev_ctrl_spine in created_ctrls:
                    cmds.parent(created_zero_grps[s_tag], created_ctrls[prev_ctrl_spine])
                elif s_tag in created_zero_grps:
                    cmds.parent(created_zero_grps[s_tag], controls_grp)
                prev_ctrl_spine = s_tag

            for child_tag, zero_grp in created_zero_grps.items():
                if child_tag in sorted_spines:
                    continue

                if child_tag in ("LeftClavicle", "RightClavicle", "Neck", "LeftShoulder", "RightShoulder"):
                    if child_tag in ("LeftClavicle", "RightClavicle", "Neck"):
                        parent_tag = top_spine_tag
                    else:
                        clav = "LeftClavicle" if child_tag.startswith("Left") else "RightClavicle"
                        parent_tag = clav if clav in created_ctrls else top_spine_tag
                else:
                    parent_tag = self.HIERARCHY_RULES.get(child_tag)

                if parent_tag and parent_tag in created_ctrls:
                    cmds.parent(zero_grp, created_ctrls[parent_tag])
                else:
                    cmds.parent(zero_grp, controls_grp)

        cmds.select(clear=True)
        return created_pins