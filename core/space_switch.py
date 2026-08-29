"""
Dynamic Space Switching Engine for DooAnimKit.
Seamlessly attaches controllers to World, Hips, Chest, or Custom Object spaces.
"""

import maya.cmds as cmds
from DooAnimKit.core.context import UndoContext


class SpaceSwitchEngine:
    SPACE_LOC_SUFFIX = "_SpaceSwitch_LOC"

    def __init__(self):
        pass

    def _get_time_range(self):
        start = int(cmds.playbackOptions(query=True, minTime=True))
        end = int(cmds.playbackOptions(query=True, maxTime=True))
        return start, end

    def switch_to_world(self):
        return self.create_space_switch(parent_target=None, label="World")

    def switch_to_custom(self, parent_target):
        if not cmds.objExists(parent_target):
            cmds.warning(f"Target object '{parent_target}' does not exist in the scene!")
            return False
        return self.create_space_switch(parent_target=parent_target, label=parent_target)

    def create_space_switch(self, parent_target=None, label="World"):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select a controller to switch space!")
            return False

        start, end = self._get_time_range()

        with UndoContext(f"SpaceSwitch_{label}"):
            for node in sel:
                loc_name = f"{node}{self.SPACE_LOC_SUFFIX}"
                if cmds.objExists(loc_name):
                    cmds.delete(loc_name)

                loc = cmds.spaceLocator(name=loc_name)[0]
                for attr in ["localScaleX", "localScaleY", "localScaleZ"]:
                    cmds.setAttr(f"{loc}.{attr}", 3)

                for s in cmds.listRelatives(loc, shapes=True) or []:
                    cmds.setAttr(f"{s}.overrideEnabled", 1)
                    cmds.setAttr(f"{s}.overrideColor", 13)

                # 1. Позиціонуємо локатор і запікаємо його рух у світі
                temp_const = cmds.parentConstraint(node, loc, maintainOffset=False)
                cmds.bakeResults(
                    loc, time=(start, end), simulation=True,
                    sampleBy=1, disableImplicitControl=True
                )
                cmds.delete(temp_const)

                # 2. Якщо задано ціль (наприклад, Hips/Chest) — робимо parent локатора
                if parent_target and cmds.objExists(parent_target):
                    cmds.parent(loc, parent_target)

                # 3. Видаляємо старі активні констрейнти з контролера та прив'язуємо до нового локатора
                old_consts = cmds.listConnections(f"{node}.translateX", type="parentConstraint") or []
                if old_consts:
                    cmds.delete(old_consts)

                cmds.parentConstraint(loc, node, maintainOffset=True)

        cmds.inViewMessage(amg=f"Controller <hl>{sel[0]}</hl> switched to <hl>{label} Space</hl>!", pos="topCenter", fade=True)
        return True

    def bake_and_restore(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            sel = cmds.ls(f"*{self.SPACE_LOC_SUFFIX}*", type="transform") or []

        if not sel:
            cmds.warning("No Space Switch setups found in selection or scene!")
            return False

        start, end = self._get_time_range()
        targets_to_bake = set()
        locs_to_delete = set()

        with UndoContext("BakeSpaceSwitch"):
            for item in sel:
                if self.SPACE_LOC_SUFFIX in item:
                    orig_ctrl = item.replace(self.SPACE_LOC_SUFFIX, "")
                    if cmds.objExists(orig_ctrl):
                        targets_to_bake.add(orig_ctrl)
                    locs_to_delete.add(item)
                else:
                    loc_name = f"{item}{self.SPACE_LOC_SUFFIX}"
                    if cmds.objExists(loc_name):
                        targets_to_bake.add(item)
                        locs_to_delete.add(loc_name)

            if targets_to_bake:
                bake_list = list(targets_to_bake)
                cmds.bakeResults(
                    bake_list, time=(start, end), simulation=True,
                    sampleBy=1, disableImplicitControl=True
                )

            for loc in locs_to_delete:
                if cmds.objExists(loc):
                    cmds.delete(loc)

        cmds.inViewMessage(amg=f"Space Switch baked & restored on <hl>{len(targets_to_bake)}</hl> controller(s).", pos="topCenter", fade=True)
        return True