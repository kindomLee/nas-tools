import re
import traceback
import xml.dom.minidom
from threading import Lock

import log
from app.downloader.downloader import Downloader
from app.filter import Filter
from app.helper import DbHelper
from app.media import Media, MetaInfo
from app.sites import Sites
from app.subscribe import Subscribe
from app.utils import DomUtils, RequestUtils, StringUtils
from app.utils.exception_utils import ExceptionUtils
from app.utils.rsstitle_utils import RssTitleUtils
from app.utils.types import MediaType, SearchType

lock = Lock()


class Rss:
    _sites = []
    filter = None
    media = None
    downloader = None
    searcher = None
    dbhelper = None
    subscribe = None

    def __init__(self):
        self.media = Media()
        self.downloader = Downloader()
        self.sites = Sites()
        self.filter = Filter()
        self.dbhelper = DbHelper()
        self.subscribe = Subscribe()
        self.init_config()

    def init_config(self):
        self._sites = self.sites.get_sites(rss=True)

    def rssdownload(self):
        """
        RSS訂閱檢索下載入口，由定時服務呼叫
        """
        if not self._sites:
            return
        with lock:
            log.info("【Rss】開始RSS訂閱...")
            # 讀取電影訂閱
            rss_movies = self.subscribe.get_subscribe_movies(state='R')
            if not rss_movies:
                log.warn("【Rss】沒有正在訂閱的電影")
            else:
                log.info("【Rss】電影訂閱清單：%s"
                         % " ".join('%s' % info.get("name") for _, info in rss_movies.items()))
            # 讀取電視劇訂閱
            rss_tvs = self.subscribe.get_subscribe_tvs(state='R')
            if not rss_tvs:
                log.warn("【Rss】沒有正在訂閱的電視劇")
            else:
                log.info("【Rss】電視劇訂閱清單：%s"
                         % " ".join('%s' % info.get("name") for _, info in rss_tvs.items()))
            # 沒有訂閱退出
            if not rss_movies and not rss_tvs:
                return
            # 獲取有訂閱的站點範圍
            check_sites = []
            check_all = False
            for rid, rinfo in rss_movies.items():
                rss_sites = rinfo.get("rss_sites")
                if not rss_sites:
                    check_all = True
                    break
                else:
                    check_sites += rss_sites
            if not check_all:
                for rid, rinfo in rss_tvs.items():
                    rss_sites = rinfo.get("rss_sites")
                    if not rss_sites:
                        check_all = True
                        break
                    else:
                        check_sites += rss_sites
            if check_all:
                check_sites = []
            else:
                check_sites = list(set(check_sites))

            # 程式碼站點配置優先順序的序號
            rss_download_torrents = []
            rss_no_exists = {}
            for site_info in self._sites:
                if not site_info:
                    continue
                # 站點名稱
                site_name = site_info.get("name")
                # 沒有訂閱的站點中的不檢索
                if check_sites and site_name not in check_sites:
                    continue
                # 站點rss連結
                rss_url = site_info.get("rssurl")
                if not rss_url:
                    log.info(f"【Rss】{site_name} 未配置rssurl，跳過...")
                    continue
                site_cookie = site_info.get("cookie")
                site_ua = site_info.get("ua")
                # 是否解析種子詳情
                site_parse = False if site_info.get("parse") == "N" else True
                # 使用的規則
                site_fliter_rule = site_info.get("rule")
                # 開始下載RSS
                log.info(f"【Rss】正在處理：{site_name}")
                if site_info.get("pri"):
                    site_order = 100 - int(site_info.get("pri"))
                else:
                    site_order = 0
                rss_acticles = self.parse_rssxml(rss_url)
                if not rss_acticles:
                    log.warn(f"【Rss】{site_name} 未下載到資料")
                    continue
                else:
                    log.info(f"【Rss】{site_name} 獲取資料：{len(rss_acticles)}")
                # 處理RSS結果
                res_num = 0
                for article in rss_acticles:
                    try:
                        # 種子名
                        title = article.get('title')
                        # 種子連結
                        enclosure = article.get('enclosure')
                        # 種子頁面
                        page_url = article.get('link')
                        # 副標題
                        description = article.get('description')
                        # 種子大小
                        size = article.get('size')
                        # 開始處理
                        log.info(f"【Rss】開始處理：{title}")
                        # 檢查這個種子是不是下過了
                        if self.dbhelper.is_torrent_rssd(enclosure):
                            log.info(f"【Rss】{title} 已成功訂閱過")
                            continue
                        # 識別種子名稱，開始檢索TMDB
                        media_info = MetaInfo(title=title, subtitle=description)
                        cache_info = self.media.get_cache_info(media_info)
                        if cache_info.get("id"):
                            # 使用快取資訊
                            media_info.tmdb_id = cache_info.get("id")
                            media_info.type = cache_info.get("type")
                            media_info.title = cache_info.get("title")
                            media_info.year = cache_info.get("year")
                        else:
                            # 重新查詢TMDB
                            media_info = self.media.get_media_info(title=title, subtitle=description)
                            if not media_info:
                                log.warn(f"【Rss】{title} 無法識別出媒體資訊！")
                            elif not media_info.tmdb_info:
                                log.info(f"【Rss】{title} 識別為 {media_info.get_name()} 未匹配到TMDB媒體資訊")
                        # 大小及種子頁面
                        media_info.set_torrent_info(size=size,
                                                    page_url=page_url,
                                                    site=site_name,
                                                    site_order=site_order,
                                                    enclosure=enclosure)
                        # 檢查種子是否匹配訂閱，返回匹配到的訂閱ID、是否洗版、總集數、上傳因子、下載因子
                        match_flag, match_msg, match_info = self.check_torrent_rss(
                            media_info=media_info,
                            rss_movies=rss_movies,
                            rss_tvs=rss_tvs,
                            site_filter_rule=site_fliter_rule,
                            site_cookie=site_cookie,
                            site_parse=site_parse,
                            site_ua=site_ua)
                        for msg in match_msg:
                            log.info(f"【Rss】{msg}")
                        # 未匹配
                        if not match_flag:
                            continue
                        # 非模糊匹配命中
                        if not match_info.get("fuzzy_match"):
                            # 匹配到訂閱，如沒有TMDB資訊則重新查詢
                            if not media_info.tmdb_info:
                                media_info.set_tmdb_info(self.media.get_tmdb_info(mtype=media_info.type,
                                                                                  tmdbid=media_info.tmdb_id))
                            # 如果是電影
                            if media_info.type == MediaType.MOVIE:
                                # 非洗版時檢查是否存在
                                if not match_info.get("over_edition"):
                                    exist_flag, rss_no_exists, _ = self.downloader.check_exists_medias(
                                        meta_info=media_info,
                                        no_exists=rss_no_exists)
                                    if exist_flag:
                                        log.info(f"【Rss】電影 {media_info.get_title_string()} 已存在，刪除訂閱...")
                                        # 完成訂閱
                                        self.subscribe.finish_rss_subscribe(rtype="MOV",
                                                                            rssid=match_info.get("id"),
                                                                            media=media_info)
                                        continue
                            # 如果是電視劇
                            else:
                                # 從登記薄中獲取缺失劇集
                                season = 1
                                if match_info.get("season"):
                                    season = int(str(match_info.get("season")).replace("S", ""))
                                total_ep = match_info.get("total")
                                current_ep = match_info.get("current_ep")
                                episodes = self.dbhelper.get_rss_tv_episodes(match_info.get("id"))
                                if episodes is None:
                                    episodes = []
                                    if current_ep:
                                        episodes = list(range(int(current_ep), int(total_ep) + 1))
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
                                    log.info("【Rss】電視劇 %s%s 已全部訂閱完成，刪除訂閱..." % (
                                        media_info.title, media_info.get_season_string()))
                                    # 完成訂閱
                                    self.subscribe.finish_rss_subscribe(rtype="TV",
                                                                        rssid=match_info.get("id"),
                                                                        media=media_info)
                                    continue
                                # 非洗版時檢查本地媒體庫情況
                                if not match_info.get("over_edition"):
                                    exist_flag, library_no_exists, _ = self.downloader.check_exists_medias(
                                        meta_info=media_info,
                                        total_ep={season: total_ep})
                                    # 當前劇集已存在，跳過
                                    if exist_flag:
                                        # 已全部存在
                                        if not library_no_exists or not library_no_exists.get(
                                                media_info.tmdb_id):
                                            log.info("【Rss】電視劇 %s 訂閱劇集已全部存在，刪除訂閱..." % (
                                                media_info.get_title_string()))
                                            # 完成訂閱
                                            self.subscribe.finish_rss_subscribe(rtype="TV",
                                                                                rssid=match_info.get("id"),
                                                                                media=media_info)
                                        continue
                                    # 取交集做為缺失集
                                    rss_no_exists = self.media.get_intersection_episodes(target=rss_no_exists,
                                                                                         source=library_no_exists,
                                                                                         title=media_info.tmdb_id)
                                    if rss_no_exists.get(media_info.tmdb_id):
                                        log.info("【Rss】%s 訂閱缺失季集：%s" % (
                                            media_info.get_title_string(),
                                            rss_no_exists.get(media_info.tmdb_id)))
                        # 返回物件
                        media_info.set_torrent_info(res_order=match_info.get("res_order"),
                                                    download_volume_factor=match_info.get("download_volume_factor"),
                                                    upload_volume_factor=match_info.get("upload_volume_factor"),
                                                    rssid=match_info.get("id"),
                                                    description=description)
                        media_info.set_download_info(download_setting=match_info.get("download_setting"),
                                                     save_path=match_info.get("save_path"))
                        # 插入資料庫
                        self.dbhelper.insert_rss_torrents(media_info)
                        # 加入下載列表
                        if media_info not in rss_download_torrents:
                            rss_download_torrents.append(media_info)
                            res_num = res_num + 1
                    except Exception as e:
                        ExceptionUtils.exception_traceback(e)
                        log.error("【Rss】處理RSS發生錯誤：%s - %s" % (str(e), traceback.format_exc()))
                        continue
                log.info("【Rss】%s 處理結束，匹配到 %s 個有效資源" % (site_name, res_num))
            log.info("【Rss】所有RSS處理結束，共 %s 個有效資源" % len(rss_download_torrents))

            # 去重擇優後開始新增下載
            if rss_download_torrents:
                download_items, left_medias = self.downloader.batch_download(SearchType.RSS,
                                                                             rss_download_torrents,
                                                                             rss_no_exists)
                # 批次刪除訂閱
                if download_items:
                    for item in download_items:
                        if item.type == MediaType.MOVIE:
                            # 刪除電影訂閱
                            if item.rssid:
                                log.info("【Rss】電影 %s 訂閱完成，刪除訂閱..." % item.get_title_string())
                                self.subscribe.finish_rss_subscribe(rtype="MOV", rssid=item.rssid, media=item)
                        else:
                            if not left_medias or not left_medias.get(item.tmdb_id):
                                # 刪除電視劇訂閱
                                if item.rssid:
                                    log.info(
                                        "【Rss】電視劇 %s %s 訂閱完成，刪除訂閱..." % (
                                            item.get_title_string(),
                                            item.get_season_string()))
                                    # 完成訂閱
                                    self.subscribe.finish_rss_subscribe(rtype="TV", rssid=item.rssid, media=item)
                            else:
                                # 更新電視劇缺失劇集
                                left_media = left_medias.get(item.tmdb_id)
                                if not left_media:
                                    continue
                                for left_season in left_media:
                                    if item.is_in_season(left_season.get("season")):
                                        if left_season.get("episodes"):
                                            log.info("【Rss】更新電視劇 %s %s 訂閱缺失集數為 %s" % (
                                                item.get_title_string(), item.get_season_string(),
                                                len(left_season.get("episodes"))))
                                            self.dbhelper.update_rss_tv_lack(rssid=item.rssid,
                                                                             lack_episodes=left_season.get("episodes"))
                                            break
                    log.info("【Rss】實際下載了 %s 個資源" % len(download_items))
                else:
                    log.info("【Rss】未下載到任何資源")

    @staticmethod
    def parse_rssxml(url):
        """
        解析RSS訂閱URL，獲取RSS中的種子資訊
        :param url: RSS地址
        :return: 種子資訊列表
        """
        _special_title_sites = {
            'pt.keepfrds.com': RssTitleUtils.keepfriends_title
        }

        # 開始處理
        ret_array = []
        if not url:
            return []
        site_domain = StringUtils.get_url_domain(url)
        try:
            ret = RequestUtils().get_res(url)
            if not ret:
                return []
            ret.encoding = ret.apparent_encoding
        except Exception as e2:
            ExceptionUtils.exception_traceback(e2)
            log.console(str(e2))
            return []
        if ret:
            ret_xml = ret.text
            try:
                # 解析XML
                dom_tree = xml.dom.minidom.parseString(ret_xml)
                rootNode = dom_tree.documentElement
                items = rootNode.getElementsByTagName("item")
                for item in items:
                    try:
                        # 標題
                        title = DomUtils.tag_value(item, "title", default="")
                        if not title:
                            continue
                        # 標題特殊處理
                        if site_domain and site_domain in _special_title_sites:
                            title = _special_title_sites.get(site_domain)(title)
                        # 描述
                        description = DomUtils.tag_value(item, "description", default="")
                        # 種子頁面
                        link = DomUtils.tag_value(item, "link", default="")
                        # 種子連結
                        enclosure = DomUtils.tag_value(item, "enclosure", "url", default="")
                        if not enclosure and not link:
                            continue
                        # 部分RSS只有link沒有enclosure
                        if not enclosure and link:
                            enclosure = link
                            link = None
                        # 大小
                        size = DomUtils.tag_value(item, "enclosure", "length", default=0)
                        if size and str(size).isdigit():
                            size = int(size)
                        else:
                            size = 0
                        # 釋出日期
                        pubdate = DomUtils.tag_value(item, "pubDate", default="")
                        if pubdate:
                            # 轉換為時間
                            pubdate = StringUtils.get_time_stamp(pubdate)
                        # 返回物件
                        tmp_dict = {'title': title,
                                    'enclosure': enclosure,
                                    'size': size,
                                    'description': description,
                                    'link': link,
                                    'pubdate': pubdate}
                        ret_array.append(tmp_dict)
                    except Exception as e1:
                        ExceptionUtils.exception_traceback(e1)
                        continue
            except Exception as e2:
                ExceptionUtils.exception_traceback(e2)
                return ret_array
        return ret_array

    def check_torrent_rss(self,
                          media_info,
                          rss_movies,
                          rss_tvs,
                          site_filter_rule,
                          site_cookie,
                          site_parse,
                          site_ua):
        """
        判斷種子是否命中訂閱
        :param media_info: 已識別的種子媒體資訊
        :param rss_movies: 電影訂閱清單
        :param rss_tvs: 電視劇訂閱清單
        :param site_filter_rule: 站點過濾規則
        :param site_cookie: 站點的Cookie
        :param site_parse: 是否解析種子詳情
        :param site_ua: 站點請求UA
        :return: 匹配到的訂閱ID、是否洗版、總集數、匹配規則的資源順序、上傳因子、下載因子，匹配的季（電視劇）
        """
        # 預設值
        # 匹配狀態 0不在訂閱範圍內 -1不符合過濾條件 1匹配
        match_flag = False
        # 匹配的rss資訊
        match_msg = []
        match_rss_info = {}
        # 上傳因素
        upload_volume_factor = None
        # 下載因素
        download_volume_factor = None
        hit_and_run = False

        # 匹配電影
        if media_info.type == MediaType.MOVIE and rss_movies:
            for rid, rss_info in rss_movies.items():
                rss_sites = rss_info.get('rss_sites')
                # 過濾訂閱站點
                if rss_sites and media_info.site not in rss_sites:
                    continue
                # tmdbid或名稱年份匹配
                name = rss_info.get('name')
                year = rss_info.get('year')
                tmdbid = rss_info.get('tmdbid')
                fuzzy_match = rss_info.get('fuzzy_match')
                # 非模糊匹配
                if not fuzzy_match:
                    # 有tmdbid時使用tmdbid匹配
                    if tmdbid and not tmdbid.startswith("DB:"):
                        if str(media_info.tmdb_id) != str(tmdbid):
                            continue
                    else:
                        # 豆瓣年份與tmdb取向不同
                        if year and str(media_info.year) not in [str(year),
                                                                 str(int(year) + 1),
                                                                 str(int(year) - 1)]:
                            continue
                        if name != media_info.title:
                            continue
                # 模糊匹配
                else:
                    # 匹配年份
                    if year and str(year) != str(media_info.year):
                        continue
                    # 匹配關鍵字或正規表示式
                    search_title = f"{media_info.org_string} {media_info.title} {media_info.year}"
                    if not re.search(name, search_title, re.I) and name not in search_title:
                        continue
                # 媒體匹配成功
                match_flag = True
                match_rss_info = rss_info

                break
        # 匹配電視劇
        elif rss_tvs:
            # 匹配種子標題
            for rid, rss_info in rss_tvs.items():
                rss_sites = rss_info.get('rss_sites')
                # 過濾訂閱站點
                if rss_sites and media_info.site not in rss_sites:
                    continue
                # 有tmdbid時精確匹配
                name = rss_info.get('name')
                year = rss_info.get('year')
                season = rss_info.get('season')
                tmdbid = rss_info.get('tmdbid')
                fuzzy_match = rss_info.get('fuzzy_match')
                # 非模糊匹配
                if not fuzzy_match:
                    if tmdbid and not tmdbid.startswith("DB:"):
                        if str(media_info.tmdb_id) != str(tmdbid):
                            continue
                    else:
                        # 匹配年份，年份可以為空
                        if year and str(year) != str(media_info.year):
                            continue
                        # 匹配名稱
                        if name != media_info.title:
                            continue
                    # 匹配季，季可以為空
                    if season and season != media_info.get_season_string():
                        continue
                # 模糊匹配
                else:
                    # 匹配季，季可以為空
                    if season and season != "S00" and season != media_info.get_season_string():
                        continue
                    # 匹配年份
                    if year and str(year) != str(media_info.year):
                        continue
                    # 匹配關鍵字或正規表示式
                    search_title = f"{media_info.org_string} {media_info.title} {media_info.year}"
                    if not re.search(name, search_title, re.I) and name not in search_title:
                        continue
                # 媒體匹配成功
                match_flag = True
                match_rss_info = rss_info
                break
        # 名稱匹配成功，開始過濾
        if match_flag:
            # 解析種子詳情
            if site_parse:
                # 檢測Free
                torrent_attr = self.sites.check_torrent_attr(torrent_url=media_info.page_url,
                                                             cookie=site_cookie,
                                                             ua=site_ua)
                if torrent_attr.get('2xfree'):
                    download_volume_factor = 0.0
                    upload_volume_factor = 2.0
                elif torrent_attr.get('free'):
                    download_volume_factor = 0.0
                    upload_volume_factor = 1.0
                else:
                    upload_volume_factor = 1.0
                    download_volume_factor = 1.0
                if torrent_attr.get('hr'):
                    hit_and_run = True
                # 設定屬性
                media_info.set_torrent_info(upload_volume_factor=upload_volume_factor,
                                            download_volume_factor=download_volume_factor,
                                            hit_and_run=hit_and_run)
            # 訂閱無過濾規則應用站點設定
            # 過濾質
            filter_dict = {
                "restype": match_rss_info.get('filter_restype'),
                "pix": match_rss_info.get('filter_pix'),
                "team": match_rss_info.get('filter_team'),
                "rule": match_rss_info.get('filter_rule') or site_filter_rule
            }
            match_filter_flag, res_order, match_filter_msg = self.filter.check_torrent_filter(meta_info=media_info,
                                                                                              filter_args=filter_dict)
            if not match_filter_flag:
                match_msg.append(match_filter_msg)
                return False, match_msg, match_rss_info
            else:
                match_msg.append("%s 識別為 %s %s 匹配訂閱成功" % (
                    media_info.org_string,
                    media_info.get_title_string(),
                    media_info.get_season_episode_string()))
                match_msg.append(f"種子描述：{media_info.subtitle}")
                match_rss_info.update({
                    "res_order": res_order,
                    "upload_volume_factor": upload_volume_factor,
                    "download_volume_factor": download_volume_factor})
                return True, match_msg, match_rss_info
        else:
            match_msg.append("%s 識別為 %s %s 不在訂閱範圍" % (
                media_info.org_string,
                media_info.get_title_string(),
                media_info.get_season_episode_string()))
            return False, match_msg, match_rss_info
