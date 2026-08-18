import maya.cmds as cmds
import maya.api.OpenMaya as om
from DooAnimKit.core.context import UndoContext


class TempAimEngine:
    """Zero-Offset Temp Aim with Cross/Circle shapes and connection line."""

    AIM_AXES = [
        ("+X", (1, 0, 0)),
        ("-X", (-1, 0, 0)),
        ("+Y", (0, 1, 0)),
        ("-Y", (0, -1, 0)),
        ("+Z", (0, 0, 1)),
        ("-Z", (0, 0, -1)),
    ]

    def __init__(self):
        self.target_ctrl = None
        self.setup_grp = None
        self.aim_crv = None
        self.up_crv = None

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
        return sorted(list(set([int(k) for k in keyframes]))) if keyframes else []

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
        start_frame = int(cmds.playbackOptions(query=True, minTime=True))

        local_aim_offset = om.MPoint(aim_vec[0] * dist, aim_vec[1] * dist, aim_vec[2] * dist)
        local_up_offset = om.MPoint(up_vec[0] * up_dist, up_vec[1] * up_dist, up_vec[2] * up_dist)

        with UndoContext("ApplyTempAim"):
            if cmds.listRelatives(self.aim_crv, parent=True):
                cmds.parent(self.aim_crv, world=True)
            if cmds.listRelatives(self.up_crv, parent=True):
                cmds.parent(self.up_crv, world=True)

            if existing_keys:
                for frame in existing_keys:
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
            cmds.group([self.aim_crv, self.up_crv, origin_loc, line_grp], name=f"{ctrl}_TempAim_GRP")

            if self.setup_grp and cmds.objExists(self.setup_grp):
                cmds.delete(self.setup_grp)

            cmds.select(self.aim_crv)
            cmds.currentTime(start_frame)
            cmds.inViewMessage(amg=f"Temp Aim created for <hl>{ctrl}</hl>", pos="topCenter", fade=True)
            return True

    def bake_and_clean(self):
        ctrl = self.target_ctrl
        if not ctrl:
            sel = cmds.ls(selection=True, type="transform")
            if sel:
                ctrl = sel[0].replace("_Aim_TARGET", "").replace("_Up_VECTOR", "").replace("_TempAim_GRP", "").replace("_Aim_LINE", "").replace("_GRP", "").replace("_Origin_LOC", "")

        if not ctrl or not cmds.objExists(ctrl):
            return False

        grp_name = f"{ctrl}_TempAim_GRP"
        aim_target = f"{ctrl}_Aim_TARGET"

        with UndoContext("BakeTempAim"):
            if cmds.objExists(grp_name) or cmds.objExists(aim_target):
                target_keys = self.get_keyframe_times(aim_target)
                start_frame = int(cmds.playbackOptions(query=True, minTime=True))
                end_frame = int(cmds.playbackOptions(query=True, maxTime=True))

                cmds.bakeResults(
                    ctrl, time=(start_frame, end_frame),
                    attribute=["rotateX", "rotateY", "rotateZ"],
                    simulation=True, disableImplicitControl=True
                )

                if target_keys:
                    for frame in range(start_frame, end_frame + 1):
                        if frame not in target_keys:
                            cmds.cutKey(ctrl, attribute=["rotateX", "rotateY", "rotateZ"], time=(frame, frame))

                if cmds.objExists(grp_name):
                    cmds.delete(grp_name)

                if cmds.objExists(ctrl):
                    cmds.select(ctrl)
                cmds.inViewMessage(amg=f"Temp Aim baked on <hl>{ctrl}</hl>", pos="topCenter", fade=True)
                return True
        return False

    def discard(self):
        if self.setup_grp and cmds.objExists(self.setup_grp):
            cmds.delete(self.setup_grp)
        ctrl = self.target_ctrl
        if ctrl:
            grp = f"{ctrl}_TempAim_GRP"
            if cmds.objExists(grp):
                cmds.delete(grp)