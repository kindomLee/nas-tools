import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import log
from app.helper import ProgressHelper
from app.indexer.client import Prowlarr, Jackett, BuiltinIndexer
from app.utils.types import SearchType
from config import Config


class Indexer(object):

    _client = None
    _client_type = None
    progress = None

    def __init__(self):
        self.progress = ProgressHelper()
        self.init_config()

    def init_config(self):
        if Config().get_config("pt").get('search_indexer') == "prowlarr":
            self._client = Prowlarr()
        elif Config().get_config("pt").get('search_indexer') == "jackett":
            self._client = Jackett()
        else:
            self._client = BuiltinIndexer()
        self._client_type = self._client.index_type

    def get_indexers(self):
        """
        獲取當前索引器的索引站點
        """
        if not self._client:
            return []
        return self._client.get_indexers()

    @staticmethod
    def get_builtin_indexers(check=True, public=True, indexer_id=None):
        """
        獲取內建索引器的索引站點
        """
        return BuiltinIndexer().get_indexers(check=check, public=public, indexer_id=indexer_id)

    @staticmethod
    def list_builtin_resources(index_id, page=0, keyword=None):
        """
        獲取內建索引器的資源列表
        :param index_id: 內建站點ID
        :param page: 頁碼
        :param keyword: 搜尋關鍵字
        """
        return BuiltinIndexer().list(index_id=index_id, page=page, keyword=keyword)

    def get_client(self):
        """
        獲取當前索引器
        """
        return self._client

    def get_client_type(self):
        """
        獲取當前索引器型別
        """
        return self._client_type

    def search_by_keyword(self,
                          key_word,
                          filter_args: dict,
                          match_media=None,
                          in_from: SearchType = None):
        """
        根據關鍵字呼叫 Index API 檢索
        :param key_word: 檢索的關鍵字，不能為空
        :param filter_args: 過濾條件，對應屬性為空則不過濾，{"season":季, "episode":集, "year":年, "type":型別, "site":站點,
                            "":, "restype":質量, "pix":解析度, "sp_state":促銷狀態, "key":其它關鍵字}
                            sp_state: 為UL DL，* 代表不關心，
        :param match_media: 需要匹配的媒體資訊
        :param in_from: 搜尋渠道
        :return: 命中的資源媒體資訊列表
        """
        if not key_word:
            return []

        indexers = self.get_indexers()
        if not indexers:
            log.error(f"【{self._client_type}】沒有有效的索引器配置！")
            return []
        # 計算耗時
        start_time = datetime.datetime.now()
        if filter_args and filter_args.get("site"):
            log.info(f"【{self._client_type}】開始檢索 %s，站點：%s ..." % (key_word, filter_args.get("site")))
            self.progress.update(ptype='search', text="開始檢索 %s，站點：%s ..." % (key_word, filter_args.get("site")))
        else:
            log.info(f"【{self._client_type}】開始並行檢索 %s，執行緒數：%s ..." % (key_word, len(indexers)))
            self.progress.update(ptype='search', text="開始並行檢索 %s，執行緒數：%s ..." % (key_word, len(indexers)))
        # 多執行緒
        executor = ThreadPoolExecutor(max_workers=len(indexers))
        all_task = []
        for index in indexers:
            order_seq = 100 - int(index.pri)
            task = executor.submit(self._client.search,
                                   order_seq,
                                   index,
                                   key_word,
                                   filter_args,
                                   match_media,
                                   in_from)
            all_task.append(task)
        ret_array = []
        finish_count = 0
        for future in as_completed(all_task):
            result = future.result()
            finish_count += 1
            self.progress.update(ptype='search', value=round(100 * (finish_count / len(all_task))))
            if result:
                ret_array = ret_array + result
        # 計算耗時
        end_time = datetime.datetime.now()
        log.info(f"【{self._client_type}】所有站點檢索完成，有效資源數：%s，總耗時 %s 秒"
                 % (len(ret_array), (end_time - start_time).seconds))
        self.progress.update(ptype='search', text="所有站點檢索完成，有效資源數：%s，總耗時 %s 秒"
                                                  % (len(ret_array), (end_time - start_time).seconds),
                             value=100)
        return ret_array
