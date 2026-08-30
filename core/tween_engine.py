"""
Tween Engine for DooAnimKit.
Supports precise Graph Editor channel selection, selected keys filtering,
Channel Box selection, discrete steps, real-time dragging, and single-chunk undo.
"""

import maya.cmds as cmds
from DooAnimKit.core.context import UndoContext


class TweenEngine:
    DEFAULT_CHANNELS = [
        "translateX", "translateY", "translateZ",
        "rotateX", "rotateY", "rotateZ",
        "scaleX", "scaleY", "scaleZ"
    ]

    def __init__(self):
        self.step_percent = 5.0

    def _get_target_objects(self):
        return cmds.ls(selection=True, type="transform") or []

    def _get_target_attributes(self, node):
        """
        Detects active channels from Graph Editor Outliner, selected keys, or Channel Box.
        """
        target_attrs = set()

        # 1. Точне зчитування виділених каналів у лівій колонці Graph Editor
        try:
            for sc in ["graphEditor1FromOutliner", "graphEditor1SelectionConnection"]:
                if cmds.selectionConnection(sc, exists=True):
                    items = cmds.selectionConnection(sc, query=True, obj=True) or []
                    for item in items:
                        if "." in item:
                            obj, attr = item.split(".", 1)
                            if obj == node or obj.endswith(f"|{node}"):
                                target_attrs.add(attr)
                        elif cmds.nodeType(item).startswith("animCurve"):
                            plugs = cmds.listConnections(f"{item}.output", plugs=True) or []
                            for plug in plugs:
                                if plug.startswith(f"{node}."):
                                    target_attrs.add(plug.split(".", 1)[-1])
        except Exception:
            pass

        # 2. Зчитування кривих із виділеними ключами
        try:
            sl_curves = cmds.keyframe(node, query=True, selected=True, name=True) or []
            for curve in sl_curves:
                plugs = cmds.listConnections(f"{curve}.output", plugs=True) or []
                for plug in plugs:
                    if plug.startswith(f"{node}."):
                        target_attrs.add(plug.split(".", 1)[-1])
        except Exception:
            pass

        # 3. Зчитування Channel Box
        try:
            cb_attrs = cmds.channelBox("mainChannelBox", query=True, selectedMainAttributes=True) or []
            for a in cb_attrs:
                if cmds.attributeQuery(a, node=node, exists=True):
                    target_attrs.add(a)
        except Exception:
            pass

        if target_attrs:
            return [a for a in target_attrs if cmds.attributeQuery(a, node=node, exists=True)]

        return [a for a in self.DEFAULT_CHANNELS if cmds.attributeQuery(a, node=node, exists=True)]

    def cache_current_tween_state(self):
        """Caches start positions of keys when starting to drag slider."""
        targets = self._get_target_objects()
        if not targets:
            return {}

        current_frame = cmds.currentTime(query=True)
        cached = {}

        for node in targets:
            if not cmds.objExists(node):
                continue

            active_attrs = self._get_target_attributes(node)
            cached[node] = {}

            for attr in active_attrs:
                full_attr = f"{node}.{attr}"
                if cmds.getAttr(full_attr, lock=True):
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
        """Interactive drag delta from center handle."""
        targets = self._get_target_objects()
        if not targets or not base_values:
            return False

        current_frame = cmds.currentTime(query=True)
        changed = False

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
                changed = True

        if changed:
            cmds.refresh()

        return True

    def step_nudge(self, direction=-1, step_percent=5.0):
        """Nudges pose by fixed step percentage (5%, 15%, 25%)."""
        targets = self._get_target_objects()
        if not targets:
            cmds.warning("Please select at least one controller to tween!")
            return False

        current_frame = cmds.currentTime(query=True)
        step_factor = (float(step_percent) / 100.0) * direction
        applied_any = False

        with UndoContext("TweenStepNudge"):
            for node in targets:
                if not cmds.objExists(node):
                    continue

                active_attrs = self._get_target_attributes(node)

                for attr in active_attrs:
                    full_attr = f"{node}.{attr}"
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
                    curr_val = cmds.keyframe(full_attr, query=True, time=(current_frame, current_frame), valueChange=True)[0] if has_key else cmds.getAttr(full_attr)

                    val_range = next_val - prev_val
                    if abs(val_range) > 1e-5:
                        current_factor = (curr_val - prev_val) / val_range
                        new_factor = max(-0.5, min(1.5, current_factor + step_factor))
                        new_val = prev_val + val_range * new_factor
                    else:
                        new_val = curr_val

                    cmds.setKeyframe(full_attr, time=current_frame, value=new_val)
                    applied_any = True

        if applied_any:
            cmds.refresh()
            dir_str = f"Left (-{int(step_percent)}%)" if direction < 0 else f"Right (+{int(step_percent)}%)"
            cmds.inViewMessage(amg=f"Tween: <hl>{dir_str}</hl>", pos="topCenter", fade=True)
        return applied_any