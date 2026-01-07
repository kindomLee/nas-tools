import datetime
import random
from threading import Lock
from time import sleep

import log
from app.downloader import Downloader
from app.helper import DbHelper
from app.media import Media, MetaInfo
from app.media.douban import DouBan
from app.message import Message
from app.searcher import Searcher
from app.subscribe import Subscribe
from app.utils.exception_utils import ExceptionUtils
from app.utils.types import SearchType, MediaType
from config import Config

lock = Lock()


class DoubanSync:
    douban = None
    searcher = None
    media = None
    downloader = None
    dbhelper = None
    subscribe = None
    _interval = None
    _auto_search = None
    _auto_rss = None
    _users = None
    _days = None
    _types = None

    def __init__(self):
        self.douban = DouBan()
        self.searcher = Searcher()
        self.downloader = Downloader()
        self.media = Media()
        self.message = Message()
        self.dbhelper = DbHelper()
        self.subscribe = Subscribe()
        self.init_config()

    def init_config(self):
        douban = Config().get_config('douban')
        if douban:
            # 同步間隔
            self._interval = int(douban.get('interval')) if str(douban.get('interval')).isdigit() else None
            self._auto_search = douban.get('auto_search')
            self._auto_rss = douban.get('auto_rss')
            # 使用者列表
            users = douban.get('users')
            if users:
                if not isinstance(users, list):
                    users = [users]
                self._users = users
            # 時間範圍
            self._days = int(douban.get('days')) if str(douban.get('days')).isdigit() else None
            # 型別
            types = douban.get('types')
            if types:
                self._types = types.split(',')

    def sync(self):
        """
        同步豆瓣資料
        """
        if not self._interval:
            log.info("【Douban】豆瓣配置：同步間隔未配置或配置不正確")
            return
        try:
            lock.acquire()
            log.info("【Douban】開始同步豆瓣資料...")
            # 拉取豆瓣資料
            medias = self.__get_all_douban_movies()
            # 開始檢索
            if self._auto_search:
                # 需要檢索
                for media in medias:
                    if not media:
                        continue
                    # 查詢資料庫狀態，已經加入RSS的不處理
                    search_state = self.dbhelper.get_douban_search_state(media.get_name(), media.year)
                    if not search_state or search_state[0][0] == "NEW":
                        if media.begin_season:
                            subtitle = "第%s季" % media.begin_season
                        else:
                            subtitle = None
                        media_info = self.media.get_media_info(title="%s %s" % (media.get_name(), media.year or ""),
                                                               subtitle=subtitle,
                                                               mtype=media.type)
                        # 不需要自動加訂閱，則直接搜尋
                        if not media_info or not media_info.tmdb_info:
                            log.warn("【Douban】%s 未查詢到媒體資訊" % media.get_name())
                            continue
                        # 檢查是否存在，電視劇返回不存在的集清單
                        exist_flag, no_exists, _ = self.downloader.check_exists_medias(meta_info=media_info)
                        # 已經存在
                        if exist_flag:
                            # 更新為已下載狀態
                            log.info("【Douban】%s 已存在" % media.get_name())
                            self.dbhelper.insert_douban_media_state(media, "DOWNLOADED")
                            continue
                        if not self._auto_rss:
                            # 合併季
                            media_info.begin_season = media.begin_season
                            # 開始檢索
                            search_result, no_exists, search_count, download_count = self.searcher.search_one_media(
                                media_info=media_info,
                                in_from=SearchType.DB,
                                no_exists=no_exists,
                                user_name=media_info.user_name)
                            if search_result:
                                # 下載全了更新為已下載，沒下載全的下次同步再次搜尋
                                self.dbhelper.insert_douban_media_state(media, "DOWNLOADED")
                        else:
                            # 需要加訂閱，則由訂閱去檢索
                            log.info(
                                "【Douban】%s %s 更新到%s訂閱中..." % (media.get_name(), media.year, media.type.value))
                            code, msg, _ = self.subscribe.add_rss_subscribe(mtype=media.type,
                                                                            name=media.get_name(),
                                                                            year=media.year,
                                                                            season=media.begin_season,
                                                                            doubanid=media.douban_id)
                            if code != 0:
                                log.error("【Douban】%s 新增訂閱失敗：%s" % (media.get_name(), msg))
                                # 訂閱已存在
                                if code == 9:
                                    self.dbhelper.insert_douban_media_state(media, "RSS")
                            else:
                                # 傳送訂閱訊息
                                self.message.send_rss_success_message(in_from=SearchType.DB,
                                                                      media_info=media)
                                # 插入為已RSS狀態
                                self.dbhelper.insert_douban_media_state(media, "RSS")
                    else:
                        log.info("【Douban】%s %s 已處理過" % (media.get_name(), media.year))
            else:
                # 不需要檢索
                if self._auto_rss:
                    # 加入訂閱，使狀態為R
                    for media in medias:
                        log.info("【Douban】%s %s 更新到%s訂閱中..." % (media.get_name(), media.year, media.type.value))
                        code, msg, _ = self.subscribe.add_rss_subscribe(mtype=media.type,
                                                                        name=media.get_name(),
                                                                        year=media.year,
                                                                        season=media.begin_season,
                                                                        doubanid=media.douban_id,
                                                                        state="R")
                        if code != 0:
                            log.error("【Douban】%s 新增訂閱失敗：%s" % (media.get_name(), msg))
                            # 訂閱已存在
                            if code == 9:
                                self.dbhelper.insert_douban_media_state(media, "RSS")
                        else:
                            # 傳送訂閱訊息
                            self.message.send_rss_success_message(in_from=SearchType.DB,
                                                                  media_info=media)
                            # 插入為已RSS狀態
                            self.dbhelper.insert_douban_media_state(media, "RSS")
            log.info("【Douban】豆瓣資料同步完成")
        finally:
            lock.release()

    def __get_all_douban_movies(self):
        """
        獲取每一個使用者的每一個型別的豆瓣標記
        :return: 檢索到的媒體資訊列表（不含TMDB資訊）
        """
        if not self._interval \
                or not self._days \
                or not self._users \
                or not self._types:
            log.warn("【Douban】豆瓣未配置或配置不正確")
            return []
        # 返回媒體列表
        media_list = []
        # 豆瓣ID列表
        douban_ids = {}
        # 每頁條數
        perpage_number = 15
        # 每一個使用者
        for user in self._users:
            if not user:
                continue
            # 查詢使用者名稱稱
            user_name = ""
            userinfo = self.douban.get_user_info(userid=user)
            if userinfo:
                user_name = userinfo.get("name")
            # 每一個型別成功數量
            user_succnum = 0
            for mtype in self._types:
                if not mtype:
                    continue
                log.info(f"【Douban】開始獲取 {user_name or user} 的 {mtype} 資料...")
                # 開始序號
                start_number = 0
                # 型別成功數量
                user_type_succnum = 0
                # 每一頁
                while True:
                    # 頁數
                    page_number = int(start_number / perpage_number + 1)
                    # 當前頁成功數量
                    sucess_urlnum = 0
                    # 是否繼續下一頁
                    continue_next_page = True
                    log.debug(f"【Douban】開始解析第 {page_number} 頁資料...")
                    try:
                        items = self.douban.get_douban_wish(dtype=mtype, userid=user, page=page_number, wait=True)
                        if not items:
                            log.warn(f"【Douban】第 {page_number} 頁未獲取到資料")
                            break
                        # 解析豆瓣ID
                        for item in items:
                            # 時間範圍
                            date = item.get("date")
                            if not date:
                                continue_next_page = False
                                break
                            else:
                                mark_date = datetime.datetime.strptime(date, '%Y-%m-%d')
                                if not (datetime.datetime.now() - mark_date).days < int(self._days):
                                    continue_next_page = False
                                    break
                            doubanid = item.get("id")
                            if str(doubanid).isdigit():
                                log.info("【Douban】解析到媒體：%s" % doubanid)
                                if doubanid not in douban_ids:
                                    douban_ids[doubanid] = {
                                        "user_name": user_name
                                    }
                                sucess_urlnum += 1
                                user_type_succnum += 1
                                user_succnum += 1
                        log.debug(f"【Douban】{user_name or user} 第 {page_number} 頁解析完成，共獲取到 {sucess_urlnum} 個媒體")
                    except Exception as err:
                        ExceptionUtils.exception_traceback(err)
                        log.error(f"【Douban】{user_name or user} 第 {page_number} 頁解析出錯：%s" % str(err))
                        break
                    # 繼續下一頁
                    if continue_next_page:
                        start_number += perpage_number
                    else:
                        break
                # 當前型別解析結束
                log.debug(f"【Douban】使用者 {user_name or user} 的 {mtype} 解析完成，共獲取到 {user_type_succnum} 個媒體")
            log.info(f"【Douban】使用者 {user_name or user} 解析完成，共獲取到 {user_succnum} 個媒體")
        log.info(f"【Douban】所有使用者解析完成，共獲取到 {len(douban_ids)} 個媒體")
        # 查詢豆瓣詳情
        for doubanid, info in douban_ids.items():
            douban_info = self.douban.get_douban_detail(doubanid=doubanid, wait=True)
            # 組裝媒體資訊
            if not douban_info:
                log.warn("【Douban】%s 未正確獲取豆瓣詳細資訊，嘗試使用網頁獲取" % doubanid)
                douban_info = self.douban.get_media_detail_from_web(doubanid)
                if not douban_info:
                    log.warn("【Douban】%s 無許可權訪問，需要配置豆瓣Cookie" % doubanid)
                    # 隨機休眠
                    sleep(round(random.uniform(1, 5), 1))
                    continue
            media_type = MediaType.TV if douban_info.get("episodes_count") else MediaType.MOVIE
            log.info("【Douban】%s：%s %s".strip() % (media_type.value, douban_info.get("title"), douban_info.get("year")))
            meta_info = MetaInfo(title="%s %s" % (douban_info.get("title"), douban_info.get("year") or ""))
            meta_info.douban_id = doubanid
            meta_info.type = media_type
            meta_info.overview = douban_info.get("intro")
            meta_info.poster_path = douban_info.get("cover_url")
            rating = douban_info.get("rating", {}) or {}
            meta_info.vote_average = rating.get("value") or ""
            meta_info.imdb_id = douban_info.get("imdbid")
            meta_info.user_name = info.get("user_name")
            if meta_info not in media_list:
                media_list.append(meta_info)
            # 隨機休眠
            sleep(round(random.uniform(1, 5), 1))
        return media_list
