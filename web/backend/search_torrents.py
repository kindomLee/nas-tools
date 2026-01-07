import re

import cn2an

import log
from app.downloader import Downloader
from app.helper import DbHelper, ProgressHelper
from app.indexer import Indexer
from app.media import MetaInfo, Media
from app.media.douban import DouBan
from app.message import Message
from app.searcher import Searcher
from app.sites import Sites
from app.subscribe import Subscribe
from app.utils import StringUtils
from app.utils.types import SearchType, MediaType, IndexerType
from config import Config

SEARCH_MEDIA_CACHE = {}
SEARCH_MEDIA_TYPE = {}


def search_medias_for_web(content, ident_flag=True, filters=None, tmdbid=None, media_type=None):
    """
    WEB資源搜尋
    :param content: 關鍵字文字，可以包括 型別、標題、季、集、年份等資訊，使用 空格分隔，也支援種子的命名格式
    :param ident_flag: 是否進行媒體資訊識別
    :param filters: 其它過濾條件
    :param tmdbid: TMDBID或DB:豆瓣ID
    :param media_type: 媒體型別，配合tmdbid傳入
    :return: 錯誤碼，錯誤原因，成功時直接插入資料庫
    """
    mtype, key_word, season_num, episode_num, year, content = StringUtils.get_keyword_from_string(content)
    if not key_word:
        log.info("【Web】%s 檢索關鍵字有誤！" % content)
        return -1, "%s 未識別到搜尋關鍵字！" % content
    # 開始進度
    search_process = ProgressHelper()
    search_process.start('search')
    # 識別媒體
    media_info = None
    if ident_flag:
        # 有TMDBID或豆瓣ID
        if tmdbid:
            # 豆瓣ID
            if tmdbid.startswith("DB:"):
                # 以豆瓣ID查詢
                doubanid = tmdbid[3:]
                # 先從網頁抓取（含TMDBID）
                doubaninfo = DouBan().get_media_detail_from_web(doubanid)
                if not doubaninfo or not doubaninfo.get("imdbid"):
                    # 從API抓取
                    doubaninfo = DouBan().get_douban_detail(doubanid=doubanid, mtype=media_type)
                    if not doubaninfo:
                        return -1, "%s 查詢不到豆瓣資訊，請確認網路是否正常！" % content
                if doubaninfo.get("imdbid"):
                    # 按IMDBID查詢TMDB
                    tmdbid = Media().get_tmdbid_by_imdbid(doubaninfo.get("imdbid"))
                    if tmdbid:
                        # 以TMDBID查詢
                        media_info = MetaInfo(mtype=media_type or mtype, title=content)
                        media_info.set_tmdb_info(Media().get_tmdb_info(mtype=media_type or mtype, tmdbid=tmdbid))
                        media_info.imdb_id = doubaninfo.get("imdbid")
                        if doubaninfo.get("season") and str(doubaninfo.get("season")).isdigit():
                            media_info.begin_season = int(doubaninfo.get("season"))
                if not media_info or not media_info.tmdb_info:
                    # 按豆瓣名稱查
                    title = doubaninfo.get("title")
                    media_info = Media().get_media_info(mtype=media_type,
                                                        title="%s %s" % (title, doubaninfo.get("year")),
                                                        strict=True)
                    # 整合集
                    if media_info and episode_num:
                        media_info.begin_episode = int(episode_num)
            # TMDBID
            else:
                # 以TMDBID查詢
                media_info = MetaInfo(mtype=media_type or mtype, title=content)
                media_info.set_tmdb_info(Media().get_tmdb_info(mtype=media_type or mtype, tmdbid=tmdbid))
        else:
            # 按輸入名稱查
            media_info = Media().get_media_info(mtype=media_type or mtype, title=content)

        if media_info and media_info.tmdb_info:
            log.info(f"【Web】從TMDB中匹配到{media_info.type.value}：{media_info.get_title_string()}")
            # 查詢的季
            if media_info.begin_season is None:
                search_season = None
            else:
                search_season = media_info.get_season_list()
            # 查詢的集
            search_episode = media_info.get_episode_list()
            if search_episode and not search_season:
                search_season = [1]
            # 中文名
            if media_info.cn_name:
                search_cn_name = media_info.cn_name
            else:
                search_cn_name = media_info.title
            # 英文名
            search_en_name = None
            if media_info.en_name:
                search_en_name = media_info.en_name
            else:
                if media_info.original_language == "en":
                    search_en_name = media_info.original_title
                else:
                    en_info = Media().get_tmdb_info(mtype=media_info.type, tmdbid=media_info.tmdb_id, language="en-US")
                    if en_info:
                        search_en_name = en_info.get("title") if media_info.type == MediaType.MOVIE else en_info.get(
                            "name")
            # 兩次搜尋名稱
            second_search_name = None
            if Config().get_config("laboratory").get("search_en_title"):
                if search_en_name:
                    first_search_name = search_en_name
                    second_search_name = search_cn_name
                else:
                    first_search_name = search_cn_name
            else:
                first_search_name = search_cn_name
                if search_en_name:
                    second_search_name = search_en_name

            filter_args = {"season": search_season,
                           "episode": search_episode,
                           "year": media_info.year,
                           "type": media_info.type}
        else:
            # 查詢不到資料，使用快速搜尋
            log.info(f"【Web】{content} 未從TMDB匹配到媒體資訊，將使用快速搜尋...")
            ident_flag = False
            media_info = None
            first_search_name = key_word
            second_search_name = None
            filter_args = {"season": season_num,
                           "episode": episode_num,
                           "year": year}
    # 快速搜尋
    else:
        first_search_name = key_word
        second_search_name = None
        filter_args = {"season": season_num,
                       "episode": episode_num,
                       "year": year}
    # 整合高階查詢條件
    if filters:
        filter_args.update(filters)
    # 開始檢索
    log.info("【Web】開始檢索 %s ..." % content)
    media_list = Searcher().search_medias(key_word=first_search_name,
                                          filter_args=filter_args,
                                          match_media=media_info,
                                          in_from=SearchType.WEB)
    # 使用第二名稱重新搜尋
    if ident_flag \
            and len(media_list) == 0 \
            and second_search_name \
            and second_search_name != first_search_name:
        search_process.start('search')
        search_process.update(ptype='search',
                              text="%s 未檢索到資源,嘗試透過 %s 重新檢索 ..." % (first_search_name, second_search_name))
        log.info("【Searcher】%s 未檢索到資源,嘗試透過 %s 重新檢索 ..." % (first_search_name, second_search_name))
        media_list = Searcher().search_medias(key_word=second_search_name,
                                              filter_args=filter_args,
                                              match_media=media_info,
                                              in_from=SearchType.WEB)
    # 清空快取結果
    dbhepler = DbHelper()
    dbhepler.delete_all_search_torrents()
    # 結束進度
    search_process.end('search')
    if len(media_list) == 0:
        log.info("【Web】%s 未檢索到任何資源" % content)
        return 1, "%s 未檢索到任何資源" % content
    else:
        log.info("【Web】共檢索到 %s 個有效資源" % len(media_list))
        # 插入資料庫
        media_list = sorted(media_list, key=lambda x: "%s%s%s" % (str(x.res_order).rjust(3, '0'),
                                                                  str(x.site_order).rjust(3, '0'),
                                                                  str(x.seeders).rjust(10, '0')), reverse=True)
        dbhepler.insert_search_results(media_list)
        return 0, ""


