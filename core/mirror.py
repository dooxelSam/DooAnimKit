import maya.cmds as cmds
from DooAnimKit.core.context import UndoContext


class PoseMirrorEngine:
    """
    Singleton Pose & Animation Mirroring Engine with Anatomy Validation,
    Default Pose cache, and Animation Copy/Paste/Mirror support.
    """

    _instance = None

    REQUIRED_HIK_TAGS = [
        "Main_Root", "Hips",
        "LeftShoulder_FK", "RightShoulder_FK",
        "LeftElbow_FK", "RightElbow_FK",
        "LeftFoot_FK", "RightFoot_FK"
    ]

    CHANNELS = [
        "translateX", "translateY", "translateZ",
        "rotateX", "rotateY", "rotateZ",
        "scaleX", "scaleY", "scaleZ"
    ]

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PoseMirrorEngine, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.default_pose = {}
        self.symmetry_table = {}
        self.is_rig_scanned = False
        self.is_manually_locked = False
        self.copied_pose_data = {}
        self.copied_anim_data = {}

    def _get_time_range(self):
        start = int(cmds.playbackOptions(query=True, minTime=True))
        end = int(cmds.playbackOptions(query=True, maxTime=True))
        return start, end

    # --- SCAN & DEFAULT POSE ---

    def scan_selected_rig(self):
        """Scans current character pose, caches default neutral state and builds symmetry pairs."""
        sel = cmds.ls(selection=True, type="transform") or []

        if not sel:
            sel = cmds.ls("*_CTRL", "*_ctrl", "*_Ctrl", "*_CTL", "*_ctl", "*_IK", "*_FK", type="transform") or []

        if not sel:
            cmds.warning("Please select character controllers or rig root to Scan Rig!")
            return False

        self.default_pose.clear()
        self.symmetry_table.clear()

        attrs = ["translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"]

        for node in sel:
            if not cmds.objExists(node):
                continue
            self.default_pose[node] = {}
            for attr in attrs:
                full_attr = f"{node}.{attr}"
                if cmds.attributeQuery(attr, node=node, exists=True) and not cmds.getAttr(full_attr, lock=True):
                    self.default_pose[node][attr] = cmds.getAttr(full_attr)

        self.is_rig_scanned = True
        self.is_manually_locked = True

        try:
            import DooAnimKit
            if getattr(DooAnimKit, "_hub_instance", None) is not None:
                DooAnimKit._hub_instance.sync_ui_state()
        except Exception:
            pass

        cmds.inViewMessage(
            amg=f"Rig Scanned: Cached neutral pose on <hl>{len(self.default_pose)}</hl> controller(s).",
            pos="topCenter", fade=True
        )
        return True

    def reset_to_default_pose(self):
        """Resets selected controllers (or full rig) back to scanned neutral default pose."""
        if not self.default_pose:
            self.scan_selected_rig()
            return True

        sel = cmds.ls(selection=True, type="transform") or []
        targets = sel if sel else list(self.default_pose.keys())

        curr_time = cmds.currentTime(query=True)
        reset_count = 0

        with UndoContext("ResetToDefaultPose"):
            for node in targets:
                if node in self.default_pose:
                    for attr, val in self.default_pose[node].items():
                        full_attr = f"{node}.{attr}"
                        if cmds.objExists(full_attr) and not cmds.getAttr(full_attr, lock=True):
                            cmds.setAttr(full_attr, val)
                            if cmds.keyframe(full_attr, query=True, time=(curr_time, curr_time), keyframeCount=True):
                                cmds.setKeyframe(full_attr, time=curr_time, value=val)
                            reset_count += 1

        cmds.refresh()
        cmds.inViewMessage(amg=f"Reset <hl>{len(targets)}</hl> controller(s) to Default Pose.", pos="topCenter", fade=True)
        return True

    def validate_pins_anatomy(self, pins_list):
        if not self.is_rig_scanned and not self.default_pose:
            return "UNINITIALIZED", []

        if self.is_manually_locked:
            return "READY", []

        present_tags = set(p.get("hik_tag") for p in pins_list if p.get("hik_tag") and p.get("hik_tag") != "None")
        missing = [req for req in self.REQUIRED_HIK_TAGS if req not in present_tags]

        if not missing:
            return "READY", []
        return "PARTIAL", missing

    def toggle_manual_lock(self, pins_list):
        self.is_manually_locked = not self.is_manually_locked
        status = "LOCKED & READY" if self.is_manually_locked else "UNLOCKED"
        cmds.inViewMessage(amg=f"Rig Status: <hl>{status}</hl>", pos="topCenter", fade=True)
        return self.is_manually_locked

    # --- POSE LOGIC ---

    def copy_pose(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Select controllers to copy pose!")
            return False
        self.copied_pose_data.clear()
        attrs = ["translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"]
        for node in sel:
            self.copied_pose_data[node] = {}
            for attr in attrs:
                full_attr = f"{node}.{attr}"
                if cmds.attributeQuery(attr, node=node, exists=True) and not cmds.getAttr(full_attr, lock=True):
                    self.copied_pose_data[node][attr] = cmds.getAttr(full_attr)
        cmds.inViewMessage(amg=f"Copied pose from <hl>{len(sel)}</hl> controller(s).", pos="topCenter", fade=True)
        return True

    def paste_pose(self):
        if not self.copied_pose_data:
            cmds.warning("No pose data copied!")
            return False
        curr_time = cmds.currentTime(query=True)
        with UndoContext("PastePose"):
            for node, attr_dict in self.copied_pose_data.items():
                if cmds.objExists(node):
                    for attr, val in attr_dict.items():
                        full_attr = f"{node}.{attr}"
                        if cmds.objExists(full_attr) and not cmds.getAttr(full_attr, lock=True):
                            cmds.setAttr(full_attr, val)
                            if cmds.keyframe(full_attr, query=True, time=(curr_time, curr_time), keyframeCount=True):
                                cmds.setKeyframe(full_attr, time=curr_time, value=val)
        cmds.refresh()
        cmds.inViewMessage(amg=f"Pasted pose onto <hl>{len(self.copied_pose_data)}</hl> controller(s).", pos="topCenter", fade=True)
        return True

    def smart_mirror_pose(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Select controllers to Mirror/Flip pose!")
            return False
        curr_time = cmds.currentTime(query=True)
        with UndoContext("SmartMirrorPose"):
            for node in sel:
                for attr in ["translateX", "rotateY", "rotateZ"]:
                    full_attr = f"{node}.{attr}"
                    if cmds.attributeQuery(attr, node=node, exists=True) and not cmds.getAttr(full_attr, lock=True):
                        val = cmds.getAttr(full_attr)
                        cmds.setAttr(full_attr, -val)
                        if cmds.keyframe(full_attr, query=True, time=(curr_time, curr_time), keyframeCount=True):
                            cmds.setKeyframe(full_attr, time=curr_time, value=-val)
        cmds.refresh()
        cmds.inViewMessage(amg="Smart Mirror applied.", pos="topCenter", fade=True)
        return True

    # --- ANIMATION LOGIC ---

    def copy_animation(self):
        """Copies keyframes for selected controllers across full timeline range."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Select animated controllers to copy animation!")
            return False

        start_f, end_f = self._get_time_range()
        self.copied_anim_data.clear()

        for node in sel:
            self.copied_anim_data[node] = {}
            for attr in self.CHANNELS:
                full_attr = f"{node}.{attr}"
                if cmds.attributeQuery(attr, node=node, exists=True):
                    times = cmds.keyframe(full_attr, query=True, time=(start_f, end_f), timeChange=True) or []
                    vals = cmds.keyframe(full_attr, query=True, time=(start_f, end_f), valueChange=True) or []
                    if times:
                        self.copied_anim_data[node][attr] = list(zip(times, vals))

        cmds.inViewMessage(amg=f"Copied animation from <hl>{len(sel)}</hl> controller(s).", pos="topCenter", fade=True)
        return True

    def paste_animation(self):
        """Pastes copied animation curves onto selected controllers."""
        if not self.copied_anim_data:
            cmds.warning("No animation data copied!")
            return False

        sel = cmds.ls(selection=True, type="transform") or []
        targets = sel if sel else list(self.copied_anim_data.keys())

        with UndoContext("PasteAnimation"):
            for node in targets:
                source_data = self.copied_anim_data.get(node)
                if not source_data:
                    # Якщо виділено один об'єкт, пробуємо вставити перший скопійований
                    source_data = next(iter(self.copied_anim_data.values()), {})

                if cmds.objExists(node) and source_data:
                    for attr, keys in source_data.items():
                        full_attr = f"{node}.{attr}"
                        if cmds.attributeQuery(attr, node=node, exists=True) and not cmds.getAttr(full_attr, lock=True):
                            for t, val in keys:
                                cmds.setKeyframe(full_attr, time=t, value=val)

        cmds.refresh()
        cmds.inViewMessage(amg=f"Pasted animation onto <hl>{len(targets)}</hl> controller(s).", pos="topCenter", fade=True)
        return True

    def smart_mirror_animation(self):
        """Inverts symmetry axes on animation curves for selected controllers."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Select animated controllers to mirror animation!")
            return False

        start_f, end_f = self._get_time_range()
        mirror_attrs = ["translateX", "rotateY", "rotateZ"]

        with UndoContext("MirrorAnimation"):
            for node in sel:
                for attr in mirror_attrs:
                    full_attr = f"{node}.{attr}"
                    if cmds.attributeQuery(attr, node=node, exists=True) and not cmds.getAttr(full_attr, lock=True):
                        times = cmds.keyframe(full_attr, query=True, time=(start_f, end_f), timeChange=True) or []
                        vals = cmds.keyframe(full_attr, query=True, time=(start_f, end_f), valueChange=True) or []
                        for t, val in zip(times, vals):
                            cmds.setKeyframe(full_attr, time=t, value=-val)

        cmds.refresh()
        cmds.inViewMessage(amg=f"Mirrored animation on <hl>{len(sel)}</hl> controller(s).", pos="topCenter", fade=True)
        return True