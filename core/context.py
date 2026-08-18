from maya import cmds

class UndoContext:
    """Контекст-менеджер для об'єднання операцій у єдиний Undo Chunk."""
    def __init__(self, name="AnimKitOperation"):
        self.name = name

    def __enter__(self):
        cmds.undoInfo(openChunk=True, chunkName=self.name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        cmds.undoInfo(closeChunk=True)