import os
import re
import shutil

from setuptools import setup

package_name = "dlcv_labelme_ai"  # 包名
packages: list = ["dlcv_labelme_ai"]  # 需要打包的包
package_data: dict[str:list] = {"dlcv_labelme_ai": ["*", "*/*"]}  # 哪个包需要打包哪些资源文件
version_file_path = f"labelme/__init__.py"


def get_version():
    try:
        with open(version_file_path) as f:
            match = re.search(r"""^__version__ = ['"]([^'"]*)['"]""", f.read(),
                              re.M)
    except:
        with open(version_file_path, encoding='utf8') as f:
            match = re.search(r"""^__version__ = ['"]([^'"]*)['"]""", f.read(),
                              re.M)
    if not match:
        raise RuntimeError("{} doesn't contain __version__".format(version_file_path))
    version = match.groups()[0]
    return version


def main():
    version = get_version()

    setup(
        name=package_name,
        version=version,
        description="深圳市深度视觉科技有限公司-Labelme AI",
        install_requires=["pyqt-toast-notification"],
        # long_description=get_long_description(),
        # long_description_content_type="text/markdown",
        author="DLCV",
        author_email="ypw@dlcv.ai",
        url="",
        keywords="DLCV, Machine Learning",
        packages=packages,
        package_data=package_data,
        options={
            "bdist_wheel": {
                'plat_name': 'win_amd64',
                'python_tag': 'cp311',
            },
        },
    )


if __name__ == "__main__":
    import warnings

    egg_info_path = f'{package_name}.egg-info'

    path_list = ['build', 'dist', 'whl', egg_info_path]
    for path in path_list:
        if os.path.exists(path):
            warnings.warn(f'remove {path}')
            shutil.rmtree(path)
        else:
            print(f'no such file:{path}')

    main()

    path_list = ['build', egg_info_path]
    for path in path_list:
        if os.path.exists(path):
            warnings.warn(f'remove {path}')
            shutil.rmtree(path)
        else:
            print(f'no such file:{path}')
