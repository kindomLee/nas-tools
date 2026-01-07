from abc import ABCMeta, abstractmethod


class IMessageClient(metaclass=ABCMeta):

    @abstractmethod
    def init_config(self):
        """
        初始化配置
        """
        pass

    @abstractmethod
    def send_msg(self, title, text, image, url, user_id):
        """
        訊息傳送入口，支援文字、圖片、連結跳轉、指定傳送物件
        :param title: 訊息標題
        :param text: 訊息內容
        :param image: 圖片地址
        :param url: 點選訊息跳轉URL
        :param user_id: 訊息傳送物件的ID，為空則發給所有人
        :return: 傳送狀態，錯誤資訊
        """
        pass

    @abstractmethod
    def send_list_msg(self, medias: list, user_id="", title="", url=""):
        """
        傳送列表類訊息
        :param title: 訊息標題
        :param medias: 媒體列表
        :param user_id: 訊息傳送物件的ID，為空則發給所有人
        :param url: 跳轉連結地址
        """
        pass
