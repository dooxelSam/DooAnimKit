"""
Multi-Limb Temp IK Engine for DooAnimKit.
Supports multiple simultaneous limbs (Arms + Legs), Clavicle/Hips base tracking,
and 1-Click Instant FK <-> IK Match-Switching.
"""

import maya.cmds as cmds

try:
    from DooAnimKit.core.context import UndoContext
except ImportError:
    class UndoContext:
        def __init__(self, name="UndoChunk"):
            self.name = name
        def __enter__(self):
            cmds.undoInfo(openChunk=True, chunkName=self.name)
        def __exit__(self, exc_type, exc_val, exc_tb):
            cmds.undoInfo(closeChunk=True)


class TempIKEngine:

    LIMB_TAG_CHAINS = {
        "LeftLeg": ["LeftUpLeg", "LeftKnee", "LeftFoot"],
        "RightLeg": ["RightUpLeg", "RightKnee", "RightFoot"],
        "LeftArm": ["LeftShoulder", "LeftElbow", "LeftWrist"],
        "RightArm": ["RightShoulder", "RightElbow", "RightWrist"]
    }

    TEMP_MASTER_GRP = "DooAnim_TempIK_GRP"

    def __init__(self):
        pass

    def _resolve_nodes(self, limb_name, pins):
        """Resolves root, mid, and tip FK controls and skeleton joints."""
        side = "Left" if limb_name.startswith("Left") else "Right"
        limb_type = "Leg" if "Leg" in limb_name else "Arm"

        if limb_type == "Leg":
            ctrls = [f"CTRL_{side}UpLeg", f"CTRL_{side}Knee", f"CTRL_{side}Foot"]
            jnts = [f"JNT_{side}UpLeg", f"JNT_{side}Knee", f"JNT_{side}Foot"]
        else:
            ctrls = [f"CTRL_{side}Shoulder", f"CTRL_{side}Elbow", f"CTRL_{side}Wrist"]
            jnts = [f"JNT_{side}Shoulder", f"JNT_{side}Elbow", f"JNT_{side}Wrist"]

        if all(cmds.objExists(c) for c in ctrls) and all(cmds.objExists(j) for j in jnts):
            return ctrls, jnts

        target_tags = self.LIMB_TAG_CHAINS.get(limb_name, [])
        tag_to_ctrl = {}
        for p in pins:
            tag = p.get("hik_tag", "")
            for t_tag in target_tags:
                if t_tag in tag:
                    tag_to_ctrl[t_tag] = p.get("name")

        resolved_ctrls = [tag_to_ctrl.get(t) for t in target_tags]
        if all(resolved_ctrls) and all(cmds.objExists(c) for c in resolved_ctrls):
            resolved_jnts = [c.replace("CTRL_", "JNT_") if cmds.objExists(c.replace("CTRL_", "JNT_")) else c for c in resolved_ctrls]
            return resolved_ctrls, resolved_jnts

        return None, None

    def is_temp_ik_active(self, limb_name):
        return bool(cmds.objExists(f"TEMP_CTRL_IK_{limb_name}"))

    def create_temp_ik(self, limb_name, pins=[]):
        """Builds independent Temp IK setup connected to Clavicle/Hips base."""
        ctrls, jnts = self._resolve_nodes(limb_name, pins)
        if not ctrls or not jnts:
            cmds.warning(f"Temp IK: Could not resolve controls for {limb_name}!")
            return None

        root_ctrl, mid_ctrl, tip_ctrl = ctrls
        root_jnt, mid_jnt, tip_jnt = jnts

        # Очищаємо лише цей конкретний limb перед створенням
        self.remove_temp_ik(limb_name)

        if not cmds.objExists(self.TEMP_MASTER_GRP):
            cmds.group(empty=True, name=self.TEMP_MASTER_GRP)

        limb_grp = f"TEMP_GRP_{limb_name}"
        if not cmds.objExists(limb_grp):
            limb_grp = cmds.group(empty=True, name=limb_grp, parent=self.TEMP_MASTER_GRP)

        with UndoContext(f"CreateTempIK_{limb_name}"):
            # 1. Вимикаємо FK parent-констрейнти тільки для суглобів цієї кінцівки
            for tag in self.LIMB_TAG_CHAINS.get(limb_name, []):
                fk_const = f"CONST_FK_{tag}"
                if cmds.objExists(fk_const):
                    aliases = cmds.parentConstraint(fk_const, query=True, weightAliasList=True) or []
                    for a in aliases:
                        cmds.setAttr(f"{fk_const}.{a}", 0.0)

            # 2. Отримуємо світові позиції суглобів
            root_pos = cmds.xform(root_jnt, query=True, worldSpace=True, translation=True)
            mid_pos = cmds.xform(mid_jnt, query=True, worldSpace=True, translation=True)
            tip_pos = cmds.xform(tip_jnt, query=True, worldSpace=True, translation=True)

            # 3. Створюємо ізольований ланцюжок джойнтів
            cmds.select(clear=True)
            t_root = cmds.joint(name=f"TEMP_JNT_{limb_name}_01", position=root_pos)
            
            bend_offset = 0.15 if "Leg" in limb_name else -0.15
            t_mid = cmds.joint(name=f"TEMP_JNT_{limb_name}_02", position=[mid_pos[0], mid_pos[1], mid_pos[2] + bend_offset])
            t_tip = cmds.joint(name=f"TEMP_JNT_{limb_name}_03", position=tip_pos)

            cmds.parent(t_root, limb_grp)

            cmds.joint(t_root, edit=True, oj="xyz", sao="yup", zso=True)
            cmds.joint(t_mid, edit=True, oj="xyz", sao="yup", zso=True)
            cmds.joint(t_tip, edit=True, oj="none", zso=True)
            cmds.joint(t_mid, edit=True, setPreferredAngles=True)

            # 4. Point Constraint до бази (плече слідує за ключицею, стегно за тазом)
            cmds.pointConstraint(root_jnt, t_root, maintainOffset=False, name=f"TEMP_CONST_{limb_name}_BaseFollow")

            # 5. IK Handle
            ik_hdl, _ = cmds.ikHandle(
                name=f"TEMP_IK_HDL_{limb_name}",
                startJoint=t_root,
                endEffector=t_tip,
                solver="ikRPsolver"
            )
            cmds.parent(ik_hdl, limb_grp)

            # 6. Master IK Box Control
            col = 6 if "Left" in limb_name else 13
            ctrl_ik = cmds.curve(
                name=f"TEMP_CTRL_IK_{limb_name}",
                degree=1,
                point=[
                    [-2.5, 0, -2.5], [2.5, 0, -2.5], [2.5, 0, 2.5], [-2.5, 0, 2.5], [-2.5, 0, -2.5],
                    [-2.5, 2.5, -2.5], [2.5, 2.5, -2.5], [2.5, 0, -2.5],
                    [2.5, 2.5, -2.5], [2.5, 2.5, 2.5], [2.5, 0, 2.5],
                    [2.5, 2.5, 2.5], [-2.5, 2.5, 2.5], [-2.5, 0, 2.5],
                    [-2.5, 2.5, 2.5], [-2.5, 2.5, -2.5]
                ]
            )
            c_shape = cmds.listRelatives(ctrl_ik, shapes=True)[0]
            cmds.setAttr(f"{c_shape}.overrideEnabled", 1)
            cmds.setAttr(f"{c_shape}.overrideColor", col)

            cmds.matchTransform(ctrl_ik, tip_ctrl, pos=True, rot=True)
            cmds.parent(ctrl_ik, limb_grp)
            cmds.parentConstraint(ctrl_ik, ik_hdl, maintainOffset=True)

            # 7. Pole Vector Control
            ctrl_pv = cmds.curve(
                name=f"TEMP_CTRL_PV_{limb_name}",
                degree=1,
                point=[[0, 1.6, 0], [1.6, 0, 0], [0, -1.6, 0], [-1.6, 0, 0], [0, 1.6, 0], [0, 0, 1.6], [0, -1.6, 0], [0, 0, -1.6], [0, 1.6, 0]]
            )
            pv_shape = cmds.listRelatives(ctrl_pv, shapes=True)[0]
            cmds.setAttr(f"{pv_shape}.overrideEnabled", 1)
            cmds.setAttr(f"{pv_shape}.overrideColor", col)

            pv_dist = 30.0 if "Leg" in limb_name else -30.0
            cmds.xform(ctrl_pv, worldSpace=True, translation=[mid_pos[0], mid_pos[1], mid_pos[2] + pv_dist])
            cmds.parent(ctrl_pv, limb_grp)
            cmds.poleVectorConstraint(ctrl_pv, ik_hdl)

            # 8. Зв'язуємо обертання та позицію
            cmds.orientConstraint(t_root, root_ctrl, maintainOffset=True, name=f"TEMP_CONST_{limb_name}_RootRot")
            cmds.orientConstraint(t_mid, mid_ctrl, maintainOffset=True, name=f"TEMP_CONST_{limb_name}_MidRot")
            cmds.orientConstraint(ctrl_ik, tip_ctrl, maintainOffset=True, name=f"TEMP_CONST_{limb_name}_TipRot")

            cmds.parentConstraint(t_root, root_jnt, maintainOffset=True, name=f"TEMP_CONST_{limb_name}_RootJnt")
            cmds.parentConstraint(t_mid, mid_jnt, maintainOffset=True, name=f"TEMP_CONST_{limb_name}_MidJnt")
            cmds.parentConstraint(ctrl_ik, tip_jnt, maintainOffset=True, name=f"TEMP_CONST_{limb_name}_TipJnt")

        cmds.select(ctrl_ik)
        cmds.inViewMessage(amg=f"Temp IK: <hl>{limb_name} IK активовано!</hl>", pos="topCenter", fade=True)

        return {
            "ik_ctrl": ctrl_ik,
            "pv_ctrl": ctrl_pv,
            "limb": limb_name
        }

    def switch_to_fk_and_bake_pose(self, limb_name, pins=[]):
        """Matches FK controls to the current Temp IK pose, sets keys, and removes Temp IK."""
        ctrls, _ = self._resolve_nodes(limb_name, pins)
        if not ctrls:
            self.remove_temp_ik(limb_name)
            return

        with UndoContext(f"SwitchToFK_{limb_name}"):
            # Зчитуємо поточні трансформації, досягнуті через IK
            for c in ctrls:
                rot = cmds.xform(c, query=True, rotation=True)
                cmds.setKeyframe(c, attribute="rotate", value=rot[0], at="rotateX")
                cmds.setKeyframe(c, attribute="rotate", value=rot[1], at="rotateY")
                cmds.setKeyframe(c, attribute="rotate", value=rot[2], at="rotateZ")

            self.remove_temp_ik(limb_name)

        cmds.select(ctrls)
        cmds.inViewMessage(amg=f"Temp IK: <hl>{limb_name} перемкнено у FK (позу збережено)!</hl>", pos="topCenter", fade=True)

    def bake_and_delete_temp_ik(self, limb_name, pins=[]):
        """Bakes full time-range animation from Temp IK back to FK controls."""
        ctrls, _ = self._resolve_nodes(limb_name, pins)
        if not ctrls:
            self.remove_temp_ik(limb_name)
            return

        start_time = cmds.playbackOptions(query=True, minTime=True)
        end_time = cmds.playbackOptions(query=True, maxTime=True)

        with UndoContext(f"BakeTempIK_{limb_name}"):
            cmds.bakeResults(
                ctrls,
                time=(start_time, end_time),
                simulation=True,
                sampleBy=1,
                disableImplicitControl=True,
                preserveExternalKeys=True,
                sparseAnimCurveBake=False,
                removeBakedAttributeFromLayer=False,
                bakeOnOverrideLayer=False,
                minimizeRotation=True,
                controlPoints=False,
                shape=True
            )
            self.remove_temp_ik(limb_name)

        cmds.select(ctrls)
        cmds.inViewMessage(amg=f"Temp IK: <hl>{limb_name} запечено у FK на таймлайні!</hl>", pos="topCenter", fade=True)

    def remove_temp_ik(self, limb_name):
        """Safely removes the specific limb's Temp IK group and restores native FK constraints."""
        limb_grp = f"TEMP_GRP_{limb_name}"
        if cmds.objExists(limb_grp):
            try:
                cmds.delete(limb_grp)
            except Exception:
                pass

        # Відновлюємо ваги рідних FK констрейнтів для цієї кінцівки
        for tag in self.LIMB_TAG_CHAINS.get(limb_name, []):
            fk_const = f"CONST_FK_{tag}"
            if cmds.objExists(fk_const):
                aliases = cmds.parentConstraint(fk_const, query=True, weightAliasList=True) or []
                for a in aliases:
                    cmds.setAttr(f"{fk_const}.{a}", 1.0)

        if cmds.objExists(self.TEMP_MASTER_GRP):
            children = cmds.listRelatives(self.TEMP_MASTER_GRP, children=True) or []
            if not children:
                try:
                    cmds.delete(self.TEMP_MASTER_GRP)
                except Exception:
                    pass