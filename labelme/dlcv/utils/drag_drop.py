from pathlib import Path


def get_drop_target(paths, image_extensions):
    """返回拖拽目标目录及需要选中的图片。"""
    paths = [Path(path) for path in paths if path]
    if len(paths) != 1:
        return None, None

    path = paths[0]
    if path.is_dir():
        return str(path), None

    extensions = {
        extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        for extension in image_extensions
    }
    if path.is_file() and path.suffix.lower() in extensions:
        return str(path.parent), str(path)
    return None, None
