import maya.cmds as cmds
import maya.mel as mel
from DooAnimKit.core.context import UndoContext


class MotionTrailManager:
    """Керування чистими траєкторіями руху у Viewport."""

    @staticmethod
    def toggle_motion_trail(targets=None):
        selection = targets or cmds.ls(selection=True, type="transform")
        if not selection:
            cmds.warning("Виберіть об'єкт або контролер!")
            return

        ctrl = selection[0]
        start_frame = int(cmds.playbackOptions(query=True, minTime=True))
        end_frame = int(cmds.playbackOptions(query=True, maxTime=True))

        with UndoContext("CreateMotionTrail"):
            mel.eval(f'snapshot -motionTrail 1 -increment 1 -startTime {start_frame} -endTime {end_frame} "{ctrl}";')
            shapes = cmds.ls(type="motionTrailShape")
            if shapes:
                latest_shape = shapes[-1]
                if cmds.attributeQuery("showFrameNumber", node=latest_shape, exists=True):
                    cmds.setAttr(f"{latest_shape}.showFrameNumber", 0)
                if cmds.attributeQuery("drawFrames", node=latest_shape, exists=True):
                    cmds.setAttr(f"{latest_shape}.drawFrames", 1)
                if cmds.attributeQuery("drawKeys", node=latest_shape, exists=True):
                    cmds.setAttr(f"{latest_shape}.drawKeys", 1)
                cmds.setAttr(f"{latest_shape}.overrideEnabled", 1)
                cmds.setAttr(f"{latest_shape}.overrideColor", 18)

    @staticmethod
    def clear_all_trails():
        with UndoContext("ClearAllTrails"):
            trail_shapes = cmds.ls(type="motionTrailShape") or []
            trail_nodes = cmds.ls(type="motionTrail") or []
            handles = []
            for shape in trail_shapes:
                parent = cmds.listRelatives(shape, parent=True)
                if parent:
                    handles.extend(parent)

            named_handles = cmds.ls("*motionTrail*Handle*", "*MotionTrail*", type="transform") or []
            all_objects = list(set(trail_shapes + trail_nodes + handles + named_handles))

            if all_objects:
                existing = [obj for obj in all_objects if cmds.objExists(obj)]
                if existing:
                    cmds.delete(existing)
                    cmds.inViewMessage(amg=f"Видалено <hl>{len(existing)}</hl> траєкторій", pos="topCenter", fade=True)