import maya.cmds as cmds
from DooAnimKit.core.context import UndoContext


class TweenEngine:
    """AnimBot-style keyframe tweening engine with clean percentage blending and interactive delta."""

    CHANNELS = [
        "translateX", "translateY", "translateZ",
        "rotateX", "rotateY", "rotateZ",
        "scaleX", "scaleY", "scaleZ"
    ]

    def __init__(self):
        self.step_percent = 5.0

    def _get_target_objects(self):
        return cmds.ls(selection=True, type="transform") or []

    def step_nudge(self, direction=-1, step_percent=5.0):
        """
        Applies exact percentage blend towards previous key (-5%, -20%, -50%) 
        or next key (+5%, +20%, +50%).
        direction: -1 (Left / Prev), +1 (Right / Next)
        step_percent: 5.0, 20.0, 50.0
        """
        targets = self._get_target_objects()
        if not targets:
            cmds.warning("Please select at least one controller to tween!")
            return False

        current_frame = cmds.currentTime(query=True)
        # Розраховуємо цільовий відсоток між лівим (0%) і правим (100%) ключем:
        # -50% -> 0.0 (Left-most), -20% -> 0.30, -5% -> 0.45, +5% -> 0.55, +20% -> 0.70, +50% -> 1.0 (Right-most)
        target_factor = 0.5 + (float(step_percent) / 100.0) * direction
        target_factor = max(0.0, min(1.0, target_factor))
        applied_any = False

        with UndoContext("TweenStepNudge"):
            for node in targets:
                if not cmds.objExists(node):
                    continue

                for attr in self.CHANNELS:
                    full_attr = f"{node}.{attr}"
                    if not cmds.attributeQuery(attr, node=node, exists=True) or cmds.getAttr(full_attr, lock=True):
                        continue

                    prev_keys = cmds.keyframe(full_attr, query=True, time=(None, current_frame - 0.001), timeChange=True) or []
                    next_keys = cmds.keyframe(full_attr, query=True, time=(current_frame + 0.001, None), timeChange=True) or []

                    if not prev_keys or not next_keys:
                        continue

                    prev_val = cmds.keyframe(full_attr, query=True, time=(prev_keys[-1], prev_keys[-1]), valueChange=True)[0]
                    next_val = cmds.keyframe(full_attr, query=True, time=(next_keys[0], next_keys[0]), valueChange=True)[0]

                    new_val = prev_val + (next_val - prev_val) * target_factor
                    cmds.setKeyframe(full_attr, time=current_frame, value=new_val)
                    applied_any = True

        if applied_any:
            dir_str = f"Left (-{int(step_percent)}%)" if direction < 0 else f"Right (+{int(step_percent)}%)"
            cmds.inViewMessage(amg=f"Tween: <hl>{dir_str}</hl>", pos="topCenter", fade=True)
        return applied_any

    def cache_current_tween_state(self):
        """Caches base keys when starting to drag slider."""
        targets = self._get_target_objects()
        if not targets:
            return {}

        current_frame = cmds.currentTime(query=True)
        cached = {}

        for node in targets:
            if not cmds.objExists(node):
                continue
            cached[node] = {}

            for attr in self.CHANNELS:
                full_attr = f"{node}.{attr}"
                if not cmds.attributeQuery(attr, node=node, exists=True) or cmds.getAttr(full_attr, lock=True):
                    continue

                prev_keys = cmds.keyframe(full_attr, query=True, time=(None, current_frame - 0.001), timeChange=True) or []
                next_keys = cmds.keyframe(full_attr, query=True, time=(current_frame + 0.001, None), timeChange=True) or []

                if not prev_keys or not next_keys:
                    continue

                prev_val = cmds.keyframe(full_attr, query=True, time=(prev_keys[-1], prev_keys[-1]), valueChange=True)[0]
                next_val = cmds.keyframe(full_attr, query=True, time=(next_keys[0], next_keys[0]), valueChange=True)[0]

                has_key = bool(cmds.keyframe(full_attr, query=True, time=(current_frame, current_frame), keyframeCount=True))
                start_val = cmds.keyframe(full_attr, query=True, time=(current_frame, current_frame), valueChange=True)[0] if has_key else cmds.getAttr(full_attr)

                cached[node][attr] = {
                    "prev_val": prev_val,
                    "next_val": next_val,
                    "start_val": start_val
                }
        return cached

    def tween_interactive_delta(self, base_values, factor_delta):
        """
        Interactive drag delta from center handle:
        factor_delta = -1.0 -> 100% Left (Prev Key)
        factor_delta = 0.0  -> Base state
        factor_delta = +1.0 -> 100% Right (Next Key)
        """
        targets = self._get_target_objects()
        if not targets or not base_values:
            return False

        current_frame = cmds.currentTime(query=True)

        for node in targets:
            if node not in base_values:
                continue

            for attr, data in base_values[node].items():
                full_attr = f"{node}.{attr}"
                prev_val = data["prev_val"]
                next_val = data["next_val"]
                start_val = data["start_val"]

                if factor_delta < 0:
                    new_val = start_val + (start_val - prev_val) * factor_delta
                else:
                    new_val = start_val + (next_val - start_val) * factor_delta

                cmds.setKeyframe(full_attr, time=current_frame, value=new_val)
        return True

    def tween_absolute(self, percentage=50.0):
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
                    if not cmds.attributeQuery(attr, node=node, exists=True) or cmds.getAttr(full_attr, lock=True):
                        continue

                    prev_keys = cmds.keyframe(full_attr, query=True, time=(None, current_frame - 0.001), timeChange=True) or []
                    next_keys = cmds.keyframe(full_attr, query=True, time=(current_frame + 0.001, None), timeChange=True) or []

                    if not prev_keys or not next_keys:
                        continue

                    prev_val = cmds.keyframe(full_attr, query=True, time=(prev_keys[-1], prev_keys[-1]), valueChange=True)[0]
                    next_val = cmds.keyframe(full_attr, query=True, time=(next_keys[0], next_keys[0]), valueChange=True)[0]

                    new_val = prev_val + (next_val - prev_val) * factor
                    cmds.setKeyframe(full_attr, time=current_frame, value=new_val)
                    applied_any = True

        if applied_any:
            cmds.inViewMessage(amg=f"Tween set to <hl>{int(percentage)}%</hl>", pos="topCenter", fade=True)
        return applied_any