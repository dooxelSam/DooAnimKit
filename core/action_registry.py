"""
Action Registry for DooAnimKit.
Registers all core tools: Tween, Time Shift, Temp Controls, Space Switching, Pose, Animation, Bake.
"""

import maya.cmds as cmds
import maya.mel as mel
from DooAnimKit.ui.viewport_aim_hud import ViewportAimHUD
from DooAnimKit.core.space_switch import SpaceSwitchEngine
from DooAnimKit.core.context import UndoContext


class ActionRegistry:
    def __init__(self, main_window):
        self.win = main_window
        self.actions = {}
        self.space_engine = SpaceSwitchEngine()
        self._register_default_actions()

    def register(self, action_id, name, callback, category="General", color="#3E8E41"):
        self.actions[action_id] = {
            "id": action_id,
            "name": name,
            "callback": callback,
            "category": category,
            "color": color
        }

    # --- TWEEN & TIME SHIFT HELPERS ---

    def _shift_selected_keys(self, offset):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Select animated controller(s) to shift keys!")
            return
        with UndoContext("ShiftKeys"):
            cmds.keyframe(sel, edit=True, relative=True, timeChange=offset)

    def _cascade_shift_keys(self, step=1, reverse=False):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Select controllers in sequence for cascade overlap!")
            return
        ordered = list(reversed(sel)) if reverse else list(sel)
        with UndoContext("CascadeShift"):
            for idx, ctrl in enumerate(ordered):
                shift = idx * step
                if shift != 0:
                    cmds.keyframe(ctrl, edit=True, relative=True, timeChange=shift)

    def _tween_percent(self, pct=50.0):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Select animated controller(s) for Tween!")
            return
        curr_t = cmds.currentTime(query=True)
        factor = pct / 100.0

        with UndoContext("TweenKey"):
            for node in sel:
                for attr in ["translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"]:
                    full_attr = f"{node}.{attr}"
                    if not cmds.attributeQuery(attr, node=node, exists=True):
                        continue

                    prev_keys = cmds.keyframe(full_attr, query=True, time=(curr_t - 9999, curr_t - 0.001), timeChange=True) or []
                    next_keys = cmds.keyframe(full_attr, query=True, time=(curr_t + 0.001, curr_t + 9999), timeChange=True) or []

                    if not prev_keys or not next_keys:
                        continue

                    prev_t = prev_keys[-1]
                    next_t = next_keys[0]

                    prev_val = cmds.keyframe(full_attr, query=True, time=(prev_t, prev_t), valueChange=True)[0]
                    next_val = cmds.keyframe(full_attr, query=True, time=(next_t, next_t), valueChange=True)[0]

                    new_val = prev_val + (next_val - prev_val) * factor
                    cmds.setKeyframe(full_attr, time=curr_t, value=new_val)

    # --- AIM WINDOW ---

    def open_temp_aim_window(self):
        if hasattr(self.win, "temp_aim_engine") and self.win.temp_aim_engine.create_setup():
            if hasattr(self.win, "aim_window") and self.win.aim_window is not None:
                try:
                    self.win.aim_window.close()
                except Exception:
                    pass
            self.win.aim_window = ViewportAimHUD(self.win.temp_aim_engine, parent=self.win)
            self.win.aim_window.show()

    # --- UNIVERSAL BAKE LOGIC ---

    def universal_bake_selected(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select an element to bake!")
            return

        aim_nodes = [obj for obj in sel if "_Aim_" in obj or "_Up_" in obj or "_TempAim_" in obj]
        if aim_nodes and hasattr(self.win, "temp_aim_engine"):
            self.win.temp_aim_engine.bake_and_clean()
            return

        space_nodes = [obj for obj in sel if "_SpaceSwitch_LOC" in obj]
        if space_nodes:
            self.space_engine.bake_and_restore()
            return

        if hasattr(self.win, "temp_ctrl_mgr"):
            self.win.temp_ctrl_mgr.bake_selected()

    def universal_bake_all(self):
        aim_temps = cmds.ls("*_TempAim_GRP*", "*_Aim_TARGET*", "*_Aim_LOC*", type="transform") or []
        if aim_temps and hasattr(self.win, "temp_aim_engine"):
            try:
                self.win.temp_aim_engine.bake_all()
            except Exception:
                pass

        try:
            self.space_engine.bake_and_restore()
        except Exception:
            pass

        if hasattr(self.win, "temp_ctrl_mgr"):
            try:
                self.win.temp_ctrl_mgr.bake_back_all()
            except Exception:
                pass

        cmds.inViewMessage(amg="<hl>Bake All</hl>: Temporary setups baked & scene cleaned.", pos="topCenter", fade=True)

    # --- ACTIONS CATALOG ---

    def _register_default_actions(self):
        # 1. Tween
        self.register("tween_mid_50", "Tween 50% Breakdown", lambda: self._tween_percent(50.0), "Tween", "#6A1B9A")
        self.register("tween_step_left_20", "Tween Left (-20%)", lambda: self._tween_percent(30.0), "Tween", "#EC407A")
        self.register("tween_step_right_20", "Tween Right (+20%)", lambda: self._tween_percent(70.0), "Tween", "#AB47BC")
        self.register("tween_snap_left", "Snap Left (100%)", lambda: self._tween_percent(0.0), "Tween", "#D81B60")
        self.register("tween_snap_right", "Snap Right (100%)", lambda: self._tween_percent(100.0), "Tween", "#8E24AA")

        # 2. Time Shift & Cascade
        self.register("shift_fwd_1", "Shift Forward (+1f)", lambda: self._shift_selected_keys(1), "Time Shift", "#00796B")
        self.register("shift_bwd_1", "Shift Backward (-1f)", lambda: self._shift_selected_keys(-1), "Time Shift", "#00796B")
        self.register("shift_fwd_5", "Shift Forward (+5f)", lambda: self._shift_selected_keys(5), "Time Shift", "#004D40")
        self.register("shift_bwd_5", "Shift Backward (-5f)", lambda: self._shift_selected_keys(-5), "Time Shift", "#004D40")
        self.register("cascade_fwd_1", "Cascade Overlap (+1f)", lambda: self._cascade_shift_keys(1, False), "Time Shift", "#00838F")
        self.register("cascade_bwd_1", "Cascade Overlap Reverse", lambda: self._cascade_shift_keys(1, True), "Time Shift", "#00838F")

        # 3. Temp Controls & Space
        if hasattr(self.win, "temp_ctrl_mgr"):
            self.register("temp_smart", "Smart Temp Control", self.win.temp_ctrl_mgr.create_smart, "Temp Controls", "#1976D2")
            self.register("temp_set_pivot", "Set Pivot Loc", self.win.temp_ctrl_mgr.create_pivot_locator, "Temp Controls", "#AB47BC")
            self.register("temp_bake_pivot", "Bake Pivot", self.win.temp_ctrl_mgr.apply_pivot_locator, "Temp Controls", "#7E57C2")

        self.register("space_world", "Switch to World Space", self.space_engine.switch_to_world, "Temp Controls", "#00838F")
        self.register("space_bake", "Bake & Restore Space", self.space_engine.bake_and_restore, "Temp Controls", "#006064")

        if hasattr(self.win, "temp_aim_engine"):
            self.register("temp_aim_create", "Aim Setup", self.open_temp_aim_window, "Temp Controls", "#00BCD4")

        # 4. Pose
        if hasattr(self.win, "pose_mirror_engine"):
            self.register("copy_pose", "Copy Pose", self.win.pose_mirror_engine.copy_pose, "Pose", "#3949AB")
            self.register("paste_pose", "Paste Pose", self.win.pose_mirror_engine.paste_pose, "Pose", "#3949AB")
            self.register("mirror_pose", "Mirror / Flip Pose", self.win.pose_mirror_engine.smart_mirror_pose, "Pose", "#1E88E5")

        # 5. Animation
        if hasattr(self.win, "pose_mirror_engine"):
            self.register("copy_anim", "Copy Animation", self.win.pose_mirror_engine.copy_animation, "Animation", "#00897B")
            self.register("paste_anim", "Paste Animation", self.win.pose_mirror_engine.paste_animation, "Animation", "#00897B")
            self.register("mirror_anim", "Mirror / Flip Animation", self.win.pose_mirror_engine.smart_mirror_animation, "Animation", "#039BE5")

        if hasattr(self.win, "euler_filter"):
            self.register("smart_euler_filter", "Smart Euler Filter", self.win.euler_filter.apply_smart_filter, "Animation", "#00ACC1")

        # 6. Bake
        self.register("bake_selected", "Bake Selected", self.universal_bake_selected, "Bake", "#43A047")
        self.register("temp_bake_all", "Bake All", self.universal_bake_all, "Bake", "#2E7D32")
        if hasattr(self.win, "temp_ctrl_mgr"):
            self.register("toggle_sampling", "Toggle: Keys / All", self.win.temp_ctrl_mgr.toggle_bake_mode, "Bake", "#FB8C00")

        # 7. Direct
        if hasattr(self.win, "temp_ctrl_mgr"):
            self.register("temp_offset_toggle", "Global Offset Mode", self.win.temp_ctrl_mgr.toggle_offset_mode, "Direct", "#E65100")
        if hasattr(self.win, "trail_mgr"):
            self.register("trail_toggle", "Motion Trail", self.win.trail_mgr.toggle_motion_trail, "Direct", "#D81B60")
        if hasattr(self.win, "pose_mirror_engine"):
            self.register("scan_rig", "Scan Rig (Validate Skeleton)", self.win.pose_mirror_engine.scan_selected_rig, "Direct", "#5E35B1")
            self.register("default_pose", "Reset to Default Pose", self.win.pose_mirror_engine.reset_to_default_pose, "Direct", "#00838F")

    def execute(self, action_id):
        if action_id in self.actions:
            self.actions[action_id]["callback"]()

    def get_action_list(self):
        return list(self.actions.values())