def search_media_by_message(input_str, in_from: SearchType, user_id, user_name=None):
    """
    輸入字串，解析要求並進行資源檢索
    :param input_str: 輸入字串，可以包括標題、年份、季、集的資訊，使用空格隔開
    :param in_from: 搜尋下載的請求來源
    :param user_id: 需要傳送訊息的，傳入該引數，則只給對應使用者傳送互動訊息
    :param user_name: 使用者名稱稱
    :return: 請求的資源是否全部下載完整、請求的文字對應識別出來的媒體資訊、請求的資源如果是劇集，則返回下載後仍然缺失的季集資訊
    """
    global SEARCH_MEDIA_TYPE
    global SEARCH_MEDIA_CACHE

    if not input_str:
        log.info("【Searcher】檢索關鍵字有誤！")
        return
    # 如果是數字，表示選擇項
    if input_str.isdigit() and int(input_str) < 10:
        # 獲取之前儲存的可選項
        choose = int(input_str) - 1
        if not SEARCH_MEDIA_CACHE.get(user_id) or \
                choose < 0 or choose >= len(SEARCH_MEDIA_CACHE.get(user_id)):
            Message().send_channel_msg(channel=in_from,
                                       title="輸入有誤！",
                                       user_id=user_id)
            log.warn("【Web】錯誤的輸入值：%s" % input_str)
            return
        media_info = SEARCH_MEDIA_CACHE[user_id][choose]
        if not SEARCH_MEDIA_TYPE.get(user_id) \
                or SEARCH_MEDIA_TYPE.get(user_id) == "SEARCH":
            # 如果是豆瓣資料，需要重新查詢TMDB的資料
            if media_info.douban_id:
                _title = media_info.get_title_string()
                # 先從網頁抓取（含TMDBID）
                doubaninfo = DouBan().get_media_detail_from_web(media_info.douban_id)
                if doubaninfo and doubaninfo.get("imdbid"):
                    tmdbid = Media().get_tmdbid_by_imdbid(doubaninfo.get("imdbid"))
                    if tmdbid:
                        # 按IMDBID查詢TMDB
                        media_info.set_tmdb_info(Media().get_tmdb_info(mtype=media_info.type, tmdbid=tmdbid))
                        media_info.imdb_id = doubaninfo.get("imdbid")
                else:
                    search_episode = media_info.begin_episode
                    media_info = Media().get_media_info(title="%s %s" % (media_info.title, media_info.year),
                                                        mtype=media_info.type,
                                                        strict=True)
                    media_info.begin_episode = search_episode
                if not media_info or not media_info.tmdb_info:
                    Message().send_channel_msg(channel=in_from,
                                               title="%s 從TMDB查詢不到媒體資訊！" % _title,
                                               user_id=user_id)
                    return
            # 搜尋
            __search_media(in_from=in_from,
                           media_info=media_info,
                           user_id=user_id,
                           user_name=user_name)
        else:
            # 訂閱
            __rss_media(in_from=in_from,
                        media_info=media_info,
                        user_id=user_id,
                        user_name=user_name)
    # 接收到文字，開始查詢可能的媒體資訊供選擇
    else:
        if input_str.startswith("訂閱"):
            SEARCH_MEDIA_TYPE[user_id] = "SUBSCRIBE"
            input_str = re.sub(r"訂閱[:：\s]*", "", input_str)
        else:
            input_str = re.sub(r"[搜尋|下載][:：\s]*", "", input_str)
            SEARCH_MEDIA_TYPE[user_id] = "SEARCH"

        # 去掉查詢中的電影或電視劇關鍵字
        mtype, _, _, _, _, org_content = StringUtils.get_keyword_from_string(input_str)

        # 獲取字串中可能的RSS站點列表
        rss_sites, content = StringUtils.get_idlist_from_string(org_content,
                                                                [{
                                                                    "id": site.get("name"),
                                                                    "name": site.get("name")
                                                                } for site in Sites().get_sites(rss=True)])

        # 索引器型別
        indexer_type = Indexer().get_client_type()
        indexers = Indexer().get_indexers()

        # 獲取字串中可能的搜尋站點列表
        if indexer_type == IndexerType.BUILTIN.value:
            search_sites, _ = StringUtils.get_idlist_from_string(org_content, [{
                "id": indexer.name,
                "name": indexer.name
            } for indexer in indexers])
        else:
            search_sites, content = StringUtils.get_idlist_from_string(content, [{
                "id": indexer.name,
                "name": indexer.name
            } for indexer in indexers])

        # 獲取字串中可能的下載設定
        download_setting, content = StringUtils.get_idlist_from_string(content, [{
            "id": dl.get("id"),
            "name": dl.get("name")
        } for dl in Downloader().get_download_setting().values()])
        if download_setting:
            download_setting = download_setting[0]

        # 識別媒體資訊，列出匹配到的所有媒體
        log.info("【Web】正在識別 %s 的媒體資訊..." % content)
        media_info = MetaInfo(title=content, mtype=mtype)
        if not media_info.get_name():
            Message().send_channel_msg(channel=in_from,
                                       title="無法識別搜尋內容！",
                                       user_id=user_id)
            return

        # 搜尋名稱
        use_douban_titles = Config().get_config("laboratory").get("use_douban_titles")
        if use_douban_titles:
            tmdb_infos = DouBan().search_douban_medias(
                keyword=media_info.get_name() if not media_info.year else "%s %s" % (
                    media_info.get_name(), media_info.year),
                mtype=mtype,
                num=6,
                season=media_info.begin_season,
                episode=media_info.begin_episode)
        else:
            tmdb_infos = Media().get_tmdb_infos(title=media_info.get_name(), year=media_info.year, mtype=mtype)
        if not tmdb_infos:
            # 查詢不到媒體資訊
            Message().send_channel_msg(channel=in_from,
                                       title="%s 查詢不到媒體資訊！" % content,
                                       user_id=user_id)
            return

        # 儲存識別資訊到臨時結果中
        SEARCH_MEDIA_CACHE[user_id] = []
        if use_douban_titles:
            for meta_info in tmdb_infos:
                # 合併站點和下載設定資訊
                meta_info.rss_sites = rss_sites
                meta_info.search_sites = search_sites
                media_info.set_download_info(download_setting=download_setting)
                SEARCH_MEDIA_CACHE[user_id].append(meta_info)
        else:
            for tmdb_info in tmdb_infos:
                meta_info = MetaInfo(title=content)
                meta_info.set_tmdb_info(tmdb_info)
                if meta_info.begin_season:
                    meta_info.title = "%s 第%s季" % (meta_info.title, cn2an.an2cn(meta_info.begin_season, mode='low'))
                if meta_info.begin_episode:
                    meta_info.title = "%s 第%s集" % (meta_info.title, meta_info.begin_episode)
                # 合併站點和下載設定資訊
                meta_info.rss_sites = rss_sites
                meta_info.search_sites = search_sites
                media_info.set_download_info(download_setting=download_setting)
                SEARCH_MEDIA_CACHE[user_id].append(meta_info)

        if 1 == len(SEARCH_MEDIA_CACHE[user_id]):
            # 只有一條資料，直接開始搜尋
            media_info = SEARCH_MEDIA_CACHE[user_id][0]
            if not SEARCH_MEDIA_TYPE.get(user_id) \
                    or SEARCH_MEDIA_TYPE.get(user_id) == "SEARCH":
                # 如果是豆瓣資料，需要重新查詢TMDB的資料
                if media_info.douban_id:
                    _title = media_info.get_title_string()
                    media_info = Media().get_media_info(title="%s %s" % (media_info.title, media_info.year),
                                                        mtype=media_info.type, strict=True)
                    if not media_info or not media_info.tmdb_info:
                        Message().send_channel_msg(channel=in_from,
                                                   title="%s 從TMDB查詢不到媒體資訊！" % _title,
                                                   user_id=user_id)
                        return
                # 傳送訊息
                Message().send_channel_msg(channel=in_from,
                                           title=media_info.get_title_vote_string(),
                                           text=media_info.get_overview_string(),
                                           image=media_info.get_message_image(),
                                           url=media_info.get_detail_url(),
                                           user_id=user_id)
                # 開始搜尋
                __search_media(in_from=in_from,
                               media_info=media_info,
                               user_id=user_id,
                               user_name=user_name)
            else:
                # 新增訂閱
                __rss_media(in_from=in_from,
                            media_info=media_info,
                            user_id=user_id,
                            user_name=user_name)
        else:
            # 傳送訊息通知選擇
            Message().send_channel_list_msg(channel=in_from,
                                            title="共找到%s條相關資訊，請回復對應序號" % len(SEARCH_MEDIA_CACHE[user_id]),
                                            medias=SEARCH_MEDIA_CACHE[user_id],
                                            user_id=user_id)


