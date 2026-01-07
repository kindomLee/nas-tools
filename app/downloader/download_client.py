import os.path
from abc import ABCMeta, abstractmethod

from config import Config


class IDownloadClient(metaclass=ABCMeta):
    user_config = None
    host = None
    port = None
    username = None
    password = None
    secret = None

    def __init__(self, user_config=None):
        if user_config:
            self.user_config = user_config
        self.init_config()

    def init_config(self):
        """
        檢查連通性
        """
        self.get_config()
        self.set_user_config()
        self.connect()

    @abstractmethod
    def get_config(self):
        """
        獲取配置
        """
        pass

    @abstractmethod
    def connect(self):
        """
        連線
        """
        pass

    def set_user_config(self):
        if self.user_config:
            # 使用輸入配置
            self.host = self.user_config.get("host")
            self.port = self.user_config.get("port")
            self.username = self.user_config.get("username")
            self.password = self.user_config.get("password")

    @abstractmethod
    def get_status(self):
        """
        檢查連通性
        """
        pass

    @abstractmethod
    def get_torrents(self, ids, status, tag):
        """
        按條件讀取種子資訊
        :param ids: 種子ID，單個ID或者ID列表
        :param status: 種子狀態過濾
        :param tag: 種子標籤過濾
        :return: 種子資訊列表
        """
        pass

    @abstractmethod
    def get_downloading_torrents(self, tag):
        """
        讀取下載中的種子資訊
        """
        pass

    @abstractmethod
    def get_completed_torrents(self, tag):
        """
        讀取下載完成的種子資訊
        """
        pass

    @abstractmethod
    def set_torrents_status(self, ids, tags=None):
        """
        遷移完成後設定種子標籤為 已整理
        :param ids: 種子ID列表
        :param tags: 種子標籤列表
        """
        pass

    @abstractmethod
    def get_transfer_task(self, tag):
        """
        獲取需要轉移的種子列表
        """
        pass

    @abstractmethod
    def get_remove_torrents(self, config):
        """
        獲取需要清理的種子清單
        :param config: 刪種策略
        :return: 種子ID列表
        """
        pass

    @abstractmethod
    def add_torrent(self, **kwargs):
        """
        新增下載任務
        """
        pass

    @abstractmethod
    def start_torrents(self, ids):
        """
        下載控制：開始
        """
        pass

    @abstractmethod
    def stop_torrents(self, ids):
        """
        下載控制：停止
        """
        pass

    @abstractmethod
    def delete_torrents(self, delete_file, ids):
        """
        刪除種子
        """
        pass

    @abstractmethod
    def get_download_dirs(self):
        """
        獲取下載目錄清單
        """
        pass

    @staticmethod
    def get_replace_path(path):
        """
        對目錄路徑進行轉換
        """
        if not path:
            return ""
        downloaddir = Config().get_config('downloaddir') or []
        path = os.path.normpath(path)
        for attr in downloaddir:
            if not attr.get("save_path") or not attr.get("container_path"):
                continue
            save_path = os.path.normpath(attr.get("save_path"))
            container_path = os.path.normpath(attr.get("container_path"))
            if path.startswith(save_path):
                return path.replace(save_path, container_path)
        return path

    @abstractmethod
    def change_torrent(self, **kwargs):
        """
        修改種子狀態
        """
        pass
