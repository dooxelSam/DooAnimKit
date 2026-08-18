import maya.cmds as cmds
from DooAnimKit.core.context import UndoContext


class TempControlManager:
    """Universal manager for Temp Controls and Selection-based Live Timeline Offset."""

    BOOKMARK_NAME = "AnimKit_Offset_Bookmark"

    def __init__(self):
        self.session_data = {}        # {active_temp_loc: [target_ctrls]}
        self.base_curves_cache = {}   # {node: {attr: {frame: val}}}
        self.script_jobs = []         # Active scriptJob IDs
        self.attr_jobs = []           # Attribute change scriptJobs
        self.offset_active = False
        self._is_updating = False

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
        """Intelligently bakes only selected controls (deleting temporary nodes, preserving real controls)."""
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
                # 1. Is this a Temp Control or master group?
                if item in self.session_data:
                    targets_to_bake.update(self.session_data[item])
                    temp_nodes_to_delete.add(item)
                elif "_TEMP_CTRL" in item or "_TEMP_LOC" in item or "Group_Temp_CTRL" in item:
                    constraints = cmds.listRelatives(item, allDescendents=True, type="parentConstraint") or []
                    for c in constraints:
                        targets_to_bake.update(cmds.parentConstraint(c, query=True, targetList=True) or [])
                    temp_nodes_to_delete.add(item)
                else:
                    # Check if this regular controller is driven by a temp node
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
                        # Regular controller: Just bake, NEVER delete
                        regular_ctrls_to_bake.add(item)

            # Bake associated temp control targets
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

            # Bake regular controllers without deleting them
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
                cmds.warning("No animation found to bake on selected objects.")
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

            nodes_to_delete = cmds.ls("*_TEMP_CTRL*", "*_TEMP_LOC*", "*Group_Temp_CTRL*", type="transform")
            if nodes_to_delete:
                cmds.delete(nodes_to_delete)

            self.session_data.clear()
            self.base_curves_cache.clear()
            if target_list:
                cmds.select(target_list)
            cmds.inViewMessage(amg=f"Baked back and cleaned <hl>{len(target_list)}</hl> controller(s).", pos="topCenter", fade=True)