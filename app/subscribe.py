import json
from threading import Lock

import log
from app.downloader import Downloader
from app.media.douban import DouBan
from app.helper import DbHelper, MetaHelper
from app.media import MetaInfo, Media
from app.message import Message
from app.searcher import Searcher
from app.utils.types import MediaType, SearchType

lock = Lock()


class Subscribe:
    dbhelper = None
    metahelper = None
    searcher = None
    message = None
    media = None
    downloader = None

    def __init__(self):
        self.dbhelper = DbHelper()
        self.metahelper = MetaHelper()
        self.searcher = Searcher()
        self.message = Message()
        self.media = Media()
        self.downloader = Downloader()

    def add_rss_subscribe(self, mtype, name, year,
                          season=None,
                          fuzzy_match=False,
                          doubanid=None,
                          tmdbid=None,
                          rss_sites=None,
                          search_sites=None,
                          over_edition=False,
                          filter_restype=None,
                          filter_pix=None,
                          filter_team=None,
                          filter_rule=None,
                          save_path=None,
                          download_setting=None,
                          total_ep=None,
                          current_ep=None,
                          state="D",
                          rssid=None):
        """
        新增電影、電視劇訂閱
        :param mtype: 型別，電影、電視劇、動漫
        :param name: 標題
        :param year: 年份，如要是劇集需要是首播年份
        :param season: 第幾季，數字
        :param fuzzy_match: 是否模糊匹配
        :param doubanid: 豆瓣ID，有此ID時從豆瓣查詢資訊
        :param tmdbid: TMDBID，有此ID時優先使用ID查詢TMDB資訊，沒有則使用名稱查詢
        :param rss_sites: 訂閱站點列表，為空則表示全部站點
        :param search_sites: 搜尋站點列表，為空則表示全部站點
        :param over_edition: 是否選版
        :param filter_restype: 質量過濾
        :param filter_pix: 解析度過濾
        :param filter_team: 製作組/字幕組過濾
        :param filter_rule: 關鍵字過濾
        :param save_path: 儲存路徑
        :param download_setting: 下載設定
        :param state: 新增訂閱時的狀態
        :param rssid: 修改訂閱時傳入
        :param total_ep: 總集數
        :param current_ep: 開始訂閱集數
        :return: 錯誤碼：0代表成功，錯誤資訊
        """
        if not name:
            return -1, "標題或型別有誤", None
        year = int(year) if str(year).isdigit() else ""
        rss_sites = rss_sites or []
        search_sites = search_sites or []
        over_edition = 1 if over_edition else 0
        filter_rule = int(filter_rule) if str(filter_rule).isdigit() else None
        total_ep = int(total_ep) if str(total_ep).isdigit() else None
        current_ep = int(current_ep) if str(current_ep).isdigit() else None
        download_setting = int(download_setting) if str(download_setting).isdigit() else -1
        fuzzy_match = True if fuzzy_match else False
        # 檢索媒體資訊
        if not fuzzy_match:
            # 精確匹配
            media = Media()
            # 根據TMDBID查詢，從推薦加訂閱的情況
            if season:
                title = "%s %s 第%s季".strip() % (name, year, season)
            else:
                title = "%s %s".strip() % (name, year)
            if tmdbid:
                # 根據TMDBID查詢
                media_info = MetaInfo(title=title, mtype=mtype)
                media_info.set_tmdb_info(media.get_tmdb_info(mtype=mtype, tmdbid=tmdbid))
                if not media_info.tmdb_info:
                    return 1, "無法查詢到媒體資訊", None
            else:
                # 根據名稱和年份查詢
                media_info = media.get_media_info(title=title,
                                                  mtype=mtype,
                                                  strict=True if year else False,
                                                  cache=False)
                if media_info and media_info.tmdb_info:
                    tmdbid = media_info.tmdb_id
                elif doubanid:
                    # 先從豆瓣網頁抓取（含TMDBID）
                    douban_info = DouBan().get_media_detail_from_web(doubanid)
                    if not douban_info:
                        douban_info = DouBan().get_douban_detail(doubanid=doubanid, mtype=mtype)
                    if not douban_info or douban_info.get("localized_message"):
                        return 1, "無法查詢到豆瓣媒體資訊", None
                    media_info = MetaInfo(title="%s %s".strip() % (douban_info.get('title'), year), mtype=mtype)
                    # 以IMDBID查詢TMDB
                    if douban_info.get("imdbid"):
                        tmdbid = Media().get_tmdbid_by_imdbid(douban_info.get("imdbid"))
                        if tmdbid:
                            media_info.set_tmdb_info(Media().get_tmdb_info(mtype=mtype, tmdbid=tmdbid))
                    # 無法識別TMDB時以豆瓣資訊訂閱
                    if not media_info.tmdb_info:
                        media_info.title = douban_info.get('title')
                        media_info.year = douban_info.get("year")
                        media_info.type = mtype
                        media_info.backdrop_path = douban_info.get("cover_url")
                        media_info.tmdb_id = "DB:%s" % doubanid
                        media_info.overview = douban_info.get("intro")
                        media_info.total_episodes = douban_info.get("episodes_count")
                    # 合併季
                    if season:
                        media_info.begin_season = int(season)
                else:
                    return 1, "無法查詢到媒體資訊", None
            # 新增訂閱
            if media_info.type != MediaType.MOVIE:
                if tmdbid:
                    if season or media_info.begin_season is not None:
                        season = int(season) if season else media_info.begin_season
                        total_episode = media.get_tmdb_season_episodes_num(sea=season, tmdbid=tmdbid)
                    else:
                        # 查詢季及集資訊
                        total_seasoninfo = media.get_tmdb_seasons_list(tmdbid=tmdbid)
                        if not total_seasoninfo:
                            return 2, "獲取劇集資訊失敗", media_info
                        # 按季號降序排序
                        total_seasoninfo = sorted(total_seasoninfo, key=lambda x: x.get("season_number"),
                                                  reverse=True)
                        # 取最新季
                        season = total_seasoninfo[0].get("season_number")
                        total_episode = total_seasoninfo[0].get("episode_count")
                    if not total_episode:
                        return 3, "%s 獲取劇集數失敗，請確認該季是否存在" % media_info.get_title_string(), media_info
                    media_info.begin_season = season
                    media_info.total_episodes = total_episode
                if total_ep:
                    total = total_ep
                else:
                    total = media_info.total_episodes
                if current_ep:
                    lack = total - current_ep - 1
                else:
                    lack = total
                if rssid:
                    self.dbhelper.delete_rss_tv(rssid=rssid)
                code = self.dbhelper.insert_rss_tv(media_info=media_info,
                                                   total=total,
                                                   lack=lack,
                                                   state=state,
                                                   rss_sites=rss_sites,
                                                   search_sites=search_sites,
                                                   over_edition=over_edition,
                                                   filter_restype=filter_restype,
                                                   filter_pix=filter_pix,
                                                   filter_team=filter_team,
                                                   filter_rule=filter_rule,
                                                   save_path=save_path,
                                                   download_setting=download_setting,
                                                   total_ep=total_ep,
                                                   current_ep=current_ep,
                                                   fuzzy_match=0,
                                                   desc=media_info.overview,
                                                   note=self.gen_rss_note(media_info))
            else:
                if rssid:
                    self.dbhelper.delete_rss_movie(rssid=rssid)
                code = self.dbhelper.insert_rss_movie(media_info=media_info,
                                                      state=state,
                                                      rss_sites=rss_sites,
                                                      search_sites=search_sites,
                                                      over_edition=over_edition,
                                                      filter_restype=filter_restype,
                                                      filter_pix=filter_pix,
                                                      filter_team=filter_team,
                                                      filter_rule=filter_rule,
                                                      save_path=save_path,
                                                      download_setting=download_setting,
                                                      fuzzy_match=0,
                                                      desc=media_info.overview,
                                                      note=self.gen_rss_note(media_info))
        else:
            # 模糊匹配
            media_info = MetaInfo(title=name, mtype=mtype)
            media_info.title = name
            media_info.type = mtype
            if season:
                media_info.begin_season = int(season)
            if mtype == MediaType.MOVIE:
                if rssid:
                    self.dbhelper.delete_rss_movie(rssid=rssid)
                code = self.dbhelper.insert_rss_movie(media_info=media_info,
                                                      state="R",
                                                      rss_sites=rss_sites,
                                                      search_sites=search_sites,
                                                      over_edition=over_edition,
                                                      filter_restype=filter_restype,
                                                      filter_pix=filter_pix,
                                                      filter_team=filter_team,
                                                      filter_rule=filter_rule,
                                                      save_path=save_path,
                                                      download_setting=download_setting,
                                                      fuzzy_match=1)
            else:
                if rssid:
                    self.dbhelper.delete_rss_tv(rssid=rssid)
                code = self.dbhelper.insert_rss_tv(media_info=media_info,
                                                   total=0,
                                                   lack=0,
                                                   state="R",
                                                   rss_sites=rss_sites,
                                                   search_sites=search_sites,
                                                   over_edition=over_edition,
                                                   filter_restype=filter_restype,
                                                   filter_pix=filter_pix,
                                                   filter_team=filter_team,
                                                   filter_rule=filter_rule,
                                                   save_path=save_path,
                                                   download_setting=download_setting,
                                                   fuzzy_match=1)

        if code == 0:
            return code, "新增訂閱成功", media_info
        elif code == 9:
            return code, "訂閱已存在", media_info
        else:
            return code, "新增訂閱失敗", media_info

    def finish_rss_subscribe(self, rtype, rssid, media):
        """
        完成訂閱
        :param rtype: 訂閱型別
        :param rssid: 訂閱ID
        :param media: 識別的媒體資訊，傳送訊息使用
        """
        if not rtype or not rssid or not media:
            return
        # 電影訂閱
        if rtype == "MOV":
            # 查詢電影RSS資料
            rss = self.dbhelper.get_rss_movies(rssid=rssid)
            if not rss:
                return
            # 登記訂閱歷史
            self.dbhelper.insert_rss_history(rssid=rssid,
                                             rtype=rtype,
                                             name=rss[0].NAME,
                                             year=rss[0].YEAR,
                                             tmdbid=rss[0].TMDBID,
                                             image=media.get_poster_image(),
                                             desc=media.overview)

            # 刪除訂閱
            self.dbhelper.delete_rss_movie(rssid=rssid)

        # 電視劇訂閱
        else:
            # 查詢電視劇RSS資料
            rss = self.dbhelper.get_rss_tvs(rssid=rssid)
            if not rss:
                return
            total = rss[0].TOTAL_EP
            # 登記訂閱歷史
            self.dbhelper.insert_rss_history(rssid=rssid,
                                             rtype=rtype,
                                             name=rss[0].NAME,
                                             year=rss[0].YEAR,
                                             season=rss[0].SEASON,
                                             tmdbid=rss[0].TMDBID,
                                             image=media.get_poster_image(),
                                             desc=media.overview,
                                             total=total if total else rss[0].TOTAL,
                                             start=rss[0].CURRENT_EP)
            # 刪除訂閱
            self.dbhelper.delete_rss_tv(rssid=rssid)

        # 傳送訂閱完成的訊息
        if media:
            Message().send_rss_finished_message(media_info=media)

    def get_subscribe_movies(self, rid=None, state=None):
        """
        獲取電影訂閱
        """
        ret_dict = {}
        rss_movies = self.dbhelper.get_rss_movies(rssid=rid, state=state)
        for rss_movie in rss_movies:
            desc = rss_movie.DESC
            note = rss_movie.NOTE
            tmdbid = rss_movie.TMDBID
            rss_sites = rss_movie.RSS_SITES
            rss_sites = json.loads(rss_sites) if rss_sites else []
            search_sites = rss_movie.SEARCH_SITES
            search_sites = json.loads(search_sites) if search_sites else []
            over_edition = True if rss_movie.OVER_EDITION == 1 else False
            filter_restype = rss_movie.FILTER_RESTYPE
            filter_pix = rss_movie.FILTER_PIX
            filter_team = rss_movie.FILTER_TEAM
            filter_rule = rss_movie.FILTER_RULE
            download_setting = rss_movie.DOWNLOAD_SETTING
            save_path = rss_movie.SAVE_PATH
            fuzzy_match = True if rss_movie.FUZZY_MATCH == 1 else False
            # 相容舊配置
            if desc and desc.find('{') != -1:
                desc = self.__parse_rss_desc(desc)
                rss_sites = desc.get("rss_sites")
                search_sites = desc.get("search_sites")
                over_edition = True if desc.get("over_edition") == 'Y' else False
                filter_restype = desc.get("restype")
                filter_pix = desc.get("pix")
                filter_team = desc.get("team")
                filter_rule = desc.get("rule")
                download_setting = -1
                save_path = ""
                fuzzy_match = False if tmdbid else True
            if note:
                note_info = self.__parse_rss_desc(note)
            else:
                note_info = {}
            ret_dict[str(rss_movie.ID)] = {
                "id": rss_movie.ID,
                "name": rss_movie.NAME,
                "year": rss_movie.YEAR,
                "tmdbid": rss_movie.TMDBID,
                "image": rss_movie.IMAGE,
                "overview": rss_movie.DESC,
                "rss_sites": rss_sites,
                "search_sites": search_sites,
                "over_edition": over_edition,
                "filter_restype": filter_restype,
                "filter_pix": filter_pix,
                "filter_team": filter_team,
                "filter_rule": filter_rule,
                "save_path": save_path,
                "download_setting": download_setting,
                "fuzzy_match": fuzzy_match,
                "state": rss_movie.STATE,
                "poster": note_info.get("poster"),
                "release_date": note_info.get("release_date"),
                "vote": note_info.get("vote")

            }
        return ret_dict

    def get_subscribe_tvs(self, rid=None, state=None):
        ret_dict = {}
        rss_tvs = self.dbhelper.get_rss_tvs(rssid=rid, state=state)
        for rss_tv in rss_tvs:
            desc = rss_tv.DESC
            note = rss_tv.NOTE
            tmdbid = rss_tv.TMDBID
            rss_sites = json.loads(rss_tv.RSS_SITES) if rss_tv.RSS_SITES else []
            search_sites = json.loads(rss_tv.SEARCH_SITES) if rss_tv.SEARCH_SITES else []
            over_edition = True if rss_tv.OVER_EDITION == 1 else False
            filter_restype = rss_tv.FILTER_RESTYPE
            filter_pix = rss_tv.FILTER_PIX
            filter_team = rss_tv.FILTER_TEAM
            filter_rule = rss_tv.FILTER_RULE
            download_setting = rss_tv.DOWNLOAD_SETTING
            save_path = rss_tv.SAVE_PATH
            total_ep = rss_tv.TOTAL_EP
            current_ep = rss_tv.CURRENT_EP
            fuzzy_match = True if rss_tv.FUZZY_MATCH == 1 else False
            # 相容舊配置
            if desc and desc.find('{') != -1:
                desc = self.__parse_rss_desc(desc)
                rss_sites = desc.get("rss_sites")
                search_sites = desc.get("search_sites")
                over_edition = True if desc.get("over_edition") == 'Y' else False
                filter_restype = desc.get("restype")
                filter_pix = desc.get("pix")
                filter_team = desc.get("team")
                filter_rule = desc.get("rule")
                save_path = ""
                download_setting = -1
                total_ep = desc.get("total")
                current_ep = desc.get("current")
                fuzzy_match = False if tmdbid else True
            if note:
                note_info = self.__parse_rss_desc(note)
            else:
                note_info = {}
            ret_dict[str(rss_tv.ID)] = {
                "id": rss_tv.ID,
                "name": rss_tv.NAME,
                "year": rss_tv.YEAR,
                "season": rss_tv.SEASON,
                "tmdbid": rss_tv.TMDBID,
                "image": rss_tv.IMAGE,
                "overview": rss_tv.DESC,
                "rss_sites": rss_sites,
                "search_sites": search_sites,
                "over_edition": over_edition,
                "filter_restype": filter_restype,
                "filter_pix": filter_pix,
                "filter_team": filter_team,
                "filter_rule": filter_rule,
                "save_path": save_path,
                "download_setting": download_setting,
                "total": rss_tv.TOTAL,
                "lack": rss_tv.LACK,
                "total_ep": total_ep,
                "current_ep": current_ep,
                "fuzzy_match": fuzzy_match,
                "state": rss_tv.STATE,
                "poster": note_info.get("poster"),
                "release_date": note_info.get("release_date"),
                "vote": note_info.get("vote")
            }
        return ret_dict

    @staticmethod
    def __parse_rss_desc(desc):
        """
        解析訂閱的JSON欄位
        """
        if not desc:
            return {}
        return json.loads(desc) or {}

    @staticmethod
    def gen_rss_note(media):
        """
        生成訂閱的JSON備註資訊
        :param media: 媒體資訊
        :return: 備註資訊
        """
        if not media:
            return {}
        note = {
            "poster": media.get_poster_image(),
            "release_date": media.release_date,
            "vote": media.vote_average
        }
        return json.dumps(note)

    def refresh_rss_metainfo(self):
        """
        定時將豆瓣訂閱轉換為TMDB的訂閱，並更新訂閱的TMDB資訊
        """
        # 更新電影
        log.info("【Subscribe】開始重新整理訂閱TMDB資訊...")
        rss_movies = self.get_subscribe_movies(state='R')
        for rid, rss_info in rss_movies.items():
            # 跳過模糊匹配的
            if rss_info.get("fuzzy_match"):
                continue
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            # 更新TMDB資訊
            media_info = self.__get_media_info(tmdbid=tmdbid,
                                               name=name,
                                               year=year,
                                               mtype=MediaType.MOVIE,
                                               cache=False)
            if media_info and media_info.tmdb_id and media_info.title != name:
                log.info(f"【Subscribe】檢測到TMDB資訊變化，更新電影訂閱 {name} 為 {media_info.title}")
                # 更新訂閱資訊
                self.dbhelper.update_rss_movie_tmdb(rid=rssid,
                                                    tmdbid=media_info.tmdb_id,
                                                    title=media_info.title,
                                                    year=media_info.year,
                                                    image=media_info.get_message_image(),
                                                    desc=media_info.overview,
                                                    note=self.gen_rss_note(media_info))
                # 清除TMDB快取
                self.metahelper.delete_meta_data_by_tmdbid(media_info.tmdb_id)

        # 更新電視劇
        rss_tvs = self.get_subscribe_tvs(state='R')
        for rid, rss_info in rss_tvs.items():
            # 跳過模糊匹配的
            if rss_info.get("fuzzy_match"):
                continue
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            season = rss_info.get("season") or 1
            total = rss_info.get("total")
            total_ep = rss_info.get("total_ep")
            lack = rss_info.get("lack")
            # 更新TMDB資訊
            media_info = self.__get_media_info(tmdbid=tmdbid,
                                               name=name,
                                               year=year,
                                               mtype=MediaType.TV,
                                               cache=False)
            if media_info and media_info.tmdb_id:
                # 獲取總集數
                total_episode = self.media.get_tmdb_season_episodes_num(sea=int(str(season).replace("S", "")),
                                                                        tv_info=media_info.tmdb_info)
                # 設定總集數的，不更新集數
                if total_ep:
                    total_episode = total_ep
                if total_episode and (name != media_info.title or total != total_episode):
                    # 新的缺失集數
                    lack_episode = total_episode - (total - lack)
                    log.info(
                        f"【Subscribe】檢測到TMDB資訊變化，更新電視劇訂閱 {name} 為 {media_info.title}，總集數為：{total_episode}")
                    # 更新訂閱資訊
                    self.dbhelper.update_rss_tv_tmdb(rid=rssid,
                                                     tmdbid=media_info.tmdb_id,
                                                     title=media_info.title,
                                                     year=media_info.year,
                                                     total=total_episode,
                                                     lack=lack_episode,
                                                     image=media_info.get_message_image(),
                                                     desc=media_info.overview,
                                                     note=self.gen_rss_note(media_info))
                    # 清除TMDB快取
                    self.metahelper.delete_meta_data_by_tmdbid(media_info.tmdb_id)
        log.info("【Subscribe】訂閱TMDB資訊重新整理完成")

    @staticmethod
    def __get_media_info(tmdbid, name, year, mtype, cache=True):
        """
        綜合返回媒體資訊
        """
        if tmdbid and not tmdbid.startswith("DB:"):
            media_info = MetaInfo(title="%s %s".strip() % (name, year))
            tmdb_info = Media().get_tmdb_info(mtype=mtype, tmdbid=tmdbid)
            media_info.set_tmdb_info(tmdb_info)
        else:
            media_info = Media().get_media_info(title="%s %s" % (name, year), mtype=mtype, strict=True, cache=cache)
        return media_info

    def subscribe_search_all(self):
        """
        搜尋R狀態的所有訂閱，由定時服務呼叫
        """
        self.subscribe_search(state="R")

    def subscribe_search(self, state="D"):
        """
        RSS訂閱佇列中狀態的任務處理，先進行存量資源檢索，缺失的才標誌為RSS狀態，由定時服務呼叫
        """
        try:
            lock.acquire()
            # 處理電影
            self.subscribe_search_movie(state=state)
            # 處理電視劇
            self.subscribe_search_tv(state=state)
        finally:
            lock.release()

    def subscribe_search_movie(self, rssid=None, state='D'):
        """
        檢索電影RSS
        :param rssid: 訂閱ID，未輸入時檢索所有狀態為D的，輸入時檢索該ID任何狀態的
        :param state: 檢索的狀態，預設為佇列中才檢索
        """
        if rssid:
            rss_movies = self.get_subscribe_movies(rid=rssid)
        else:
            rss_movies = self.get_subscribe_movies(state=state)
        if rss_movies:
            log.info("【Subscribe】共有 %s 個電影訂閱需要檢索" % len(rss_movies))
        for rid, rss_info in rss_movies.items():
            # 跳過模糊匹配的
            if rss_info.get("fuzzy_match"):
                continue
            # 搜尋站點範圍
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")

            # 開始搜尋
            self.dbhelper.update_rss_movie_state(rssid=rssid, state='S')
            # 識別
            media_info = self.__get_media_info(tmdbid, name, year, MediaType.MOVIE)
            # 未識別到媒體資訊
            if not media_info or not media_info.tmdb_info:
                self.dbhelper.update_rss_movie_state(rssid=rssid, state='R')
                continue
            media_info.set_download_info(download_setting=rss_info.get("download_setting"),
                                         save_path=rss_info.get("save_path"))
            # 非洗版的情況檢查是否存在
            if not rss_info.get("over_edition"):
                # 檢查是否存在
                exist_flag, no_exists, _ = self.downloader.check_exists_medias(meta_info=media_info)
                # 已經存在
                if exist_flag:
                    log.info("【Subscribe】電影 %s 已存在，刪除訂閱..." % name)
                    self.finish_rss_subscribe(rtype="MOV", rssid=rssid, media=media_info)
                    continue
            else:
                # 洗版時按缺失來下載
                no_exists = {}
            # 開始檢索
            filter_dict = {
                "restype": rss_info.get('filter_restype'),
                "pix": rss_info.get('filter_pix'),
                "team": rss_info.get('filter_team'),
                "rule": rss_info.get('filter_rule'),
                "site": rss_info.get("search_sites")
            }
            search_result, no_exists, search_count, download_count = self.searcher.search_one_media(
                media_info=media_info,
                in_from=SearchType.RSS,
                no_exists=no_exists,
                sites=rss_info.get("search_sites"),
                filters=filter_dict)
            if search_result:
                log.info("【Subscribe】電影 %s 下載完成，刪除訂閱..." % name)
                self.finish_rss_subscribe(rtype="MOV", rssid=rssid, media=media_info)
            else:
                self.dbhelper.update_rss_movie_state(rssid=rssid, state='R')

    def subscribe_search_tv(self, rssid=None, state="D"):
        """
        檢索電視劇RSS
        :param rssid: 訂閱ID，未輸入時檢索所有狀態為D的，輸入時檢索該ID任何狀態的
        :param state: 檢索的狀態，預設為佇列中才檢索
        """
        if rssid:
            rss_tvs = self.get_subscribe_tvs(rid=rssid)
        else:
            rss_tvs = self.get_subscribe_tvs(state=state)
        if rss_tvs:
            log.info("【Subscribe】共有 %s 個電視劇訂閱需要檢索" % len(rss_tvs))
        rss_no_exists = {}
        for rid, rss_info in rss_tvs.items():
            # 跳過模糊匹配的
            if rss_info.get("fuzzy_match"):
                continue
            rssid = rss_info.get("id")
            name = rss_info.get("name")
            year = rss_info.get("year") or ""
            tmdbid = rss_info.get("tmdbid")
            # 開始搜尋
            self.dbhelper.update_rss_tv_state(rssid=rssid, state='S')
            # 識別
            media_info = self.__get_media_info(tmdbid, name, year, MediaType.TV)
            # 未識別到媒體資訊
            if not media_info or not media_info.tmdb_info:
                self.dbhelper.update_rss_tv_state(rssid=rssid, state='R')
                continue
            # 取下載設定
            media_info.set_download_info(download_setting=rss_info.get("download_setting"),
                                         save_path=rss_info.get("save_path"))
            # 從登記薄中獲取缺失劇集
            season = 1
            if rss_info.get("season"):
                season = int(str(rss_info.get("season")).replace("S", ""))
            # 訂閱季
            media_info.begin_season = season
            # 自定義集數
            total_ep = rss_info.get("total")
            current_ep = rss_info.get("current_ep")
            # 表中記錄的剩餘訂閱集數
            episodes = self.dbhelper.get_rss_tv_episodes(rss_info.get("id"))
            if episodes is None:
                episodes = []
                if current_ep:
                    episodes = list(range(current_ep, total_ep + 1))
                rss_no_exists[media_info.tmdb_id] = [
                    {"season": season,
                     "episodes": episodes,
                     "total_episodes": total_ep}]
            elif episodes:
                rss_no_exists[media_info.tmdb_id] = [
                    {"season": season,
                     "episodes": episodes,
                     "total_episodes": total_ep}]
            else:
                log.info("【Subscribe】電視劇 %s%s 已全部訂閱完成，刪除訂閱..." % (
                    media_info.title, media_info.get_season_string()))
                # 完成訂閱
                self.finish_rss_subscribe(rtype="TV",
                                          rssid=rss_info.get("id"),
                                          media=media_info)
                continue
            # 非洗版時檢查本地媒體庫情況
            if not rss_info.get("over_edition"):
                exist_flag, library_no_exists, _ = self.downloader.check_exists_medias(
                    meta_info=media_info,
                    total_ep={season: total_ep})
                # 當前劇集已存在，跳過
                if exist_flag:
                    # 已全部存在
                    if not library_no_exists or not library_no_exists.get(
                            media_info.tmdb_id):
                        log.info("【Subscribe】電視劇 %s 訂閱劇集已全部存在，刪除訂閱..." % (
                            media_info.get_title_string()))
                        # 完成訂閱
                        self.finish_rss_subscribe(rtype="TV",
                                                  rssid=rss_info.get("id"),
                                                  media=media_info)
                    continue
                # 取交集做為缺失集
                rss_no_exists = self.media.get_intersection_episodes(target=rss_no_exists,
                                                                     source=library_no_exists,
                                                                     title=media_info.tmdb_id)
                if rss_no_exists.get(media_info.tmdb_id):
                    log.info("【Subscribe】%s 訂閱缺失季集：%s" % (
                        media_info.get_title_string(),
                        rss_no_exists.get(media_info.tmdb_id)))

            # 開始檢索
            filter_dict = {
                "restype": rss_info.get('filter_restype'),
                "pix": rss_info.get('filter_pix'),
                "team": rss_info.get('filter_team'),
                "rule": rss_info.get('filter_rule'),
                "site": rss_info.get("search_sites")
            }
            search_result, no_exists, search_count, download_count = self.searcher.search_one_media(
                media_info=media_info,
                in_from=SearchType.RSS,
                no_exists=rss_no_exists,
                sites=rss_info.get("search_sites"),
                filters=filter_dict)
            if not no_exists or not no_exists.get(media_info.tmdb_id):
                # 沒有剩餘或者剩餘缺失季集中沒有當前標題，說明下完了
                log.info("【Subscribe】電視劇 %s 下載完成，刪除訂閱..." % name)
                # 完成訂閱
                self.finish_rss_subscribe(rtype="TV", rssid=rssid, media=media_info)
            else:
                # 更新狀態
                self.dbhelper.update_rss_tv_state(rssid=rssid, state='R')
                no_exist_items = no_exists.get(media_info.tmdb_id)
                for no_exist_item in no_exist_items:
                    if str(no_exist_item.get("season")) == media_info.get_season_seq():
                        if no_exist_item.get("episodes"):
                            log.info("【Subscribe】更新電視劇 %s %s 缺失集數為 %s" % (
                                media_info.get_title_string(), media_info.get_season_string(),
                                len(no_exist_item.get("episodes"))))
                            self.dbhelper.update_rss_tv_lack(rssid=rssid, lack_episodes=no_exist_item.get("episodes"))
                        break
