import maya.cmds as cmds
import maya.api.OpenMaya as om
from DooAnimKit.core.context import UndoContext
from DooAnimKit.core.temp_control import TempControlManager


class TempAimEngine:
    """Zero-Offset Temp Aim Engine with shared global sampling mode."""

    AIM_AXES = [
        ("+X", (1, 0, 0)),
        ("-X", (-1, 0, 0)),
        ("+Y", (0, 1, 0)),
        ("-Y", (0, -1, 0)),
        ("+Z", (0, 0, 1)),
        ("-Z", (0, 0, -1)),
    ]

    def __init__(self, main_window=None):
        self.win = main_window
        self.target_ctrl = None
        self.setup_grp = None
        self.aim_crv = None
        self.up_crv = None

    def _get_time_range(self):
        start = int(cmds.playbackOptions(query=True, minTime=True))
        end = int(cmds.playbackOptions(query=True, maxTime=True))
        return start, end

    def _is_keys_only(self):
        """Always reads the single source of truth from TempControlManager."""
        return TempControlManager.BAKE_KEYS_ONLY

    def get_orthogonal_up(self, aim_vec, twist_idx):
        ax, ay, az = aim_vec
        if abs(ax) > 0.9:
            perps = [(0, 1, 0), (0, 0, 1), (0, -1, 0), (0, 0, -1)]
        elif abs(ay) > 0.9:
            perps = [(0, 0, 1), (1, 0, 0), (0, 0, -1), (-1, 0, 0)]
        else:
            perps = [(1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0)]
        return perps[twist_idx % 4]

    def _create_cross_curve(self, name, scale=1.2, color_index=13):
        points = [
            (-0.5, 0, 1.5), (0.5, 0, 1.5), (0.5, 0, 0.5), (1.5, 0, 0.5),
            (1.5, 0, -0.5), (0.5, 0, -0.5), (0.5, 0, -1.5), (-0.5, 0, -1.5),
            (-0.5, 0, -0.5), (-1.5, 0, -0.5), (-1.5, 0, 0.5), (-0.5, 0, 0.5),
            (-0.5, 0, 1.5)
        ]
        scaled_pts = [(p[0] * scale, p[1] * scale, p[2] * scale) for p in points]
        crv = cmds.curve(d=1, p=scaled_pts, k=range(len(scaled_pts)), name=name)
        for shape in cmds.listRelatives(crv, shapes=True) or []:
            cmds.setAttr(f"{shape}.overrideEnabled", 1)
            cmds.setAttr(f"{shape}.overrideColor", color_index)
        return crv

    def _create_circle_curve(self, name, radius=1.0, color_index=14):
        crv = cmds.circle(name=name, nr=(0, 1, 0), r=radius, ch=False)[0]
        for shape in cmds.listRelatives(crv, shapes=True) or []:
            cmds.setAttr(f"{shape}.overrideEnabled", 1)
            cmds.setAttr(f"{shape}.overrideColor", color_index)
        return crv

    def _create_connection_line(self, start_obj, end_obj, line_name):
        if cmds.objExists(line_name):
            cmds.delete(line_name)

        pos1 = cmds.xform(start_obj, query=True, ws=True, translation=True)
        pos2 = cmds.xform(end_obj, query=True, ws=True, translation=True)

        crv = cmds.curve(d=1, p=[pos1, pos2], k=[0, 1], name=line_name)
        shape = cmds.listRelatives(crv, shapes=True)[0]

        cls1 = cmds.cluster(f"{crv}.cv[0]", name=f"{line_name}_cls1")[1]
        cls2 = cmds.cluster(f"{crv}.cv[1]", name=f"{line_name}_cls2")[1]

        cmds.parentConstraint(start_obj, cls1, maintainOffset=False)
        cmds.parentConstraint(end_obj, cls2, maintainOffset=False)

        cmds.setAttr(f"{cls1}.visibility", 0)
        cmds.setAttr(f"{cls2}.visibility", 0)
        cmds.setAttr(f"{shape}.overrideEnabled", 1)
        cmds.setAttr(f"{shape}.overrideDisplayType", 2)
        cmds.setAttr(f"{shape}.overrideColor", 17)

        return cmds.group([crv, cls1, cls2], name=f"{line_name}_GRP")

    def get_keyframe_times(self, obj):
        keyframes = cmds.keyframe(obj, query=True, timeChange=True)
        if not keyframes:
            return []
        return sorted(list(set([int(round(float(k))) for k in keyframes])))

    def create_setup(self, target_ctrl=None):
        sel = target_ctrl or cmds.ls(selection=True, type="transform")
        if not sel:
            cmds.warning("Please select a controller!")
            return False

        self.target_ctrl = sel[0] if isinstance(sel, list) else sel
        self.discard()

        self.setup_grp = cmds.group(em=True, name=f"{self.target_ctrl}_SETUP_GRP")
        cmds.matchTransform(self.setup_grp, self.target_ctrl, pos=True, rot=True)

        self.aim_crv = self._create_cross_curve(f"{self.target_ctrl}_Aim_TARGET", scale=1.2, color_index=13)
        self.up_crv = self._create_circle_curve(f"{self.target_ctrl}_Up_VECTOR", radius=1.0, color_index=14)

        cmds.parent(self.aim_crv, self.setup_grp)
        cmds.parent(self.up_crv, self.setup_grp)
        return True

    def update_preview(self, aim_idx, twist_idx, dist):
        if not self.setup_grp or not cmds.objExists(self.setup_grp):
            return

        aim_name, aim_vec = self.AIM_AXES[aim_idx]
        up_vec = self.get_orthogonal_up(aim_vec, twist_idx)
        up_dist = dist * 0.6

        cmds.setAttr(f"{self.aim_crv}.translate", aim_vec[0] * dist, aim_vec[1] * dist, aim_vec[2] * dist)
        cmds.setAttr(f"{self.up_crv}.translate", up_vec[0] * up_dist, up_vec[1] * up_dist, up_vec[2] * up_dist)

    def apply_aim(self, aim_idx, twist_idx, dist):
        if not self.target_ctrl or not cmds.objExists(self.target_ctrl):
            return False

        ctrl = self.target_ctrl
        aim_vec = self.AIM_AXES[aim_idx][1]
        up_vec = self.get_orthogonal_up(aim_vec, twist_idx)
        up_dist = dist * 0.6

        existing_keys = self.get_keyframe_times(ctrl)
        start_frame, end_frame = self._get_time_range()
        keys_only = self._is_keys_only()

        # If Keys Only mode and keys exist -> sample only keys; else sample full range
        if keys_only and existing_keys:
            frames_to_sample = existing_keys
        else:
            frames_to_sample = list(range(start_frame, end_frame + 1))

        local_aim_offset = om.MPoint(aim_vec[0] * dist, aim_vec[1] * dist, aim_vec[2] * dist)
        local_up_offset = om.MPoint(up_vec[0] * up_dist, up_vec[1] * up_dist, up_vec[2] * up_dist)

        with UndoContext("ApplyTempAim"):
            final_grp = f"{ctrl}_TempAim_GRP"
            if cmds.objExists(final_grp):
                cmds.delete(final_grp)
            final_grp = cmds.group(em=True, name=final_grp)

            if cmds.listRelatives(self.aim_crv, parent=True):
                cmds.parent(self.aim_crv, world=True)
            if cmds.listRelatives(self.up_crv, parent=True):
                cmds.parent(self.up_crv, world=True)

            for frame in frames_to_sample:
                cmds.currentTime(frame)
                matrix_list = cmds.xform(ctrl, query=True, ws=True, matrix=True)
                ctrl_matrix = om.MMatrix(matrix_list)

                world_aim = local_aim_offset * ctrl_matrix
                cmds.setKeyframe(self.aim_crv, time=frame, v=world_aim.x, at="translateX")
                cmds.setKeyframe(self.aim_crv, time=frame, v=world_aim.y, at="translateY")
                cmds.setKeyframe(self.aim_crv, time=frame, v=world_aim.z, at="translateZ")

                world_up = local_up_offset * ctrl_matrix
                cmds.setKeyframe(self.up_crv, time=frame, v=world_up.x, at="translateX")
                cmds.setKeyframe(self.up_crv, time=frame, v=world_up.y, at="translateY")
                cmds.setKeyframe(self.up_crv, time=frame, v=world_up.z, at="translateZ")

            cmds.aimConstraint(
                self.aim_crv, ctrl,
                aimVector=aim_vec, upVector=up_vec,
                worldUpType="object", worldUpObject=self.up_crv,
                mo=False, name=f"{ctrl}_TempAimConstraint"
            )

            origin_loc = cmds.spaceLocator(name=f"{ctrl}_Origin_LOC")[0]
            cmds.setAttr(f"{origin_loc}.visibility", 0)
            cmds.parentConstraint(ctrl, origin_loc, maintainOffset=False)

            line_grp = self._create_connection_line(origin_loc, self.aim_crv, f"{ctrl}_Aim_LINE")

            cmds.parent(self.aim_crv, final_grp)
            cmds.parent(self.up_crv, final_grp)
            cmds.parent(origin_loc, final_grp)
            cmds.parent(line_grp, final_grp)

            if self.setup_grp and cmds.objExists(self.setup_grp):
                cmds.delete(self.setup_grp)

            cmds.select(self.aim_crv)
            cmds.currentTime(start_frame)
            mode_desc = "Keyframes Only" if (keys_only and existing_keys) else "Every Frame"
            cmds.inViewMessage(amg=f"Temp Aim created ({mode_desc}) in folder <hl>{final_grp}</hl>", pos="topCenter", fade=True)
            return True

    def _resolve_ctrl_from_item(self, item):
        if cmds.objExists(f"{item}_TempAim_GRP") or cmds.objExists(f"{item}_TempAimConstraint"):
            return item
        clean = item.replace("_Aim_TARGET", "").replace("_Up_VECTOR", "").replace("_TempAim_GRP", "").replace("_Aim_LINE", "").replace("_Origin_LOC", "").replace("_GRP", "")
        if cmds.objExists(clean) and (cmds.objExists(f"{clean}_TempAim_GRP") or cmds.objExists(f"{clean}_TempAimConstraint")):
            return clean

        constraints = cmds.listConnections(item, type="aimConstraint") or []
        for ac in constraints:
            if "_TempAimConstraint" in ac:
                driven = cmds.aimConstraint(ac, query=True, targetList=False) or []
                if driven:
                    return driven[0]
        return None

    def _bake_single_ctrl(self, ctrl, start_frame, end_frame, keys_only):
        grp_name = f"{ctrl}_TempAim_GRP"
        aim_target = f"{ctrl}_Aim_TARGET"
        target_keys = self.get_keyframe_times(aim_target) if cmds.objExists(aim_target) else []

        # 1. Запікаємо весь діапазон
        cmds.bakeResults(
            ctrl, time=(start_frame, end_frame),
            attribute=["rotateX", "rotateY", "rotateZ"],
            simulation=True, sampleBy=1, disableImplicitControl=True
        )

        # 2. Якщо увімкнено Keys Only — фільтруємо зайві проміжні кадри
        if keys_only and target_keys:
            valid_set = set(target_keys)
            all_baked_keys = self.get_keyframe_times(ctrl)
            for k_frame in all_baked_keys:
                if k_frame not in valid_set and start_frame <= k_frame <= end_frame:
                    cmds.cutKey(ctrl, attribute=["rotateX", "rotateY", "rotateZ"], time=(k_frame, k_frame))

        if cmds.objExists(grp_name):
            cmds.delete(grp_name)
        if cmds.objExists(f"{ctrl}_TempAimConstraint"):
            cmds.delete(f"{ctrl}_TempAimConstraint")

    def bake_selected(self, custom_sel=None):
        sel = custom_sel or cmds.ls(selection=True, type="transform") or []
        if not sel:
            return False

        ctrls_to_bake = set()
        for item in sel:
            resolved = self._resolve_ctrl_from_item(item)
            if resolved:
                ctrls_to_bake.add(resolved)

        if not ctrls_to_bake:
            return False

        start_frame, end_frame = self._get_time_range()
        keys_only = self._is_keys_only()

        with UndoContext("BakeSelectedTempAim"):
            for ctrl in ctrls_to_bake:
                self._bake_single_ctrl(ctrl, start_frame, end_frame, keys_only)

            cmds.select(list(ctrls_to_bake))
            mode_str = "Keyframes Only" if keys_only else "Every Frame"
            cmds.inViewMessage(amg=f"Baked Temp Aim ({mode_str}) for <hl>{len(ctrls_to_bake)}</hl> controller(s).", pos="topCenter", fade=True)
            return True

    def bake_all(self):
        all_aim_grps = cmds.ls("*_TempAim_GRP*", type="transform") or []
        all_aim_consts = cmds.ls("*_TempAimConstraint*", type="aimConstraint") or []

        ctrls_to_bake = set()
        for grp in all_aim_grps:
            ctrl_name = grp.replace("_TempAim_GRP", "")
            if cmds.objExists(ctrl_name):
                ctrls_to_bake.add(ctrl_name)

        for ac in all_aim_consts:
            clean = ac.replace("_TempAimConstraint", "")
            if cmds.objExists(clean):
                ctrls_to_bake.add(clean)

        if not ctrls_to_bake:
            return False

        start_frame, end_frame = self._get_time_range()
        keys_only = self._is_keys_only()

        with UndoContext("BakeAllTempAim"):
            for ctrl in ctrls_to_bake:
                self._bake_single_ctrl(ctrl, start_frame, end_frame, keys_only)

            leftovers = cmds.ls("*_TempAim_GRP*", "*_Aim_TARGET*", "*_Up_VECTOR*", "*_Origin_LOC*", "*_Aim_LINE*", type="transform") or []
            if leftovers:
                cmds.delete(leftovers)

        mode_str = "Keyframes Only" if keys_only else "Every Frame"
        cmds.inViewMessage(amg=f"Baked All Temp Aim ({mode_str}) for <hl>{len(ctrls_to_bake)}</hl> controller(s).", pos="topCenter", fade=True)
        return True

    def discard(self):
        if self.setup_grp and cmds.objExists(self.setup_grp):
            cmds.delete(self.setup_grp)
        ctrl = self.target_ctrl
        if ctrl:
            grp = f"{ctrl}_TempAim_GRP"
            if cmds.objExists(grp):
                cmds.delete(grp)