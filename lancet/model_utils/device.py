# Copyright: Ajatt-Tools and contributors; https://github.com/Ajatt-Tools
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import enum

import torch

class TorchDevice(enum.Enum):
    cuda = enum.auto()
    mps = enum.auto()
    cpu = enum.auto()


def get_device(*, force_cpu: bool) -> TorchDevice:
    """Select the best available device for model inference."""
    if not force_cpu:
        if torch.cuda.is_available():
            return TorchDevice.cuda
        if torch.backends.mps.is_available():
            return TorchDevice.mps
    return TorchDevice.cpu


def move_model_to_device(model: torch.nn.Module, *, force_cpu: bool) -> TorchDevice:
    """Move a PyTorch model to the best available device and return the device name."""
    device = get_device(force_cpu=force_cpu)
    match device:
        case TorchDevice.cuda:
            model.cuda()
        case TorchDevice.mps:
            model.to(device.name)
    return device
