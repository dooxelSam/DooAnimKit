"""
Action Registry for DooAnimKit with Semantic Text-to-Pose support.
"""

import maya.cmds as cmds
try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets

from DooAnimKit.ui.viewport_aim_hud import ViewportAimHUD


class ActionRegistry:
    def __init__(self, main_window):
        self.win = main_window
        self.actions = {}
        self._register_default_actions()

    def register(self, action_id, name, callback, category="General", color="#3E8E41"):
        self.actions[action_id] = {
            "id": action_id,
            "name": name,
            "callback": callback,
            "category": category,
            "color": color
        }

    def open_temp_aim_window(self):
        if hasattr(self.win, "temp_aim_engine") and self.win.temp_aim_engine.create_setup():
            if hasattr(self.win, "aim_window") and self.win.aim_window is not None:
                try:
                    self.win.aim_window.close()
                except Exception:
                    pass
            self.win.aim_window = ViewportAimHUD(self.win.temp_aim_engine, parent=self.win)
            self.win.aim_window.show()

    def prompt_text_pose(self):
        """Opens prompt dialog for Text-to-Pose generation."""
        text, ok = QtWidgets.QInputDialog.getText(
            self.win, "Text-to-Pose Prompt",
            "Enter pose description (e.g. 'kneeling pistol shoot', 'crouch', 'combat stance'):"
        )
        if ok and text and hasattr(self.win, "semantic_pose_engine"):
            self.win.semantic_pose_engine.apply_pose_by_prompt(text)

    def universal_bake_selected(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select an element in Maya to bake!")
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
        if hasattr(self.win, "temp_aim_engine"):
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

    def _register_default_actions(self):
        # 1. Tween
        if hasattr(self.win, "tween_engine"):
            self.register("tween_step_left", "Tween Left (-5%)", lambda: self.win.tween_engine.step_nudge(-1, 5.0), "Tween", "#EC407A")
            self.register("tween_step_right", "Tween Right (+5%)", lambda: self.win.tween_engine.step_nudge(1, 5.0), "Tween", "#AB47BC")
            self.register("tween_mid_50", "Tween 50% (Breakdown)", lambda: self.win.tween_engine.tween_absolute(50.0), "Tween", "#6A1B9A")

        # 2. Time Shift & Cascade
        if hasattr(self.win, "time_shift_engine"):
            self.register("cascade_fwd_1", "Cascade Overlap (+1f)", lambda: self.win.time_shift_engine.cascade_shift(step=1, reverse=False), "Time Shift", "#00897B")
            self.register("cascade_fwd_2", "Cascade Overlap (+2f)", lambda: self.win.time_shift_engine.cascade_shift(step=2, reverse=False), "Time Shift", "#00796B")
            self.register("cascade_bwd_1", "Cascade Overlap (-1f)", lambda: self.win.time_shift_engine.cascade_shift(step=1, reverse=True), "Time Shift", "#0097A7")
            self.register("shift_left_1", "Shift Left (-1f)", lambda: self.win.time_shift_engine.shift_selected(frame_offset=-1), "Time Shift", "#00ACC1")
            self.register("shift_right_1", "Shift Right (+1f)", lambda: self.win.time_shift_engine.shift_selected(frame_offset=1), "Time Shift", "#26C6DA")

        # 3. Temp Controls
        if hasattr(self.win, "temp_ctrl_mgr"):
            self.register("temp_smart", "Smart Temp Control", self.win.temp_ctrl_mgr.create_smart, "Temp Controls", "#1976D2")
            self.register("temp_set_pivot", "Set Pivot Loc", self.win.temp_ctrl_mgr.create_pivot_locator, "Temp Controls", "#AB47BC")
            self.register("temp_bake_pivot", "Bake Pivot", self.win.temp_ctrl_mgr.apply_pivot_locator, "Temp Controls", "#7E57C2")

        if hasattr(self.win, "temp_aim_engine"):
            self.register("temp_aim_create", "Aim Setup", self.open_temp_aim_window, "Temp Controls", "#00BCD4")

        if hasattr(self.win, "temp_ik_mgr"):
            self.register("temp_ik_create", "Temp IK", self.win.temp_ik_mgr.create_temp_ik, "Temp Controls", "#00897B")

        # 4. Pose & Semantic Prompt
        self.register("prompt_pose", "💬 Pose by Text Prompt...", self.prompt_text_pose, "Pose", "#9C27B0")
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

        # 7. Direct Tools
        if hasattr(self.win, "temp_ctrl_mgr"):
            self.register("temp_offset_toggle", "Global Offset Mode", self.win.temp_ctrl_mgr.toggle_offset_mode, "Direct", "#E65100")
        if hasattr(self.win, "trail_mgr"):
            self.register("trail_toggle", "Motion Trail", self.win.trail_mgr.toggle_motion_trail, "Direct", "#D81B60")
        if hasattr(self.win, "pose_mirror_engine"):
            self.register("scan_rig", "Scan Rig (Default Pose)", self.win.pose_mirror_engine.scan_selected_rig, "Direct", "#5E35B1")
            self.register("default_pose", "Reset to Default Pose", self.win.pose_mirror_engine.reset_to_default_pose, "Direct", "#00838F")

    def execute(self, action_id):
        if action_id in self.actions:
            self.actions[action_id]["callback"]()

    def get_action_list(self):
        return list(self.actions.values())