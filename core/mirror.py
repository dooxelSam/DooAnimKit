import maya.cmds as cmds
from DooAnimKit.core.context import UndoContext


class PoseMirrorEngine:
    """
    Handles Pose/Animation Copy, Paste, Smart Mirror/Flip, and Default Pose.
    Includes smart detection for FK chains vs IK controls.
    """

    CHANNELS = [
        "translateX", "translateY", "translateZ",
        "rotateX", "rotateY", "rotateZ",
        "scaleX", "scaleY", "scaleZ"
    ]

    def __init__(self):
        self.copied_pose = {}       # {ctrl_name: {attr: val}}
        self.symmetry_table = {}    # {ctrl_name: partner_ctrl_name}
        self.default_pose = {}      # {ctrl_name: {attr: val}}

    def _get_opposite_name(self, name):
        """Finds opposite control name based on standard rigging naming conventions."""
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
        """Retrieves mapped symmetry partner or dynamically resolves opposite name."""
        partner = self.symmetry_table.get(ctrl)
        if not partner or not cmds.objExists(partner):
            partner = self._get_opposite_name(ctrl)
            if partner:
                self.symmetry_table[ctrl] = partner
        return partner

    def _is_fk_control(self, ctrl):
        """Detects whether a controller is an FK rotational chain control."""
        name_lower = ctrl.lower()
        if "fk" in name_lower or "finger" in name_lower or "thumb" in name_lower:
            return True
        # If translate is locked/hidden and only rotate is available, it behaves as FK
        tx_settable = cmds.attributeQuery("translateX", node=ctrl, exists=True) and cmds.getAttr(f"{ctrl}.translateX", settable=True)
        rx_settable = cmds.attributeQuery("rotateX", node=ctrl, exists=True) and cmds.getAttr(f"{ctrl}.rotateX", settable=True)
        if rx_settable and not tx_settable:
            return True
        return False

    def _read_transforms(self, ctrl):
        """Safely reads settable transform channels for a control."""
        data = {}
        for attr in self.CHANNELS:
            full_attr = f"{ctrl}.{attr}"
            if cmds.attributeQuery(attr, node=ctrl, exists=True):
                if cmds.getAttr(full_attr, settable=True):
                    data[attr] = cmds.getAttr(full_attr)
        return data

    def _calculate_mirror_value(self, ctrl, attr, val):
        """Calculates mirrored value based on controller type (IK vs FK vs Center)."""
        is_fk = self._is_fk_control(ctrl)

        if is_fk:
            # FK controllers on standard rigs share symmetrical local axes (1:1 copy)
            return val
        else:
            # IK / World space controllers invert across the X-plane
            if attr in ("translateX", "rotateY", "rotateZ"):
                return -val
            return val

    def _apply_transforms(self, ctrl, data, mirror_mode=False):
        """Applies transform values with appropriate mirroring rules."""
        for attr, val in data.items():
            full_attr = f"{ctrl}.{attr}"
            if cmds.attributeQuery(attr, node=ctrl, exists=True):
                if cmds.getAttr(full_attr, settable=True):
                    final_val = self._calculate_mirror_value(ctrl, attr, val) if mirror_mode else val
                    try:
                        cmds.setAttr(full_attr, final_val)
                    except Exception:
                        pass

    # --- RIG SCAN & DEFAULT POSE ---

    def scan_selected_rig(self):
        """Scans selected controls, maps symmetry, and saves Default (Rest) Pose."""
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

        cmds.inViewMessage(
            amg=f"Rig scanned: <hl>{len(sel)}</hl> controls mapped (Default Pose saved).",
            pos="topCenter", fade=True
        )
        return True

    def reset_to_default_pose(self):
        """Resets selected (or all scanned) controls to the saved Default Pose."""
        if not self.default_pose:
            cmds.warning("No Default Pose found! Please run 'Scan Rig' in T-Pose first.")
            return False

        sel = cmds.ls(selection=True, type="transform") or []
        targets = [c for c in sel if c in self.default_pose] if sel else list(self.default_pose.keys())

        with UndoContext("ResetToDefaultPose"):
            for ctrl in targets:
                if cmds.objExists(ctrl):
                    self._apply_transforms(ctrl, self.default_pose[ctrl], mirror_mode=False)

        cmds.inViewMessage(amg=f"Reset <hl>{len(targets)}</hl> controls to Default Pose.", pos="topCenter", fade=True)
        return True

    # --- POSE COPY / PASTE ---

    def copy_pose(self):
        """Copies transform values for selected controllers."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select controllers to copy pose!")
            return False

        self.copied_pose.clear()
        for ctrl in sel:
            self.copied_pose[ctrl] = self._read_transforms(ctrl)

        cmds.inViewMessage(
            amg=f"Copied pose for <hl>{len(self.copied_pose)}</hl> controls.",
            pos="topCenter", fade=True
        )
        return True

    def paste_pose(self):
        """Applies copied pose onto selected controllers."""
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
                if ctrl in self.copied_pose:
                    self._apply_transforms(ctrl, self.copied_pose[ctrl], mirror_mode=False)
                    applied_count += 1

        cmds.inViewMessage(
            amg=f"Pasted pose onto <hl>{applied_count}</hl> matching controls.",
            pos="topCenter", fade=True
        )
        return True

    # --- ANIMATION COPY / PASTE ---

    def copy_animation(self):
        """Copies animation keys from selected controllers."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select controllers with keys to copy animation!")
            return False

        cmds.copyKey(sel, time=(), hierarchy="none", controlPoints=0, shape=0)
        cmds.inViewMessage(
            amg=f"Copied animation for <hl>{len(sel)}</hl> controls.",
            pos="topCenter", fade=True
        )
        return True

    def paste_animation(self):
        """Pastes animation keys onto selected controllers."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select controllers to paste animation onto!")
            return False

        with UndoContext("PasteAnimation"):
            cmds.pasteKey(sel, option="replace", connect=False)

        cmds.inViewMessage(
            amg=f"Pasted animation onto <hl>{len(sel)}</hl> controls.",
            pos="topCenter", fade=True
        )
        return True

    # --- SMART MIRROR / FLIP ---

    def smart_mirror_pose(self):
        """Intelligently detects whether to execute Mirror (Source -> Target) or Flip (Swap)."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select controller(s) to Mirror/Flip!")
            return False

        # Check if both symmetrical partners are selected (Flip Mode)
        flip_pairs = set()
        for ctrl in sel:
            partner = self._get_partner(ctrl)
            if partner and partner != ctrl and partner in sel:
                pair = tuple(sorted([ctrl, partner]))
                flip_pairs.add(pair)

        with UndoContext("SmartMirrorPose"):
            if flip_pairs:
                # --- FLIP MODE ---
                for ctrl_a, ctrl_b in flip_pairs:
                    data_a = self._read_transforms(ctrl_a)
                    data_b = self._read_transforms(ctrl_b)

                    self._apply_transforms(ctrl_a, data_b, mirror_mode=True)
                    self._apply_transforms(ctrl_b, data_a, mirror_mode=True)

                cmds.inViewMessage(
                    amg=f"Pose <hl>Flip</hl> executed on {len(flip_pairs) * 2} controls.",
                    pos="topCenter", fade=True
                )
            else:
                # --- MIRROR MODE ---
                mirrored_count = 0
                for ctrl in sel:
                    partner = self._get_partner(ctrl)
                    if partner and partner != ctrl and cmds.objExists(partner):
                        src_data = self._read_transforms(ctrl)
                        self._apply_transforms(partner, src_data, mirror_mode=True)
                        mirrored_count += 1

                if mirrored_count > 0:
                    cmds.inViewMessage(
                        amg=f"Pose <hl>Mirror</hl> copied from {mirrored_count} control(s) to opposite side.",
                        pos="topCenter", fade=True
                    )
                else:
                    cmds.warning("No symmetrical opposite controllers found for selection!")

        return True

    def smart_mirror_animation(self):
        """Placeholder for animation mirror logic."""
        self.smart_mirror_pose()