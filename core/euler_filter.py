import math
import maya.cmds as cmds
import maya.mel as mel
from DooAnimKit.core.context import UndoContext


class SmartEulerFilter:
    """Smart Euler & Gimbal Lock Filter for Maya Graph Curves."""

    ROT_ATTRS = ["rotateX", "rotateY", "rotateZ"]

    def _get_target_nodes(self):
        return cmds.ls(selection=True, type="transform") or []

    def apply_smart_filter(self):
        nodes = self._get_target_nodes()
        if not nodes:
            cmds.warning("Please select a controller to apply Smart Euler Filter!")
            return False

        with UndoContext("SmartEulerFilter"):
            for node in nodes:
                if not cmds.objExists(node):
                    continue

                # 1. Знаходимо анімаційні криві обертання для даного об'єкта
                curves = []
                for attr in self.ROT_ATTRS:
                    full_attr = f"{node}.{attr}"
                    conns = cmds.listConnections(full_attr, type="animCurve", source=True, destination=False) or []
                    if conns:
                        curves.extend(conns)

                if not curves:
                    # Якщо з'єднань немає напряму, пробуємо через filterCurve на ноду
                    try:
                        cmds.filterCurve(f"{node}.rotateX", f"{node}.rotateY", f"{node}.rotateZ")
                    except Exception:
                        pass
                    continue

                # 2. Викликаємо C++ двигун EulerFilter на анімаційні криві
                try:
                    cmds.filterCurve(curves)
                except Exception:
                    pass

                # 3. Виконуємо додатковий прохід для усунення 360° фазових зміщень
                for attr in self.ROT_ATTRS:
                    full_attr = f"{node}.{attr}"
                    keys_count = cmds.keyframe(full_attr, query=True, keyframeCount=True) or 0
                    if keys_count < 2:
                        continue

                    times = cmds.keyframe(full_attr, query=True, timeChange=True) or []
                    values = cmds.keyframe(full_attr, query=True, valueChange=True) or []

                    if not times or not values:
                        continue

                    prev_val = values[0]
                    for t, v in zip(times[1:], values[1:]):
                        diff = v - prev_val
                        # Якщо стрибок більше 170 градусів
                        if abs(diff) > 170.0:
                            turns = round(diff / 360.0)
                            if turns != 0:
                                corrected_v = v - turns * 360.0
                                cmds.keyframe(full_attr, time=(t, t), valueChange=corrected_v)
                                prev_val = corrected_v
                                continue
                        prev_val = v

                # 4. Згладжуємо дотичні
                try:
                    cmds.keyTangent(node, attribute=["rotateX", "rotateY", "rotateZ"], edit=True, auto=True)
                except Exception:
                    pass

        cmds.inViewMessage(amg=f"Smart Euler Filter applied to <hl>{len(nodes)}</hl> controller(s)!", pos="topCenter", fade=True)
        return True