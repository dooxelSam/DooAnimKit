import os
import json
import tempfile
import maya.cmds as cmds
import maya.mel as mel
from DooAnimKit.core.context import UndoContext


class PoseMirrorEngine:
    """
    Handles Pose & Animation Copy, Paste, Smart Mirror/Flip, and Default Pose.
    Persists copied data to disk (JSON) to allow sharing between multiple Maya instances.
    """

    CHANNELS = [
        "translateX", "translateY", "translateZ",
        "rotateX", "rotateY", "rotateZ",
        "scaleX", "scaleY", "scaleZ"
    ]

    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
        self.pose_file = os.path.join(self.temp_dir, "doo_pose_buffer.json")
        self.anim_file = os.path.join(self.temp_dir, "doo_anim_buffer.json")

        self.copied_pose = {}
        self.copied_anim = {}
        self.symmetry_table = {}
        self.default_pose = {}

    # --- DISK PERSISTENCE (CROSS-MAYA BUFFER) ---

    def _save_json(self, file_path, data):
        """Saves dictionary data to disk for cross-instance access."""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            cmds.warning(f"Failed to save clipboard buffer: {e}")
            return False

    def _load_json(self, file_path):
        """Loads dictionary data from disk if available."""
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            cmds.warning(f"Failed to read clipboard buffer: {e}")
            return None

    # --- TIME RANGE & UTILS ---

    def _get_time_range(self):
        """Returns active timeline highlight range, or scene playback min/max."""
        gPlayBackSlider = mel.eval('$tmpVar=$gPlayBackSlider;')
        time_range = cmds.timeControl(gPlayBackSlider, query=True, rangeArray=True)
        if time_range and (time_range[1] - time_range[0] > 1):
            return int(time_range[0]), int(time_range[1])
        start = int(cmds.playbackOptions(query=True, minTime=True))
        end = int(cmds.playbackOptions(query=True, maxTime=True))
        return start, end

    def _clean_name(self, name):
        """Strips namespace and path delimiters to allow matching across scenes."""
        return name.split(":")[-1].split("|")[-1]

    def _get_opposite_name(self, name):
        """Finds opposite control name based on standard naming conventions."""
        patterns = [
            ("L_", "R_"), ("_L", "_R"),
            ("Left", "Right"), ("left", "right"),
            ("l_", "r_"), ("_l", "_r"),
            ("LF", "RT"), ("lf", "rt")
        ]
        for left, right in patterns:
            if left in name:
                candidate = name.replace(left, right)
                if cmds.objExists(candidate):
                    return candidate
            elif right in name:
                candidate = name.replace(right, left)
                if cmds.objExists(candidate):
                    return candidate
        return None

    def _get_partner(self, ctrl):
        """Retrieves symmetry partner or dynamically maps opposite name."""
        partner = self.symmetry_table.get(ctrl)
        if not partner or not cmds.objExists(partner):
            partner = self._get_opposite_name(ctrl)
            if partner:
                self.symmetry_table[ctrl] = partner
        return partner

    def _is_fk_control(self, ctrl):
        """Detects whether a controller is an FK chain component."""
        name_lower = ctrl.lower()
        if "fk" in name_lower or "finger" in name_lower or "thumb" in name_lower:
            return True
        tx_settable = cmds.attributeQuery("translateX", node=ctrl, exists=True) and cmds.getAttr(f"{ctrl}.translateX", settable=True)
        rx_settable = cmds.attributeQuery("rotateX", node=ctrl, exists=True) and cmds.getAttr(f"{ctrl}.rotateX", settable=True)
        if rx_settable and not tx_settable:
            return True
        return False

    def _calculate_mirror_value(self, ctrl, attr, val):
        """Calculates value sign based on IK vs FK mirroring behavior."""
        if self._is_fk_control(ctrl):
            return val
        else:
            if attr in ("translateX", "rotateY", "rotateZ"):
                return -val
            return val

    # --- POSE CORE ---

    def _read_transforms(self, ctrl):
        data = {}
        for attr in self.CHANNELS:
            full_attr = f"{ctrl}.{attr}"
            if cmds.attributeQuery(attr, node=ctrl, exists=True):
                if cmds.getAttr(full_attr, settable=True):
                    data[attr] = cmds.getAttr(full_attr)
        return data

    def _apply_transforms(self, ctrl, data, mirror_mode=False):
        for attr, val in data.items():
            full_attr = f"{ctrl}.{attr}"
            if cmds.attributeQuery(attr, node=ctrl, exists=True):
                if cmds.getAttr(full_attr, settable=True):
                    final_val = self._calculate_mirror_value(ctrl, attr, val) if mirror_mode else val
                    try:
                        cmds.setAttr(full_attr, final_val)
                    except Exception:
                        pass

    # --- ANIMATION CORE ---

    def _read_animation(self, ctrl, start_frame, end_frame):
        anim_data = {}
        for attr in self.CHANNELS:
            full_attr = f"{ctrl}.{attr}"
            if cmds.attributeQuery(attr, node=ctrl, exists=True):
                key_times = cmds.keyframe(full_attr, query=True, time=(start_frame, end_frame), timeChange=True)
                if key_times:
                    keys_list = []
                    for t in key_times:
                        val = cmds.keyframe(full_attr, query=True, time=(t, t), valueChange=True)[0]
                        in_tan = cmds.keyTangent(full_attr, query=True, time=(t, t), inTangentType=True)[0]
                        out_tan = cmds.keyTangent(full_attr, query=True, time=(t, t), outTangentType=True)[0]
                        keys_list.append({
                            "time": t,
                            "val": val,
                            "in_tan": in_tan,
                            "out_tan": out_tan
                        })
                    anim_data[attr] = keys_list
        return anim_data

    def _apply_animation(self, ctrl, anim_data, start_frame, end_frame, mirror_mode=False):
        for attr, keys in anim_data.items():
            full_attr = f"{ctrl}.{attr}"
            if cmds.attributeQuery(attr, node=ctrl, exists=True):
                if cmds.getAttr(full_attr, settable=True):
                    cmds.cutKey(full_attr, time=(start_frame, end_frame))
                    for k in keys:
                        t = k["time"]
                        v = self._calculate_mirror_value(ctrl, attr, k["val"]) if mirror_mode else k["val"]
                        cmds.setKeyframe(full_attr, time=t, value=v)
                        try:
                            cmds.keyTangent(full_attr, time=(t, t), inTangentType=k["in_tan"], outTangentType=k["out_tan"])
                        except Exception:
                            pass

    # --- RIG SCAN & DEFAULT POSE ---

    def scan_selected_rig(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            all_ctrls = cmds.ls("*_CTRL*", "*_ctrl*", "*_Ctrl*", "*_CTL*", type="transform") or []
            sel = [c for c in all_ctrls if not cmds.listRelatives(c, shapes=True, type="camera")]

        if not sel:
            cmds.warning("Please select controllers to scan rig symmetry!")
            return False

        self.symmetry_table.clear()
        self.default_pose.clear()

        with UndoContext("ScanRigAndDefaultPose"):
            for ctrl in sel:
                self.default_pose[ctrl] = self._read_transforms(ctrl)
                partner = self._get_opposite_name(ctrl)
                self.symmetry_table[ctrl] = partner if partner else ctrl

        cmds.inViewMessage(amg=f"Rig scanned: <hl>{len(sel)}</hl> controls mapped.", pos="topCenter", fade=True)
        return True

    def reset_to_default_pose(self):
        if not self.default_pose:
            cmds.warning("No Default Pose found! Run 'Scan Rig' first.")
            return False

        sel = cmds.ls(selection=True, type="transform") or []
        targets = [c for c in sel if c in self.default_pose] if sel else list(self.default_pose.keys())

        with UndoContext("ResetToDefaultPose"):
            for ctrl in targets:
                if cmds.objExists(ctrl):
                    self._apply_transforms(ctrl, self.default_pose[ctrl], mirror_mode=False)

        cmds.inViewMessage(amg=f"Reset <hl>{len(targets)}</hl> controls to Default Pose.", pos="topCenter", fade=True)
        return True

    # --- POSE COPY / PASTE (CROSS-SCENE / CROSS-MAYA) ---

    def copy_pose(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select controllers to copy pose!")
            return False

        self.copied_pose.clear()
        # Save both full name and clean name (without namespaces)
        for ctrl in sel:
            data = self._read_transforms(ctrl)
            self.copied_pose[ctrl] = data
            self.copied_pose[self._clean_name(ctrl)] = data

        self._save_json(self.pose_file, self.copied_pose)

        cmds.inViewMessage(amg=f"Copied pose for <hl>{len(sel)}</hl> controls (Saved to Buffer).", pos="topCenter", fade=True)
        return True

    def paste_pose(self):
        # Reload latest buffer from disk (in case it was copied in another Maya)
        disk_data = self._load_json(self.pose_file)
        if disk_data:
            self.copied_pose = disk_data

        if not self.copied_pose:
            cmds.warning("Pose buffer is empty! Please Copy Pose first.")
            return False

        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select controllers to paste pose onto!")
            return False

        applied_count = 0
        with UndoContext("PastePose"):
            for ctrl in sel:
                clean = self._clean_name(ctrl)
                data = self.copied_pose.get(ctrl) or self.copied_pose.get(clean)
                if data:
                    self._apply_transforms(ctrl, data, mirror_mode=False)
                    applied_count += 1

        cmds.inViewMessage(amg=f"Pasted pose onto <hl>{applied_count}</hl> controls.", pos="topCenter", fade=True)
        return True

    # --- ANIMATION COPY / PASTE (CROSS-SCENE / CROSS-MAYA) ---

    def copy_animation(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select controllers to copy animation!")
            return False

        start_frame, end_frame = self._get_time_range()
        self.copied_anim.clear()

        count = 0
        for ctrl in sel:
            data = self._read_animation(ctrl, start_frame, end_frame)
            if data:
                clean = self._clean_name(ctrl)
                self.copied_anim[ctrl] = data
                self.copied_anim[clean] = data
                count += 1

        # Package data with time metadata
        payload = {
            "start_frame": start_frame,
            "end_frame": end_frame,
            "data": self.copied_anim
        }
        self._save_json(self.anim_file, payload)

        cmds.inViewMessage(
            amg=f"Copied animation for <hl>{count}</hl> controls ({start_frame}..{end_frame}).",
            pos="topCenter", fade=True
        )
        return True

    def paste_animation(self):
        # Reload latest buffer from disk
        payload = self._load_json(self.anim_file)
        if payload and "data" in payload:
            self.copied_anim = payload["data"]
            default_start = payload.get("start_frame")
            default_end = payload.get("end_frame")
        else:
            default_start, default_end = None, None

        if not self.copied_anim:
            cmds.warning("Animation buffer is empty! Please Copy Animation first.")
            return False

        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select controllers to paste animation onto!")
            return False

        curr_start, curr_end = self._get_time_range()
        start_frame = curr_start if curr_start is not None else default_start
        end_frame = curr_end if curr_end is not None else default_end

        applied_count = 0
        with UndoContext("PasteAnimation"):
            for ctrl in sel:
                clean = self._clean_name(ctrl)
                data = self.copied_anim.get(ctrl) or self.copied_anim.get(clean)
                if data:
                    self._apply_animation(ctrl, data, start_frame, end_frame, mirror_mode=False)
                    applied_count += 1

        cmds.inViewMessage(
            amg=f"Pasted animation onto <hl>{applied_count}</hl> controls ({start_frame}..{end_frame}).",
            pos="topCenter", fade=True
        )
        return True

    # --- SMART MIRROR / FLIP (POSE & ANIMATION) ---

    def smart_mirror_pose(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select controller(s) to Mirror/Flip Pose!")
            return False

        flip_pairs = set()
        for ctrl in sel:
            partner = self._get_partner(ctrl)
            if partner and partner != ctrl and partner in sel:
                pair = tuple(sorted([ctrl, partner]))
                flip_pairs.add(pair)

        with UndoContext("SmartMirrorPose"):
            if flip_pairs:
                for ctrl_a, ctrl_b in flip_pairs:
                    data_a = self._read_transforms(ctrl_a)
                    data_b = self._read_transforms(ctrl_b)
                    self._apply_transforms(ctrl_a, data_b, mirror_mode=True)
                    self._apply_transforms(ctrl_b, data_a, mirror_mode=True)
                cmds.inViewMessage(amg=f"Pose <hl>Flip</hl> executed on {len(flip_pairs) * 2} controls.", pos="topCenter", fade=True)
            else:
                mirrored_count = 0
                for ctrl in sel:
                    partner = self._get_partner(ctrl)
                    if partner and partner != ctrl and cmds.objExists(partner):
                        src_data = self._read_transforms(ctrl)
                        self._apply_transforms(partner, src_data, mirror_mode=True)
                        mirrored_count += 1
                if mirrored_count > 0:
                    cmds.inViewMessage(amg=f"Pose <hl>Mirror</hl> applied to {mirrored_count} opposite controls.", pos="topCenter", fade=True)
                else:
                    cmds.warning("No symmetrical opposite controllers found!")
        return True

    def smart_mirror_animation(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select controller(s) to Mirror/Flip Animation!")
            return False

        start_frame, end_frame = self._get_time_range()

        flip_pairs = set()
        for ctrl in sel:
            partner = self._get_partner(ctrl)
            if partner and partner != ctrl and partner in sel:
                pair = tuple(sorted([ctrl, partner]))
                flip_pairs.add(pair)

        with UndoContext("SmartMirrorAnimation"):
            if flip_pairs:
                for ctrl_a, ctrl_b in flip_pairs:
                    anim_a = self._read_animation(ctrl_a, start_frame, end_frame)
                    anim_b = self._read_animation(ctrl_b, start_frame, end_frame)
                    self._apply_animation(ctrl_a, anim_b, start_frame, end_frame, mirror_mode=True)
                    self._apply_animation(ctrl_b, anim_a, start_frame, end_frame, mirror_mode=True)

                cmds.inViewMessage(
                    amg=f"Animation <hl>Flip</hl> executed on {len(flip_pairs) * 2} controls ({start_frame}..{end_frame}).",
                    pos="topCenter", fade=True
                )
            else:
                mirrored_count = 0
                for ctrl in sel:
                    partner = self._get_partner(ctrl)
                    if partner and partner != ctrl and cmds.objExists(partner):
                        src_anim = self._read_animation(ctrl, start_frame, end_frame)
                        if src_anim:
                            self._apply_animation(partner, src_anim, start_frame, end_frame, mirror_mode=True)
                            mirrored_count += 1

                if mirrored_count > 0:
                    cmds.inViewMessage(
                        amg=f"Animation <hl>Mirror</hl> applied to {mirrored_count} opposite controls ({start_frame}..{end_frame}).",
                        pos="topCenter", fade=True
                    )
                else:
                    cmds.warning("No symmetrical opposite controllers with animation found!")

        return True