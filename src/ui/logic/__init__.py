"""ui.logic - business logic for the WorkshopArt GUI, split by domain.

GUIMethodsMixin is assembled here from the domain mixins; ui.app mixes it into
the main window.
"""
from ui.logic.files import FilesMixin
from ui.logic.fragmentation import FragmentationMixin
from ui.logic.processing import ProcessingMixin
from ui.logic.system import SystemMixin
from ui.logic.upload import UploadMixin


class GUIMethodsMixin(SystemMixin, FilesMixin, ProcessingMixin,
                      FragmentationMixin, UploadMixin):
    """All processing/business-logic methods for the WorkshopArt GUI.

    Must be mixed in alongside a tkinter root that exposes `self.root`,
    `self.update_queue`, and the widget attributes documented in each mixin.
    """


__all__ = ["GUIMethodsMixin"]
