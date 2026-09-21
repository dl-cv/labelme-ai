from labelme.dlcv.utils.drag_drop import get_drop_target


def test_get_drop_target_directory(tmp_path):
    directory, filename = get_drop_target([tmp_path], ["png", "jpg"])

    assert directory == str(tmp_path)
    assert filename is None


def test_get_drop_target_image(tmp_path):
    image_path = tmp_path / "selected.PNG"
    image_path.touch()

    directory, filename = get_drop_target([image_path], ["png", ".jpg"])

    assert directory == str(tmp_path)
    assert filename == str(image_path)


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


def _drop(paths):
    from labelme.dlcv.app import MainWindow

    opened = []

    class Window:
        @staticmethod
        def mayContinue():
            return True

        @staticmethod
        def _openDirectory(directory, filename=None):
            opened.append((directory, filename))

    event = _DropEvent(paths)
    MainWindow.dropEvent(Window(), event)
    return opened, event


def test_drop_directory_opens_directory(tmp_path):
    opened, event = _drop([str(tmp_path)])

    assert opened == [(str(tmp_path), None)]
    assert event.accepted is True
    assert event.ignored is False


def test_drop_image_opens_parent_directory_and_selects_image(tmp_path):
    image_path = tmp_path / "selected.png"
    image_path.touch()

    opened, event = _drop([str(image_path)])

    assert opened == [(str(tmp_path), str(image_path))]
    assert event.accepted is True
    assert event.ignored is False
