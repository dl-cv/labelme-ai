"""检查实际打包元数据中的核心库依赖。"""

import importlib.util
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet


def test_package_requires_core_with_image_json(monkeypatch):
    setup_path = Path(__file__).resolve().parents[1] / "setup.py"
    spec = importlib.util.spec_from_file_location(
        "labelme_package_metadata", setup_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = {}
    monkeypatch.setattr(module, "setup", lambda **kwargs: metadata.update(kwargs))
    monkeypatch.chdir(setup_path.parent)
    module.main()
    assert metadata["name"] == "dlcv_labelme_ai"
    requirements = [Requirement(value) for value in metadata["install_requires"]]
    core = [value for value in requirements if value.name == "dlcv-core"]
    assert len(core) == 1
    assert core[0].specifier == SpecifierSet(">=2026.10.8.6a0")
    assert not core[0].specifier.contains("2026.10.8.5a0")
    assert core[0].specifier.contains("2026.10.8.6a0")
    assert core[0].specifier.contains("2026.10.8.6")
