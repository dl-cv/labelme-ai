from labelme.dlcv.utils.drag_drop import classify_dropped_paths


def test_classify_single_dropped_directory(tmp_path):
    directory, image_paths = classify_dropped_paths([tmp_path], ["png", "jpg"])

    assert directory == str(tmp_path)
    assert image_paths == []


def test_classify_dropped_images(tmp_path):
    png_path = tmp_path / "first.PNG"
    jpg_path = tmp_path / "second.jpg"
    text_path = tmp_path / "notes.txt"

    directory, image_paths = classify_dropped_paths(
        [png_path, jpg_path, text_path], ["png", ".jpg"]
    )

    assert directory is None
    assert image_paths == [str(png_path), str(jpg_path)]


def test_multiple_dropped_directories_are_not_opened_as_one(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    directory, image_paths = classify_dropped_paths([first, second], ["png"])

    assert directory is None
    assert image_paths == []


class _LocalUrl:
    def __init__(self, path):
        self._path = path

    def toLocalFile(self):
        return self._path


class _MimeData:
    def __init__(self, paths):
        self._urls = [_LocalUrl(path) for path in paths]

    def urls(self):
        return self._urls


class _DropEvent:
    def __init__(self, paths):
        self._mime_data = _MimeData(paths)
        self.accepted = False
        self.ignored = False

    def mimeData(self):
        return self._mime_data

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


def test_drop_directory_opens_directory_without_image_import(tmp_path):
    from labelme.dlcv.app import MainWindow

    opened = []

    class Window:
        @staticmethod
        def mayContinue():
            return True

        @staticmethod
        def _openDirectory(directory):
            opened.append(directory)

    event = _DropEvent([str(tmp_path)])

    MainWindow.dropEvent(Window(), event)

    assert opened == [str(tmp_path)]
    assert event.accepted is True
    assert event.ignored is False
