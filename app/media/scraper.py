import os.path
import time
from xml.dom import minidom

import log
from app.media.douban import DouBan
from app.utils.exception_utils import ExceptionUtils
from config import TMDB_IMAGE_W500_URL
from app.utils import DomUtils, RequestUtils
from app.utils.types import MediaType
from app.media import Media


class Scraper:
    media = None

    def __init__(self):
        self.media = Media()
        self.douban = DouBan()

    def __gen_common_nfo(self,
                         tmdbinfo: dict,
                         doubaninfo: dict,
                         scraper_nfo: dict,
                         doc,
                         root,
                         chinese=False):
        if scraper_nfo.get("basic"):
            # 新增時間
            DomUtils.add_node(doc, root, "dateadded", time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())))
            # TMDB
            DomUtils.add_node(doc, root, "tmdbid", tmdbinfo.get("id") or "")
            uniqueid_tmdb = DomUtils.add_node(doc, root, "uniqueid", tmdbinfo.get("id") or "")
            uniqueid_tmdb.setAttribute("type", "tmdb")
            uniqueid_tmdb.setAttribute("default", "true")
            # TVDB IMDB
            if tmdbinfo.get("external_ids"):
                tvdbid = tmdbinfo.get("external_ids", {}).get("tvdb_id", 0)
                if tvdbid:
                    DomUtils.add_node(doc, root, "tvdbid", tvdbid)
                    uniqueid_tvdb = DomUtils.add_node(doc, root, "uniqueid", tvdbid)
                    uniqueid_tvdb.setAttribute("type", "tvdb")
                imdbid = tmdbinfo.get("external_ids", {}).get("imdb_id", "")
                if imdbid:
                    DomUtils.add_node(doc, root, "imdbid", imdbid)
                    uniqueid_imdb = DomUtils.add_node(doc, root, "uniqueid", imdbid)
                    uniqueid_imdb.setAttribute("type", "imdb")
                    uniqueid_imdb.setAttribute("default", "true")
                    uniqueid_tmdb.setAttribute("default", "false")

            # 簡介
            xplot = DomUtils.add_node(doc, root, "plot")
            xplot.appendChild(doc.createCDATASection(tmdbinfo.get("overview") or ""))
            xoutline = DomUtils.add_node(doc, root, "outline")
            xoutline.appendChild(doc.createCDATASection(tmdbinfo.get("overview") or ""))
        if scraper_nfo.get("credits"):
            # 導演
            directors, actors = self.__get_tmdbinfo_directors_actors(tmdbinfo.get("credits"))
            if chinese:
                directors, actors = self.__gen_people_chinese_info(directors, actors, doubaninfo)
            for director in directors:
                xdirector = DomUtils.add_node(doc, root, "director", director.get("name") or "")
                xdirector.setAttribute("tmdbid", str(director.get("id") or ""))
            # 演員
            for actor in actors:
                xactor = DomUtils.add_node(doc, root, "actor")
                DomUtils.add_node(doc, xactor, "name", actor.get("name") or "")
                DomUtils.add_node(doc, xactor, "type", "Actor")
                DomUtils.add_node(doc, xactor, "role", actor.get("character") or "")
                DomUtils.add_node(doc, xactor, "order", actor.get("order") if actor.get("order") is not None else "")
                DomUtils.add_node(doc, xactor, "tmdbid", actor.get("id") or "")
                DomUtils.add_node(doc, xactor, "thumb", f"https://image.tmdb.org/t/p/h632{actor.get('profile_path')}")
                DomUtils.add_node(doc, xactor, "profile", f"https://www.themoviedb.org/person/{actor.get('id')}")
        if scraper_nfo.get("basic"):
            # 風格
            genres = tmdbinfo.get("genres") or []
            for genre in genres:
                DomUtils.add_node(doc, root, "genre", genre.get("name") or "")
            # 評分
            DomUtils.add_node(doc, root, "rating", tmdbinfo.get("vote_average") or "0")
        return doc

    def gen_movie_nfo_file(self,
                           tmdbinfo: dict,
                           doubaninfo: dict,
                           scraper_movie_nfo: dict,
                           out_path,
                           file_name):
        """
        生成電影的NFO描述檔案
        :param tmdbinfo: TMDB後設資料
        :param doubaninfo: 豆瓣後設資料
        :param scraper_movie_nfo: 刮削配置
        :param out_path: 電影根目錄
        :param file_name: 電影檔名，不含字尾
        """
        # 開始生成XML
        log.info("【Scraper】正在生成電影NFO檔案：%s" % file_name)
        doc = minidom.Document()
        root = DomUtils.add_node(doc, doc, "movie")
        # 公共部分
        doc = self.__gen_common_nfo(tmdbinfo=tmdbinfo,
                                    doubaninfo=doubaninfo,
                                    scraper_nfo=scraper_movie_nfo,
                                    doc=doc,
                                    root=root,
                                    chinese=scraper_movie_nfo.get("credits_chinese"))
        # 基礎部分
        if scraper_movie_nfo.get("basic"):
            # 標題
            DomUtils.add_node(doc, root, "title", tmdbinfo.get("title") or "")
            DomUtils.add_node(doc, root, "originaltitle", tmdbinfo.get("original_title") or "")
            # 釋出日期
            DomUtils.add_node(doc, root, "premiered", tmdbinfo.get("release_date") or "")
            # 年份
            DomUtils.add_node(doc, root, "year",
                              tmdbinfo.get("release_date")[:4] if tmdbinfo.get("release_date") else "")
        # 儲存
        self.__save_nfo(doc, os.path.join(out_path, "%s.nfo" % file_name))

    def gen_tv_nfo_file(self,
                        tmdbinfo: dict,
                        doubaninfo: dict,
                        scraper_tv_nfo: dict,
                        out_path):
        """
        生成電視劇的NFO描述檔案
        :param tmdbinfo: TMDB後設資料
        :param doubaninfo: 豆瓣後設資料
        :param scraper_tv_nfo: 刮削配置
        :param out_path: 電視劇根目錄
        """
        # 開始生成XML
        log.info("【Scraper】正在生成電視劇NFO檔案：%s" % out_path)
        doc = minidom.Document()
        root = DomUtils.add_node(doc, doc, "tvshow")
        # 公共部分
        doc = self.__gen_common_nfo(tmdbinfo=tmdbinfo,
                                    doubaninfo=doubaninfo,
                                    scraper_nfo=scraper_tv_nfo,
                                    doc=doc,
                                    root=root,
                                    chinese=scraper_tv_nfo.get("credits_chinese"))
        if scraper_tv_nfo.get("basic"):
            # 標題
            DomUtils.add_node(doc, root, "title", tmdbinfo.get("name") or "")
            DomUtils.add_node(doc, root, "originaltitle", tmdbinfo.get("original_name") or "")
            # 釋出日期
            DomUtils.add_node(doc, root, "premiered", tmdbinfo.get("first_air_date") or "")
            # 年份
            DomUtils.add_node(doc, root, "year",
                              tmdbinfo.get("first_air_date")[:4] if tmdbinfo.get("first_air_date") else "")
            DomUtils.add_node(doc, root, "season", "-1")
            DomUtils.add_node(doc, root, "episode", "-1")
        # 儲存
        self.__save_nfo(doc, os.path.join(out_path, "tvshow.nfo"))

    def gen_tv_season_nfo_file(self, tmdbinfo: dict, season, out_path):
        """
        生成電視劇季的NFO描述檔案
        :param tmdbinfo: TMDB季媒體資訊
        :param season: 季號
        :param out_path: 電視劇季的目錄
        """
        log.info("【Scraper】正在生成季NFO檔案：%s" % out_path)
        doc = minidom.Document()
        root = DomUtils.add_node(doc, doc, "season")
        # 新增時間
        DomUtils.add_node(doc, root, "dateadded", time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())))
        # 簡介
        xplot = DomUtils.add_node(doc, root, "plot")
        xplot.appendChild(doc.createCDATASection(tmdbinfo.get("overview") or ""))
        xoutline = DomUtils.add_node(doc, root, "outline")
        xoutline.appendChild(doc.createCDATASection(tmdbinfo.get("overview") or ""))
        # 標題
        DomUtils.add_node(doc, root, "title", "季 %s" % season)
        # 發行日期
        DomUtils.add_node(doc, root, "premiered", tmdbinfo.get("air_date") or "")
        DomUtils.add_node(doc, root, "releasedate", tmdbinfo.get("air_date") or "")
        # 發行年份
        DomUtils.add_node(doc, root, "year", tmdbinfo.get("air_date")[:4] if tmdbinfo.get("air_date") else "")
        # seasonnumber
        DomUtils.add_node(doc, root, "seasonnumber", season)
        # 儲存
        self.__save_nfo(doc, os.path.join(out_path, "season.nfo"))

    def gen_tv_episode_nfo_file(self,
                                tmdbinfo: dict,
                                scraper_tv_nfo,
                                season: int,
                                episode: int,
                                out_path,
                                file_name):
        """
        生成電視劇集的NFO描述檔案
        :param tmdbinfo: TMDB後設資料
        :param scraper_tv_nfo: 刮削配置
        :param season: 季號
        :param episode: 集號
        :param out_path: 電視劇季的目錄
        :param file_name: 電視劇檔名，不含字尾
        """
        # 開始生成集的資訊
        log.info("【Scraper】正在生成劇集NFO檔案：%s" % file_name)
        # 集的資訊
        episode_detail = {}
        for episode_info in tmdbinfo.get("episodes") or []:
            if int(episode_info.get("episode_number")) == int(episode):
                episode_detail = episode_info
        if not episode_detail:
            return
        doc = minidom.Document()
        root = DomUtils.add_node(doc, doc, "episodedetails")
        if scraper_tv_nfo.get("episode_basic"):
            # 新增時間
            DomUtils.add_node(doc, root, "dateadded", time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())))
            # TMDBID
            uniqueid = DomUtils.add_node(doc, root, "uniqueid", tmdbinfo.get("id") or "")
            uniqueid.setAttribute("type", "tmdb")
            uniqueid.setAttribute("default", "true")
            # tmdbid
            DomUtils.add_node(doc, root, "tmdbid", tmdbinfo.get("id") or "")
            # 標題
            DomUtils.add_node(doc, root, "title", episode_detail.get("name") or "第 %s 集" % episode)
            # 簡介
            xplot = DomUtils.add_node(doc, root, "plot")
            xplot.appendChild(doc.createCDATASection(episode_detail.get("overview") or ""))
            xoutline = DomUtils.add_node(doc, root, "outline")
            xoutline.appendChild(doc.createCDATASection(episode_detail.get("overview") or ""))
            # 釋出日期
            DomUtils.add_node(doc, root, "aired", episode_detail.get("air_date") or "")
            # 年份
            DomUtils.add_node(doc, root, "year",
                              episode_detail.get("air_date")[:4] if episode_detail.get("air_date") else "")
            # 季
            DomUtils.add_node(doc, root, "season", season)
            # 集
            DomUtils.add_node(doc, root, "episode", episode)
            # 評分
            DomUtils.add_node(doc, root, "rating", episode_detail.get("vote_average") or "0")
        if scraper_tv_nfo.get("episode_credits"):
            # 導演
            directors = episode_detail.get("crew") or []
            for director in directors:
                if director.get("known_for_department") == "Directing":
                    xdirector = DomUtils.add_node(doc, root, "director", director.get("name") or "")
                    xdirector.setAttribute("tmdbid", str(director.get("id") or ""))
            # 演員
            actors = episode_detail.get("guest_stars") or []
            for actor in actors:
                if actor.get("known_for_department") == "Acting":
                    xactor = DomUtils.add_node(doc, root, "actor")
                    DomUtils.add_node(doc, xactor, "name", actor.get("name") or "")
                    DomUtils.add_node(doc, xactor, "type", "Actor")
                    DomUtils.add_node(doc, xactor, "tmdbid", actor.get("id") or "")
        # 儲存檔案
        self.__save_nfo(doc, os.path.join(out_path, os.path.join(out_path, "%s.nfo" % file_name)))

    @staticmethod
    def __save_image(url, out_path, itype="poster"):
        """
        下載poster.jpg並儲存
        """
        if not url or not out_path:
            return
        if os.path.exists(os.path.join(out_path, "%s.%s" % (itype, str(url).split('.')[-1]))):
            return
        try:
            log.info(f"【Scraper】正在下載{itype}圖片：{url} ...")
            r = RequestUtils().get_res(url)
            if r:
                with open(file=os.path.join(out_path, "%s.%s" % (itype, str(url).split('.')[-1])),
                          mode="wb") as img:
                    img.write(r.content)
                log.info(f"【Scraper】{itype}圖片已儲存：{out_path}")
            else:
                log.info(f"【Scraper】{itype}圖片下載失敗，請檢查網路連通性")
        except Exception as err:
            ExceptionUtils.exception_traceback(err)

    @staticmethod
    def __save_nfo(doc, out_file):
        xml_str = doc.toprettyxml(indent="  ", encoding="utf-8")
        with open(out_file, "wb") as xml_file:
            xml_file.write(xml_str)

    def gen_scraper_files(self, media, scraper_nfo, scraper_pic, dir_path, file_name):
        """
        刮削後設資料
        :param media: 已識別的媒體資訊
        :param scraper_nfo: NFO刮削配置
        :param scraper_pic: 圖片刮削配置
        :param dir_path: 檔案路徑
        :param file_name: 檔名
        """
        if not scraper_nfo:
            scraper_nfo = {}
        if not scraper_pic:
            scraper_pic = {}
        try:
            # 電影
            if media.type == MediaType.MOVIE:
                scraper_movie_nfo = scraper_nfo.get("movie")
                scraper_movie_pic = scraper_pic.get("movie")
                # 已存在時不處理
                if os.path.exists(os.path.join(dir_path, "movie.nfo")):
                    return
                if os.path.exists(os.path.join(dir_path, "%s.nfo" % file_name)):
                    return
                #  nfo
                if scraper_movie_nfo.get("basic") or scraper_movie_nfo.get("credits"):
                    # 查詢Douban資訊
                    if scraper_movie_nfo.get("credits") and scraper_movie_nfo.get("credits_chinese"):
                        doubaninfo = self.douban.get_douban_info(media)
                    else:
                        doubaninfo = None
                    #  生成電影描述檔案
                    self.gen_movie_nfo_file(tmdbinfo=media.tmdb_info,
                                            doubaninfo=doubaninfo,
                                            scraper_movie_nfo=scraper_movie_nfo,
                                            out_path=dir_path,
                                            file_name=file_name)
                # poster
                if scraper_movie_pic.get("poster"):
                    poster_image = media.get_poster_image(original=True)
                    if poster_image:
                        self.__save_image(poster_image, dir_path)
                # backdrop
                if scraper_movie_pic.get("backdrop"):
                    backdrop_image = media.get_backdrop_image(default=False, original=True)
                    if backdrop_image:
                        self.__save_image(backdrop_image, dir_path, "fanart")
                # background
                if scraper_movie_pic.get("background"):
                    background_image = media.fanart.get_background(media_type=media.type, queryid=media.tmdb_id)
                    if background_image:
                        self.__save_image(background_image, dir_path, "background")
                # logo
                if scraper_movie_pic.get("logo"):
                    logo_image = media.fanart.get_logo(media_type=media.type, queryid=media.tmdb_id)
                    if logo_image:
                        self.__save_image(logo_image, dir_path, "logo")
                # disc
                if scraper_movie_pic.get("disc"):
                    disc_image = media.fanart.get_disc(media_type=media.type, queryid=media.tmdb_id)
                    if disc_image:
                        self.__save_image(disc_image, dir_path, "disc")
                # banner
                if scraper_movie_pic.get("banner"):
                    banner_image = media.fanart.get_banner(media_type=media.type, queryid=media.tmdb_id)
                    if banner_image:
                        self.__save_image(banner_image, dir_path, "banner")
                # thumb
                if scraper_movie_pic.get("thumb"):
                    thumb_image = media.fanart.get_thumb(media_type=media.type, queryid=media.tmdb_id)
                    if thumb_image:
                        self.__save_image(thumb_image, dir_path, "thumb")

            # 電視劇
            else:
                scraper_tv_nfo = scraper_nfo.get("tv")
                scraper_tv_pic = scraper_pic.get("tv")
                # 處理根目錄
                if not os.path.exists(os.path.join(os.path.dirname(dir_path), "tvshow.nfo")):
                    if scraper_tv_nfo.get("basic") or scraper_tv_nfo.get("credits"):
                        # 查詢Douban資訊
                        if scraper_tv_nfo.get("credits") and scraper_tv_nfo.get("credits_chinese"):
                            doubaninfo = self.douban.get_douban_info(media)
                        else:
                            doubaninfo = None
                        # 根目錄描述檔案
                        self.gen_tv_nfo_file(media.tmdb_info, doubaninfo, scraper_tv_nfo, os.path.dirname(dir_path))
                    # poster
                    if scraper_tv_pic.get("poster"):
                        poster_image = media.get_poster_image(original=True)
                        if poster_image:
                            self.__save_image(poster_image, os.path.dirname(dir_path))
                    # backdrop
                    if scraper_tv_pic.get("backdrop"):
                        backdrop_image = media.get_backdrop_image(default=False, original=True)
                        if backdrop_image:
                            self.__save_image(backdrop_image, os.path.dirname(dir_path), "fanart")
                    # background
                    if scraper_tv_pic.get("background"):
                        background_image = media.fanart.get_background(media_type=media.type, queryid=media.tvdb_id)
                        if background_image:
                            self.__save_image(background_image, dir_path, "show")
                    # logo
                    if scraper_tv_pic.get("logo"):
                        logo_image = media.fanart.get_logo(media_type=media.type, queryid=media.tvdb_id)
                        if logo_image:
                            self.__save_image(logo_image, dir_path, "logo")
                    # clearart
                    if scraper_tv_pic.get("clearart"):
                        clearart_image = media.fanart.get_disc(media_type=media.type, queryid=media.tvdb_id)
                        if clearart_image:
                            self.__save_image(clearart_image, dir_path, "clearart")
                    # banner
                    if scraper_tv_pic.get("banner"):
                        banner_image = media.fanart.get_banner(media_type=media.type, queryid=media.tvdb_id)
                        if banner_image:
                            self.__save_image(banner_image, dir_path, "banner")
                    # thumb
                    if scraper_tv_pic.get("thumb"):
                        thumb_image = media.fanart.get_thumb(media_type=media.type, queryid=media.tvdb_id)
                        if thumb_image:
                            self.__save_image(thumb_image, dir_path, "thumb")
                # 處理集
                if not os.path.exists(os.path.join(dir_path, "%s.nfo" % file_name)):
                    # 查詢TMDB資訊
                    if scraper_tv_nfo.get("season_basic") \
                            or scraper_tv_nfo.get("episode_basic") \
                            or scraper_tv_nfo.get("episode_credits"):
                        seasoninfo = self.media.get_tmdb_tv_season_detail(tmdbid=media.tmdb_id,
                                                                          season=int(media.get_season_seq()))
                        if scraper_tv_nfo.get("episode_basic") or scraper_tv_nfo.get("episode_credits"):
                            self.gen_tv_episode_nfo_file(tmdbinfo=seasoninfo,
                                                         scraper_tv_nfo=scraper_tv_nfo,
                                                         season=int(media.get_season_seq()),
                                                         episode=int(media.get_episode_seq()),
                                                         out_path=dir_path,
                                                         file_name=file_name)
                        # 處理季
                        if not os.path.exists(os.path.join(dir_path, "season.nfo")):
                            # season nfo
                            if scraper_tv_nfo.get("season_basic"):
                                self.gen_tv_season_nfo_file(seasoninfo, int(media.get_season_seq()), dir_path)
                            # season poster
                            if scraper_tv_pic.get("season_poster"):
                                seasonposter = media.fanart.get_seasonposter(media_type=media.type,
                                                                             queryid=media.tvdb_id,
                                                                             season=media.get_season_seq())
                                if seasonposter:
                                    self.__save_image(seasonposter,
                                                      os.path.dirname(dir_path),
                                                      "season%s-poster" % media.get_season_seq().rjust(2, '0'))
                                else:
                                    self.__save_image(TMDB_IMAGE_W500_URL % seasoninfo.get("poster_path"),
                                                      os.path.dirname(dir_path),
                                                      "season%s-poster" % media.get_season_seq().rjust(2, '0'))
                            # season banner
                            if scraper_tv_pic.get("season_banner"):
                                seasonbanner = media.fanart.get_seasonbanner(media_type=media.type,
                                                                             queryid=media.tvdb_id,
                                                                             season=media.get_season_seq())
                                if seasonbanner:
                                    self.__save_image(seasonbanner,
                                                      os.path.dirname(dir_path),
                                                      "season%s-banner" % media.get_season_seq().rjust(2, '0'))
                            # season thumb
                            if scraper_tv_pic.get("season_thumb"):
                                seasonthumb = media.fanart.get_seasonthumb(media_type=media.type,
                                                                           queryid=media.tvdb_id,
                                                                           season=media.get_season_seq())
                                if seasonthumb:
                                    self.__save_image(seasonthumb,
                                                      os.path.dirname(dir_path),
                                                      "season%s-landscape" % media.get_season_seq().rjust(2, '0'))

        except Exception as e:
            ExceptionUtils.exception_traceback(e)

    def __gen_people_chinese_info(self, directors, actors, doubaninfo):
        """
        匹配豆瓣演職人員中文名
        """
        if doubaninfo:
            directors_douban = doubaninfo.get("directors") or []
            actors_douban = doubaninfo.get("actors") or []
            # douban英文名姓和名分開匹配，（豆瓣中名前姓後，TMDB中不確定）
            for director_douban in directors_douban:
                if director_douban["latin_name"]:
                    director_douban["latin_name"] = director_douban.get("latin_name", "").lower().split(" ")
                else:
                    director_douban["latin_name"] = director_douban.get("name", "").lower().split(" ")
            for actor_douban in actors_douban:
                if actor_douban["latin_name"]:
                    actor_douban["latin_name"] = actor_douban.get("latin_name", "").lower().split(" ")
                else:
                    actor_douban["latin_name"] = actor_douban.get("name", "").lower().split(" ")
            # 導演
            if directors:
                for director in directors:
                    director_douban = self.__match_people_in_douban(director, directors_douban)
                    if director_douban:
                        director["name"] = director_douban.get("name")
                    else:
                        log.info("【Scraper】豆瓣該影片或劇集無導演 %s 資訊" % director.get("name"))
            # 演員
            if actors:
                for actor in actors:
                    actor_douban = self.__match_people_in_douban(actor, actors_douban)
                    if actor_douban:
                        actor["name"] = actor_douban.get("name")
                        if actor_douban.get("character") != "演員":
                            actor["character"] = actor_douban.get("character")[2:]
                    else:
                        log.info("【Scraper】豆瓣該影片或劇集無演員 %s 資訊" % actor.get("name"))
        else:
            log.info("【Scraper】豆瓣無該影片或劇集資訊")
        return directors, actors

    def __match_people_in_douban(self, people, peoples_douban):
        """
        名字加又名構成匹配列表
        """
        people_aka_names = self.media.get_tmdbperson_aka_names(people.get("id")) or []
        people_aka_names.append(people.get("name"))
        for people_aka_name in people_aka_names:
            for people_douban in peoples_douban:
                latin_match_res = True
                #  姓和名分開匹配
                for latin_name in people_douban.get("latin_name"):
                    latin_match_res = latin_match_res and (latin_name in people_aka_name.lower())
                if latin_match_res or (people_douban.get("name") == people_aka_name):
                    return people_douban
        return None

    @staticmethod
    def __get_tmdbinfo_directors_actors(tmdbinfo):
        """
        查詢導演和演員
        :param tmdbinfo: TMDB後設資料
        :return: 導演列表，演員列表
        """
        if not tmdbinfo:
            return [], []
        directors = []
        actors = []
        casts = tmdbinfo.get("cast") or []
        for cast in casts:
            if not cast:
                continue
            if cast.get("known_for_department") == "Acting":
                actors.append(cast)
        crews = tmdbinfo.get("crew") or []
        for crew in crews:
            if not crew:
                continue
            if crew.get("job") == "Director":
                directors.append(crew)
        return directors, actors
