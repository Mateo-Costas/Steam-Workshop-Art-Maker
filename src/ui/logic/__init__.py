"""ui.logic - business logic for the WorkshopArt GUI, split by domain.

GUIMethodsMixin is assembled here from the domain mixins. The PRO feature
patch (_pro_features, gitignored in the public repo) replaces the free-tier
stub methods when present - same behaviour as the old gui_methods.py.
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


# PRO feature patch: _pro_features.py is gitignored and absent in the public
# repo; the ImportError branch is the normal code path for open-source users.
try:
    import _pro_features as _pf

    GUIMethodsMixin.process_full_ai = _pf.process_full_ai
    GUIMethodsMixin._fragment_workshop_flow = _pf.fragment_workshop_flow
    GUIMethodsMixin.enhance_animation = _pf.enhance_animation
except ImportError:
    pass

__all__ = ["GUIMethodsMixin"]
