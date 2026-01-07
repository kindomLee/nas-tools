import os
import pickle
import random
import time
from enum import Enum
from threading import RLock

from app.utils.commons import singleton
from app.utils.exception_utils import ExceptionUtils
from config import Config

lock = RLock()

CACHE_EXPIRE_TIMESTAMP_STR = "cache_expire_timestamp"
EXPIRE_TIMESTAMP = 7 * 24 * 3600


@singleton
class MetaHelper(object):
    """
    {
        "id": '',
        "title": '',
        "year": '',
        "type": MediaType
    }
    """
    _meta_data = {}

    _meta_path = None
    _tmdb_cache_expire = False

    def __init__(self):
        self.init_config()

    def init_config(self):
        laboratory = Config().get_config('laboratory')
        if laboratory:
            self._tmdb_cache_expire = laboratory.get("tmdb_cache_expire")
        self._meta_path = os.path.join(Config().get_config_path(), 'tmdb.dat')
        self._meta_data = self.__load_meta_data(self._meta_path)

    def clear_meta_data(self):
        """
        清空所有TMDB快取
        """
        with lock:
            self._meta_data = {}

    def get_meta_data_path(self):
        """
        返回TMDB快取檔案路徑
        """
        return self._meta_path

    def get_meta_data_by_key(self, key):
        """
        根據KEY值獲取快取值
        """
        with lock:
            info: dict = self._meta_data.get(key)
            if info:
                expire = info.get(CACHE_EXPIRE_TIMESTAMP_STR)
                if not expire or int(time.time()) < expire:
                    info[CACHE_EXPIRE_TIMESTAMP_STR] = int(time.time()) + EXPIRE_TIMESTAMP
                    self.update_meta_data({key: info})
                elif expire and self._tmdb_cache_expire:
                    self.delete_meta_data(key)
            return info or {}

    def dump_meta_data(self, search, page, num):
        """
        分頁獲取當前快取列表
        @param search: 檢索的快取key
        @param page: 頁碼
        @param num: 單頁大小
        @return: 總數, 快取列表
        """
        if page == 1:
            begin_pos = 0
        else:
            begin_pos = (page - 1) * num

        with lock:
            search_metas = [(k, {
                "id": v.get("id"),
                "title": v.get("title"),
                "year": v.get("year"),
                "media_type": v.get("type").value if isinstance(v.get("type"), Enum) else v.get("type"),
                "poster_path": v.get("poster_path"),
                "backdrop_path": v.get("backdrop_path")
            },  str(k).replace("[電影]", "").replace("[電視劇]", "").replace("[未知]", "").replace("-None", ""))
                for k, v in self._meta_data.items() if search.lower() in k.lower() and v.get("id") != 0]
            return len(search_metas), search_metas[begin_pos: begin_pos + num]

    def delete_meta_data(self, key):
        """
        刪除快取資訊
        @param key: 快取key
        @return: 被刪除的快取內容
        """
        with lock:
            return self._meta_data.pop(key, None)

    def delete_meta_data_by_tmdbid(self, tmdbid):
        """
        清空對應TMDBID的所有快取記錄，以強制更新TMDB中最新的資料
        """
        for key in list(self._meta_data):
            if str(self._meta_data.get(key, {}).get("id")) == str(tmdbid):
                with lock:
                    self._meta_data.pop(key)

    def delete_unknown_meta(self):
        """
        清除未識別的快取記錄，以便重新檢索TMDB
        """
        for key in list(self._meta_data):
            if str(self._meta_data.get(key, {}).get("id")) == '0':
                with lock:
                    self._meta_data.pop(key)

    def modify_meta_data(self, key, title):
        """
        刪除快取資訊
        @param key: 快取key
        @param title: 標題
        @return: 被修改後快取內容
        """
        with lock:
            if self._meta_data.get(key):
                self._meta_data[key]['title'] = title
                self._meta_data[key][CACHE_EXPIRE_TIMESTAMP_STR] = int(time.time()) + EXPIRE_TIMESTAMP
            return self._meta_data.get(key)

    @staticmethod
    def __load_meta_data(path):
        """
        從檔案中載入快取
        """
        try:
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    data = pickle.load(f)
                return data
            return {}
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return {}

    def update_meta_data(self, meta_data):
        """
        新增或更新快取條目
        """
        if not meta_data:
            return
        with lock:
            for key, item in meta_data.items():
                if not self._meta_data.get(key):
                    item[CACHE_EXPIRE_TIMESTAMP_STR] = int(time.time()) + EXPIRE_TIMESTAMP
                    self._meta_data[key] = item

    def save_meta_data(self, force=False):
        """
        儲存快取資料到檔案
        """
        meta_data = self.__load_meta_data(self._meta_path)
        new_meta_data = {k: v for k, v in self._meta_data.items() if str(v.get("id")) != '0'}

        if not force \
                and not self._random_sample(new_meta_data) \
                and meta_data.keys() == new_meta_data.keys():
            return

        with open(self._meta_path, 'wb') as f:
            pickle.dump(new_meta_data, f, pickle.HIGHEST_PROTOCOL)

    def _random_sample(self, new_meta_data):
        """
        取樣分析是否需要儲存
        """
        ret = False
        if len(new_meta_data) < 25:
            keys = list(new_meta_data.keys())
            for k in keys:
                info = new_meta_data.get(k)
                expire = info.get(CACHE_EXPIRE_TIMESTAMP_STR)
                if not expire:
                    ret = True
                    info[CACHE_EXPIRE_TIMESTAMP_STR] = int(time.time()) + EXPIRE_TIMESTAMP
                elif int(time.time()) >= expire:
                    ret = True
                    if self._tmdb_cache_expire:
                        new_meta_data.pop(k)
        else:
            count = 0
            keys = random.sample(new_meta_data.keys(), 25)
            for k in keys:
                info = new_meta_data.get(k)
                expire = info.get(CACHE_EXPIRE_TIMESTAMP_STR)
                if not expire:
                    ret = True
                    info[CACHE_EXPIRE_TIMESTAMP_STR] = int(time.time()) + EXPIRE_TIMESTAMP
                elif int(time.time()) >= expire:
                    ret = True
                    if self._tmdb_cache_expire:
                        new_meta_data.pop(k)
                        count += 1
            if count >= 5:
                ret |= self._random_sample(new_meta_data)
        return ret

    def get_cache_title(self, key):
        """
        獲取快取的標題
        """
        cache_media_info = self._meta_data.get(key)
        if not cache_media_info or not cache_media_info.get("id"):
            return None
        return cache_media_info.get("title")

    def set_cache_title(self, key, cn_title):
        """
        重新設定快取標題
        """
        cache_media_info = self._meta_data.get(key)
        if not cache_media_info:
            return
        self._meta_data[key]['title'] = cn_title
