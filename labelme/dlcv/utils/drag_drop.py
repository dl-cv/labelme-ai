from pathlib import Path


def classify_dropped_paths(paths, image_extensions):
    """区分单个目录与图片文件拖拽。"""
    paths = [str(path) for path in paths if path]
    if len(paths) == 1 and Path(paths[0]).is_dir():
        return paths[0], []

    extensions = tuple(
        extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        for extension in image_extensions
    )
    image_paths = [path for path in paths if path.lower().endswith(extensions)]
    return None, image_paths
