"""
Semantic Text-to-Pose Engine for DooAnimKit.
Matches natural language prompts to HIK-tagged rig controllers.
"""

import os
import json
import maya.cmds as cmds
from DooAnimKit.core.context import UndoContext


class SemanticPoseEngine:
    def __init__(self, main_window=None):
        self.win = main_window
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.presets_dir = os.path.join(base_dir, "presets")
        self.library_path = os.path.join(self.presets_dir, "pose_library.json")
        self.picker_data_path = os.path.join(self.presets_dir, "picker_data.json")

    def _load_library(self):
        if os.path.exists(self.library_path):
            try:
                with open(self.library_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                cmds.warning(f"Failed to read pose library: {e}")
        return {}

    def _get_tag_to_node_map(self):
        """Builds a lookup table: { 'Hips': 'HipSwinger_M', 'LeftLeg_IK': 'IKLeg_L', ... }"""
        tag_map = {}
        if os.path.exists(self.picker_data_path):
            try:
                with open(self.picker_data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for pin in data.get("pins", []):
                        tag = pin.get("hik_tag")
                        node = pin.get("name")
                        if tag and tag != "None" and node and cmds.objExists(node):
                            tag_map[tag] = node
            except Exception:
                pass
        return tag_map

    def apply_pose_by_prompt(self, prompt_text):
        """Finds closest matching pose in library and applies deltas to tagged controllers."""
        if not prompt_text:
            return False

        library = self._load_library()
        if not library:
            cmds.warning("Pose library is empty!")
            return False

        p_clean = prompt_text.lower().strip()
        matched_pose_key = None

        # 1. Пошук за ключовими словами
        for key, pdata in library.items():
            keywords = pdata.get("keywords", [])
            for kw in keywords:
                if kw.lower() in p_clean:
                    matched_pose_key = key
                    break
            if matched_pose_key:
                break

        if not matched_pose_key:
            cmds.warning(f"No pose match found for prompt: '{prompt_text}'. Try 'kneeling', 'crouch', or 'combat'.")
            return False

        pose_data = library[matched_pose_key]
        tag_map = self._get_tag_to_node_map()

        if not tag_map:
            cmds.warning("No HIK tags mapped in Canvas! Please map and scan your pins first.")
            return False

        applied_count = 0
        with UndoContext("ApplySemanticPose"):
            # Застосовуємо трансформації
            for tag, xforms in pose_data.get("transforms", {}).items():
                ctrl_node = tag_map.get(tag)
                if not ctrl_node or not cmds.objExists(ctrl_node):
                    continue

                for attr, val in xforms.items():
                    full_attr = f"{ctrl_node}.{attr}"
                    if cmds.attributeQuery(attr, node=ctrl_node, exists=True):
                        if not cmds.getAttr(full_attr, lock=True) and cmds.getAttr(full_attr, settable=True):
                            try:
                                cmds.setAttr(full_attr, val)
                            except Exception:
                                pass
                applied_count += 1

        label = pose_data.get("label", matched_pose_key)
        cmds.inViewMessage(
            amg=f"<hl style='color:#00E676;'>✓ Pose Applied: {label}</hl> ({applied_count} controls updated)",
            pos="topCenter", fade=True
        )
        return True