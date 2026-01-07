import os
import shutil

import ruamel.yaml

import log
from app.utils.exception_utils import ExceptionUtils
from config import Config
from app.utils.commons import singleton


@singleton
class Category:
    _category_path = None
    _categorys = None
    _tv_categorys = None
    _movie_categorys = None
    _anime_categorys = None

    def __init__(self):
        self.init_config()

    def init_config(self):
        media = Config().get_config('media')
        if media:
            category = media.get('category')
            if not category:
                return
            self._category_path = os.path.join(Config().get_config_path(), "%s.yaml" % category)
            try:
                if not os.path.exists(self._category_path):
                    shutil.copy(os.path.join(Config().get_inner_config_path(), "default-category.yaml"),
                                self._category_path)
                    log.console("【Config】分類配置檔案 %s.yaml 不存在，已將配置檔案模板複製到配置目錄..." % category)
                with open(self._category_path, mode='r', encoding='utf-8') as f:
                    try:
                        yaml = ruamel.yaml.YAML()
                        self._categorys = yaml.load(f)
                    except Exception as e:
                        ExceptionUtils.exception_traceback(e)
                        log.console("【Config】%s.yaml 分類配置檔案格式出現嚴重錯誤！請檢查：%s" % (category, str(e)))
                        self._categorys = {}
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.console("【Config】載入 %s.yaml 配置出錯：%s" % (category, str(err)))
                return False

            if self._categorys:
                self._movie_categorys = self._categorys.get('movie')
                self._tv_categorys = self._categorys.get('tv')
                self._anime_categorys = self._categorys.get('anime')

    def get_movie_category_flag(self):
        """
        獲取電影分類標誌
        """
        if self._movie_categorys:
            return True
        return False

    def get_tv_category_flag(self):
        """
        獲取電視劇分類標誌
        """
        if self._tv_categorys:
            return True
        return False

    def get_anime_category_flag(self):
        """
        獲取動漫分類標誌
        """
        if self._anime_categorys:
            return True
        return False

    def get_movie_categorys(self):
        """
        獲取電影分類清單
        """
        if not self._movie_categorys:
            return []
        return self._movie_categorys.keys()

    def get_tv_categorys(self):
        """
        獲取電視劇分類清單
        """
        if not self._tv_categorys:
            return []
        return self._tv_categorys.keys()

    def get_anime_categorys(self):
        """
        獲取動漫分類清單
        """
        if not self._anime_categorys:
            return []
        return self._anime_categorys.keys()

    def get_movie_category(self, tmdb_info):
        """
        判斷電影的分類
        :param tmdb_info: 識別的TMDB中的資訊
        :return: 二級分類的名稱
        """
        return self.get_category(self._movie_categorys, tmdb_info)

    def get_tv_category(self, tmdb_info):
        """
        判斷電視劇的分類
        :param tmdb_info: 識別的TMDB中的資訊
        :return: 二級分類的名稱
        """
        return self.get_category(self._tv_categorys, tmdb_info)

    def get_anime_category(self, tmdb_info):
        """
        判斷動漫的分類
        :param tmdb_info: 識別的TMDB中的資訊
        :return: 二級分類的名稱
        """
        return self.get_category(self._anime_categorys, tmdb_info)

    @staticmethod
    def get_category(categorys, tmdb_info):
        """
        根據 TMDB資訊與分類配置檔案進行比較，確定所屬分類
        :param categorys: 分類配置
        :param tmdb_info: TMDB資訊
        :return: 分類的名稱
        """
        if not tmdb_info:
            return ""
        if not categorys:
            return ""
        for key, item in categorys.items():
            if not item:
                return key
            match_flag = True
            for attr, value in item.items():
                if not value:
                    continue
                info_value = tmdb_info.get(attr)
                if not info_value:
                    match_flag = False
                    continue
                elif attr == "production_countries":
                    info_values = [str(val.get("iso_3166_1")).upper() for val in info_value]
                else:
                    if isinstance(info_value, list):
                        info_values = [str(val).upper() for val in info_value]
                    else:
                        info_values = [str(info_value).upper()]

                if value.find(",") != -1:
                    values = [str(val).upper() for val in value.split(",")]
                else:
                    values = [str(value).upper()]

                if not set(values).intersection(set(info_values)):
                    match_flag = False
            if match_flag:
                return key
        return ""
