"""Read source image dimensions without scaling the E3D pixmap gadgets."""
from pathlib import Path

from PySide6.QtGui import QImageReader


def resolve_image_path(filename, directories=()):
    path = Path(filename)
    if not path.is_absolute():
        for directory in directories:
            candidate = Path(directory) / path
            try:
                if candidate.is_file():
                    return str(candidate)
            except (OSError, ValueError):
                continue
    return str(path)


def sync_image_size(gadget, directories=()):
    if gadget.display_mode != 'PIXMAP':
        return False
    before = gadget.width, gadget.height, gadget.width_ref
    # A reference to another gadget cannot override the source file's dimensions.
    gadget.width_ref = ''
    filenames = gadget.items if gadget.kind == 'option' else [gadget.pixmap_path]
    sizes = []
    for filename in filenames:
        if not filename:
            continue
        reader = QImageReader(resolve_image_path(filename, directories))
        size = reader.size()
        if size.isValid() and size.width() > 0 and size.height() > 0:
            sizes.append((size.width(), size.height()))
    if sizes:
        gadget.width = max(width for width, _ in sizes)
        gadget.height = max(height for _, height in sizes)
    # An unavailable share keeps the last known dimensions saved in the project.
    return before != (gadget.width, gadget.height, gadget.width_ref)
