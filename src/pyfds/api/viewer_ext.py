"""Views, tours, section boxes, annotations, floors, skybox, preferences, CSV data, screenshots and movies
for ``api.viewer`` (a mixin of :class:`~pyfds.api.viewer.ViewerManager`)."""
from __future__ import annotations

from typing import Callable, List, Optional

from .viewer_ext_common import (  # noqa: F401  (re-exported)
    Renderer,
)
from .viewer_ext_annotations import (  # noqa: F401  (re-exported)
    ViewerExtrasAnnotationsMixin,
)
from .viewer_ext_camera import (  # noqa: F401  (re-exported)
    ViewerExtrasCameraMixin,
)
from .viewer_ext_capture import (  # noqa: F401  (re-exported)
    ViewerExtrasCaptureMixin,
)
from .viewer_ext_data import (  # noqa: F401  (re-exported)
    ViewerExtrasDataMixin,
)
from .viewer_ext_prefs import (  # noqa: F401  (re-exported)
    ViewerExtrasPrefsMixin,
)
from .viewer_ext_sections import (  # noqa: F401  (re-exported)
    ViewerExtrasSectionsMixin,
)
from .viewer_ext_tours import (  # noqa: F401  (re-exported)
    ViewerExtrasToursMixin,
)


class ViewerExtras(ViewerExtrasCameraMixin, ViewerExtrasToursMixin, ViewerExtrasSectionsMixin, ViewerExtrasAnnotationsMixin, ViewerExtrasPrefsMixin, ViewerExtrasDataMixin, ViewerExtrasCaptureMixin):
    def _init_extras(self) -> None:
        self.viz_listeners: List[Callable[[], None]] = []
        #: set by whoever can draw (the results window, the command line); scripts and the agent call it through screenshot()
        self.renderer: Optional[Renderer] = None
        self.motion_blur_span = 0.0                # simulated seconds one movie frame's shutter stays open
