import os
import re

import log
from app.utils.exception_utils import ExceptionUtils
from config import Config
from app.mediaserver.media_client import IMediaClient
from app.utils.commons import singleton
from app.utils import RequestUtils, SystemUtils
from app.utils.types import MediaType, MediaServerType


@singleton
class Emby(IMediaClient):
    _apikey = None
    _host = None
    _user = None
    _libraries = []
    server_type = MediaServerType.EMBY.value

    def __init__(self):
        self.init_config()

    def init_config(self):
        emby = Config().get_config('emby')
        if emby:
            self._host = emby.get('host')
            if self._host:
                if not self._host.startswith('http'):
                    self._host = "http://" + self._host
                if not self._host.endswith('/'):
                    self._host = self._host + "/"
            self._apikey = emby.get('api_key')
            if self._host and self._apikey:
                self._libraries = self.__get_emby_librarys()
                self._user = self.get_admin_user()

    def get_status(self):
        """
        測試連通性
        """
        return True if self.get_medias_count() else False

    def __get_emby_librarys(self):
        """
        獲取Emby媒體庫列表
        """
        if not self._host or not self._apikey:
            return []
        req_url = "%semby/Library/SelectableMediaFolders?api_key=%s" % (self._host, self._apikey)
        try:
            res = RequestUtils().get_res(req_url)
            if res:
                return res.json()
            else:
                log.error(f"【{self.server_type}】Library/SelectableMediaFolders 未獲取到返回資料")
                return []
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Library/SelectableMediaFolders 出錯：" + str(e))
            return []

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

    def get_user_count(self):
        """
        獲得使用者數量
        """
        if not self._host or not self._apikey:
            return 0
        req_url = "%semby/Users/Query?api_key=%s" % (self._host, self._apikey)
        try:
            res = RequestUtils().get_res(req_url)
            if res:
                return res.json().get("TotalRecordCount")
            else:
                log.error(f"【{self.server_type}】Users/Query 未獲取到返回資料")
                return 0
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Users/Query出錯：" + str(e))
            return 0

    def get_activity_log(self, num):
        """
        獲取Emby活動記錄
        """
        if not self._host or not self._apikey:
            return []
        req_url = "%semby/System/ActivityLog/Entries?api_key=%s&" % (self._host, self._apikey)
        ret_array = []
        try:
            res = RequestUtils().get_res(req_url)
            if res:
                ret_json = res.json()
                items = ret_json.get('Items')
                for item in items:
                    if item.get("Type") == "AuthenticationSucceeded":
                        event_type = "LG"
                        event_date = SystemUtils.get_local_time(item.get("Date"))
                        event_str = "%s, %s" % (item.get("Name"), item.get("ShortOverview"))
                        activity = {"type": event_type, "event": event_str, "date": event_date}
                        ret_array.append(activity)
                    if item.get("Type") == "VideoPlayback":
                        event_type = "PL"
                        event_date = SystemUtils.get_local_time(item.get("Date"))
                        event_str = item.get("Name")
                        activity = {"type": event_type, "event": event_str, "date": event_date}
                        ret_array.append(activity)
            else:
                log.error(f"【{self.server_type}】System/ActivityLog/Entries 未獲取到返回資料")
                return []
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線System/ActivityLog/Entries出錯：" + str(e))
            return []
        return ret_array[:num]

    def get_medias_count(self):
        """
        獲得電影、電視劇、動漫媒體數量
        :return: MovieCount SeriesCount SongCount
        """
        if not self._host or not self._apikey:
            return {}
        req_url = "%semby/Items/Counts?api_key=%s" % (self._host, self._apikey)
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

    def __get_emby_series_id_by_name(self, name, year):
        """
        根據名稱查詢Emby中劇集的SeriesId
        :param name: 標題
        :param year: 年份
        :return: None 表示連不通，""表示未找到，找到返回ID
        """
        if not self._host or not self._apikey:
            return None
        req_url = "%semby/Items?IncludeItemTypes=Series&Fields=ProductionYear&StartIndex=0&Recursive=true&SearchTerm=%s&Limit=10&IncludeSearchTypes=false&api_key=%s" % (
            self._host, name, self._apikey)
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

    def get_movies(self, title, year=None):
        """
        根據標題和年份，檢查電影是否在Emby中存在，存在則返回列表
        :param title: 標題
        :param year: 年份，可以為空，為空時不按年份過濾
        :return: 含title、year屬性的字典列表
        """
        if not self._host or not self._apikey:
            return None
        req_url = "%semby/Items?IncludeItemTypes=Movie&Fields=ProductionYear&StartIndex=0&Recursive=true&SearchTerm=%s&Limit=10&IncludeSearchTypes=false&api_key=%s" % (
            self._host, title, self._apikey)
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

    def __get_emby_tv_episodes(self, title, year, tmdb_id=None, season=None):
        """
        根據標題和年份和季，返回Emby中的劇集列表
        :param title: 標題
        :param year: 年份，可以為空，為空時不按年份過濾
        :param tmdb_id: TMDBID
        :param season: 季
        :return: 集號的列表
        """
        if not self._host or not self._apikey:
            return None
        # 電視劇
        item_id = self.__get_emby_series_id_by_name(title, year)
        if item_id is None:
            return None
        if not item_id:
            return []
        # 驗證tmdbid是否相同
        item_tmdbid = self.get_iteminfo(item_id).get("ProviderIds", {}).get("Tmdb")
        if tmdb_id and item_tmdbid:
            if str(tmdb_id) != str(item_tmdbid):
                return []
        # /Shows/Id/Episodes 查集的資訊
        if not season:
            season = 1
        req_url = "%semby/Shows/%s/Episodes?Season=%s&IsMissing=false&api_key=%s" % (
            self._host, item_id, season, self._apikey)
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
        根據標題、年份、季、總集數，查詢Emby中缺少哪幾集
        :param meta_info: 已識別的需要查詢的媒體資訊
        :param season: 季號，數字
        :param total_num: 該季的總集數
        :return: 該季不存在的集號列表
        """
        if not self._host or not self._apikey:
            return None
        exists_episodes = self.__get_emby_tv_episodes(meta_info.title, meta_info.year, meta_info.tmdb_id, season)
        if not isinstance(exists_episodes, list):
            return None
        total_episodes = [episode for episode in range(1, total_num + 1)]
        return list(set(total_episodes).difference(set(exists_episodes)))

    def get_image_by_id(self, item_id, image_type):
        """
        根據ItemId從Emby查詢圖片地址
        :param item_id: 在Emby中的ID
        :param image_type: 圖片的類弄地，poster或者backdrop等
        :return: 圖片對應在TMDB中的URL
        """
        if not self._host or not self._apikey:
            return None
        req_url = "%semby/Items/%s/RemoteImages?api_key=%s" % (self._host, item_id, self._apikey)
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

    def __refresh_emby_library_by_id(self, item_id):
        """
        通知Emby重新整理一個專案的媒體庫
        """
        if not self._host or not self._apikey:
            return False
        req_url = "%semby/Items/%s/Refresh?Recursive=true&api_key=%s" % (self._host, item_id, self._apikey)
        try:
            res = RequestUtils().post_res(req_url)
            if res:
                return True
            else:
                log.info(f"【{self.server_type}】重新整理媒體庫物件 {item_id} 失敗，無法連線Emby！")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Items/Id/Refresh出錯：" + str(e))
            return False
        return False

    def refresh_root_library(self):
        """
        通知Emby重新整理整個媒體庫
        """
        if not self._host or not self._apikey:
            return False
        req_url = "%semby/Library/Refresh?api_key=%s" % (self._host, self._apikey)
        try:
            res = RequestUtils().post_res(req_url)
            if res:
                return True
            else:
                log.info(f"【{self.server_type}】重新整理媒體庫失敗，無法連線Emby！")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Library/Refresh出錯：" + str(e))
            return False
        return False

    def refresh_library_by_items(self, items):
        """
        按型別、名稱、年份來重新整理媒體庫
        :param items: 已識別的需要重新整理媒體庫的媒體資訊列表
        """
        if not items:
            return
        # 收集要重新整理的媒體庫資訊
        log.info(f"【{self.server_type}】開始重新整理Emby媒體庫...")
        library_ids = []
        for item in items:
            if not item:
                continue
            library_id = self.__get_emby_library_id_by_item(item)
            if library_id and library_id not in library_ids:
                library_ids.append(library_id)
        # 開始重新整理媒體庫
        if "/" in library_ids:
            self.refresh_root_library()
            return
        for library_id in library_ids:
            if library_id != "/":
                self.__refresh_emby_library_by_id(library_id)
        log.info(f"【{self.server_type}】Emby媒體庫重新整理完成")

    def __get_emby_library_id_by_item(self, item):
        """
        根據媒體資訊查詢在哪個媒體庫，返回要重新整理的位置的ID
        :param item: 由title、year、type組成的字典
        """
        if not item.get("title") or not item.get("year") or not item.get("type"):
            return None
        if item.get("type") == MediaType.TV:
            item_id = self.__get_emby_series_id_by_name(item.get("title"), item.get("year"))
            if item_id:
                # 存在電視劇，則直接重新整理這個電視劇就行
                return item_id
        else:
            if self.get_movies(item.get("title"), item.get("year")):
                # 已存在，不用重新整理
                return None
        # 查詢需要重新整理的媒體庫ID
        for library in self._libraries:
            # 找同級路徑最多的媒體庫（要求容器內對映路徑與實際一致）
            max_equal_path_id = None
            max_path_len = 0
            equal_path_num = 0
            for folder in library.get("SubFolders"):
                path_list = re.split(pattern='/+|\\\\+', string=folder.get("Path"))
                if item.get("category") != path_list[-1]:
                    continue
                try:
                    path_len = len(os.path.commonpath([item.get("target_path"), folder.get("Path")]))
                    if path_len >= max_path_len:
                        max_path_len = path_len
                        max_equal_path_id = folder.get("Id")
                        equal_path_num += 1
                except Exception as err:
                    ExceptionUtils.exception_traceback(err)
                    continue
            if max_equal_path_id:
                return max_equal_path_id if equal_path_num == 1 else library.get("Id")
            # 如果找不到，只要路徑中有分類目錄名就命中
            for folder in library.get("SubFolders"):
                if folder.get("Path") and re.search(r"[/\\]%s" % item.get("category"), folder.get("Path")):
                    return library.get("Id")
        # 重新整理根目錄
        return "/"

    def get_libraries(self):
        """
        獲取媒體伺服器所有媒體庫列表
        """
        if self._host and self._apikey:
            self._libraries = self.__get_emby_librarys()
        libraries = []
        for library in self._libraries:
            libraries.append({"id": library.get("Id"), "name": library.get("Name")})
        return libraries

    def get_iteminfo(self, itemid):
        """
        獲取單個專案詳情
        """
        if not itemid:
            return {}
        if not self._host or not self._apikey:
            return {}
        req_url = "%semby/Users/%s/Items/%s?api_key=%s" % (self._host, self._user, itemid, self._apikey)
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
        req_url = "%semby/Users/%s/Items?ParentId=%s&api_key=%s" % (self._host, self._user, parent, self._apikey)
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
                        for item in self.get_items(parent=result.get('Id')):
                            yield item
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error(f"【{self.server_type}】連線Users/Items出錯：" + str(e))
        yield {}
