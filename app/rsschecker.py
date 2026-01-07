import json
import traceback

import jsonpath
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from lxml import etree

import log
from app.downloader import Downloader
from app.filter import Filter
from app.helper import DbHelper
from app.media import Media, MetaInfo
from app.message import Message
from app.searcher import Searcher
from app.subscribe import Subscribe
from app.utils import RequestUtils, StringUtils
from app.utils.commons import singleton
from app.utils.exception_utils import ExceptionUtils
from app.utils.types import MediaType, SearchType
from config import Config


@singleton
class RssChecker(object):
    message = None
    searcher = None
    filter = None
    media = None
    filterrule = None
    downloader = None
    subscribe = None
    dbhelper = None

    _scheduler = None
    _rss_tasks = []
    _rss_parsers = []
    _site_users = {
        "D": "下載",
        "R": "訂閱",
        "S": "搜尋"
    }

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.dbhelper = DbHelper()
        self.message = Message()
        self.searcher = Searcher()
        self.filter = Filter()
        self.media = Media()
        self.downloader = Downloader()
        self.subscribe = Subscribe()
        # 移除現有任務
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
        # 讀取解析器列表
        rss_parsers = self.dbhelper.get_userrss_parser()
        self._rss_parsers = []
        for rss_parser in rss_parsers:
            self._rss_parsers.append(
                {
                    "id": rss_parser.ID,
                    "name": rss_parser.NAME,
                    "type": rss_parser.TYPE,
                    "format": rss_parser.FORMAT,
                    "params": rss_parser.PARAMS,
                    "note": rss_parser.NOTE
                }
            )
        # 讀取任務任務列表
        rsstasks = self.dbhelper.get_userrss_tasks()
        self._rss_tasks = []
        for task in rsstasks:
            parser = self.get_userrss_parser(task.PARSER)
            if task.FILTER:
                filterrule = self.filter.get_rule_groups(groupid=task.FILTER)
            else:
                filterrule = {}
            # 相容舊配置
            note = task.NOTE
            if str(note).find('seeding_time_limit') != -1:
                note = json.loads(task.NOTE)
                save_path = note.get("save_path")
                download_setting = -1
            else:
                save_path = note
                download_setting = -1
            self._rss_tasks.append({
                "id": task.ID,
                "name": task.NAME,
                "address": task.ADDRESS,
                "parser": task.PARSER,
                "parser_name": parser.get("name") if parser else "",
                "interval": task.INTERVAL,
                "uses": task.USES,
                "uses_text": self._site_users.get(task.USES),
                "include": task.INCLUDE,
                "exclude": task.EXCLUDE,
                "filter": task.FILTER,
                "filter_name": filterrule.get("name") if filterrule else "",
                "update_time": task.UPDATE_TIME,
                "counter": task.PROCESS_COUNT,
                "state": task.STATE,
                "save_path": task.SAVE_PATH or save_path,
                "download_setting": task.DOWNLOAD_SETTING or download_setting
            })
        if not self._rss_tasks:
            return
        # 啟動RSS任務
        self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai",
                                              executors={
                                                  'default': ThreadPoolExecutor(30)
                                              })
        rss_flag = False
        for task in self._rss_tasks:
            if task.get("state") == "Y" and task.get("interval") and str(task.get("interval")).isdigit():
                rss_flag = True
                self._scheduler.add_job(func=self.check_task_rss,
                                        args=[task.get("id")],
                                        trigger='interval',
                                        seconds=int(task.get("interval")) * 60)
        if rss_flag:
            self._scheduler.print_jobs()
            self._scheduler.start()
            log.info("自定義訂閱服務啟動")

    def get_rsstask_info(self, taskid=None):
        """
        獲取單個RSS任務詳細資訊
        """
        if taskid:
            if str(taskid).isdigit():
                taskid = int(taskid)
                for task in self._rss_tasks:
                    if task.get("id") == taskid:
                        return task
            else:
                return {}
        return self._rss_tasks

    def check_task_rss(self, taskid):
        """
        處理自定義RSS任務，由定時服務呼叫
        :param taskid: 自定義RSS的ID
        """
        if not taskid:
            return
        # 需要下載的專案
        rss_download_torrents = []
        # 需要訂閱的專案
        rss_subscribe_torrents = []
        # 需要搜尋的專案
        rss_search_torrents = []
        # 任務資訊
        taskinfo = self.get_rsstask_info(taskid)
        if not taskinfo:
            return
        rss_result = self.__parse_userrss_result(taskinfo)
        if len(rss_result) == 0:
            log.warn("【RssChecker】%s 未下載到資料" % taskinfo.get("name"))
            return
        else:
            log.info("【RssChecker】%s 獲取資料：%s" % (taskinfo.get("name"), len(rss_result)))
        # 處理RSS結果
        res_num = 0
        no_exists = {}
        for res in rss_result:
            try:
                # 種子名
                title = res.get('title')
                if not title:
                    continue
                # 種子連結
                enclosure = res.get('enclosure')
                # 種子頁面
                page_url = res.get('link')
                # 副標題
                description = res.get('description')
                # 種子大小
                size = res.get('size')
                # 年份
                year = res.get('year')
                if year and len(year) > 4:
                    year = year[:4]
                # 型別
                mediatype = res.get('type')
                if mediatype:
                    mediatype = MediaType.MOVIE if mediatype == "movie" else MediaType.TV

                log.info("【RssChecker】開始處理：%s" % title)

                # 檢查是不是處理過
                meta_name = "%s %s" % (title, year) if year else title
                if self.dbhelper.is_userrss_finished(meta_name, enclosure):
                    log.info("【RssChecker】%s 已處理過" % title)
                    continue

                if taskinfo.get("uses") != "R":
                    # 識別種子名稱，開始檢索TMDB
                    media_info = MetaInfo(title=meta_name,
                                          subtitle=description,
                                          mtype=mediatype)
                    cache_info = self.media.get_cache_info(media_info)
                    if cache_info.get("id"):
                        # 有快取，直接使用快取
                        media_info.tmdb_id = cache_info.get("id")
                        media_info.type = cache_info.get("type")
                        media_info.title = cache_info.get("title")
                        media_info.year = cache_info.get("year")
                    else:
                        media_info = self.media.get_media_info(title=meta_name,
                                                               subtitle=description,
                                                               mtype=mediatype)
                        if not media_info:
                            log.warn("【RssChecker】%s 識別媒體資訊出錯！" % title)
                            continue
                        if not media_info.tmdb_info:
                            log.info("【RssChecker】%s 識別為 %s 未匹配到媒體資訊" % (title, media_info.get_name()))
                            continue
                    # 檢查是否已存在
                    if media_info.type == MediaType.MOVIE:
                        exist_flag, no_exists, _ = self.downloader.check_exists_medias(meta_info=media_info,
                                                                                       no_exists=no_exists)
                        if exist_flag:
                            log.info("【RssChecker】電影 %s 已存在" % media_info.get_title_string())
                            continue
                    else:
                        exist_flag, no_exists, _ = self.downloader.check_exists_medias(meta_info=media_info,
                                                                                       no_exists=no_exists)
                        # 當前劇集已存在，跳過
                        if exist_flag:
                            # 已全部存在
                            if not no_exists or not no_exists.get(
                                    media_info.tmdb_id):
                                log.info("【RssChecker】電視劇 %s %s 已存在" % (
                                    media_info.get_title_string(), media_info.get_season_episode_string()))
                            continue
                        if no_exists.get(media_info.tmdb_id):
                            log.info("【RssChecker】%s 缺失季集：%s"
                                     % (media_info.get_title_string(), no_exists.get(media_info.tmdb_id)))
                    # 大小及種子頁面
                    media_info.set_torrent_info(size=size,
                                                page_url=page_url,
                                                site=taskinfo.get("name"),
                                                enclosure=enclosure)
                    # 檢查種子是否匹配過濾條件
                    filter_args = {
                        "include": taskinfo.get("include"),
                        "exclude": taskinfo.get("exclude"),
                        "rule": taskinfo.get("filter")
                    }
                    match_flag, res_order, match_msg = self.filter.check_torrent_filter(meta_info=media_info,
                                                                                        filter_args=filter_args)
                    # 未匹配
                    if not match_flag:
                        log.info(f"【RssChecker】{match_msg}")
                        continue
                    else:
                        # 匹配優先順序
                        media_info.set_torrent_info(res_order=res_order)
                        log.info("【RssChecker】%s 識別為 %s %s 匹配成功" % (
                            title,
                            media_info.get_title_string(),
                            media_info.get_season_episode_string()))
                        # 補充TMDB完整資訊
                        if not media_info.tmdb_info:
                            media_info.set_tmdb_info(self.media.get_tmdb_info(mtype=media_info.type,
                                                                              tmdbid=media_info.tmdb_id))
                else:
                    media_info = MetaInfo(title=meta_name, subtitle=description, mtype=mediatype)

                # 下載
                if taskinfo.get("uses") == "D":
                    if not enclosure:
                        log.warn("【RssChecker】%s RSS報文中沒有enclosure種子連結" % taskinfo.get("name"))
                        continue
                    if media_info not in rss_download_torrents:
                        media_info.set_download_info(download_setting=taskinfo.get("download_setting"),
                                                     save_path=taskinfo.get("save_path"))
                        rss_download_torrents.append(media_info)
                        res_num = res_num + 1
                # 訂閱
                elif taskinfo.get("uses") == "R":
                    # 訂閱型別的 保持現狀直接插入資料庫
                    self.dbhelper.insert_rss_torrents(media_info)
                    if media_info not in rss_subscribe_torrents:
                        rss_subscribe_torrents.append(media_info)
                        res_num = res_num + 1
                # 搜尋
                elif taskinfo.get("uses") == "S":
                    # 搜尋型別的 保持現狀直接插入資料庫
                    self.dbhelper.insert_rss_torrents(media_info)
                    if media_info not in rss_search_torrents:
                        rss_search_torrents.append(media_info)
                        res_num = res_num + 1
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error("【RssChecker】處理RSS發生錯誤：%s - %s" % (str(e), traceback.format_exc()))
                continue
        log.info("【RssChecker】%s 處理結束，匹配到 %s 個有效資源" % (taskinfo.get("name"), res_num))
        # 新增下載
        if rss_download_torrents:
            for media in rss_download_torrents:
                ret, ret_msg = self.downloader.download(media_info=media,
                                                        download_dir=media.save_path,
                                                        download_setting=media.download_setting)
                if ret:
                    self.message.send_download_message(in_from=SearchType.USERRSS,
                                                       can_item=media)
                    # 下載型別的 這裡下載成功了 插入資料庫
                    self.dbhelper.insert_rss_torrents(media)
                    # 登記自定義RSS任務下載記錄
                    downloader = self.downloader.get_default_client_type().value
                    if media.download_setting:
                        download_attr = self.downloader.get_download_setting(media.download_setting)
                        if download_attr.get("downloader"):
                            downloader = download_attr.get("downloader")
                    self.dbhelper.insert_userrss_task_history(taskid, media.org_string, downloader)
                else:
                    log.error("【RssChecker】新增下載任務 %s 失敗：%s" % (
                        media.get_title_string(), ret_msg or "請檢查下載任務是否已存在"))
                    if ret_msg:
                        self.message.send_download_fail_message(media, ret_msg)
        # 新增訂閱
        if rss_subscribe_torrents:
            for media in rss_subscribe_torrents:
                code, msg, rss_media = self.subscribe.add_rss_subscribe(mtype=media.type,
                                                                        name=media.get_name(),
                                                                        year=media.year,
                                                                        season=media.begin_season)
                if rss_media and code == 0:
                    self.message.send_rss_success_message(in_from=SearchType.USERRSS, media_info=rss_media)
                else:
                    log.warn("【RssChecker】%s 新增訂閱失敗：%s" % (media.get_name(), msg))
        # 直接搜尋
        if rss_search_torrents:
            for media in rss_search_torrents:
                self.searcher.search_one_media(in_from=SearchType.USERRSS,
                                               media_info=media,
                                               no_exists=no_exists)

        # 更新狀態
        counter = len(rss_download_torrents) + len(rss_subscribe_torrents) + len(rss_search_torrents)
        if counter:
            self.dbhelper.update_userrss_task_info(taskid, counter)

    def __parse_userrss_result(self, taskinfo):
        """
        獲取RSS連結資料，根據PARSER進行解析獲取返回結果
        """
        rss_parser = self.get_userrss_parser(taskinfo.get("parser"))
        if not rss_parser:
            log.error("【RssChecker】任務 %s 的解析配置不存在" % taskinfo.get("name"))
            return []
        if not rss_parser.get("format"):
            log.error("【RssChecker】任務 %s 的解析配置不正確" % taskinfo.get("name"))
            return []
        try:
            rss_parser_format = json.loads(rss_parser.get("format"))
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error("【RssChecker】任務 %s 的解析配置不是合法的Json格式" % taskinfo.get("name"))
            return []
        # 拼裝連結
        rss_url = taskinfo.get("address")
        if not rss_url:
            return []
        if rss_parser.get("params"):
            _dict = {
                "TMDBKEY": Config().get_config("app").get("rmt_tmdbkey")
            }
            try:
                param_url = rss_parser.get("params").format(**_dict)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error("【RssChecker】任務 %s 的解析配置附加引數不合法" % taskinfo.get("name"))
                return []
            rss_url = "%s?%s" % (rss_url, param_url) if rss_url.find("?") == -1 else "%s&%s" % (rss_url, param_url)
        # 請求資料
        try:
            ret = RequestUtils().get_res(rss_url)
            if not ret:
                return []
            ret.encoding = ret.apparent_encoding
        except Exception as e2:
            ExceptionUtils.exception_traceback(e2)
            return []
        # 解析資料 XPATH
        rss_result = []
        if rss_parser.get("type") == "XML":
            try:
                result_tree = etree.XML(ret.text.encode("utf-8"))
                item_list = result_tree.xpath(rss_parser_format.get("list")) or []
                for item in item_list:
                    rss_item = {}
                    for key, attr in rss_parser_format.get("item", {}).items():
                        if attr.get("path"):
                            if attr.get("namespaces"):
                                value = item.xpath("//ns:%s" % attr.get("path"),
                                                   namespaces={"ns": attr.get("namespaces")})
                            else:
                                value = item.xpath(attr.get("path"))
                        elif attr.get("value"):
                            value = attr.get("value")
                        else:
                            continue
                        if value:
                            rss_item.update({key: value[0]})
                    rss_result.append(rss_item)
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error("【RssChecker】任務 %s 獲取的訂閱報文無法解析：%s" % (taskinfo.get("name"), str(err)))
                return []
        elif rss_parser.get("type") == "JSON":
            try:
                result_json = json.loads(ret.text)
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error("【RssChecker】任務 %s 獲取的訂閱報文不是合法的Json格式：%s" % (taskinfo.get("name"), str(err)))
                return []
            item_list = jsonpath.jsonpath(result_json, rss_parser_format.get("list"))[0]
            if not isinstance(item_list, list):
                log.error("【RssChecker】任務 %s 獲取的訂閱報文list後不是列表" % taskinfo.get("name"))
                return []
            for item in item_list:
                rss_item = {}
                for key, attr in rss_parser_format.get("item", {}).items():
                    if attr.get("path"):
                        value = jsonpath.jsonpath(item, attr.get("path"))
                    elif attr.get("value"):
                        value = attr.get("value")
                    else:
                        continue
                    if value:
                        rss_item.update({key: value[0]})
                rss_result.append(rss_item)
        return rss_result

    def get_userrss_parser(self, pid=None):
        if pid:
            for rss_parser in self._rss_parsers:
                if rss_parser.get("id") == int(pid):
                    return rss_parser
            return {}
        else:
            return self._rss_parsers

    def get_rss_articles(self, taskid):
        """
        檢視自定義RSS報文
        :param taskid: 自定義RSS的ID
        """
        if not taskid:
            return
        # 下載訂閱的文章列表
        rss_articles = []
        # 任務資訊
        taskinfo = self.get_rsstask_info(taskid)
        if not taskinfo:
            return
        rss_result = self.__parse_userrss_result(taskinfo)
        if len(rss_result) == 0:
            return []
        for res in rss_result:
            try:
                # 種子名
                title = res.get('title')
                if not title:
                    continue
                # 種子連結
                enclosure = res.get('enclosure')
                # 種子頁面
                link = res.get('link')
                # 副標題
                description = res.get('description')
                # 種子大小
                size = res.get('size')
                # 釋出日期
                date = StringUtils.unify_datetime_str(res.get('date'))
                # 年份
                year = res.get('year')
                if year and len(year) > 4:
                    year = year[:4]
                # 檢查是不是處理過
                meta_name = "%s %s" % (title, year) if year else title
                finish_flag = self.dbhelper.is_userrss_finished(meta_name, enclosure)
                # 資訊聚合
                params = {
                    "title": title,
                    "link": link,
                    "enclosure": enclosure,
                    "size": size,
                    "description": description,
                    "date": date,
                    "finish_flag": finish_flag,
                }
                if params not in rss_articles:
                    rss_articles.append(params)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error("【RssChecker】獲取RSS報文發生錯誤：%s - %s" % (str(e), traceback.format_exc()))
        return rss_articles

    def test_rss_articles(self, taskid, title):
        """
        測試RSS報文
        :param taskid: 自定義RSS的ID
        :param title: RSS報文title
        """
        # 任務資訊
        taskinfo = self.get_rsstask_info(taskid)
        if not taskinfo:
            return
        # 識別種子名稱，開始檢索TMDB
        media_info = MetaInfo(title=title)
        cache_info = self.media.get_cache_info(media_info)
        if cache_info.get("id"):
            # 有快取，直接使用快取
            media_info.tmdb_id = cache_info.get("id")
            media_info.type = cache_info.get("type")
            media_info.title = cache_info.get("title")
            media_info.year = cache_info.get("year")
        else:
            media_info = self.media.get_media_info(title=title)
            if not media_info:
                log.warn("【RssChecker】%s 識別媒體資訊出錯！" % title)
        # 檢查是否匹配
        filter_args = {
            "include": taskinfo.get("include"),
            "exclude": taskinfo.get("exclude"),
            "rule": taskinfo.get("filter")
        }
        match_flag, res_order, match_msg = self.filter.check_torrent_filter(meta_info=media_info,
                                                                            filter_args=filter_args)
        # 未匹配
        if not match_flag:
            log.info(f"【RssChecker】{match_msg}")
        else:
            log.info("【RssChecker】%s 識別為 %s %s 匹配成功" % (
                title,
                media_info.get_title_string(),
                media_info.get_season_episode_string()))
        media_info.set_torrent_info(res_order=res_order)
        # 檢查是否已存在
        no_exists = {}
        exist_flag = False
        if not media_info.tmdb_info:
            log.info("【RssChecker】%s 識別為 %s 未匹配到媒體資訊" % (title, media_info.get_name()))
        else:
            if media_info.type == MediaType.MOVIE:
                exist_flag, no_exists, _ = self.downloader.check_exists_medias(meta_info=media_info,
                                                                               no_exists=no_exists)
                if exist_flag:
                    log.info("【RssChecker】電影 %s 已存在" % media_info.get_title_string())
            else:
                exist_flag, no_exists, _ = self.downloader.check_exists_medias(meta_info=media_info,
                                                                               no_exists=no_exists)
                if exist_flag:
                    # 已全部存在
                    if not no_exists or not no_exists.get(
                            media_info.tmdb_id):
                        log.info("【RssChecker】電視劇 %s %s 已存在" % (
                            media_info.get_title_string(), media_info.get_season_episode_string()))
                if no_exists.get(media_info.tmdb_id):
                    log.info("【RssChecker】%s 缺失季集：%s"
                             % (media_info.get_title_string(), no_exists.get(media_info.tmdb_id)))
        return media_info, match_flag, exist_flag

    def check_rss_articles(self, flag, articles):
        """
        RSS報文處理設定
        :param flag: set_finished/set_unfinish
        :param articles: 報文(title/enclosure)
        """
        try:
            if flag == "set_finished":
                for article in articles:
                    title = article.get("title")
                    enclosure = article.get("enclosure")
                    if not self.dbhelper.is_userrss_finished(title, enclosure):
                        self.dbhelper.simple_insert_rss_torrents(title, enclosure)
            elif flag == "set_unfinish":
                for article in articles:
                    self.dbhelper.simple_delete_rss_torrents(article.get("title"), article.get("enclosure"))
            else:
                return False
            return True
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error("【RssChecker】設定RSS報文狀態時發生錯誤：%s - %s" % (str(e), traceback.format_exc()))
            return False

    def download_rss_articles(self, taskid, articles):
        """
        RSS報文下載
        :param taskid: 自定義RSS的ID
        :param articles: 報文(title/enclosure)
        """
        if not taskid:
            return
        # 任務資訊
        taskinfo = self.get_rsstask_info(taskid)
        if not taskinfo:
            return
        for article in articles:
            media = self.media.get_media_info(title=article.get("title"))
            media.set_torrent_info(enclosure=article.get("enclosure"))
            ret, ret_msg = self.downloader.download(media_info=media,
                                                    download_dir=taskinfo.get("save_path"),
                                                    download_setting=taskinfo.get("download_setting"))
            if ret:
                self.message.send_download_message(in_from=SearchType.USERRSS,
                                                   can_item=media)
                # 插入資料庫
                self.dbhelper.insert_rss_torrents(media)
                # 登記自定義RSS任務下載記錄
                downloader = self.downloader.get_default_client_type().value
                if taskinfo.get("download_setting"):
                    download_attr = self.downloader.get_download_setting(taskinfo.get("download_setting"))
                    if download_attr.get("downloader"):
                        downloader = download_attr.get("downloader")
                self.dbhelper.insert_userrss_task_history(taskid, media.org_string, downloader)
            else:
                log.error("【RssChecker】新增下載任務 %s 失敗：%s" % (
                    media.get_title_string(), ret_msg or "請檢查下載任務是否已存在"))
                if ret_msg:
                    self.message.send_download_fail_message(media, ret_msg)
                return False
        return True
