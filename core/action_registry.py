"""
Action Registry for DooAnimKit.
Maintains action database, connects UI widgets, and handles universal bake, pivot, tween, mirror, cascade & default pose logic.
"""

import maya.cmds as cmds
from DooAnimKit.ui.viewport_aim_hud import ViewportAimHUD


class ActionRegistry:
    def __init__(self, main_window):
        self.win = main_window
        self.actions = {}
        self._register_default_actions()

    def register(self, action_id, name, callback, category="General", color="#3E8E41"):
        """Registers an action with id, label, callback, category and UI color."""
        self.actions[action_id] = {
            "id": action_id,
            "name": name,
            "callback": callback,
            "category": category,
            "color": color
        }

    def open_temp_aim_window(self):
        """Creates setup preview and opens floating dialog."""
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
        """Bakes selected Temp Controls, Temp Aim setups, or Temp IK setups."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select a Temp Control, Aim Locator, or Temp IK element to bake!")
            return

        aim_nodes = [obj for obj in sel if "_Aim_" in obj or "_Up_" in obj or "_TempAim_" in obj]
        if aim_nodes and hasattr(self.win, "temp_aim_engine"):
            self.win.temp_aim_engine.bake_and_clean()
            return

        ik_nodes = [obj for obj in sel if "_TempIK_" in obj]
        if ik_nodes and hasattr(self.win, "temp_ik_mgr"):
            if self.win.temp_ik_mgr.bake_selected(sel):
                return

        if hasattr(self.win, "temp_ctrl_mgr"):
            self.win.temp_ctrl_mgr.bake_selected()

    def universal_bake_all(self):
        """Bakes and cleans ALL Temp Controls, Temp Aim setups, and Temp IK across the scene."""
        aim_temps = cmds.ls("*_TempAim_GRP*", "*_Aim_TARGET*", "*_Aim_LOC*", type="transform") or []
        if aim_temps and hasattr(self.win, "temp_aim_engine"):
            try:
                self.win.temp_aim_engine.bake_all()
            except Exception as e:
                cmds.warning(f"Temp Aim bake all warning: {e}")

        if hasattr(self.win, "temp_ik_mgr"):
            try:
                self.win.temp_ik_mgr.bake_all()
            except Exception as e:
                cmds.warning(f"Temp IK bake all warning: {e}")

        if hasattr(self.win, "temp_ctrl_mgr"):
            try:
                self.win.temp_ctrl_mgr.bake_back_all()
            except Exception as e:
                cmds.warning(f"Temp Controls bake all warning: {e}")

        cmds.inViewMessage(amg="<hl>Bake All</hl>: All temporary controls baked & scene cleaned.", pos="topCenter", fade=True)

    # --- ACTIONS CATALOG ---

    def _register_default_actions(self):
        # 1. Tween Category
        self.register("tween_step_left", "Tween Left (-5%)", lambda: self.win.tween_engine.step_nudge(-1, 5.0), "Tween", "#EC407A")
        self.register("tween_step_right", "Tween Right (+5%)", lambda: self.win.tween_engine.step_nudge(1, 5.0), "Tween", "#AB47BC")
        self.register("tween_mid_50", "Tween 50% (Breakdown)", lambda: self.win.tween_engine.tween_absolute(50.0), "Tween", "#6A1B9A")

        # 2. Time Shift & Cascade Category
        if hasattr(self.win, "time_shift_engine"):
            self.register("cascade_fwd_1", "Cascade Overlap (+1f)", lambda: self.win.time_shift_engine.cascade_shift(step=1, reverse=False), "Time Shift", "#00897B")
            self.register("cascade_fwd_2", "Cascade Overlap (+2f)", lambda: self.win.time_shift_engine.cascade_shift(step=2, reverse=False), "Time Shift", "#00796B")
            self.register("cascade_bwd_1", "Cascade Overlap (-1f)", lambda: self.win.time_shift_engine.cascade_shift(step=1, reverse=True), "Time Shift", "#0097A7")
            self.register("shift_left_1", "Shift Left (-1f)", lambda: self.win.time_shift_engine.shift_selected(frame_offset=-1), "Time Shift", "#00ACC1")
            self.register("shift_right_1", "Shift Right (+1f)", lambda: self.win.time_shift_engine.shift_selected(frame_offset=1), "Time Shift", "#26C6DA")

        # 3. Temp Controls Category
        self.register("temp_smart", "Smart Temp Control", self.win.temp_ctrl_mgr.create_smart, "Temp Controls", "#1976D2")
        self.register("temp_aim_create", "Aim Setup", self.open_temp_aim_window, "Temp Controls", "#00BCD4")
        if hasattr(self.win, "temp_ik_mgr"):
            self.register("temp_ik_create", "Temp IK", self.win.temp_ik_mgr.create_temp_ik, "Temp Controls", "#00897B")
        self.register("temp_set_pivot", "Set Pivot Loc", self.win.temp_ctrl_mgr.create_pivot_locator, "Temp Controls", "#AB47BC")
        self.register("temp_bake_pivot", "Bake Pivot", self.win.temp_ctrl_mgr.apply_pivot_locator, "Temp Controls", "#7E57C2")

        # 4. Pose Category
        self.register("copy_pose", "Copy Pose", self.win.pose_mirror_engine.copy_pose, "Pose", "#3949AB")
        self.register("paste_pose", "Paste Pose", self.win.pose_mirror_engine.paste_pose, "Pose", "#3949AB")
        self.register("mirror_pose", "Mirror / Flip Pose", self.win.pose_mirror_engine.smart_mirror_pose, "Pose", "#1E88E5")

        # 5. Animation Category
        self.register("copy_anim", "Copy Animation", self.win.pose_mirror_engine.copy_animation, "Animation", "#00897B")
        self.register("paste_anim", "Paste Animation", self.win.pose_mirror_engine.paste_animation, "Animation", "#00897B")
        self.register("mirror_anim", "Mirror / Flip Animation", self.win.pose_mirror_engine.smart_mirror_animation, "Animation", "#039BE5")
        self.register("smart_euler_filter", "Smart Euler Filter", self.win.euler_filter.apply_smart_filter, "Animation", "#00ACC1")

        # 6. Bake Category
        self.register("bake_selected", "Bake Selected", self.universal_bake_selected, "Bake", "#43A047")
        self.register("temp_bake_all", "Bake All", self.universal_bake_all, "Bake", "#2E7D32")
        self.register("toggle_sampling", "Toggle: Keys / All", self.win.temp_ctrl_mgr.toggle_bake_mode, "Bake", "#FB8C00")

        # 7. Direct Tools
        self.register("temp_offset_toggle", "Global Offset Mode", self.win.temp_ctrl_mgr.toggle_offset_mode, "Direct", "#E65100")
        self.register("trail_toggle", "Motion Trail", self.win.trail_mgr.toggle_motion_trail, "Direct", "#D81B60")
        self.register("scan_rig", "Scan Rig (Default Pose)", self.win.pose_mirror_engine.scan_selected_rig, "Direct", "#5E35B1")
        self.register("default_pose", "Reset to Default Pose", self.win.pose_mirror_engine.reset_to_default_pose, "Direct", "#00838F")

    def execute(self, action_id):
        """Executes action callback by ID."""
        if action_id in self.actions:
            self.actions[action_id]["callback"]()

    def get_action_list(self):
        """Returns list of all action dictionaries."""
        return list(self.actions.values())