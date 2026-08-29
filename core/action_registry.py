"""
Action Registry for DooAnimKit.
Maintains action database, connects UI widgets, handles universal bake logic,
and provides entry points for Kimodo AI text-to-motion generation.
"""

import maya.cmds as cmds
from DooAnimKit.ui.viewport_aim_hud import ViewportAimHUD


class ActionRegistry:
    def __init__(self, main_window):
        self.win = main_window
        self.actions = {}
        self._register_default_actions()

    def register(self, action_id, name, callback, category="General", color="#3E8E41"):
        """Registers an action with id, label, callback, category, and UI color."""
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

    def open_kimodo_window(self):
        """Opens NVIDIA Kimodo Text-to-Motion floating generator."""
        from DooAnimKit.ui.kimodo_dialog import KimodoMotionDialog
        if hasattr(self.win, "kimodo_window") and self.win.kimodo_window is not None:
            try:
                self.win.kimodo_window.close()
            except Exception:
                pass
        self.win.kimodo_window = KimodoMotionDialog(main_window=self.win, parent=self.win)
        self.win.kimodo_window.show()

    # --- UNIVERSAL BAKE LOGIC ---

    def universal_bake_selected(self):
        """Bakes selected Temp Controls, Temp Aim setups, or Temp IK setups."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select a Temp Control, Aim Locator, or Temp IK element to bake!")
            return

        # 1. Check for Temp Aim
        aim_nodes = [obj for obj in sel if "_Aim_" in obj or "_Up_" in obj or "_TempAim_" in obj]
        if aim_nodes and hasattr(self.win, "temp_aim_engine"):
            self.win.temp_aim_engine.bake_and_clean()
            return

        # 2. Check for Temp IK
        ik_nodes = [obj for obj in sel if "_TempIK_" in obj]
        if ik_nodes and hasattr(self.win, "temp_ik_mgr"):
            if self.win.temp_ik_mgr.bake_selected(sel):
                return

        # 3. Regular Temp Controls
        if hasattr(self.win, "temp_ctrl_mgr"):
            self.win.temp_ctrl_mgr.bake_selected()

    def universal_bake_all(self):
        """Bakes and cleans ALL Temp Controls, Temp Aim setups, and Temp IK across the scene."""
        # 1. Bake all Aim setups
        aim_temps = cmds.ls("*_TempAim_GRP*", "*_Aim_TARGET*", "*_Aim_LOC*", type="transform") or []
        if aim_temps and hasattr(self.win, "temp_aim_engine"):
            try:
                self.win.temp_aim_engine.bake_and_clean()
            except Exception as e:
                cmds.warning(f"Temp Aim bake all warning: {e}")

        # 2. Bake all Temp IK setups
        if hasattr(self.win, "temp_ik_mgr"):
            try:
                self.win.temp_ik_mgr.bake_all()
            except Exception as e:
                cmds.warning(f"Temp IK bake all warning: {e}")

        # 3. Bake all Temp Controls and reset Offset
        if hasattr(self.win, "temp_ctrl_mgr"):
            try:
                self.win.temp_ctrl_mgr.bake_back_all()
            except Exception as e:
                cmds.warning(f"Temp Controls bake all warning: {e}")

        cmds.inViewMessage(amg="<hl>Bake All</hl>: All temporary controls baked & scene cleaned.", pos="topCenter", fade=True)

    # --- ACTIONS CATALOG ---

    def _register_default_actions(self):
        # Temp Controls
        self.register("temp_smart", "Smart", self.win.temp_ctrl_mgr.create_smart, "Temp Controls", "#1976D2")
        self.register("temp_aim_create", "Aim", self.open_temp_aim_window, "Temp Controls", "#00BCD4")
        if hasattr(self.win, "temp_ik_mgr"):
            self.register("temp_ik_create", "Temp IK", self.win.temp_ik_mgr.create_temp_ik, "Temp Controls", "#00897B")

        # Pose & AI
        self.register("copy_pose", "Copy", self.win.pose_mirror_engine.copy_pose, "Pose", "#3949AB")
        self.register("paste_pose", "Paste", self.win.pose_mirror_engine.paste_pose, "Pose", "#3949AB")
        self.register("mirror_pose", "Mirror", self.win.pose_mirror_engine.smart_mirror_pose, "Pose", "#1E88E5")
        self.register("kimodo_gen", "🤖 Kimodo Motion...", self.open_kimodo_window, "Pose", "#00897B")
        if hasattr(self.win, "ai_pose_matcher"):
            self.register("ai_pose_image", "🤖 Pose from Image", self.win.ai_pose_matcher.process_canvas_image, "Pose", "#8E24AA")

        # Animation
        self.register("copy_anim", "Copy", self.win.pose_mirror_engine.copy_animation, "Animation", "#00897B")
        self.register("paste_anim", "Paste", self.win.pose_mirror_engine.paste_animation, "Animation", "#00897B")
        self.register("mirror_anim", "Mirror", self.win.pose_mirror_engine.smart_mirror_animation, "Animation", "#039BE5")

        # Bake
        self.register("bake_selected", "Selected", self.universal_bake_selected, "Bake", "#43A047")
        self.register("temp_bake_all", "All", self.universal_bake_all, "Bake", "#2E7D32")

        # Direct Tools
        self.register("temp_offset_toggle", "Offset", self.win.temp_ctrl_mgr.toggle_offset_mode, "Direct", "#E65100")
        self.register("trail_toggle", "Motion Trail", self.win.trail_mgr.toggle_motion_trail, "Direct", "#D81B60")
        self.register("scan_rig", "Scan Rig", self.win.pose_mirror_engine.scan_selected_rig, "Direct", "#5E35B1")
        self.register("default_pose", "Default Pose", self.win.pose_mirror_engine.reset_to_default_pose, "Direct", "#00838F")

    def execute(self, action_id):
        """Executes the action callback by ID."""
        if action_id in self.actions:
            self.actions[action_id]["callback"]()

    def get_action_list(self):
        """Returns action dictionary list for populating menus and canvas buttons."""
        return list(self.actions.values())