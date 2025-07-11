from abc import ABC, abstractmethod


class ABCStrategy(ABC):

    @abstractmethod
    def is_target(self, path: str) -> bool:
        pass

    @abstractmethod
    def get_json_path(self, path: str) -> str:
        """返回标注json路径"""
        pass

    @abstractmethod
    def get_img_name_list(self, path: str) -> list[str]:
        """返回[文件名]"""
        pass
