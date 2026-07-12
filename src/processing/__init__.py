"""processing - core media-processing engine for WorkshopArt.

Split from the former monolithic processor.py (2900+ lines) into one module
per domain. SteamProcessor is assembled here from the domain mixins;
src/processor.py re-exports it so existing imports keep working unchanged.
"""
from processing.base import SteamProcessorBase
from processing.frames import FramesMixin
from processing.gif_encode import GifEncodeMixin
from processing.splitting import SplitMixin
from processing.enhance import EnhanceMixin
from processing.shrink import ShrinkMixin


class SteamProcessor(FramesMixin, GifEncodeMixin, SplitMixin,
                     EnhanceMixin, ShrinkMixin, SteamProcessorBase):
    """Main processor for images, video, and GIFs destined for Steam Workshop uploads."""


__all__ = ["SteamProcessor"]
