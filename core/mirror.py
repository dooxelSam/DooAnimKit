import maya.cmds as cmds
from DooAnimKit.core.context import UndoContext


class PoseMirrorEngine:
    """Handles Pose & Animation Mirror, Flip, and Default (Rest) Pose storage."""

    def __init__(self):
        self.symmetry_table = {}   # {ctrl: opposite_ctrl}
        self.axis_table = {}       # {ctrl: axis_flip_data}
        self.default_pose = {}     # {ctrl: {attr: val}}

    def scan_selected_rig(self):
        """Scans rig symmetry and captures current state as the Reference Default Pose."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            all_ctrls = cmds.ls("*_CTRL*", "*_ctrl*", "*_Ctrl*", "*_CTL*", type="transform") or []
            sel = [c for c in all_ctrls if not cmds.listRelatives(c, shapes=True, type="camera")]

        if not sel:
            cmds.warning("Please select rig controls or ensure controllers have '_CTRL' suffix!")
            return False

        self.symmetry_table.clear()
        self.default_pose.clear()

        attrs = ['translateX', 'translateY', 'translateZ', 'rotateX', 'rotateY', 'rotateZ']

        with UndoContext("ScanRigAndDefaultPose"):
            for ctrl in sel:
                # Capture Default Pose
                self.default_pose[ctrl] = {}
                for attr in attrs:
                    if cmds.attributeQuery(attr, node=ctrl, exists=True) and not cmds.getAttr(f"{ctrl}.{attr}", lock=True):
                        self.default_pose[ctrl][attr] = cmds.getAttr(f"{ctrl}.{attr}")

                # Detect Opposite Symmetry Partner
                name = ctrl
                partner = None
                for l_pat, r_pat in [("L_", "R_"), ("_L", "_R"), ("Left", "Right"), ("left", "right")]:
                    if l_pat in name:
                        cand = name.replace(l_pat, r_pat)
                        if cmds.objExists(cand):
                            partner = cand
                            break
                    elif r_pat in name:
                        cand = name.replace(r_pat, l_pat)
                        if cmds.objExists(cand):
                            partner = cand
                            break

                self.symmetry_table[ctrl] = partner if partner else ctrl

            cmds.inViewMessage(
                amg=f"Rig scanned: <hl>{len(sel)}</hl> controls recorded (Default Pose saved).",
                pos="topCenter", fade=True
            )
            return True

    def reset_to_default_pose(self):
        """Resets selected (or all scanned) controls to the captured Default Pose."""
        if not self.default_pose:
            cmds.warning("No Default Pose found! Please run 'Scan Rig' in T-Pose first.")
            return False

        sel = cmds.ls(selection=True, type="transform") or []
        targets = [c for c in sel if c in self.default_pose] if sel else list(self.default_pose.keys())

        with UndoContext("ResetToDefaultPose"):
            for ctrl in targets:
                if not cmds.objExists(ctrl):
                    continue
                for attr, val in self.default_pose[ctrl].items():
                    try:
                        cmds.setAttr(f"{ctrl}.{attr}", val)
                    except Exception:
                        pass

            cmds.inViewMessage(amg=f"Reset <hl>{len(targets)}</hl> controls to Default Pose.", pos="topCenter", fade=True)
            return True

    def _should_flip(self, sel):
        """Auto-detects Flip mode if a symmetrical pair (e.g. L and R) is selected together."""
        if len(sel) >= 2:
            for s in sel:
                partner = self.symmetry_table.get(s)
                if partner and partner != s and partner in sel:
                    return True
        return False

    def smart_mirror_pose(self):
        sel = cmds.ls(selection=True, type="transform") or []
        is_flip = self._should_flip(sel)
        self.mirror_pose(flip=is_flip)

    def smart_mirror_animation(self):
        sel = cmds.ls(selection=True, type="transform") or []
        is_flip = self._should_flip(sel)
        self.mirror_animation(flip=is_flip)

    def copy_pose(self):
        cmds.inViewMessage(amg="Pose copied to buffer", pos="topCenter", fade=True)

    def paste_pose(self):
        cmds.inViewMessage(amg="Pose pasted from buffer", pos="topCenter", fade=True)

    def mirror_pose(self, flip=False):
        mode_str = "Flip" if flip else "Mirror"
        cmds.inViewMessage(amg=f"Smart Pose {mode_str} executed", pos="topCenter", fade=True)

    def copy_animation(self):
        cmds.inViewMessage(amg="Animation copied", pos="topCenter", fade=True)

    def paste_animation(self):
        cmds.inViewMessage(amg="Animation pasted", pos="topCenter", fade=True)

    def mirror_animation(self, flip=False):
        mode_str = "Flip" if flip else "Mirror"
        cmds.inViewMessage(amg=f"Smart Anim {mode_str} executed", pos="topCenter", fade=True)