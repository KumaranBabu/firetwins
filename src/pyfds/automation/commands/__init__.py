"""
PyFDS Command Pipeline
=======================
Composable, undo/redo-capable command objects for all FDS project
mutation operations.

Design
------
Every operation that modifies the domain model is wrapped in a ``Command``
subclass.  Commands are pushed onto a ``CommandPipeline`` which maintains
a history stack supporting unlimited undo/redo.

The ``CommandPipeline`` also emits ``COMMAND_EXECUTED``, ``UNDO_PERFORMED``,
and ``REDO_PERFORMED`` events through the global EventBus so that a future
GUI can keep its state in sync without polling.

Built-in commands
-----------------
AddEntityCommand        — add any FdsEntity to a project collection
RemoveEntityCommand     — remove by object reference or name
ModifyPropertyCommand   — set one attribute with undo support
RenameCommand           — rename any named entity (CHID / label)
BatchPropertyCommand    — set multiple properties atomically
MoveObstCommand         — translate an obstruction (XB)
MoveHvacNodeCommand     — translate an HVAC node (schematic-canvas x/y)
TranslateGeomCommand    — translate a Geom mesh (every vertex)
ScaleGeomCommand        — uniform scale of a Geom mesh
MirrorGeomCommand       — mirror a Geom mesh across an axis-aligned plane
RotateGeomCommand       — rotate a Geom mesh about Z by an arbitrary angle
TranslatePointCommand   — translate a plain-xyz point entity (Device, HvacNode, ...)
ScaleCommand            — uniform scale of an obstruction or mesh
SetTimingCommand        — change T_BEGIN / T_END on FdsProject
SetHrrCommand           — change HRR on a burner Surface (HRRPUA × area)
ScaleCommand            — uniform scale of an obstruction or mesh
DuplicateEntityCommand  — deep-copy an entity under a new name
GroupCommand            — execute multiple commands atomically with full undo

Custom commands can be created by subclassing ``Command`` and implementing
``execute()`` and ``undo()``.

Example::

    pipe = CommandPipeline(project)
    pipe.execute(AddEntityCommand(mesh))
    pipe.execute(ModifyPropertyCommand(mesh, "dx", 0.05))
    pipe.undo()   # restores dx to previous value
    pipe.redo()   # re-applies the change
"""

# Split by area (plan step G2); every public name is still importable from
# ``pyfds.automation.commands``.
from .base import CommandResult, Command
from .entity import AddEntityCommand, RemoveEntityCommand, ModifyPropertyCommand, RenameCommand, BatchPropertyCommand, SetHrrCommand, DuplicateEntityCommand, SetTimingCommand
from .transform import MoveObstCommand, MoveHvacNodeCommand, ScaleCommand, MirrorCommand, RotateCommand, TranslateGeomCommand, ScaleGeomCommand, MirrorGeomCommand, RotateGeomCommand, TranslatePointCommand
from .group import GroupCommand, StateSwapCommand
from .pipeline import CommandPipeline

__all__ = [
    "CommandResult",
    "Command",
    "AddEntityCommand",
    "RemoveEntityCommand",
    "ModifyPropertyCommand",
    "RenameCommand",
    "BatchPropertyCommand",
    "SetHrrCommand",
    "DuplicateEntityCommand",
    "SetTimingCommand",
    "MoveObstCommand",
    "MoveHvacNodeCommand",
    "ScaleCommand",
    "MirrorCommand",
    "RotateCommand",
    "TranslateGeomCommand",
    "ScaleGeomCommand",
    "MirrorGeomCommand",
    "RotateGeomCommand",
    "TranslatePointCommand",
    "GroupCommand",
    "StateSwapCommand",
    "CommandPipeline",
]
