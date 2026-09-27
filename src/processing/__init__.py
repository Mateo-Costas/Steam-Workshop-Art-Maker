"""processing - core media-processing engine for WorkshopArt.

One module per domain, assembled into SteamProcessor here:
    base        workspace folders, manifests, tool and GPU discovery
    frames      frame extraction and AI upscaling
    gif_encode  video/frames -> GIF, gifsicle, Steam trailer patch
    splitting   showcase presets and the shared fragment encoder
    enhance     color adjustments
    shrink      size-cap optimizer
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