def __search_media(in_from, media_info, user_id, user_name=None):
    """
    開始搜尋和傳送訊息
    """
    # 檢查是否存在，電視劇返回不存在的集清單
    exist_flag, no_exists, messages = Downloader().check_exists_medias(meta_info=media_info)
    if messages:
        Message().send_channel_msg(channel=in_from,
                                   title="\n".join(messages),
                                   user_id=user_id)
    # 已經存在
    if exist_flag:
        return

    # 開始檢索
    Message().send_channel_msg(channel=in_from,
                               title="開始檢索 %s ..." % media_info.title,
                               user_id=user_id)
    search_result, no_exists, search_count, download_count = Searcher().search_one_media(media_info=media_info,
                                                                                         in_from=in_from,
                                                                                         no_exists=no_exists,
                                                                                         sites=media_info.search_sites,
                                                                                         user_name=user_name)
    # 沒有搜尋到資料
    if not search_count:
        Message().send_channel_msg(channel=in_from,
                                   title="%s 未搜尋到任何資源" % media_info.title,
                                   user_id=user_id)
    else:
        # 搜尋到了但是沒開自動下載
        if download_count is None:
            Message().send_channel_msg(channel=in_from,
                                       title="%s 共搜尋到%s個資源，點選選擇下載" % (media_info.title, search_count),
                                       image=media_info.get_message_image(),
                                       url="search",
                                       user_id=user_id)
            return
        else:
            # 搜尋到了但是沒下載到資料
            if download_count == 0:
                Message().send_channel_msg(channel=in_from,
                                           title="%s 共搜尋到%s個結果，但沒有下載到任何資源" % (
                                               media_info.title, search_count),
                                           user_id=user_id)
    # 沒有下載完成，且開啟了自動新增訂閱
    if not search_result and Config().get_config('pt').get('search_no_result_rss'):
        # 新增訂閱
        __rss_media(in_from=in_from,
                    media_info=media_info,
                    user_id=user_id,
                    state='R',
                    user_name=user_name)


