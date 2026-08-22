import maya.cmds as cmds
from DooAnimKit.core.context import UndoContext


class TweenEngine:
    """AnimBot-style keyframe tweening engine with incremental nudging and instant snap to neighbors."""

    CHANNELS = [
        "translateX", "translateY", "translateZ",
        "rotateX", "rotateY", "rotateZ",
        "scaleX", "scaleY", "scaleZ"
    ]

    def __init__(self):
        self.step_percent = 5.0

    def _get_target_objects(self):
        sel = cmds.ls(selection=True, type="transform") or []
        return sel

    def step_nudge(self, direction=-1, step_percent=5.0):
        """
        Shifts pose by +5% or -5% between previous and next neighbor keys continuously.
        direction = -1 (towards Left / Previous Key)
        direction = +1 (towards Right / Next Key)
        """
        targets = self._get_target_objects()
        if not targets:
            cmds.warning("Please select at least one controller to tween!")
            return False

        current_frame = cmds.currentTime(query=True)
        step = (float(step_percent) / 100.0) * direction
        applied_any = False

        with UndoContext("TweenStepNudge"):
            for node in targets:
                if not cmds.objExists(node):
                    continue

                for attr in self.CHANNELS:
                    full_attr = f"{node}.{attr}"
                    if not cmds.attributeQuery(attr, node=node, exists=True):
                        continue
                    if cmds.getAttr(full_attr, lock=True):
                        continue

                    prev_keys = cmds.keyframe(full_attr, query=True, time=(None, current_frame - 0.001), timeChange=True) or []
                    next_keys = cmds.keyframe(full_attr, query=True, time=(current_frame + 0.001, None), timeChange=True) or []

                    if not prev_keys or not next_keys:
                        continue

                    prev_time = prev_keys[-1]
                    next_time = next_keys[0]

                    prev_val = cmds.keyframe(full_attr, query=True, time=(prev_time, prev_time), valueChange=True)[0]
                    next_val = cmds.keyframe(full_attr, query=True, time=(next_time, next_time), valueChange=True)[0]

                    has_key = bool(cmds.keyframe(full_attr, query=True, time=(current_frame, current_frame), keyframeCount=True))
                    if has_key:
                        curr_val = cmds.keyframe(full_attr, query=True, time=(current_frame, current_frame), valueChange=True)[0]
                    else:
                        curr_val = cmds.getAttr(full_attr)

                    val_range = next_val - prev_val

                    if abs(val_range) > 1e-5:
                        current_factor = (curr_val - prev_val) / val_range
                        new_factor = current_factor + step
                        new_val = prev_val + val_range * new_factor
                    else:
                        new_val = curr_val

                    cmds.setKeyframe(full_attr, time=current_frame, value=new_val)
                    applied_any = True

        if applied_any:
            dir_str = "Left (-5%)" if direction < 0 else "Right (+5%)"
            cmds.inViewMessage(amg=f"Tween Nudge: <hl>{dir_str}</hl>", pos="topCenter", fade=True)
        return applied_any

    def snap_to_neighbor(self, direction=-1):
        """
        Instantly snaps and matches 100% of the neighbor pose at the current frame.
        direction = -1 -> 100% Left (Previous Key)
        direction = +1 -> 100% Right (Next Key)
        """
        targets = self._get_target_objects()
        if not targets:
            cmds.warning("Please select at least one controller!")
            return False

        current_frame = cmds.currentTime(query=True)
        applied_any = False

        with UndoContext("SnapToNeighbor"):
            for node in targets:
                if not cmds.objExists(node):
                    continue

                for attr in self.CHANNELS:
                    full_attr = f"{node}.{attr}"
                    if not cmds.attributeQuery(attr, node=node, exists=True):
                        continue
                    if cmds.getAttr(full_attr, lock=True):
                        continue

                    if direction < 0:
                        keys = cmds.keyframe(full_attr, query=True, time=(None, current_frame - 0.001), timeChange=True) or []
                        if not keys:
                            continue
                        target_time = keys[-1]
                    else:
                        keys = cmds.keyframe(full_attr, query=True, time=(current_frame + 0.001, None), timeChange=True) or []
                        if not keys:
                            continue
                        target_time = keys[0]

                    target_val = cmds.keyframe(full_attr, query=True, time=(target_time, target_time), valueChange=True)[0]
                    cmds.setKeyframe(full_attr, time=current_frame, value=target_val)
                    applied_any = True

        if applied_any:
            side_str = "Left (Previous Key)" if direction < 0 else "Right (Next Key)"
            cmds.inViewMessage(amg=f"Snapped 100% to <hl>{side_str}</hl>", pos="topCenter", fade=True)
        return applied_any

    def tween_absolute(self, percentage=50.0):
        """Snaps to exact percentage between neighbors (e.g. 50% breakdown)."""
        targets = self._get_target_objects()
        if not targets:
            cmds.warning("Please select at least one controller!")
            return False

        current_frame = cmds.currentTime(query=True)
        factor = float(percentage) / 100.0
        applied_any = False

        with UndoContext("TweenAbsolute"):
            for node in targets:
                if not cmds.objExists(node):
                    continue

                for attr in self.CHANNELS:
                    full_attr = f"{node}.{attr}"
                    if not cmds.attributeQuery(attr, node=node, exists=True):
                        continue
                    if cmds.getAttr(full_attr, lock=True):
                        continue

                    prev_keys = cmds.keyframe(full_attr, query=True, time=(None, current_frame - 0.001), timeChange=True) or []
                    next_keys = cmds.keyframe(full_attr, query=True, time=(current_frame + 0.001, None), timeChange=True) or []

                    if not prev_keys or not next_keys:
                        continue

                    prev_time = prev_keys[-1]
                    next_time = next_keys[0]

                    prev_val = cmds.keyframe(full_attr, query=True, time=(prev_time, prev_time), valueChange=True)[0]
                    next_val = cmds.keyframe(full_attr, query=True, time=(next_time, next_time), valueChange=True)[0]

                    new_val = prev_val + (next_val - prev_val) * factor
                    cmds.setKeyframe(full_attr, time=current_frame, value=new_val)
                    applied_any = True

        if applied_any:
            cmds.inViewMessage(amg=f"Tween set to <hl>{int(percentage)}%</hl>", pos="topCenter", fade=True)
        return applied_any