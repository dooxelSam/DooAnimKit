import sys
import maya.cmds as cmds

try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets

# Explicit full package import
from DooAnimKit.ui.main_window import DooAnimKitHubWindow


def show():
    """Main launch entrypoint with dockable window support in Maya."""
    workspace_name = f"{DooAnimKitHubWindow.UI_NAME}WorkspaceControl"
    if cmds.workspaceControl(workspace_name, exists=True):
        cmds.deleteUI(workspace_name, control=True)

    win = DooAnimKitHubWindow()
    win.show(dockable=True)
    return win