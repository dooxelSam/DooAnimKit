import maya.cmds as cmds
import maya.mel as mel
from DooAnimKit.core.context import UndoContext


class TempControlManager:
    """Universal manager for Temp Controls, Live Timeline Offset, and Clean Pivot Reparenting."""

    BOOKMARK_NAME = "AnimKit_Offset_Bookmark"
    BAKE_KEYS_ONLY = True

    def __init__(self, main_window=None):
        self.win = main_window
        self.session_data = {}        # {active_temp_loc: [target_ctrls]}
        self.base_curves_cache = {}   # {node: {attr: {frame: val}}}
        self.script_jobs = []
        self.attr_jobs = []
        self.offset_active = False
        self._is_updating = False

    @property
    def bake_keys_only(self):
        return TempControlManager.BAKE_KEYS_ONLY

    def toggle_bake_mode(self):
        TempControlManager.BAKE_KEYS_ONLY = not TempControlManager.BAKE_KEYS_ONLY
        mode_str = "Keyframes Only" if TempControlManager.BAKE_KEYS_ONLY else "Every Frame"
        cmds.inViewMessage(amg=f"Sampling Mode: <hl>{mode_str}</hl>", pos="topCenter", fade=True)
        if self.win:
            self.win.sync_ui_state()
        return TempControlManager.BAKE_KEYS_ONLY

    def _get_time_range(self):
        start_frame = int(cmds.playbackOptions(query=True, minTime=True))
        end_frame = int(cmds.playbackOptions(query=True, maxTime=True))
        return start_frame, end_frame

    def _create_wireframe_box(self, bounds, name="Group_Temp_CTRL"):
        xmin, ymin, zmin, xmax, ymax, zmax = bounds
        dx = (xmax - xmin) * 0.15 or 1.0
        dy = (ymax - ymin) * 0.15 or 1.0
        dz = (zmax - zmin) * 0.15 or 1.0

        xmin -= dx; xmax += dx
        ymin -= dy; ymax += dy
        zmin -= dz; zmax += dz

        points = [
            [xmin, ymin, zmin], [xmax, ymin, zmin], [xmax, ymax, zmin], [xmin, ymax, zmin],
            [xmin, ymin, zmin], [xmin, ymin, zmax], [xmax, ymin, zmax], [xmax, ymax, zmax],
            [xmin, ymax, zmax], [xmin, ymin, zmax], [xmax, ymin, zmax], [xmax, ymin, zmin],
            [xmax, ymax, zmin], [xmax, ymax, zmax], [xmin, ymax, zmax], [xmin, ymin, zmin]
        ]
        curve = cmds.curve(degree=1, point=points, knot=list(range(len(points))), name=name)
        cmds.xform(curve, centerPivots=True)

        for s in cmds.listRelatives(curve, shapes=True) or []:
            cmds.setAttr(f"{s}.overrideEnabled", 1)
            cmds.setAttr(f"{s}.overrideColor", 17)
        return curve

    def _get_target_nodes(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if sel:
            return sel
        return [node for node in self.session_data.keys() if cmds.objExists(node)]

    def _cache_temp_curves(self, nodes=None):
        self.base_curves_cache.clear()
        target_nodes = nodes or self._get_target_nodes()
        attrs = ['translateX', 'translateY', 'translateZ', 'rotateX', 'rotateY', 'rotateZ']
        start_frame, end_frame = self._get_time_range()

        for node in target_nodes:
            if not cmds.objExists(node):
                continue
            self.base_curves_cache[node] = {}
            for attr in attrs:
                full_attr = f"{node}.{attr}"
                if cmds.attributeQuery(attr, node=node, exists=True):
                    times = cmds.keyframe(full_attr, query=True, time=(start_frame, end_frame), timeChange=True) or []
                    vals = cmds.keyframe(full_attr, query=True, time=(start_frame, end_frame), valueChange=True) or []
                    if times:
                        self.base_curves_cache[node][attr] = dict(zip(times, vals))

    def set_offset_mode(self, active=True):
        self.offset_active = active
        if cmds.objExists(self.BOOKMARK_NAME):
            cmds.delete(self.BOOKMARK_NAME)

        if active:
            start_frame, end_frame = self._get_time_range()
            try:
                cmds.timeSliderBookmark(
                    name=self.BOOKMARK_NAME,
                    start=start_frame,
                    stop=end_frame,
                    color=[0.9, 0.35, 0.1],
                    annotation="OFFSET MODE ACTIVE"
                )
            except Exception:
                pass
            self.register_script_jobs()
            self._on_selection_or_time_changed()
            cmds.inViewMessage(amg="<hl>TIMELINE OFFSET: ON</hl>", pos="topCenter", fade=True)
        else:
            self.kill_script_jobs()
            self.base_curves_cache.clear()
            cmds.inViewMessage(amg="TIMELINE OFFSET: OFF", pos="topCenter", fade=True)

    def toggle_offset_mode(self):
        new_state = not self.offset_active
        self.set_offset_mode(new_state)
        return new_state

    def kill_script_jobs(self):
        for job_id in self.script_jobs + self.attr_jobs:
            if cmds.scriptJob(exists=job_id):
                cmds.scriptJob(kill=job_id, force=True)
        self.script_jobs.clear()
        self.attr_jobs.clear()

    def kill_attr_jobs(self):
        for job_id in self.attr_jobs:
            if cmds.scriptJob(exists=job_id):
                cmds.scriptJob(kill=job_id, force=True)
        self.attr_jobs.clear()

    def register_script_jobs(self):
        self.kill_script_jobs()
        if not self.offset_active:
            return
        sel_job = cmds.scriptJob(event=["SelectionChanged", self._on_selection_or_time_changed], killWithScene=True)
        time_job = cmds.scriptJob(event=["timeChanged", self._on_selection_or_time_changed], killWithScene=True)
        self.script_jobs.extend([sel_job, time_job])

    def _on_selection_or_time_changed(self):
        if self._is_updating or not self.offset_active:
            return
        target_nodes = self._get_target_nodes()
        self._cache_temp_curves(target_nodes)

        self.kill_attr_jobs()
        attrs = ['translateX', 'translateY', 'translateZ', 'rotateX', 'rotateY', 'rotateZ']
        for node in target_nodes:
            if cmds.objExists(node):
                for attr in attrs:
                    full_attr = f"{node}.{attr}"
                    if cmds.attributeQuery(attr, node=node, exists=True):
                        job = cmds.scriptJob(
                            attributeChange=[full_attr, lambda a=attr, n=node: self._on_attr_changed(n, a)],
                            killWithScene=True
                        )
                        self.attr_jobs.append(job)

    def _on_attr_changed(self, node, attr):
        if self._is_updating or not self.offset_active:
            return
        self.apply_timeline_offset()

    def create_smart(self):
        sel = cmds.ls(selection=True, type="transform")
        if not sel:
            cmds.warning("Please select controllers in the scene!")
            return

        start_frame, end_frame = self._get_time_range()
        keys_only = TempControlManager.BAKE_KEYS_ONLY

        with UndoContext("CreateSmartTemp"):
            if len(sel) == 1:
                target_ctrl = sel[0]
                loc_name = f"{target_ctrl}_TEMP_CTRL"
                if cmds.objExists(loc_name):
                    cmds.delete(loc_name)

                loc = cmds.spaceLocator(name=loc_name)[0]
                for attr in ['localScaleX', 'localScaleY', 'localScaleZ']:
                    cmds.setAttr(f"{loc}.{attr}", 4)

                for s in cmds.listRelatives(loc, shapes=True) or []:
                    cmds.setAttr(f"{s}.overrideEnabled", 1)
                    cmds.setAttr(f"{s}.overrideColor", 18)

                temp_const = cmds.parentConstraint(target_ctrl, loc, maintainOffset=False)
                cmds.bakeResults(
                    loc, time=(start_frame, end_frame), simulation=True,
                    sampleBy=1, disableImplicitControl=True
                )
                cmds.delete(temp_const)

                if keys_only:
                    source_keys = cmds.keyframe(target_ctrl, query=True, timeChange=True) or []
                    valid_set = set([int(round(float(k))) for k in source_keys])
                    if valid_set:
                        all_k = cmds.keyframe(loc, query=True, timeChange=True) or []
                        for f in all_k:
                            f_int = int(round(float(f)))
                            if f_int not in valid_set and start_frame <= f_int <= end_frame:
                                cmds.cutKey(loc, time=(f_int, f_int))

                cmds.parentConstraint(loc, target_ctrl, maintainOffset=True)
                self.session_data[loc] = [target_ctrl]
                cmds.select(loc)
            else:
                combined_bounds = [float('inf'), float('inf'), float('inf'), float('-inf'), float('-inf'), float('-inf')]
                for obj in sel:
                    bbox = cmds.xform(obj, query=True, boundingBox=True, ws=True)
                    combined_bounds[0] = min(combined_bounds[0], bbox[0])
                    combined_bounds[1] = min(combined_bounds[1], bbox[1])
                    combined_bounds[2] = min(combined_bounds[2], bbox[2])
                    combined_bounds[3] = max(combined_bounds[3], bbox[3])
                    combined_bounds[4] = max(combined_bounds[4], bbox[4])
                    combined_bounds[5] = max(combined_bounds[5], bbox[5])

                master_ctrl = self._create_wireframe_box(combined_bounds, name="Group_Temp_CTRL")
                associated = []

                for ctrl in sel:
                    loc = cmds.spaceLocator(name=f"{ctrl}_TEMP_LOC")[0]
                    temp_const = cmds.parentConstraint(ctrl, loc, maintainOffset=False)
                    cmds.bakeResults(
                        loc, time=(start_frame, end_frame), simulation=True,
                        sampleBy=1, disableImplicitControl=True
                    )
                    cmds.delete(temp_const)
                    cmds.parent(loc, master_ctrl)
                    cmds.parentConstraint(loc, ctrl, maintainOffset=True)
                    associated.append(ctrl)

                self.session_data[master_ctrl] = associated
                cmds.select(master_ctrl)

        self._on_selection_or_time_changed()

    # --- UNIVERSAL PIVOT LOCATOR WORKFLOW (SMART TEMP & TEMP IK) ---

    def create_pivot_locator(self):
        """Spawns a pivot locator at the selected Temp Control OR Temp IK Control position."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select an active Temp Control or Temp IK Control to create a Pivot Locator!")
            return False

        temp_ctrl = sel[0]
        piv_name = f"{temp_ctrl}_PIVOT_LOC"
        if cmds.objExists(piv_name):
            cmds.delete(piv_name)

        with UndoContext("CreatePivotLocator"):
            piv_loc = cmds.spaceLocator(name=piv_name)[0]
            for attr in ['localScaleX', 'localScaleY', 'localScaleZ']:
                cmds.setAttr(f"{piv_loc}.{attr}", 3)

            for s in cmds.listRelatives(piv_loc, shapes=True) or []:
                cmds.setAttr(f"{s}.overrideEnabled", 1)
                cmds.setAttr(f"{s}.overrideColor", 9)  # Pink / Purple

            cmds.matchTransform(piv_loc, temp_ctrl, pos=True, rot=True)
            cmds.select(piv_loc)

        cmds.inViewMessage(
            amg=f"Move <hl>{piv_loc}</hl> to fingertip/corner, then click <hl>'Bake Pivot'</hl>.",
            pos="topCenter", fade=True
        )
        return True

    def apply_pivot_locator(self):
        """
        Transfers motion cleanly to the new pivot position.
        Supports both Smart Temp Controls and Temp IK Controls seamlessly.
        """
        sel = cmds.ls(selection=True, type="transform") or []

        piv_loc = None
        temp_ctrl = None

        if sel and "_PIVOT_LOC" in sel[0]:
            piv_loc = sel[0]
            temp_ctrl = piv_loc.replace("_PIVOT_LOC", "")
        else:
            piv_locs = cmds.ls("*_PIVOT_LOC*", type="transform") or []
            if piv_locs:
                piv_loc = piv_locs[0]
                temp_ctrl = piv_loc.replace("_PIVOT_LOC", "")

        if not piv_loc or not cmds.objExists(piv_loc) or not temp_ctrl or not cmds.objExists(temp_ctrl):
            cmds.warning("No active Pivot Locator found in scene! Run 'Set Pivot Loc' first.")
            return False

        start_frame, end_frame = self._get_time_range()
        keys_only = TempControlManager.BAKE_KEYS_ONLY

        # --- КЕЙС 1: ЦЕ TEMP IK CTRL (наприклад на пальцях чи зап'ясті) ---
        is_temp_ik = "_TempIK_CTRL" in temp_ctrl or (
            self.win and hasattr(self.win, "temp_ik_mgr") and temp_ctrl in self.win.temp_ik_mgr.active_ik_setups
        )

        if is_temp_ik:
            ik_mgr = self.win.temp_ik_mgr if (self.win and hasattr(self.win, "temp_ik_mgr")) else None
            ik_data = ik_mgr.active_ik_setups.get(temp_ctrl) if ik_mgr else None

            # Знаходимо керований Handle та End Joint
            base_name = temp_ctrl.replace("_TempIK_CTRL", "")
            ik_handle = f"{base_name}_TempIK_Handle"
            j_end = f"{base_name}_TempIK_JntEnd"

            with UndoContext("ApplyPivotToTempIK"):
                # 1. Запікаємо рух кінцевого локатора в Pivot Locator
                bake_const = cmds.parentConstraint(temp_ctrl, piv_loc, maintainOffset=True)
                cmds.bakeResults(
                    piv_loc, time=(start_frame, end_frame), simulation=True,
                    sampleBy=1, disableImplicitControl=True
                )
                cmds.delete(bake_const)

                if keys_only:
                    ik_keys = cmds.keyframe(temp_ctrl, query=True, timeChange=True) or []
                    valid_set = set([int(round(float(k))) for k in ik_keys])
                    if valid_set:
                        all_k = cmds.keyframe(piv_loc, query=True, timeChange=True) or []
                        for f in all_k:
                            f_int = int(round(float(f)))
                            if f_int not in valid_set and start_frame <= f_int <= end_frame:
                                cmds.cutKey(piv_loc, time=(f_int, f_int))

                # 2. Видаляємо старий TempIK_CTRL
                old_grp = ik_data['grp'] if (ik_data and 'grp' in ik_data) else f"{base_name}_TempIK_GRP"
                if cmds.objExists(temp_ctrl):
                    cmds.delete(temp_ctrl)

                # 3. Перетворюємо Pivot Locator на новий TempIK_CTRL
                new_ik_ctrl = cmds.rename(piv_loc, temp_ctrl)
                for s in cmds.listRelatives(new_ik_ctrl, shapes=True) or []:
                    cmds.setAttr(f"{s}.overrideColor", 13)  # Cyan

                # 4. Поновлюємо констрейнти на IK Handle та End Joint
                if cmds.objExists(ik_handle):
                    cmds.parentConstraint(new_ik_ctrl, ik_handle, maintainOffset=True)
                if cmds.objExists(j_end):
                    cmds.orientConstraint(new_ik_ctrl, j_end, maintainOffset=True)

                if cmds.objExists(old_grp):
                    cmds.parent(new_ik_ctrl, old_grp)

                if ik_mgr and ik_data:
                    ik_mgr.active_ik_setups[new_ik_ctrl] = ik_data

                cmds.select(new_ik_ctrl)
                cmds.inViewMessage(amg=f"Temp IK Pivot relocated cleanly to <hl>{new_ik_ctrl}</hl>!", pos="topCenter", fade=True)
                return True

        # --- КЕЙС 2: ЦЕ ЗВИЧАЙНИЙ SMART TEMP CONTROL ---
        targets = self.session_data.get(temp_ctrl, [])
        if not targets:
            constraints = cmds.listRelatives(temp_ctrl, allDescendents=True, type="parentConstraint") or []
            for c in constraints:
                targets.extend(cmds.parentConstraint(c, query=True, targetList=True) or [])

        if not targets:
            cmds.warning("Could not resolve target objects for this Temp Control!")
            return False

        with UndoContext("ApplyPivotLocator"):
            bake_const = cmds.parentConstraint(targets[0], piv_loc, maintainOffset=True)
            cmds.bakeResults(
                piv_loc, time=(start_frame, end_frame), simulation=True,
                sampleBy=1, disableImplicitControl=True
            )
            cmds.delete(bake_const)

            if keys_only:
                source_keys = cmds.keyframe(targets[0], query=True, timeChange=True) or []
                valid_set = set([int(round(float(k))) for k in source_keys])
                if valid_set:
                    all_k = cmds.keyframe(piv_loc, query=True, timeChange=True) or []
                    for f in all_k:
                        f_int = int(round(float(f)))
                        if f_int not in valid_set and start_frame <= f_int <= end_frame:
                            cmds.cutKey(piv_loc, time=(f_int, f_int))

            if cmds.objExists(temp_ctrl):
                cmds.delete(temp_ctrl)
            if temp_ctrl in self.session_data:
                del self.session_data[temp_ctrl]

            for t in targets:
                old_consts = cmds.listConnections(f"{t}.translateX", type="parentConstraint") or []
                if old_consts:
                    cmds.delete(old_consts)

            new_temp_ctrl = cmds.rename(piv_loc, temp_ctrl)
            for s in cmds.listRelatives(new_temp_ctrl, shapes=True) or []:
                cmds.setAttr(f"{s}.overrideColor", 18)

            for t in targets:
                cmds.parentConstraint(new_temp_ctrl, t, maintainOffset=True)

            self.session_data[new_temp_ctrl] = targets
            cmds.select(new_temp_ctrl)

        cmds.inViewMessage(amg=f"Pivot relocated cleanly to <hl>{new_temp_ctrl}</hl>!", pos="topCenter", fade=True)
        return True

    def apply_timeline_offset(self):
        if not self.base_curves_cache or self._is_updating:
            return

        current_frame = int(cmds.currentTime(query=True))
        self._is_updating = True

        try:
            for node, attr_cache in self.base_curves_cache.items():
                if not cmds.objExists(node):
                    continue

                for attr, frame_dict in attr_cache.items():
                    full_attr = f"{node}.{attr}"
                    base_val = frame_dict.get(float(current_frame), frame_dict.get(current_frame, None))
                    if base_val is None:
                        continue

                    current_val = cmds.getAttr(full_attr)
                    delta = current_val - base_val

                    if abs(delta) < 1e-4:
                        continue

                    for t, base_t_val in frame_dict.items():
                        target_val = current_val if abs(t - current_frame) < 1e-3 else (base_t_val + delta)
                        cmds.setKeyframe(full_attr, time=t, value=target_val)
        finally:
            self._is_updating = False

    def bake_selected(self):
        """Intelligently bakes only selected controls."""
        sel = cmds.ls(selection=True, type="transform")
        if not sel:
            cmds.warning("Please select a controller or Temp Rig element to bake!")
            return False

        start_frame, end_frame = self._get_time_range()
        targets_to_bake = set()
        temp_nodes_to_delete = set()
        regular_ctrls_to_bake = set()

        with UndoContext("BakeSelected"):
            for item in sel:
                if item in self.session_data:
                    targets_to_bake.update(self.session_data[item])
                    temp_nodes_to_delete.add(item)
                elif "_TEMP_CTRL" in item or "_TEMP_LOC" in item or "Group_Temp_CTRL" in item:
                    constraints = cmds.listRelatives(item, allDescendents=True, type="parentConstraint") or []
                    for c in constraints:
                        targets_to_bake.update(cmds.parentConstraint(c, query=True, targetList=True) or [])
                    temp_nodes_to_delete.add(item)
                else:
                    parent_consts = cmds.listConnections(f"{item}.translateX", type="parentConstraint") or []
                    found_temp_driver = False
                    for pc in parent_consts:
                        drivers = cmds.parentConstraint(pc, query=True, targetList=True) or []
                        for d in drivers:
                            if "_TEMP_" in d or "Group_Temp_CTRL" in d:
                                targets_to_bake.add(item)
                                temp_nodes_to_delete.add(d)
                                found_temp_driver = True

                    if not found_temp_driver:
                        regular_ctrls_to_bake.add(item)

            if targets_to_bake:
                cmds.bakeResults(
                    list(targets_to_bake), time=(start_frame, end_frame), simulation=True,
                    sampleBy=1, disableImplicitControl=True, preserveOutsideKeys=True
                )
                for node in temp_nodes_to_delete:
                    if cmds.objExists(node):
                        cmds.delete(node)
                    if node in self.session_data:
                        del self.session_data[node]

            if regular_ctrls_to_bake:
                cmds.bakeResults(
                    list(regular_ctrls_to_bake), time=(start_frame, end_frame), simulation=True,
                    sampleBy=1, disableImplicitControl=True, preserveOutsideKeys=True
                )

            total_baked = len(targets_to_bake | regular_ctrls_to_bake)
            if total_baked > 0:
                cmds.select(list(targets_to_bake | regular_ctrls_to_bake))
                cmds.inViewMessage(amg=f"Baked <hl>{total_baked}</hl> selected controller(s).", pos="topCenter", fade=True)
                return True
            else:
                return False

    def bake_back_all(self):
        """Bakes back and cleans all active temporary controls in the scene."""
        self.kill_script_jobs()
        self.set_offset_mode(False)

        active_masters = [node for node in self.session_data.keys() if cmds.objExists(node)]
        scene_temps = cmds.ls("*_TEMP_CTRL*", "*_TEMP_LOC*", "*Group_Temp_CTRL*", type="transform")
        for t in scene_temps:
            if t not in active_masters and not cmds.listRelatives(t, parent=True):
                active_masters.append(t)

        start_frame, end_frame = self._get_time_range()
        all_targets = set()

        with UndoContext("BakeBackTempControls"):
            for master in active_masters:
                if master in self.session_data:
                    all_targets.update(self.session_data[master])
                else:
                    constraints = cmds.listRelatives(master, allDescendents=True, type="parentConstraint") or []
                    for c in constraints:
                        all_targets.update(cmds.parentConstraint(c, query=True, targetList=True) or [])

            target_list = list(all_targets)
            if target_list:
                cmds.bakeResults(
                    target_list, time=(start_frame, end_frame), simulation=True,
                    sampleBy=1, disableImplicitControl=True, preserveOutsideKeys=True
                )

            nodes_to_delete = cmds.ls("*_TEMP_CTRL*", "*_TEMP_LOC*", "*Group_Temp_CTRL*", "*_PIVOT_LOC*", type="transform")
            if nodes_to_delete:
                cmds.delete(nodes_to_delete)

            self.session_data.clear()
            self.base_curves_cache.clear()
            if target_list:
                cmds.select(target_list)
            cmds.inViewMessage(amg=f"Baked back and cleaned <hl>{len(target_list)}</hl> controller(s).", pos="topCenter", fade=True)