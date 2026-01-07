from app.utils.exception_utils import ExceptionUtils
from app.utils.types import MediaServerType
from plexapi.myplex import MyPlexAccount

import log
from config import Config
from app.mediaserver.media_client import IMediaClient
from app.utils.commons import singleton
from plexapi.server import PlexServer


@singleton
class Plex(IMediaClient):
    _host = None
    _token = None
    _username = None
    _password = None
    _servername = None
    _plex = None
    _libraries = []
    server_type = MediaServerType.PLEX.value

    def __init__(self):
        self.init_config()

    def init_config(self):
        plex = Config().get_config('plex')
        if plex:
            self._host = plex.get('host')
            self._token = plex.get('token')
            if self._host:
                if not self._host.startswith('http'):
                    self._host = "http://" + self._host
                if not self._host.endswith('/'):
                    self._host = self._host + "/"
            self._username = plex.get('username')
            self._password = plex.get('password')
            self._servername = plex.get('servername')
            if self._host and self._token:
                try:
                    self._plex = PlexServer(self._host, self._token)
                except Exception as e:
                    ExceptionUtils.exception_traceback(e)
                    self._plex = None
                    log.error(f"【{self.server_type}】Plex伺服器連線失敗：{str(e)}")
            elif self._username and self._password and self._servername:
                try:
                    self._plex = MyPlexAccount(self._username, self._password).resource(self._servername).connect()
                except Exception as e:
                    ExceptionUtils.exception_traceback(e)
                    self._plex = None
                    log.error(f"【{self.server_type}】Plex伺服器連線失敗：{str(e)}")

    def get_status(self):
        """
        測試連通性
        """
        return True if self._plex else False

    @staticmethod
    def get_user_count(**kwargs):
        """
        獲得使用者數量，Plex只能配置一個使用者，固定返回1
        """
        return 1

    def get_activity_log(self, num):
        """
        獲取Plex活動記錄
        """
        if not self._plex:
            return []
        ret_array = []
        historys = self._plex.library.history(num)
        for his in historys:
            event_type = "PL"
            event_date = his.viewedAt.strftime('%Y-%m-%d %H:%M:%S')
            event_str = "開始播放 %s" % his.title
            activity = {"type": event_type, "event": event_str, "date": event_date}
            ret_array.append(activity)
        if ret_array:
            ret_array = sorted(ret_array, key=lambda x: x['date'], reverse=True)
        return ret_array

    def get_medias_count(self):
        """
        獲得電影、電視劇、動漫媒體數量
        :return: MovieCount SeriesCount SongCount
        """
        if not self._plex:
            return {}
        sections = self._plex.library.sections()
        MovieCount = SeriesCount = SongCount = 0
        for sec in sections:
            if sec.type == "movie":
                MovieCount += sec.totalSize
            if sec.type == "show":
                SeriesCount += sec.totalSize
            if sec.type == "artist":
                SongCount += sec.totalSize
        return {"MovieCount": MovieCount, "SeriesCount": SeriesCount, "SongCount": SongCount, "EpisodeCount": 0}

    def get_movies(self, title, year=None):
        """
        根據標題和年份，檢查電影是否在Plex中存在，存在則返回列表
        :param title: 標題
        :param year: 年份，為空則不過濾
        :return: 含title、year屬性的字典列表
        """
        if not self._plex:
            return None
        ret_movies = []
        if year:
            movies = self._plex.library.search(title=title, year=year, libtype="movie")
        else:
            movies = self._plex.library.search(title=title, libtype="movie")
        for movie in movies:
            ret_movies.append({'title': movie.title, 'year': movie.year})
        return ret_movies

    # 根據標題、年份、季、總集數，查詢Plex中缺少哪幾集
    def get_no_exists_episodes(self, meta_info, season, total_num):
        """
        根據標題、年份、季、總集數，查詢Plex中缺少哪幾集
        :param meta_info: 已識別的需要查詢的媒體資訊
        :param season: 季號，數字
        :param total_num: 該季的總集數
        :return: 該季不存在的集號列表
        """
        if not self._plex:
            return None
        exists_episodes = []
        video = self._plex.library.search(title=meta_info.title, year=meta_info.year, libtype="show")
        if video:
            for episode in video[0].episodes():
                if episode.seasonNumber == season:
                    exists_episodes.append(episode.index)
        total_episodes = [episode for episode in range(1, total_num + 1)]
        return list(set(total_episodes).difference(set(exists_episodes)))

    @staticmethod
    def get_image_by_id(**kwargs):
        """
        根據ItemId從Plex查詢圖片地址，該函式Plex下不使用
        """
        return None

    def refresh_root_library(self):
        """
        通知Plex重新整理整個媒體庫
        """
        if not self._plex:
            return False
        return self._plex.library.update()

    def refresh_library_by_items(self, items):
        """
        按型別、名稱、年份來重新整理媒體庫，未找到對應的API，直接刷整庫
        """
        if not self._plex:
            return False
        return self._plex.library.update()

    def get_libraries(self):
        """
        獲取媒體伺服器所有媒體庫列表
        """
        if not self._plex:
            return []
        try:
            self._libraries = self._plex.library.sections()
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return []
        libraries = []
        for library in self._libraries:
            libraries.append({"id": library.key, "name": library.title})
        return libraries

    def get_items(self, parent):
        """
        獲取媒體伺服器所有媒體庫列表
        """
        if not parent:
            yield {}
        if not self._plex:
            yield {}
        try:
            section = self._plex.library.sectionByID(parent)
            if section:
                for item in section.all():
                    if not item:
                        continue
                    yield {"id": item.key,
                           "library": item.librarySectionID,
                           "type": item.type,
                           "title": item.title,
                           "year": item.year,
                           "json": str(item.__dict__)}
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
        yield {}
