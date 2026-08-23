"""
Time Shift & Cascade (Overlap) Engine for DooAnimKit.
Offsets animation curves incrementally based on selection order or hierarchy to create overlaps.
"""

import maya.cmds as cmds
import maya.mel as mel
from DooAnimKit.core.context import UndoContext


class TimeShiftEngine:
    CHANNELS = [
        "translateX", "translateY", "translateZ",
        "rotateX", "rotateY", "rotateZ",
        "scaleX", "scaleY", "scaleZ"
    ]

    def __init__(self):
        pass

    def _get_time_range(self):
        """Returns active timeline highlight range or scene playback range."""
        gPlayBackSlider = mel.eval('$tmpVar=$gPlayBackSlider;')
        try:
            time_range = cmds.timeControl(gPlayBackSlider, query=True, rangeArray=True)
            if time_range and (time_range[1] - time_range[0] > 1):
                return int(time_range[0]), int(time_range[1])
        except Exception:
            pass
        start = int(cmds.playbackOptions(query=True, minTime=True))
        end = int(cmds.playbackOptions(query=True, maxTime=True))
        return start, end

    def shift_selected(self, frame_offset=1):
        """Shifts all keyframes on selected nodes by a fixed frame offset."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Please select controllers to shift animation!")
            return False

        start, end = self._get_time_range()

        with UndoContext("ShiftAnimation"):
            for node in sel:
                cmds.keyframe(
                    node,
                    time=(start, end),
                    relative=True,
                    timeChange=frame_offset
                )

        dir_str = f"+{frame_offset}" if frame_offset > 0 else str(frame_offset)
        cmds.inViewMessage(amg=f"Shifted animation by <hl>{dir_str} frames</hl> on {len(sel)} control(s).", pos="topCenter", fade=True)
        return True

    def cascade_shift(self, step=1, reverse=False):
        """
        Creates overlap by offsetting each subsequent selected controller incrementally.
        Item 0 -> +0 frames
        Item 1 -> +1 * step
        Item 2 -> +2 * step ...
        """
        sel = cmds.ls(selection=True, type="transform") or []
        if len(sel) < 2:
            cmds.warning("Select at least 2 controllers in sequence (e.g. Spine, Tail, Fingers) for Cascade Overlap!")
            return False

        if reverse:
            sel = list(reversed(sel))

        start, end = self._get_time_range()

        with UndoContext("CascadeShift"):
            for index, node in enumerate(sel):
                current_offset = index * step
                if current_offset != 0:
                    cmds.keyframe(
                        node,
                        time=(start, end),
                        relative=True,
                        timeChange=current_offset
                    )

        dir_label = "Backward" if reverse else "Forward"
        cmds.inViewMessage(
            amg=f"<hl>Cascade {dir_label}</hl>: Shifted {len(sel)} controls by step <hl>{step}</hl> frame(s).",
            pos="topCenter",
            fade=True
        )
        return True