import sys
import maya.cmds as cmds
from DooAnimKit.core import api


def show():
    """Main launch entrypoint with safe dockable window cleanup in Maya."""
    from DooAnimKit.ui.main_window import DooAnimKitHubWindow

    workspace_name = f"{DooAnimKitHubWindow.UI_NAME}WorkspaceControl"

    # Safely close and delete existing workspace control instances
    if cmds.workspaceControl(workspace_name, exists=True):
        try:
            cmds.workspaceControl(workspace_name, edit=True, close=True)
        except Exception:
            pass
        try:
            cmds.deleteUI(workspace_name, control=True)
        except Exception:
            pass

    win = DooAnimKitHubWindow()
    win.show(dockable=True)
    return win