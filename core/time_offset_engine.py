"""
Time Offset Engine for DooAnimKit.
Offsets animation curves interactively inside selected playback range with seamless wrapping.
"""

import maya.cmds as cmds
import maya.mel as mel
from DooAnimKit.core.context import UndoContext


class TimeOffsetEngine:
    CHANNELS = [
        "translateX", "translateY", "translateZ",
        "rotateX", "rotateY", "rotateZ",
        "scaleX", "scaleY", "scaleZ"
    ]

    def __init__(self):
        pass

    def _get_active_range(self):
        gPlayBackSlider = mel.eval('$tmpVar=$gPlayBackSlider;')
        try:
            if cmds.timeControl(gPlayBackSlider, query=True, rangeVisible=True):
                selected_range = cmds.timeControl(gPlayBackSlider, query=True, rangeArray=True)
                if selected_range and len(selected_range) >= 2:
                    start_f = int(round(selected_range[0]))
                    end_f = int(round(selected_range[1]))
                    if end_f > start_f:
                        actual_end = end_f - 1 if (selected_range[1] - selected_range[0] > 1) else end_f
                        return start_f, actual_end
        except Exception:
            pass
        return int(cmds.playbackOptions(query=True, minTime=True)), int(cmds.playbackOptions(query=True, maxTime=True))

    def cache_time_state(self):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            return {}

        start_f, end_f = self._get_active_range()
        cached = {"range": (start_f, end_f), "nodes": {}}

        for node in sel:
            if not cmds.objExists(node):
                continue
            cached["nodes"][node] = {}
            for attr in self.CHANNELS:
                full_attr = f"{node}.{attr}"
                if cmds.attributeQuery(attr, node=node, exists=True):
                    times = cmds.keyframe(full_attr, query=True, time=(start_f, end_f), timeChange=True) or []
                    vals = cmds.keyframe(full_attr, query=True, time=(start_f, end_f), valueChange=True) or []
                    if times:
                        cached["nodes"][node][attr] = list(zip(times, vals))
        return cached

    def offset_interactive_delta(self, base_cache, offset_frames):
        if not base_cache or "nodes" not in base_cache:
            return False

        start_f, end_f = base_cache["range"]
        range_len = max(1, (end_f - start_f + 1))
        shift = int(round(offset_frames))

        for node, attrs in base_cache["nodes"].items():
            if not cmds.objExists(node):
                continue

            for attr, key_list in attrs.items():
                full_attr = f"{node}.{attr}"
                cmds.cutKey(full_attr, time=(start_f, end_f))

                for orig_t, val in key_list:
                    new_t = start_f + ((int(round(orig_t)) - start_f + shift) % range_len)
                    cmds.setKeyframe(full_attr, time=new_t, value=val)

        cmds.refresh()
        return True

    def step_shift(self, offset_frames=1):
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Select animated controller(s) to shift keys!")
            return False

        cache = self.cache_time_state()
        if not cache.get("nodes"):
            return False

        with UndoContext("TimeShiftRange"):
            self.offset_interactive_delta(cache, offset_frames)

        dir_str = f"+{offset_frames}f" if offset_frames > 0 else f"{offset_frames}f"
        cmds.inViewMessage(amg=f"Time Offset (Range): <hl>{dir_str}</hl>", pos="topCenter", fade=True)
        return True