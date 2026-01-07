import threading

import log
from app.db import MediaDb
from app.helper import ProgressHelper
from app.utils.types import MediaServerType
from config import Config
from app.mediaserver.client import Emby, Jellyfin, Plex

lock = threading.Lock()
server_lock = threading.Lock()


class MediaServer:
    _server_type = None
    _server = None
    mediadb = None
    progress = None

    def __init__(self):
        self.mediadb = MediaDb()
        self.progress = ProgressHelper()
        self.init_config()

    def init_config(self):
        _type = Config().get_config('media').get('media_server')
        if _type == "jellyfin":
            self._server_type = MediaServerType.JELLYFIN
        elif _type == "plex":
            self._server_type = MediaServerType.PLEX
        else:
            self._server_type = MediaServerType.EMBY

    @property
    def server(self):
        with server_lock:
            if not self._server:
                self._server = self.__get_server()
            return self._server

    def __get_server(self):
        if self._server_type == MediaServerType.JELLYFIN:
            return Jellyfin()
        elif self._server_type == MediaServerType.PLEX:
            return Plex()
        else:
            return Emby()

    def get_type(self):
        """
        當前使用的媒體庫伺服器
        """
        return self._server_type

    def get_activity_log(self, limit):
        """
        獲取媒體伺服器的活動日誌
        :param limit: 條數限制
        """
        if not self.server:
            return []
        return self.server.get_activity_log(limit)

    def get_user_count(self):
        """
        獲取媒體伺服器的總使用者數
        """
        if not self.server:
            return 0
        return self.server.get_user_count()

    def get_medias_count(self):
        """
        獲取媒體伺服器各型別的媒體庫
        :return: MovieCount SeriesCount SongCount
        """
        if not self.server:
            return None
        return self.server.get_medias_count()

    def refresh_root_library(self):
        """
        重新整理媒體伺服器整個媒體庫
        """
        if not self.server:
            return
        return self.server.refresh_root_library()

    def get_image_by_id(self, item_id, image_type):
        """
        根據ItemId從媒體伺服器查詢圖片地址
        :param item_id: 在Emby中的ID
        :param image_type: 圖片的類弄地，poster或者backdrop等
        :return: 圖片對應在TMDB中的URL
        """
        if not self.server:
            return None
        return self.server.get_image_by_id(item_id, image_type)

    def get_no_exists_episodes(self, meta_info,
                               season_number,
                               episode_count):
        """
        根據標題、年份、季、總集數，查詢媒體伺服器中缺少哪幾集
        :param meta_info: 已識別的需要查詢的媒體資訊
        :param season_number: 季號，數字
        :param episode_count: 該季的總集數
        :return: 該季不存在的集號列表
        """
        if not self.server:
            return None
        return self.server.get_no_exists_episodes(meta_info,
                                                  season_number,
                                                  episode_count)

    def get_movies(self, title, year=None):
        """
        根據標題和年份，檢查電影是否在媒體伺服器中存在，存在則返回列表
        :param title: 標題
        :param year: 年份，可以為空，為空時不按年份過濾
        :return: 含title、year屬性的字典列表
        """
        if not self.server:
            return None
        return self.server.get_movies(title, year)

    def refresh_library_by_items(self, items):
        """
        按型別、名稱、年份來重新整理媒體庫
        :param items: 已識別的需要重新整理媒體庫的媒體資訊列表
        """
        if not self.server:
            return
        return self.server.refresh_library_by_items(items)

    def get_libraries(self):
        """
        獲取媒體伺服器所有媒體庫列表
        """
        if not self.server:
            return []
        return self.server.get_libraries()

    def get_items(self, parent):
        """
        獲取媒體庫中的所有媒體
        :param parent: 上一級的ID
        """
        if not self.server:
            return []
        return self.server.get_items(parent)

    def sync_mediaserver(self):
        """
        同步媒體庫所有資料到本地資料庫
        """
        if not self.server:
            return
        with lock:
            # 開始進度條
            log.info("【MEDIASERVER】開始同步媒體庫資料...")
            self.progress.start("mediasync")
            self.progress.update(ptype="mediasync", text="請稍候...")
            # 彙總統計
            medias_count = self.get_medias_count()
            total_media_count = medias_count.get("MovieCount") + medias_count.get("SeriesCount")
            total_count = 0
            movie_count = 0
            tv_count = 0
            # 清空登記薄
            self.mediadb.empty()
            for library in self.get_libraries():
                # 獲取媒體庫所有專案
                self.progress.update(ptype="mediasync",
                                     text="正在獲取 %s 資料..." % (library.get("name")))
                for item in self.get_items(library.get("id")):
                    if not item:
                        continue
                    if self.mediadb.insert(self._server_type.value, item):
                        total_count += 1
                        if item.get("type") in ['Movie', 'movie']:
                            movie_count += 1
                        elif item.get("type") in ['Series', 'show']:
                            tv_count += 1
                        self.progress.update(ptype="mediasync",
                                             text="正在同步 %s，已完成：%s / %s ..." % (library.get("name"), total_count, total_media_count),
                                             value=round(100 * total_count/total_media_count, 1))
            # 更新總體同步情況
            self.mediadb.statistics(server_type=self._server_type.value,
                                    total_count=total_count,
                                    movie_count=movie_count,
                                    tv_count=tv_count)
            # 結束進度條
            self.progress.update(ptype="mediasync",
                                 value=100,
                                 text="媒體庫資料同步完成，同步數量：%s" % total_count)
            self.progress.end("mediasync")
            log.info("【MEDIASERVER】媒體庫資料同步完成，同步數量：%s" % total_count)

    def check_item_exists(self, title, year=None, tmdbid=None):
        """
        檢查媒體庫是否已存在某專案，非實時同步資料，僅用於展示
        """
        return self.mediadb.exists(server_type=self._server_type.value, title=title, year=year, tmdbid=tmdbid)

    def get_mediasync_status(self):
        """
        獲取當前媒體庫同步狀態
        """
        status = self.mediadb.get_statistics(server_type=self._server_type.value)
        if not status:
            return {}
        else:
            return {"movie_count":  status.MOVIE_COUNT, "tv_count": status.TV_COUNT, "time": status.UPDATE_TIME}
