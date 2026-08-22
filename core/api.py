"""
Public Python API for DooAnimKit.
Exposes standalone functions callable directly via Maya Hotkey Editor or Shelf buttons.
"""

import maya.cmds as cmds

_global_instances = {}


def _get_engine(engine_name):
    """Lazy loader to get or initialize engine singleton instances."""
    if engine_name not in _global_instances:
        if engine_name == "temp_ctrl_mgr":
            from DooAnimKit.core.temp_control import TempControlManager
            _global_instances[engine_name] = TempControlManager()
        elif engine_name == "pose_mirror_engine":
            from DooAnimKit.core.mirror import PoseMirrorEngine
            _global_instances[engine_name] = PoseMirrorEngine()
        elif engine_name == "temp_aim_engine":
            from DooAnimKit.core.temp_aim import TempAimEngine
            _global_instances[engine_name] = TempAimEngine()
        elif engine_name == "trail_mgr":
            from DooAnimKit.core.motion_trail import MotionTrailManager
            _global_instances[engine_name] = MotionTrailManager()
        elif engine_name == "tween_engine":
            from DooAnimKit.core.tween_engine import TweenEngine
            _global_instances[engine_name] = TweenEngine()
    return _global_instances[engine_name]


# --- TWEEN ENGINE (HOTKEYS) ---

def tween_step_left():
    """Nudges keyframe -5% towards previous neighbor."""
    _get_engine("tween_engine").step_nudge(direction=-1, step_percent=5.0)

def tween_step_right():
    """Nudges keyframe +5% towards next neighbor."""
    _get_engine("tween_engine").step_nudge(direction=1, step_percent=5.0)

def tween_breakdown_50():
    """Snaps to exact 50% midpoint breakdown."""
    _get_engine("tween_engine").tween_absolute(percentage=50.0)


# --- TEMP CONTROLS & AIM ---

def create_smart():
    _get_engine("temp_ctrl_mgr").create_smart()

def toggle_offset_mode():
    _get_engine("temp_ctrl_mgr").toggle_offset_mode()

def create_pivot_locator():
    _get_engine("temp_ctrl_mgr").create_pivot_locator()

def apply_pivot_locator():
    _get_engine("temp_ctrl_mgr").apply_pivot_locator()

def create_temp_aim():
    from DooAnimKit.ui.viewport_aim_hud import ViewportAimHUD
    aim_eng = _get_engine("temp_aim_engine")
    if aim_eng.create_setup():
        hud = ViewportAimHUD(aim_eng)
        hud.show()


# --- POSE & ANIMATION ---

def copy_pose():
    _get_engine("pose_mirror_engine").copy_pose()

def paste_pose():
    _get_engine("pose_mirror_engine").paste_pose()

def mirror_pose():
    _get_engine("pose_mirror_engine").smart_mirror_pose()

def copy_animation():
    _get_engine("pose_mirror_engine").copy_animation()

def paste_animation():
    _get_engine("pose_mirror_engine").paste_animation()

def mirror_animation():
    _get_engine("pose_mirror_engine").smart_mirror_animation()

def scan_rig():
    _get_engine("pose_mirror_engine").scan_selected_rig()

def reset_default_pose():
    _get_engine("pose_mirror_engine").reset_to_default_pose()


# --- BAKE & TRAILS ---

def bake_selected():
    sel = cmds.ls(selection=True, type="transform") or []
    if not sel:
        cmds.warning("Please select an element to bake!")
        return
    aim_eng = _get_engine("temp_aim_engine")
    if not aim_eng.bake_selected(sel):
        _get_engine("temp_ctrl_mgr").bake_selected()

def bake_all():
    _get_engine("temp_aim_engine").bake_all()
    _get_engine("temp_ctrl_mgr").bake_back_all()

def toggle_bake_sampling():
    _get_engine("temp_ctrl_mgr").toggle_bake_mode()

def toggle_motion_trail():
    _get_engine("trail_mgr").toggle_motion_trail()