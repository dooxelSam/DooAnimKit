"""
Time Offset Engine for DooAnimKit.
Supports precise Graph Editor Outliner selection, selected keys filtering,
Channel Box selection, Loop Wrapping, Stagger, and single-chunk Undo.
"""

import maya.cmds as cmds
import maya.mel as mel
from DooAnimKit.core.context import UndoContext


class TimeOffsetEngine:
    DEFAULT_CHANNELS = [
        "translateX", "translateY", "translateZ",
        "rotateX", "rotateY", "rotateZ",
        "scaleX", "scaleY", "scaleZ"
    ]

    def __init__(self):
        pass

    def _get_active_range(self):
        """Gets active frame range from Time Slider selection or timeline playback bounds."""
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

    def _get_target_attributes(self, node):
        """
        Detects active channels using 100% reliable Maya API/MEL selection connections:
        1. Highlighted channels in Graph Editor Outliner (left pane).
        2. Curves with selected keyframes in Graph Editor.
        3. Highlighted channels in Channel Box.
        If nothing specific is selected, falls back to all transform channels on the object.
        """
        target_attrs = set()

        # 1. Точне зчитування виділених каналів у лівій колонці Graph Editor (Outliner)
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

        # 2. Зчитування кривих, де виділено конкретні ключі в Graph Editor
        try:
            sl_curves = cmds.keyframe(node, query=True, selected=True, name=True) or []
            for curve in sl_curves:
                plugs = cmds.listConnections(f"{curve}.output", plugs=True) or []
                for plug in plugs:
                    if plug.startswith(f"{node}."):
                        target_attrs.add(plug.split(".", 1)[-1])
        except Exception:
            pass

        # 3. Зчитування виділення в Channel Box
        try:
            cb_attrs = cmds.channelBox("mainChannelBox", query=True, selectedMainAttributes=True) or []
            for a in cb_attrs:
                if cmds.attributeQuery(a, node=node, exists=True):
                    target_attrs.add(a)
        except Exception:
            pass

        if target_attrs:
            # Повертаємо тільки валідні для цього вузла виділені атрибути
            return [a for a in target_attrs if cmds.attributeQuery(a, node=node, exists=True)]

        # 4. Якщо жоден канал спеціально не виділений — працюємо з усіма стандартними
        return [a for a in self.DEFAULT_CHANNELS if cmds.attributeQuery(a, node=node, exists=True)]

    def cache_time_state(self):
        """Caches keyframes for selected attributes in order of selection."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            return {}

        start_f, end_f = self._get_active_range()
        cached = {
            "range": (start_f, end_f),
            "ordered_nodes": sel,
            "nodes": {}
        }

        for node in sel:
            if not cmds.objExists(node):
                continue

            attrs_to_offset = self._get_target_attributes(node)
            cached["nodes"][node] = {}

            for attr in attrs_to_offset:
                full_attr = f"{node}.{attr}"
                times = cmds.keyframe(full_attr, query=True, time=(start_f, end_f), timeChange=True) or []
                vals = cmds.keyframe(full_attr, query=True, time=(start_f, end_f), valueChange=True) or []
                if times:
                    cached["nodes"][node][attr] = list(zip(times, vals))

        return cached

    def offset_interactive_delta(self, base_cache, offset_frames):
        """Applies time shift/stagger strictly across active attributes."""
        if not base_cache or "nodes" not in base_cache:
            return False

        start_f, end_f = base_cache["range"]
        range_len = max(1, (end_f - start_f + 1))
        ordered_nodes = base_cache.get("ordered_nodes", list(base_cache["nodes"].keys()))
        is_multi = len(ordered_nodes) > 1

        for idx, node in enumerate(ordered_nodes):
            if node not in base_cache["nodes"] or not cmds.objExists(node):
                continue

            if is_multi:
                node_shift = int(round(offset_frames * (idx + 1)))
            else:
                node_shift = int(round(offset_frames))

            for attr, key_list in base_cache["nodes"][node].items():
                full_attr = f"{node}.{attr}"
                cmds.cutKey(full_attr, time=(start_f, end_f))

                for orig_t, val in key_list:
                    new_t = start_f + ((int(round(orig_t)) - start_f + node_shift) % range_len)
                    cmds.setKeyframe(full_attr, time=new_t, value=val)

        cmds.refresh()
        return True

    def step_shift(self, offset_frames=1):
        """Discrete step offset with unified Undo."""
        sel = cmds.ls(selection=True, type="transform") or []
        if not sel:
            cmds.warning("Select animated controller(s) to shift keys!")
            return False

        cache = self.cache_time_state()
        if not cache.get("nodes"):
            return False

        with UndoContext("TimeShiftStep"):
            self.offset_interactive_delta(cache, offset_frames)

        dir_str = f"+{offset_frames}f" if offset_frames > 0 else f"{offset_frames}f"
        stagger_str = f" [Stagger on {len(sel)} items]" if len(sel) > 1 else ""
        cmds.inViewMessage(amg=f"Time Offset: <hl>{dir_str}</hl>{stagger_str}", pos="topCenter", fade=True)
        return True