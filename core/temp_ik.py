"""
Temp IK Manager for DooAnimKit.
Creates temporary 2-Bone IK setups over 3-element FK hierarchies (arms, legs, fingers)
for floor/surface pinning and contact animation.
"""

import maya.cmds as cmds
import maya.api.OpenMaya as om
from DooAnimKit.core.context import UndoContext
from DooAnimKit.core.temp_control import TempControlManager


class TempIKManager:
    def __init__(self, main_window=None):
        self.win = main_window
        self.active_ik_setups = {}

    def _get_time_range(self):
        start = int(cmds.playbackOptions(query=True, minTime=True))
        end = int(cmds.playbackOptions(query=True, maxTime=True))
        return start, end

    def _calculate_pv_position(self, pos_root, pos_mid, pos_end, distance=15.0):
        """Calculates Pole Vector locator position projected from triangle normal."""
        v_root = om.MVector(*pos_root)
        v_mid = om.MVector(*pos_mid)
        v_end = om.MVector(*pos_end)

        line_vec = v_end - v_root
        mid_vec = v_mid - v_root

        if line_vec.length() < 1e-4:
            return [pos_mid[0], pos_mid[1], pos_mid[2] + distance]

        proj = line_vec.normal() * (mid_vec * line_vec.normal())
        arrow = mid_vec - proj

        if arrow.length() < 1e-4:
            arrow = om.MVector(0, 0, 1)

        pv_pos = v_mid + (arrow.normal() * distance)
        return [pv_pos.x, pv_pos.y, pv_pos.z]

    def create_temp_ik(self):
        """Creates Temp IK on 3 selected hierarchical FK controllers (Root -> Mid -> End)."""
        sel = cmds.ls(selection=True, type="transform") or []
        if len(sel) < 3:
            cmds.warning("Please select 3 FK controllers in order: Root -> Mid -> End (e.g. Shoulder, Elbow, Wrist)!")
            return False

        ctrl_root, ctrl_mid, ctrl_end = sel[0], sel[1], sel[2]
        base_name = ctrl_end.replace("_CTRL", "").replace("_ctrl", "").replace("_CTL", "")
        start_frame, end_frame = self._get_time_range()
        keys_only = TempControlManager.BAKE_KEYS_ONLY

        source_keys = set()
        for c in (ctrl_root, ctrl_mid, ctrl_end):
            k = cmds.keyframe(c, query=True, timeChange=True) or []
            source_keys.update([int(round(float(t))) for t in k])
        valid_frames = sorted(list(source_keys)) if (keys_only and source_keys) else list(range(start_frame, end_frame + 1))

        with UndoContext("CreateTempIK"):
            p_root = cmds.xform(ctrl_root, query=True, ws=True, translation=True)
            p_mid = cmds.xform(ctrl_mid, query=True, ws=True, translation=True)
            p_end = cmds.xform(ctrl_end, query=True, ws=True, translation=True)

            # 1. Створюємо тимчасовий ланцюг суглобів
            cmds.select(clear=True)
            j_root = cmds.joint(name=f"{base_name}_TempIK_JntRoot", p=p_root)
            j_mid = cmds.joint(name=f"{base_name}_TempIK_JntMid", p=p_mid)
            j_end = cmds.joint(name=f"{base_name}_TempIK_JntEnd", p=p_end)
            cmds.joint(j_root, edit=True, oj="xyz", secondaryAxisOrient="yup", ch=True, zso=True)

            # 2. Створюємо IK Handle
            ik_handle, _ = cmds.ikHandle(
                name=f"{base_name}_TempIK_Handle",
                startJoint=j_root, endEffector=j_end,
                solver="ikRPsolver"
            )

            # 3. Створюємо контролери (IK Master & Pole Vector)
            ik_ctrl = cmds.spaceLocator(name=f"{base_name}_TempIK_CTRL")[0]
            for attr in ['localScaleX', 'localScaleY', 'localScaleZ']:
                cmds.setAttr(f"{ik_ctrl}.{attr}", 3.5)
            for s in cmds.listRelatives(ik_ctrl, shapes=True) or []:
                cmds.setAttr(f"{s}.overrideEnabled", 1)
                cmds.setAttr(f"{s}.overrideColor", 13)  # Cyan
            cmds.matchTransform(ik_ctrl, ctrl_end, pos=True, rot=True)

            pv_pos = self._calculate_pv_position(p_root, p_mid, p_end, distance=15.0)
            pv_ctrl = cmds.spaceLocator(name=f"{base_name}_TempIK_PV")[0]
            for attr in ['localScaleX', 'localScaleY', 'localScaleZ']:
                cmds.setAttr(f"{pv_ctrl}.{attr}", 2.0)
            for s in cmds.listRelatives(pv_ctrl, shapes=True) or []:
                cmds.setAttr(f"{s}.overrideEnabled", 1)
                cmds.setAttr(f"{s}.overrideColor", 14)  # Green
            cmds.xform(pv_ctrl, ws=True, translation=pv_pos)

            # 4. Зв'язуємо IK Handle та PV
            cmds.poleVectorConstraint(pv_ctrl, ik_handle)
            cmds.parentConstraint(ik_ctrl, ik_handle, maintainOffset=True)
            cmds.orientConstraint(ik_ctrl, j_end, maintainOffset=True)

            # 5. Запікаємо траєкторію кінцівки в IK контролери
            temp_const = cmds.parentConstraint(ctrl_end, ik_ctrl, maintainOffset=False)
            cmds.bakeResults(
                [ik_ctrl, pv_ctrl], time=(start_frame, end_frame),
                simulation=True, sampleBy=1, disableImplicitControl=True
            )
            cmds.delete(temp_const)

            if keys_only and valid_frames:
                valid_set = set(valid_frames)
                for node in (ik_ctrl, pv_ctrl):
                    all_k = cmds.keyframe(node, query=True, timeChange=True) or []
                    for f in all_k:
                        f_int = int(round(float(f)))
                        if f_int not in valid_set and start_frame <= f_int <= end_frame:
                            cmds.cutKey(node, time=(f_int, f_int))

            # 6. Констрейнимо FK контролери до IK суглобів
            c_root = cmds.parentConstraint(j_root, ctrl_root, maintainOffset=True)[0]
            c_mid = cmds.parentConstraint(j_mid, ctrl_mid, maintainOffset=True)[0]
            c_end = cmds.parentConstraint(j_end, ctrl_end, maintainOffset=True)[0]

            # 7. Пакуємо все в одну акуратну групу
            ik_grp = cmds.group([j_root, ik_handle, ik_ctrl, pv_ctrl], name=f"{base_name}_TempIK_GRP")
            cmds.setAttr(f"{j_root}.visibility", 0)
            cmds.setAttr(f"{ik_handle}.visibility", 0)

            self.active_ik_setups[ik_ctrl] = {
                'fk_chain': [ctrl_root, ctrl_mid, ctrl_end],
                'grp': ik_grp,
                'pv': pv_ctrl,
                'constraints': [c_root, c_mid, c_end]
            }

            cmds.select(ik_ctrl)
            cmds.currentTime(start_frame)
            cmds.inViewMessage(
                amg=f"Temp IK created for <hl>{ctrl_end}</hl> (Pin & Animate now)!",
                pos="topCenter", fade=True
            )
            return True

    def bake_selected(self, custom_sel=None):
        """Bakes IK animation back into the FK controllers for selected Temp IK."""
        sel = custom_sel or cmds.ls(selection=True, type="transform") or []
        if not sel:
            return False

        setups_to_bake = []
        for item in sel:
            for ik_ctrl, data in list(self.active_ik_setups.items()):
                if item in (ik_ctrl, data['pv'], data['grp']) or item in data['fk_chain'] or f"{item}_TempIK_CTRL" == ik_ctrl:
                    if (ik_ctrl, data) not in setups_to_bake:
                        setups_to_bake.append((ik_ctrl, data))

        if not setups_to_bake:
            return False

        start_frame, end_frame = self._get_time_range()
        keys_only = TempControlManager.BAKE_KEYS_ONLY

        with UndoContext("BakeSelectedTempIK"):
            for ik_ctrl, data in setups_to_bake:
                fk_chain = data['fk_chain']
                ik_keys = cmds.keyframe(ik_ctrl, query=True, timeChange=True) or []
                valid_set = set([int(round(float(k))) for k in ik_keys])

                cmds.bakeResults(
                    fk_chain, time=(start_frame, end_frame),
                    attribute=["rotateX", "rotateY", "rotateZ"],
                    simulation=True, sampleBy=1, disableImplicitControl=True
                )

                if keys_only and valid_set:
                    for fk in fk_chain:
                        all_k = cmds.keyframe(fk, query=True, timeChange=True) or []
                        for f in all_k:
                            f_int = int(round(float(f)))
                            if f_int not in valid_set and start_frame <= f_int <= end_frame:
                                cmds.cutKey(fk, attribute=["rotateX", "rotateY", "rotateZ"], time=(f_int, f_int))

                if cmds.objExists(data['grp']):
                    cmds.delete(data['grp'])

                if ik_ctrl in self.active_ik_setups:
                    del self.active_ik_setups[ik_ctrl]

            cmds.select(fk_chain)
            mode_str = "Keyframes Only" if keys_only else "Every Frame"
            cmds.inViewMessage(amg=f"Temp IK baked back to FK ({mode_str}) & scene cleaned.", pos="topCenter", fade=True)
            return True

    def bake_all(self):
        """Bakes all active Temp IK setups in the scene back to FK."""
        all_setups = list(self.active_ik_setups.items())
        start_frame, end_frame = self._get_time_range()
        keys_only = TempControlManager.BAKE_KEYS_ONLY

        with UndoContext("BakeAllTempIK"):
            for ik_ctrl, data in all_setups:
                fk_chain = data['fk_chain']
                ik_keys = cmds.keyframe(ik_ctrl, query=True, timeChange=True) or []
                valid_set = set([int(round(float(k))) for k in ik_keys])

                cmds.bakeResults(
                    fk_chain, time=(start_frame, end_frame),
                    attribute=["rotateX", "rotateY", "rotateZ"],
                    simulation=True, sampleBy=1, disableImplicitControl=True
                )

                if keys_only and valid_set:
                    for fk in fk_chain:
                        all_k = cmds.keyframe(fk, query=True, timeChange=True) or []
                        for f in all_k:
                            f_int = int(round(float(f)))
                            if f_int not in valid_set and start_frame <= f_int <= end_frame:
                                cmds.cutKey(fk, attribute=["rotateX", "rotateY", "rotateZ"], time=(f_int, f_int))

                if cmds.objExists(data['grp']):
                    cmds.delete(data['grp'])

            self.active_ik_setups.clear()
            leftovers = cmds.ls("*_TempIK_GRP*", "*_TempIK_Jnt*", "*_TempIK_Handle*", type="transform") or []
            if leftovers:
                cmds.delete(leftovers)

        return True