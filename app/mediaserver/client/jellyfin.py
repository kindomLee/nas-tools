import re

import log
from app.utils.exception_utils import ExceptionUtils
from app.utils.types import MediaServerType
from config import Config
from app.mediaserver.media_client import IMediaClient
from app.utils.commons import singleton
from app.utils import RequestUtils, SystemUtils


@singleton
class Jellyfin(IMediaClient):
    _apikey = None
    _host = None
    _user = None
    _libraries = []
    server_type = MediaServerType.JELLYFIN.value

    def __init__(self):
        self.init_config()

    def init_config(self):
        jellyfin = Config().get_config('jellyfin')
        if jellyfin:
            self._host = jellyfin.get('host')
            if self._host:
                if not self._host.startswith('http'):
                    self._host = "http://" + self._host
                if not self._host.endswith('/'):
                    self._host = self._host + "/"
            self._apikey = jellyfin.get('api_key')
            if self._host and self._apikey:
                self._user = self.get_admin_user()

    def get_status(self):
        """
        測試連通性
        """
        return True if self.get_medias_count() else False

    def __get_jellyfin_librarys(self):
        """
        獲取Jellyfin媒體庫的資訊
        """
        if not self._host or not self._apikey:
            return []
        req_url = "%sLibrary/VirtualFolders?api_key=%s" % (self._host, self._apikey)
        try:
            res = RequestUtils().get_res(req_url)
            if res:
                return res.json()
            else:
                log.error(f"【{self.server_type}】Library/VirtualFolders 未獲取到返回資料")
                return []
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Library/VirtualFolders 出錯：" + str(e))
            return []

    def get_user_count(self):
        """
        獲得使用者數量
        """
        if not self._host or not self._apikey:
            return 0
        req_url = "%sUsers?api_key=%s" % (self._host, self._apikey)
        try:
            res = RequestUtils().get_res(req_url)
            if res:
                return len(res.json())
            else:
                log.error(f"【{self.server_type}】Users 未獲取到返回資料")
                return 0
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Users出錯：" + str(e))
            return 0

    def get_admin_user(self):
        """
        獲得管理員使用者
        """
        if not self._host or not self._apikey:
            return None
        req_url = "%sUsers?api_key=%s" % (self._host, self._apikey)
        try:
            res = RequestUtils().get_res(req_url)
            if res:
                users = res.json()
                for user in users:
                    if user.get("Policy", {}).get("IsAdministrator"):
                        return user.get("Id")
            else:
                log.error(f"【{self.server_type}】Users 未獲取到返回資料")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Users出錯：" + str(e))
        return None

    def get_activity_log(self, num):
        """
        獲取Jellyfin活動記錄
        """
        if not self._host or not self._apikey:
            return []
        req_url = "%sSystem/ActivityLog/Entries?api_key=%s&Limit=%s" % (self._host, self._apikey, num)
        ret_array = []
        try:
            res = RequestUtils().get_res(req_url)
            if res:
                ret_json = res.json()
                items = ret_json.get('Items')
                for item in items:
                    if item.get("Type") == "SessionStarted":
                        event_type = "LG"
                        event_date = re.sub(r'\dZ', 'Z', item.get("Date"))
                        event_str = "%s, %s" % (item.get("Name"), item.get("ShortOverview"))
                        activity = {"type": event_type, "event": event_str,
                                    "date": SystemUtils.get_local_time(event_date)}
                        ret_array.append(activity)
                    if item.get("Type") == "VideoPlayback":
                        event_type = "PL"
                        event_date = re.sub(r'\dZ', 'Z', item.get("Date"))
                        activity = {"type": event_type, "event": item.get("Name"),
                                    "date": SystemUtils.get_local_time(event_date)}
                        ret_array.append(activity)
            else:
                log.error(f"【{self.server_type}】System/ActivityLog/Entries 未獲取到返回資料")
                return []
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線System/ActivityLog/Entries出錯：" + str(e))
            return []
        return ret_array

    def get_medias_count(self):
        """
        獲得電影、電視劇、動漫媒體數量
        :return: MovieCount SeriesCount SongCount
        """
        if not self._host or not self._apikey:
            return None
        req_url = "%sItems/Counts?api_key=%s" % (self._host, self._apikey)
        try:
            res = RequestUtils().get_res(req_url)
            if res:
                return res.json()
            else:
                log.error(f"【{self.server_type}】Items/Counts 未獲取到返回資料")
                return {}
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Items/Counts出錯：" + str(e))
            return {}

    def __get_jellyfin_series_id_by_name(self, name, year):
        """
        根據名稱查詢Jellyfin中劇集的SeriesId
        """
        if not self._host or not self._apikey or not self._user:
            return None
        req_url = "%sUsers/%s/Items?api_key=%s&searchTerm=%s&IncludeItemTypes=Series&Limit=10&Recursive=true" % (
            self._host, self._user, self._apikey, name)
        try:
            res = RequestUtils().get_res(req_url)
            if res:
                res_items = res.json().get("Items")
                if res_items:
                    for res_item in res_items:
                        if res_item.get('Name') == name and (
                                not year or str(res_item.get('ProductionYear')) == str(year)):
                            return res_item.get('Id')
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Items出錯：" + str(e))
            return None
        return ""

    def __get_jellyfin_season_id_by_name(self, name, year, season):
        """
        根據名稱查詢Jellyfin中劇集和季對應季的Id
        """
        if not self._host or not self._apikey or not self._user:
            return None, None
        series_id = self.__get_jellyfin_series_id_by_name(name, year)
        if series_id is None:
            return None, None
        if not series_id:
            return "", ""
        if not season:
            season = 1
        req_url = "%sShows/%s/Seasons?api_key=%s&userId=%s" % (
            self._host, series_id, self._apikey, self._user)
        try:
            res = RequestUtils().get_res(req_url)
            if res:
                res_items = res.json().get("Items")
                if res_items:
                    for res_item in res_items:
                        if int(res_item.get('IndexNumber')) == int(season):
                            return series_id, res_item.get('Id')
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Shows/Id/Seasons出錯：" + str(e))
            return None, None
        return "", ""

    def get_movies(self, title, year=None):
        """
        根據標題和年份，檢查電影是否在Jellyfin中存在，存在則返回列表
        :param title: 標題
        :param year: 年份，為空則不過濾
        :return: 含title、year屬性的字典列表
        """
        if not self._host or not self._apikey or not self._user:
            return None
        req_url = "%sUsers/%s/Items?api_key=%s&searchTerm=%s&IncludeItemTypes=Movie&Limit=10&Recursive=true" % (
            self._host, self._user, self._apikey, title)
        try:
            res = RequestUtils().get_res(req_url)
            if res:
                res_items = res.json().get("Items")
                if res_items:
                    ret_movies = []
                    for res_item in res_items:
                        if res_item.get('Name') == title and (
                                not year or str(res_item.get('ProductionYear')) == str(year)):
                            ret_movies.append(
                                {'title': res_item.get('Name'), 'year': str(res_item.get('ProductionYear'))})
                            return ret_movies
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Items出錯：" + str(e))
            return None
        return []

    def __get_jellyfin_tv_episodes(self, title, year=None, tmdb_id=None, season=None):
        """
        根據標題和年份和季，返回Jellyfin中的劇集列表
        :param title: 標題
        :param year: 年份，可以為空，為空時不按年份過濾
        :param tmdb_id: TMDBID
        :param season: 季
        :return: 集號的列表
        """
        if not self._host or not self._apikey or not self._user:
            return None
        # 電視劇
        series_id, season_id = self.__get_jellyfin_season_id_by_name(title, year, season)
        if series_id is None or season_id is None:
            return None
        if not series_id or not season_id:
            return []
        # 驗證tmdbid是否相同
        item_tmdbid = self.get_iteminfo(series_id).get("ProviderIds", {}).get("Tmdb")
        if tmdb_id and item_tmdbid:
            if str(tmdb_id) != str(item_tmdbid):
                return []
        req_url = "%sShows/%s/Episodes?seasonId=%s&&userId=%s&isMissing=false&api_key=%s" % (
            self._host, series_id, season_id, self._user, self._apikey)
        try:
            res_json = RequestUtils().get_res(req_url)
            if res_json:
                res_items = res_json.json().get("Items")
                exists_episodes = []
                for res_item in res_items:
                    exists_episodes.append(int(res_item.get("IndexNumber")))
                return exists_episodes
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Shows/Id/Episodes出錯：" + str(e))
            return None
        return []

    def get_no_exists_episodes(self, meta_info, season, total_num):
        """
        根據標題、年份、季、總集數，查詢Jellyfin中缺少哪幾集
        :param meta_info: 已識別的需要查詢的媒體資訊
        :param season: 季號，數字
        :param total_num: 該季的總集數
        :return: 該季不存在的集號列表
        """
        if not self._host or not self._apikey:
            return None
        exists_episodes = self.__get_jellyfin_tv_episodes(meta_info.title, meta_info.year, meta_info.tmdb_id, season)
        if not isinstance(exists_episodes, list):
            return None
        total_episodes = [episode for episode in range(1, total_num + 1)]
        return list(set(total_episodes).difference(set(exists_episodes)))

    def get_image_by_id(self, item_id, image_type):
        """
        根據ItemId從Jellyfin查詢圖片地址
        :param item_id: 在Emby中的ID
        :param image_type: 圖片的類弄地，poster或者backdrop等
        :return: 圖片對應在TMDB中的URL
        """
        if not self._host or not self._apikey:
            return None
        req_url = "%sItems/%s/RemoteImages?api_key=%s" % (self._host, item_id, self._apikey)
        try:
            res = RequestUtils().get_res(req_url)
            if res:
                images = res.json().get("Images")
                for image in images:
                    if image.get("ProviderName") == "TheMovieDb" and image.get("Type") == image_type:
                        return image.get("Url")
            else:
                log.error(f"【{self.server_type}】Items/RemoteImages 未獲取到返回資料")
                return None
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Items/Id/RemoteImages出錯：" + str(e))
            return None
        return None

    def refresh_root_library(self):
        """
        通知Jellyfin重新整理整個媒體庫
        """
        if not self._host or not self._apikey:
            return False
        req_url = "%sLibrary/Refresh?api_key=%s" % (self._host, self._apikey)
        try:
            res = RequestUtils().post_res(req_url)
            if res:
                return True
            else:
                log.info(f"【{self.server_type}】重新整理媒體庫失敗，無法連線Jellyfin！")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Library/Refresh出錯：" + str(e))
            return False

    def refresh_library_by_items(self, items):
        """
        按型別、名稱、年份來重新整理媒體庫，Jellyfin沒有刷單個專案的API，這裡直接重新整理整庫
        :param items: 已識別的需要重新整理媒體庫的媒體資訊列表
        """
        # 沒找到單專案重新整理的對應的API，先按全庫重新整理
        if not items:
            return False
        if not self._host or not self._apikey:
            return False
        return self.refresh_root_library()

    def get_libraries(self):
        """
        獲取媒體伺服器所有媒體庫列表
        """
        if self._host and self._apikey:
            self._libraries = self.__get_jellyfin_librarys()
        libraries = []
        for library in self._libraries:
            libraries.append({"id": library.get("ItemId"), "name": library.get("Name")})
        return libraries

    def get_iteminfo(self, itemid):
        """
        獲取單個專案詳情
        """
        if not itemid:
            return {}
        if not self._host or not self._apikey:
            return {}
        req_url = "%sUsers/%s/Items/%s?api_key=%s" % (
            self._host, self._user, itemid, self._apikey)
        try:
            res = RequestUtils().get_res(req_url)
            if res and res.status_code == 200:
                return res.json()
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return {}

    def get_items(self, parent):
        """
        獲取媒體伺服器所有媒體庫列表
        """
        if not parent:
            yield {}
        if not self._host or not self._apikey:
            yield {}
        req_url = "%sUsers/%s/Items?parentId=%s&api_key=%s" % (self._host, self._user, parent, self._apikey)
        try:
            res = RequestUtils().get_res(req_url)
            if res and res.status_code == 200:
                results = res.json().get("Items") or []
                for result in results:
                    if not result:
                        continue
                    if result.get("Type") in ["Movie", "Series"]:
                        item_info = self.get_iteminfo(result.get("Id"))
                        yield {"id": result.get("Id"),
                               "library": item_info.get("ParentId"),
                               "type": item_info.get("Type"),
                               "title": item_info.get("Name"),
                               "originalTitle": item_info.get("OriginalTitle"),
                               "year": item_info.get("ProductionYear"),
                               "tmdbid": item_info.get("ProviderIds", {}).get("Tmdb"),
                               "imdbid": item_info.get("ProviderIds", {}).get("Imdb"),
                               "path": item_info.get("Path"),
                               "json": str(item_info)}
                    elif "Folder" in result.get("Type"):
                        for item in self.get_items(result.get("Id")):
                            yield item
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Users/Items出錯：" + str(e))
        yield {}