def __rss_media(in_from, media_info, user_id=None, state='D', user_name=None):
    """
    開始新增訂閱和傳送訊息
    """
    # 新增訂閱
    if media_info.douban_id:
        code, msg, media_info = Subscribe().add_rss_subscribe(mtype=media_info.type,
                                                              name=media_info.title,
                                                              year=media_info.year,
                                                              season=media_info.begin_season,
                                                              doubanid=media_info.douban_id,
                                                              state=state,
                                                              rss_sites=media_info.rss_sites,
                                                              search_sites=media_info.search_sites)
    else:
        code, msg, media_info = Subscribe().add_rss_subscribe(mtype=media_info.type,
                                                              name=media_info.title,
                                                              year=media_info.year,
                                                              season=media_info.begin_season,
                                                              tmdbid=media_info.tmdb_id,
                                                              state=state,
                                                              rss_sites=media_info.rss_sites,
                                                              search_sites=media_info.search_sites)
    if code == 0:
        log.info("【Web】%s %s 已新增訂閱" % (media_info.type.value, media_info.get_title_string()))
        if in_from in [SearchType.WX, SearchType.TG, SearchType.SLACK]:
            media_info.user_name = user_name
            Message().send_rss_success_message(in_from=in_from,
                                               media_info=media_info)
    else:
        if in_from in [SearchType.WX, SearchType.TG, SearchType.SLACK]:
            log.info("【Web】%s 新增訂閱失敗：%s" % (media_info.title, msg))
            Message().send_channel_msg(channel=in_from,
                                       title="%s 新增訂閱失敗：%s" % (media_info.title, msg),
                                       user_id=user_id)
