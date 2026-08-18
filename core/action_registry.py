import maya.cmds as cmds
from DooAnimKit.ui.viewport_aim_hud import ViewportAimHUD


class ActionRegistry:
    """Registry for all DooAnimKit tools mapped cleanly to Categories."""

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
        if self.win.temp_aim_engine.create_setup():
            if hasattr(self.win, "aim_window") and self.win.aim_window is not None:
                try:
                    self.win.aim_window.close()
                except Exception:
                    pass
            self.win.aim_window = ViewportAimHUD(self.win.temp_aim_engine, parent=self.win)
            self.win.aim_window.show()

    def universal_bake_selected(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select an element in Maya to bake!")
            return

        aim_handled = False
        for item in sel:
            if "_Aim_" in item or "_Up_VECTOR" in item or "_TempAim" in item:
                self.win.temp_aim_engine.bake_and_clean()
                aim_handled = True
                break

        if not aim_handled:
            self.win.temp_ctrl_mgr.bake_selected()

    def _register_default_actions(self):
        # Temp Controls
        self.register("temp_smart", "Smart", self.win.temp_ctrl_mgr.create_smart, "Temp Controls", "#1976D2")
        self.register("temp_aim_create", "Aim", self.open_temp_aim_window, "Temp Controls", "#00BCD4")

        # Pose
        self.register("copy_pose", "Copy", self.win.pose_mirror_engine.copy_pose, "Pose", "#3949AB")
        self.register("paste_pose", "Paste", self.win.pose_mirror_engine.paste_pose, "Pose", "#3949AB")
        self.register("mirror_pose", "Mirror", self.win.pose_mirror_engine.smart_mirror_pose, "Pose", "#1E88E5")

        # Animation
        self.register("copy_anim", "Copy", self.win.pose_mirror_engine.copy_animation, "Animation", "#00897B")
        self.register("paste_anim", "Paste", self.win.pose_mirror_engine.paste_animation, "Animation", "#00897B")
        self.register("mirror_anim", "Mirror", self.win.pose_mirror_engine.smart_mirror_animation, "Animation", "#039BE5")

        # Bake
        self.register("bake_selected", "Selected", self.universal_bake_selected, "Bake", "#43A047")
        self.register("temp_bake_all", "All", self.win.temp_ctrl_mgr.bake_back_all, "Bake", "#2E7D32")

        # Standalone Tools
        self.register("temp_offset_toggle", "Offset", self.win.temp_ctrl_mgr.toggle_offset_mode, "Direct", "#E65100")
        self.register("trail_toggle", "Motion Trail", self.win.trail_mgr.toggle_motion_trail, "Direct", "#D81B60")
        self.register("scan_rig", "Scan Rig", self.win.pose_mirror_engine.scan_selected_rig, "Direct", "#5E35B1")
        self.register("default_pose", "Default Pose", self.win.pose_mirror_engine.reset_to_default_pose, "Direct", "#00838F")

    def execute(self, action_id):
        if action_id in self.actions:
            self.actions[action_id]["callback"]()

    def get_action_list(self):
        return list(self.actions.values())