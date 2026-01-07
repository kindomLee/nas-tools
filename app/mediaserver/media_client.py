from abc import ABCMeta, abstractmethod


class IMediaClient(metaclass=ABCMeta):

    @abstractmethod
    def get_status(self):
        """
        檢查連通性
        """
        pass

    @abstractmethod
    def get_user_count(self):
        """
        獲得使用者數量
        """
        pass

    @abstractmethod
    def get_activity_log(self, num):
        """
        獲取Emby活動記錄
        """
        pass

    @abstractmethod
    def get_medias_count(self):
        """
        獲得電影、電視劇、動漫媒體數量
        :return: MovieCount SeriesCount SongCount
        """
        pass

    @abstractmethod
    def get_movies(self, title, year):
        """
        根據標題和年份，檢查電影是否在存在，存在則返回列表
        :param title: 標題
        :param year: 年份，可以為空，為空時不按年份過濾
        :return: 含title、year屬性的字典列表
        """
        pass

    @abstractmethod
    def get_no_exists_episodes(self, meta_info, season, total_num):
        """
        根據標題、年份、季、總集數，查詢缺少哪幾集
        :param meta_info: 已識別的需要查詢的媒體資訊
        :param season: 季號，數字
        :param total_num: 該季的總集數
        :return: 該季不存在的集號列表
        """
        pass

    @abstractmethod
    def get_image_by_id(self, item_id, image_type):
        """
        根據ItemId查詢圖片地址
        :param item_id: 在伺服器中的ID
        :param image_type: 圖片的類弄地，poster或者backdrop等
        :return: 圖片對應在TMDB中的URL
        """
        pass

    @abstractmethod
    def refresh_root_library(self):
        """
        重新整理整個媒體庫
        """
        pass

    @abstractmethod
    def refresh_library_by_items(self, items):
        """
        按型別、名稱、年份來重新整理媒體庫
        :param items: 已識別的需要重新整理媒體庫的媒體資訊列表
        """
        pass

    @abstractmethod
    def get_libraries(self):
        """
        獲取媒體伺服器所有媒體庫列表
        """
        pass

    @abstractmethod
    def get_items(self, parent):
        """
        獲取媒體庫中的所有媒體
        :param parent: 上一級的ID
        """
        pass
