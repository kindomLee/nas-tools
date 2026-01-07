import argparse
import os
import random
import re
import shutil
import traceback
from enum import Enum
from threading import Lock
from time import sleep

import log
from app.helper import DbHelper
from app.helper import ThreadHelper
from app.media import Media, MetaInfo, Category, Scraper
from app.mediaserver import MediaServer
from app.message import Message
from app.subtitle import Subtitle
from app.utils import EpisodeFormat, PathUtils, StringUtils, SystemUtils
from app.utils.exception_utils import ExceptionUtils
from app.utils.types import MediaType, SyncType, RmtMode, RMT_MODES
from config import RMT_SUBEXT, RMT_MEDIAEXT, RMT_FAVTYPE, RMT_MIN_FILESIZE, DEFAULT_MOVIE_FORMAT, \
    DEFAULT_TV_FORMAT, Config

lock = Lock()


class FileTransfer:
    media = None
    message = None
    category = None
    mediaserver = None
    scraper = None
    threadhelper = None
    dbhelper = None

    _default_rmt_mode = None
    _movie_path = None
    _tv_path = None
    _anime_path = None
    _movie_category_flag = None
    _tv_category_flag = None
    _anime_category_flag = None
    _unknown_path = None
    _min_filesize = RMT_MIN_FILESIZE
    _filesize_cover = False
    _movie_dir_rmt_format = ""
    _movie_file_rmt_format = ""
    _tv_dir_rmt_format = ""
    _tv_season_rmt_format = ""
    _tv_file_rmt_format = ""
    _scraper_flag = False
    _scraper_nfo = {}
    _scraper_pic = {}
    _refresh_mediaserver = False
    _ignored_paths = []
    _ignored_files = ''

    def __init__(self):
        self.media = Media()
        self.message = Message()
        self.category = Category()
        self.mediaserver = MediaServer()
        self.scraper = Scraper()
        self.threadhelper = ThreadHelper()
        self.dbhelper = DbHelper()
        self.init_config()

    def init_config(self):
        media = Config().get_config('media')
        self._scraper_flag = media.get("nfo_poster")
        self._scraper_nfo = Config().get_config('scraper_nfo')
        self._scraper_pic = Config().get_config('scraper_pic')
        if media:
            # 重新整理媒體庫開關
            self._refresh_mediaserver = media.get("refresh_mediaserver")
            # 電影目錄
            self._movie_path = media.get('movie_path')
            if not isinstance(self._movie_path, list):
                if self._movie_path:
                    self._movie_path = [self._movie_path]
                else:
                    self._movie_path = []
            # 電影分類
            self._movie_category_flag = self.category.get_movie_category_flag()
            # 電視劇目錄
            self._tv_path = media.get('tv_path')
            if not isinstance(self._tv_path, list):
                if self._tv_path:
                    self._tv_path = [self._tv_path]
                else:
                    self._tv_path = []
            # 電視劇分類
            self._tv_category_flag = self.category.get_tv_category_flag()
            # 動漫目錄
            self._anime_path = media.get('anime_path')
            if not isinstance(self._anime_path, list):
                if self._anime_path:
                    self._anime_path = [self._anime_path]
                else:
                    self._anime_path = []
            # 動漫分類
            self._anime_category_flag = self.category.get_anime_category_flag()
            # 沒有動漫目漫切換為電視劇目錄和分類
            if not self._anime_path:
                self._anime_path = self._tv_path
                self._anime_category_flag = self._tv_category_flag
            # 未識別目錄
            self._unknown_path = media.get('unknown_path')
            if not isinstance(self._unknown_path, list):
                if self._unknown_path:
                    self._unknown_path = [self._unknown_path]
                else:
                    self._unknown_path = []
            # 最小檔案大小
            min_filesize = media.get('min_filesize')
            if isinstance(min_filesize, int):
                self._min_filesize = min_filesize * 1024 * 1024
            elif isinstance(min_filesize, str) and min_filesize.isdigit():
                self._min_filesize = int(min_filesize) * 1024 * 1024
            # 轉移資料夾黑名單
            ignored_paths = media.get('ignored_paths')
            if ignored_paths:
                self._ignored_paths = ignored_paths.split(';')
            # 檔案轉移忽略詞
            ignored_files = media.get('ignored_files')
            if ignored_files:
                self._ignored_files = re.compile(r'%s' % re.sub(r';', r'|', ignored_files))
            # 高質量檔案覆蓋
            self._filesize_cover = media.get('filesize_cover')
            # 電影重新命名格式
            movie_name_format = media.get('movie_name_format') or DEFAULT_MOVIE_FORMAT
            movie_formats = movie_name_format.rsplit('/', 1)
            if movie_formats:
                self._movie_dir_rmt_format = movie_formats[0]
                if len(movie_formats) > 1:
                    self._movie_file_rmt_format = movie_formats[-1]
            # 電視劇重新命名格式
            tv_name_format = media.get('tv_name_format') or DEFAULT_TV_FORMAT
            tv_formats = tv_name_format.rsplit('/', 2)
            if tv_formats:
                self._tv_dir_rmt_format = tv_formats[0]
                if len(tv_formats) > 2:
                    self._tv_season_rmt_format = tv_formats[-2]
                    self._tv_file_rmt_format = tv_formats[-1]
        self._default_rmt_mode = RMT_MODES.get(Config().get_config('pt').get('rmt_mode', 'copy'), RmtMode.COPY)

    @staticmethod
    def __transfer_command(file_item, target_file, rmt_mode):
        """
        使用系統命令處理單個檔案
        :param file_item: 檔案路徑
        :param target_file: 目標檔案路徑
        :param rmt_mode: RmtMode轉移方式
        """
        with lock:
            if rmt_mode == RmtMode.LINK:
                # 更連結
                retcode, retmsg = SystemUtils.link(file_item, target_file)
            elif rmt_mode == RmtMode.SOFTLINK:
                # 軟連結
                retcode, retmsg = SystemUtils.softlink(file_item, target_file)
            elif rmt_mode == RmtMode.MOVE:
                # 移動
                retcode, retmsg = SystemUtils.move(file_item, target_file)
            elif rmt_mode == RmtMode.RCLONE:
                # Rclone移動
                retcode, retmsg = SystemUtils.rclone_move(file_item, target_file)
            elif rmt_mode == RmtMode.RCLONECOPY:
                # Rclone複製
                retcode, retmsg = SystemUtils.rclone_copy(file_item, target_file)
            elif rmt_mode == RmtMode.MINIO:
                # Minio移動
                retcode, retmsg = SystemUtils.minio_move(file_item, target_file)
            elif rmt_mode == RmtMode.MINIOCOPY:
                # Minio複製
                retcode, retmsg = SystemUtils.minio_copy(file_item, target_file)
            else:
                # 複製
                retcode, retmsg = SystemUtils.copy(file_item, target_file)
        if retcode != 0:
            log.error("【Rmt】%s" % retmsg)
        return retcode

    def __transfer_subtitles(self, org_name, new_name, rmt_mode):
        """
        根據檔名轉移對應字幕檔案
        :param org_name: 原檔名
        :param new_name: 新檔名
        :param rmt_mode: RmtMode轉移方式
        """
        dir_name = os.path.dirname(org_name)
        file_name = os.path.basename(org_name)
        file_list = PathUtils.get_dir_level1_files(dir_name, RMT_SUBEXT)
        if len(file_list) == 0:
            log.debug("【Rmt】%s 目錄下沒有找到字幕檔案..." % dir_name)
        else:
            log.debug("【Rmt】字幕檔案清單：" + str(file_list))
            metainfo = MetaInfo(title=file_name)
            for file_item in file_list:
                sub_file_name = os.path.basename(file_item)
                sub_metainfo = MetaInfo(title=os.path.basename(file_item))
                if (os.path.splitext(file_name)[0] == os.path.splitext(sub_file_name)[0]) or \
                        (sub_metainfo.cn_name and sub_metainfo.cn_name == metainfo.cn_name) \
                        or (sub_metainfo.en_name and sub_metainfo.en_name == metainfo.en_name):
                    if metainfo.get_season_string() \
                            and metainfo.get_season_string() != sub_metainfo.get_season_string():
                        continue
                    if metainfo.get_episode_string() \
                            and metainfo.get_episode_string() != sub_metainfo.get_episode_string():
                        continue
                    new_file_type = ".未知語言"
                    # 相容jellyfin字幕識別(多重識別), emby則會識別最後一個字尾
                    if re.search(
                            r"([.\[(](((zh[-_])?(cn|ch[si]|sg|sc))|zho?"
                            r"|chinese|(cn|ch[si]|sg|zho?|eng)[-_&](cn|ch[si]|sg|zho?|eng)"
                            r"|簡[體中]?)[.\])])"
                            r"|([\u4e00-\u9fa5]{0,3}[中雙][\u4e00-\u9fa5]{0,2}[字文語][\u4e00-\u9fa5]{0,3})"
                            r"|簡體|簡中",
                            file_item, re.I):
                        new_file_type = ".chi.zh-cn"
                    elif re.search(r"([.\[(](((zh[-_])?(hk|tw|cht|tc))"
                                   r"|繁[體中]?)[.\])])"
                                   r"|繁體中[文字]|中[文字]繁體|繁體", file_item,
                                   re.I):
                        new_file_type = ".zh-tw"
                    elif re.search(r"[.\[(]eng[.\])]", file_item,
                                   re.I):
                        new_file_type = ".eng"
                    # 透過對比字幕檔案大小  儘量轉移所有存在的字幕
                    file_ext = os.path.splitext(file_item)[-1]
                    new_sub_tag_dict = {
                        ".eng": ".英文",
                        ".chi.zh-cn": ".簡體中文",
                        ".zh-tw": ".繁體中文"
                    }
                    new_sub_tag_list = [new_file_type if t == 0 else "%s%s(%s)" % (
                        new_file_type, new_sub_tag_dict.get(new_file_type, ""), t) for t in range(6)]
                    for new_sub_tag in new_sub_tag_list:
                        new_file = os.path.splitext(new_name)[0] + new_sub_tag + file_ext
                        # 如果字幕檔案不存在, 直接轉移字幕, 並跳出迴圈
                        try:
                            if not os.path.exists(new_file):
                                log.debug("【Rmt】正在處理字幕：%s" % os.path.basename(file_item))
                                retcode = self.__transfer_command(file_item=file_item,
                                                                  target_file=new_file,
                                                                  rmt_mode=rmt_mode)
                                if retcode == 0:
                                    log.info("【Rmt】字幕 %s %s完成" % (os.path.basename(file_item), rmt_mode.value))
                                    break
                                else:
                                    log.error(
                                        "【Rmt】字幕 %s %s失敗，錯誤碼 %s" % (file_name, rmt_mode.value, str(retcode)))
                                    return retcode
                            # 如果字幕檔案的大小與已存在檔案相同, 說明已經轉移過了, 則跳出迴圈
                            elif os.path.getsize(new_file) == os.path.getsize(file_item):
                                log.info("【Rmt】字幕 %s 已存在" % new_file)
                                break
                            # 否則 迴圈繼續 > 透過new_sub_tag_list 獲取新的tag附加到字幕檔名, 繼續檢查是否能轉移
                        except OSError as reason:
                            log.info("【Rmt】字幕 %s 出錯了,原因: %s" % (new_file, str(reason)))
        return 0

    def __transfer_bluray_dir(self, file_path, new_path, rmt_mode):
        """
        轉移藍光資料夾
        :param file_path: 原路徑
        :param new_path: 新路徑
        :param rmt_mode: RmtMode轉移方式
        """
        log.info("【Rmt】正在%s目錄：%s 到 %s" % (rmt_mode.value, file_path, new_path))
        # 複製
        retcode = self.__transfer_dir_files(src_dir=file_path,
                                            target_dir=new_path,
                                            rmt_mode=rmt_mode,
                                            bludir=True)
        if retcode == 0:
            log.info("【Rmt】檔案 %s %s完成" % (file_path, rmt_mode.value))
        else:
            log.error("【Rmt】檔案%s %s失敗，錯誤碼 %s" % (file_path, rmt_mode.value, str(retcode)))
        return retcode

    def is_target_dir_path(self, path):
        """
        判斷是否為目的路徑下的路徑
        :param path: 路徑
        :return: True/False
        """
        if not path:
            return False
        for tv_path in self._tv_path:
            if PathUtils.is_path_in_path(tv_path, path):
                return True
        for movie_path in self._movie_path:
            if PathUtils.is_path_in_path(movie_path, path):
                return True
        for anime_path in self._anime_path:
            if PathUtils.is_path_in_path(anime_path, path):
                return True
        for unknown_path in self._unknown_path:
            if PathUtils.is_path_in_path(unknown_path, path):
                return True
        return False

    def __transfer_dir_files(self, src_dir, target_dir, rmt_mode, bludir=False):
        """
        按目錄結構轉移所有檔案
        :param src_dir: 原路徑
        :param target_dir: 新路徑
        :param rmt_mode: RmtMode轉移方式
        :param bludir: 是否藍光目錄
        """
        file_list = PathUtils.get_dir_files(src_dir)
        retcode = 0
        for file in file_list:
            new_file = file.replace(src_dir, target_dir)
            if os.path.exists(new_file):
                log.warn("【Rmt】%s 檔案已存在" % new_file)
                continue
            new_dir = os.path.dirname(new_file)
            if not os.path.exists(new_dir):
                os.makedirs(new_dir)
            retcode = self.__transfer_command(file_item=file,
                                              target_file=new_file,
                                              rmt_mode=rmt_mode)
            if retcode != 0:
                break
            else:
                if not bludir:
                    self.dbhelper.insert_transfer_blacklist(file)
        if retcode == 0 and bludir:
            self.dbhelper.insert_transfer_blacklist(src_dir)
        return retcode

    def __transfer_origin_file(self, file_item, target_dir, rmt_mode):
        """
        按原檔名link檔案到目的目錄
        :param file_item: 原檔案路徑
        :param target_dir: 目的目錄
        :param rmt_mode: RmtMode轉移方式
        """
        if not file_item or not target_dir:
            return -1
        if not os.path.exists(file_item):
            log.warn("【Rmt】%s 不存在" % file_item)
            return -1
        # 計算目錄目錄
        parent_name = os.path.basename(os.path.dirname(file_item))
        target_dir = os.path.join(target_dir, parent_name)
        if not os.path.exists(target_dir):
            log.debug("【Rmt】正在建立目錄：%s" % target_dir)
            os.makedirs(target_dir)
        # 目錄
        if os.path.isdir(file_item):
            log.info("【Rmt】正在%s目錄：%s 到 %s" % (rmt_mode.value, file_item, target_dir))
            retcode = self.__transfer_dir_files(src_dir=file_item,
                                                target_dir=target_dir,
                                                rmt_mode=rmt_mode)
        # 檔案
        else:
            target_file = os.path.join(target_dir, os.path.basename(file_item))
            if os.path.exists(target_file):
                log.warn("【Rmt】%s 檔案已存在" % target_file)
                return 0
            retcode = self.__transfer_command(file_item=file_item,
                                              target_file=target_file,
                                              rmt_mode=rmt_mode)
            if retcode == 0:
                self.dbhelper.insert_transfer_blacklist(file_item)
        if retcode == 0:
            log.info("【Rmt】%s %s到unknown完成" % (file_item, rmt_mode.value))
        else:
            log.error("【Rmt】%s %s到unknown失敗，錯誤碼 %s" % (file_item, rmt_mode.value, retcode))
        return retcode

    def __transfer_file(self, file_item, new_file, rmt_mode, over_flag=False):
        """
        轉移一個檔案，同時處理字幕
        :param file_item: 原檔案路徑
        :param new_file: 新檔案路徑
        :param rmt_mode: RmtMode轉移方式
        :param over_flag: 是否覆蓋，為True時會先刪除再轉移
        """
        file_name = os.path.basename(file_item)
        if not over_flag and os.path.exists(new_file):
            log.warn("【Rmt】檔案已存在：%s" % new_file)
            return 0
        if over_flag and os.path.isfile(new_file):
            log.info("【Rmt】正在刪除已存在的檔案：%s" % new_file)
            os.remove(new_file)
        log.info("【Rmt】正在轉移檔案：%s 到 %s" % (file_name, new_file))
        retcode = self.__transfer_command(file_item=file_item,
                                          target_file=new_file,
                                          rmt_mode=rmt_mode)
        if retcode == 0:
            log.info("【Rmt】檔案 %s %s完成" % (file_name, rmt_mode.value))
            self.dbhelper.insert_transfer_blacklist(file_item)
        else:
            log.error("【Rmt】檔案 %s %s失敗，錯誤碼 %s" % (file_name, rmt_mode.value, str(retcode)))
            return retcode
        # 處理字幕
        return self.__transfer_subtitles(org_name=file_item,
                                         new_name=new_file,
                                         rmt_mode=rmt_mode)

    def transfer_media(self,
                       in_from: Enum,
                       in_path,
                       rmt_mode: RmtMode = None,
                       files: list = None,
                       target_dir=None,
                       unknown_dir=None,
                       tmdb_info=None,
                       media_type: MediaType = None,
                       season=None,
                       episode: (EpisodeFormat, bool) = None,
                       min_filesize=None,
                       udf_flag=False):
        """
        識別並轉移一個檔案、多個檔案或者目錄
        :param in_from: 來源，即呼叫該功能的渠道
        :param in_path: 轉移的路徑，可能是一個檔案也可以是一個目錄
        :param files: 檔案清單，非空時以該檔案清單為準，為空時從in_path中按字尾和大小限制檢索需要處理的檔案清單
        :param target_dir: 目的資料夾，非空的轉移到該資料夾，為空時則按型別轉移到配置檔案中的媒體庫資料夾
        :param unknown_dir: 未識別資料夾，非空時未識別的媒體檔案轉移到該資料夾，為空時則使用配置檔案中的未識別資料夾
        :param rmt_mode: 檔案轉移方式
        :param tmdb_info: 手動識別轉移時傳入的TMDB資訊物件，如未輸入，則按名稱筆TMDB實時查詢
        :param media_type: 手動識別轉移時傳入的檔案型別，如未輸入，則自動識別
        :param season: 手動識別目錄或檔案時傳入的的字號，如未輸入，則自動識別
        :param episode: (EpisodeFormat，是否批處理匹配)
        :param min_filesize: 過濾小檔案大小的上限值
        :param udf_flag: 自定義轉移標誌，為True時代表是自定義轉移，此時很多處理不一樣
        :return: 處理狀態，錯誤資訊
        """
        episode = (None, False) if not episode else episode
        if not in_path:
            log.error("【Rmt】輸入路徑錯誤!")
            return False, "輸入路徑錯誤"

        if not rmt_mode:
            rmt_mode = self._default_rmt_mode

        log.info("【Rmt】開始處理：%s，轉移方式：%s" % (in_path, rmt_mode.value))

        success_flag = True
        error_message = ""
        bluray_disk_dir = None
        if not files:
            # 如果傳入的是個目錄
            if os.path.isdir(in_path):
                if not os.path.exists(in_path):
                    log.error("【Rmt】檔案轉移失敗，目錄不存在 %s" % in_path)
                    return False, "目錄不存在"
                # 回收站及隱藏的檔案不處理
                if PathUtils.is_invalid_path(in_path):
                    return False, "回收站或者隱藏資料夾"
                # 判斷是不是原盤資料夾
                bluray_disk_dir = PathUtils.get_bluray_dir(in_path)
                if bluray_disk_dir:
                    file_list = [bluray_disk_dir]
                    log.info("【Rmt】當前為藍光原盤資料夾：%s" % str(in_path))
                else:
                    if udf_flag:
                        # 自定義轉移時未輸入大小限制預設不限制
                        now_filesize = 0 if not str(min_filesize).isdigit() else int(
                            min_filesize) * 1024 * 1024
                    else:
                        # 未輸入大小限制預設為配置大小限制
                        now_filesize = self._min_filesize if not str(min_filesize).isdigit() else int(
                            min_filesize) * 1024 * 1024
                    # 查詢目錄下的檔案
                    file_list = PathUtils.get_dir_files(in_path=in_path,
                                                        episode_format=episode[0],
                                                        exts=RMT_MEDIAEXT,
                                                        filesize=now_filesize)
                    log.debug("【Rmt】檔案清單：" + str(file_list))
                    if len(file_list) == 0:
                        log.warn(
                            "【Rmt】%s 目錄下未找到媒體檔案，當前最小檔案大小限制為 %s" % (
                                in_path, StringUtils.str_filesize(now_filesize)))
                        return False, "目錄下未找到媒體檔案，當前最小檔案大小限制為 %s" % StringUtils.str_filesize(
                            now_filesize)
            # 傳入的是個檔案
            else:
                if not os.path.exists(in_path):
                    log.error("【Rmt】檔案轉移失敗，檔案不存在：%s" % in_path)
                    return False, "檔案不存在"
                if os.path.splitext(in_path)[-1].lower() not in RMT_MEDIAEXT:
                    log.warn("【Rmt】不支援的媒體檔案格式，不處理：%s" % in_path)
                    return False, "不支援的媒體檔案格式"
                # 判斷是不是原盤資料夾
                bluray_disk_dir = PathUtils.get_bluray_dir(in_path)
                if bluray_disk_dir:
                    file_list = [bluray_disk_dir]
                    log.info("【Rmt】當前為藍光原盤資料夾：%s" % bluray_disk_dir)
                else:
                    file_list = [in_path]
        else:
            # 傳入的是個檔案列表，這些文失件是in_path下面的檔案
            file_list = files

        #  過濾掉檔案列表
        file_list, msg = self.check_ignore(file_list=file_list)
        if not file_list:
            return True, msg

        # 目錄同步模式下，過濾掉檔案列表中已處理過的
        if in_from == SyncType.MON:
            file_list = list(filter(self.dbhelper.is_transfer_notin_blacklist, file_list))
            if not file_list:
                log.info("【Rmt】所有檔案均已成功轉移過，沒有需要處理的檔案！如需重新處理，請清理快取（服務->清理轉移快取）")
                return True, "沒有新檔案需要處理"
        # API檢索出媒體資訊，傳入一個檔案列表，得出每一個檔案的名稱，這裡是當前目錄下所有的檔案了
        Medias = self.media.get_media_info_on_files(file_list, tmdb_info, media_type, season, episode[0])
        if not Medias:
            log.error("【Rmt】檢索媒體資訊出錯！")
            return False, "檢索媒體資訊出錯"

        # 統計總的檔案數、失敗檔案數、需要提醒的失敗數
        failed_count = 0
        alert_count = 0
        alert_messages = []
        total_count = 0
        # 電視劇可能有多集，如果在迴圈裡發訊息就太多了，要在外面發訊息
        message_medias = {}
        # 需要重新整理媒體庫的清單
        refresh_library_items = []
        # 需要下載欄位的清單
        download_subtitle_items = []
        # 處理識別後的每一個檔案或單個資料夾
        for file_item, media in Medias.items():
            try:
                if not udf_flag:
                    if re.search(r'[./\s\[]+Sample[/.\s\]]+', file_item, re.IGNORECASE):
                        log.warn("【Rmt】%s 可能是預告片，跳過..." % file_item)
                        continue
                # 總數量
                total_count = total_count + 1
                # 檔名
                file_name = os.path.basename(file_item)

                # 資料庫記錄的路徑
                if bluray_disk_dir:
                    reg_path = bluray_disk_dir
                else:
                    reg_path = file_item
                # 未識別
                if not media or not media.tmdb_info or not media.get_title_string():
                    log.warn("【Rmt】%s 無法識別媒體資訊！" % file_name)
                    success_flag = False
                    error_message = "無法識別媒體資訊"
                    if udf_flag:
                        return success_flag, error_message
                    # 記錄未識別
                    self.dbhelper.insert_transfer_unknown(reg_path, target_dir)
                    failed_count += 1
                    alert_count += 1
                    if error_message not in alert_messages:
                        alert_messages.append(error_message)
                    # 原樣轉移過去
                    if unknown_dir:
                        log.warn("【Rmt】%s 按原檔名轉移到unknown目錄：%s" % (file_name, unknown_dir))
                        self.__transfer_origin_file(file_item=file_item, target_dir=unknown_dir, rmt_mode=rmt_mode)
                    elif self._unknown_path:
                        unknown_path = self.__get_best_unknown_path(in_path)
                        if not unknown_path:
                            continue
                        log.warn("【Rmt】%s 按原檔名轉移到unknown目錄：%s" % (file_name, unknown_path))
                        self.__transfer_origin_file(file_item=file_item, target_dir=unknown_path, rmt_mode=rmt_mode)
                    else:
                        log.error("【Rmt】%s 無法識別媒體資訊！" % file_name)
                    continue
                # 當前檔案大小
                media.size = os.path.getsize(file_item)
                # 目的目錄，有輸入target_dir時，往這個目錄放
                if target_dir:
                    dist_path = target_dir
                else:
                    dist_path = self.__get_best_target_path(mtype=media.type, in_path=in_path, size=media.size)
                if not dist_path:
                    log.error("【Rmt】檔案轉移失敗，目的路徑不存在！")
                    success_flag = False
                    error_message = "目的路徑不存在"
                    failed_count += 1
                    alert_count += 1
                    if error_message not in alert_messages:
                        alert_messages.append(error_message)
                    continue
                if dist_path and not os.path.exists(dist_path):
                    return False, "目錄不存在：%s" % dist_path

                # 判斷檔案是否已存在，返回：目錄存在標誌、目錄名、檔案存在標誌、檔名
                dir_exist_flag, ret_dir_path, file_exist_flag, ret_file_path = self.__is_media_exists(dist_path, media)
                # 新檔案字尾
                file_ext = os.path.splitext(file_item)[-1]
                new_file = ret_file_path
                # 已存在的檔案數量
                exist_filenum = 0
                handler_flag = False
                # 路徑存在
                if dir_exist_flag:
                    # 藍光原盤
                    if bluray_disk_dir:
                        log.warn("【Rmt】藍光原盤目錄已存在：%s" % ret_dir_path)
                        if udf_flag:
                            return False, "藍光原盤目錄已存在：%s" % ret_dir_path
                        failed_count += 1
                        continue
                    # 檔案存在
                    if file_exist_flag:
                        exist_filenum = exist_filenum + 1
                        if rmt_mode != RmtMode.SOFTLINK:
                            if media.size > os.path.getsize(ret_file_path) and self._filesize_cover or udf_flag:
                                ret_file_path = os.path.splitext(ret_file_path)[0]
                                new_file = "%s%s" % (ret_file_path, file_ext)
                                log.info("【Rmt】檔案 %s 已存在，覆蓋..." % new_file)
                                ret = self.__transfer_file(file_item=file_item,
                                                           new_file=new_file,
                                                           rmt_mode=rmt_mode,
                                                           over_flag=True)
                                if ret != 0:
                                    success_flag = False
                                    error_message = "檔案轉移失敗，錯誤碼 %s" % ret
                                    if udf_flag:
                                        return success_flag, error_message
                                    failed_count += 1
                                    alert_count += 1
                                    if error_message not in alert_messages:
                                        alert_messages.append(error_message)
                                    continue
                                handler_flag = True
                            else:
                                log.warn("【Rmt】檔案 %s 已存在" % ret_file_path)
                                failed_count += 1
                                continue
                        else:
                            log.warn("【Rmt】檔案 %s 已存在" % ret_file_path)
                            failed_count += 1
                            continue
                # 路徑不存在
                else:
                    if not ret_dir_path:
                        log.error("【Rmt】拼裝目錄路徑錯誤，無法從檔名中識別出季集資訊：%s" % file_item)
                        success_flag = False
                        error_message = "識別失敗，無法從檔名中識別出季集資訊"
                        if udf_flag:
                            return success_flag, error_message
                        # 記錄未識別
                        self.dbhelper.insert_transfer_unknown(reg_path, target_dir)
                        failed_count += 1
                        alert_count += 1
                        if error_message not in alert_messages:
                            alert_messages.append(error_message)
                        continue
                    else:
                        # 建立電錄
                        log.debug("【Rmt】正在建立目錄：%s" % ret_dir_path)
                        os.makedirs(ret_dir_path)
                # 轉移藍光原盤
                if bluray_disk_dir:
                    ret = self.__transfer_bluray_dir(file_item, ret_dir_path, rmt_mode)
                    if ret != 0:
                        success_flag = False
                        error_message = "藍光目錄轉移失敗，錯誤碼：%s" % ret
                        if udf_flag:
                            return success_flag, error_message
                        failed_count += 1
                        alert_count += 1
                        if error_message not in alert_messages:
                            alert_messages.append(error_message)
                        continue
                else:
                    # 開始轉移檔案
                    if not handler_flag:
                        if not ret_file_path:
                            log.error("【Rmt】拼裝檔案路徑錯誤，無法從檔名中識別出集數：%s" % file_item)
                            success_flag = False
                            error_message = "識別失敗，無法從檔名中識別出集數"
                            if udf_flag:
                                return success_flag, error_message
                            # 記錄未識別
                            self.dbhelper.insert_transfer_unknown(reg_path, target_dir)
                            failed_count += 1
                            alert_count += 1
                            if error_message not in alert_messages:
                                alert_messages.append(error_message)
                            continue
                        new_file = "%s%s" % (ret_file_path, file_ext)
                        ret = self.__transfer_file(file_item=file_item,
                                                   new_file=new_file,
                                                   rmt_mode=rmt_mode,
                                                   over_flag=False)
                        if ret != 0:
                            success_flag = False
                            error_message = "檔案轉移失敗，錯誤碼 %s" % ret
                            if udf_flag:
                                return success_flag, error_message
                            failed_count += 1
                            alert_count += 1
                            if error_message not in alert_messages:
                                alert_messages.append(error_message)
                            continue
                # 媒體庫重新整理條目：型別-類別-標題-年份
                refresh_item = {"type": media.type, "category": media.category, "title": media.title,
                                "year": media.year, "target_path": dist_path}
                # 登記媒體庫重新整理
                if refresh_item not in refresh_library_items:
                    refresh_library_items.append(refresh_item)
                # 查詢TMDB詳情，需要全部資料
                media.set_tmdb_info(self.media.get_tmdb_info(mtype=media.type,
                                                             tmdbid=media.tmdb_id,
                                                             append_to_response="all"))
                # 下載字幕條目
                subtitle_item = {"type": media.type,
                                 "file": ret_file_path,
                                 "file_ext": os.path.splitext(file_item)[-1],
                                 "name": media.en_name if media.en_name else media.cn_name,
                                 "title": media.title,
                                 "year": media.year,
                                 "season": media.begin_season,
                                 "episode": media.begin_episode,
                                 "bluray": True if bluray_disk_dir else False,
                                 "imdbid": media.imdb_id}
                # 登記字幕下載
                if subtitle_item not in download_subtitle_items:
                    download_subtitle_items.append(subtitle_item)
                # 轉移歷史記錄
                self.dbhelper.insert_transfer_history(
                    in_from=in_from,
                    rmt_mode=rmt_mode,
                    in_path=reg_path,
                    out_path=new_file if not bluray_disk_dir else None,
                    dest=dist_path,
                    media_info=media)
                # 未識別手動識別或歷史記錄重新識別的批處理模式
                if isinstance(episode[1], bool) and episode[1]:
                    # 未識別手動識別，更改未識別記錄為已處理
                    self.dbhelper.update_transfer_unknown_state(file_item)
                # 電影立即傳送訊息
                if media.type == MediaType.MOVIE:
                    self.message.send_transfer_movie_message(in_from,
                                                             media,
                                                             exist_filenum,
                                                             self._movie_category_flag)
                # 否則登記彙總發訊息
                else:
                    # 按季彙總
                    message_key = "%s-%s" % (media.get_title_string(), media.get_season_string())
                    if not message_medias.get(message_key):
                        message_medias[message_key] = media
                    # 彙總集數、大小
                    if not message_medias[message_key].is_in_episode(media.get_episode_list()):
                        message_medias[message_key].total_episodes += media.total_episodes
                        message_medias[message_key].size += media.size
                # 生成nfo及poster
                if self._scraper_flag:
                    # 生成刮削檔案
                    self.scraper.gen_scraper_files(media=media,
                                                   scraper_nfo=self._scraper_nfo,
                                                   scraper_pic=self._scraper_pic,
                                                   dir_path=ret_dir_path,
                                                   file_name=os.path.basename(ret_file_path))
                # 移動模式隨機休眠（相容一些網盤掛載目錄）
                if rmt_mode == RmtMode.MOVE:
                    sleep(round(random.uniform(0, 1), 1))

            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error("【Rmt】檔案轉移時發生錯誤：%s - %s" % (str(err), traceback.format_exc()))
        # 迴圈結束
        # 統計完成情況，傳送通知
        if message_medias:
            self.message.send_transfer_tv_message(message_medias, in_from)
        # 重新整理媒體庫
        if refresh_library_items and self._refresh_mediaserver:
            self.mediaserver.refresh_library_by_items(refresh_library_items)
        # 啟新程序下載字幕
        if download_subtitle_items:
            self.threadhelper.start_thread(Subtitle().download_subtitle, (download_subtitle_items,))
        # 總結
        log.info("【Rmt】%s 處理完成，總數：%s，失敗：%s" % (in_path, total_count, failed_count))
        if alert_count > 0:
            self.message.send_transfer_fail_message(in_path, alert_count, "、".join(alert_messages))
        elif failed_count == 0:
            # 刪除空目錄
            if rmt_mode == RmtMode.MOVE \
                    and os.path.exists(in_path) \
                    and os.path.isdir(in_path) \
                    and not PathUtils.get_dir_files(in_path=in_path, exts=RMT_MEDIAEXT) \
                    and not PathUtils.get_dir_files(in_path=in_path, exts=['.!qb', '.part']):
                log.info("【Rmt】目錄下已無媒體檔案及正在下載的檔案，移動模式下刪除目錄：%s" % in_path)
                shutil.rmtree(in_path)
        return success_flag, error_message

    def transfer_manually(self, s_path, t_path, mode):
        """
        全量轉移，用於使用命令呼叫
        :param s_path: 源目錄
        :param t_path: 目的目錄
        :param mode: 轉移方式
        """
        if not s_path:
            return
        if not os.path.exists(s_path):
            print("【Rmt】源目錄不存在：%s" % s_path)
            return
        if t_path:
            if not os.path.exists(t_path):
                print("【Rmt】目的目錄不存在：%s" % t_path)
                return
        rmt_mode = RMT_MODES.get(mode)
        if not rmt_mode:
            print("【Rmt】轉移模式錯誤！")
            return
        print("【Rmt】轉移模式為：%s" % rmt_mode.value)
        print("【Rmt】正在轉移以下目錄中的全量檔案：%s" % s_path)
        for path in PathUtils.get_dir_level1_medias(s_path, RMT_MEDIAEXT):
            if PathUtils.is_invalid_path(path):
                continue
            ret, ret_msg = self.transfer_media(in_from=SyncType.MAN,
                                               in_path=path,
                                               target_dir=t_path,
                                               rmt_mode=rmt_mode)
            if not ret:
                print("【Rmt】%s 處理失敗：%s" % (path, ret_msg))

    def __is_media_exists(self,
                          media_dest,
                          media):
        """
        判斷媒體檔案是否憶存在
        :param media_dest: 媒體檔案所在目錄
        :param media: 已識別的媒體資訊
        :return: 目錄是否存在，目錄路徑，檔案是否存在，檔案路徑
        """
        # 返回變數
        dir_exist_flag = False
        file_exist_flag = False
        ret_dir_path = None
        ret_file_path = None
        # 電影
        if media.type == MediaType.MOVIE:
            # 目錄名稱
            dir_name, file_name = self.get_moive_dest_path(media)
            # 預設目錄路徑
            file_path = os.path.join(media_dest, dir_name)
            # 開啟分類時目錄路徑
            if self._movie_category_flag:
                file_path = os.path.join(media_dest, media.category, dir_name)
                for m_type in [RMT_FAVTYPE, media.category]:
                    type_path = os.path.join(media_dest, m_type, dir_name)
                    # 目錄是否存在
                    if os.path.exists(type_path):
                        file_path = type_path
                        break
            # 返回路徑
            ret_dir_path = file_path
            # 路徑存在標誌
            if os.path.exists(file_path):
                dir_exist_flag = True
            # 檔案路徑
            file_dest = os.path.join(file_path, file_name)
            # 返回檔案路徑
            ret_file_path = file_dest
            # 檔案是否存在
            for ext in RMT_MEDIAEXT:
                ext_dest = "%s%s" % (file_dest, ext)
                if os.path.exists(ext_dest):
                    file_exist_flag = True
                    ret_file_path = ext_dest
                    break
        # 電視劇或者動漫
        else:
            # 目錄名稱
            dir_name, season_name, file_name = self.get_tv_dest_path(media)
            # 劇集目錄
            if (media.type == MediaType.TV and self._tv_category_flag) or (
                    media.type == MediaType.ANIME and self._anime_category_flag):
                media_path = os.path.join(media_dest, media.category, dir_name)
            else:
                media_path = os.path.join(media_dest, dir_name)
            # 季
            if media.get_season_list():
                # 季路徑
                season_dir = os.path.join(media_path, season_name)
                # 返回目錄路徑
                ret_dir_path = season_dir
                # 目錄是否存在
                if os.path.exists(season_dir):
                    dir_exist_flag = True
                # 處理集
                episodes = media.get_episode_list()
                if episodes:
                    # 集檔案路徑
                    file_path = os.path.join(season_dir, file_name)
                    # 返回檔案路徑
                    ret_file_path = file_path
                    # 檔案存在標誌
                    for ext in RMT_MEDIAEXT:
                        ext_dest = "%s%s" % (file_path, ext)
                        if os.path.exists(ext_dest):
                            file_exist_flag = True
                            ret_file_path = ext_dest
                            break
        return dir_exist_flag, ret_dir_path, file_exist_flag, ret_file_path

    def transfer_embyfav(self, item_path):
        """
        Emby/Jellyfin點紅星後轉移電影檔案到精選分類
        :param item_path: 檔案路徑
        """
        if not item_path:
            return False
        if not self._movie_category_flag or not self._movie_path:
            return False
        if os.path.isdir(item_path):
            movie_dir = item_path
        else:
            movie_dir = os.path.dirname(item_path)
        # 已經是精選下的不處理
        movie_type = os.path.basename(os.path.dirname(movie_dir))
        if movie_type == RMT_FAVTYPE \
                or movie_type not in self.category.get_movie_categorys():
            return False
        movie_name = os.path.basename(movie_dir)
        movie_path = self.__get_best_target_path(mtype=MediaType.MOVIE, in_path=movie_dir)
        # 開始轉移檔案，轉移到同目錄下的精選目錄
        org_path = os.path.join(movie_path, movie_type, movie_name)
        new_path = os.path.join(movie_path, RMT_FAVTYPE, movie_name)
        if os.path.exists(org_path):
            log.info("【Rmt】開始轉移檔案 %s 到 %s ..." % (org_path, new_path))
            if os.path.exists(new_path):
                log.info("【Rmt】目錄 %s 已存在" % new_path)
                return False
            ret, retmsg = SystemUtils.move(org_path, new_path)
            if ret == 0:
                return True
            else:
                log.error("【Rmt】%s" % retmsg)
        else:
            log.error("【Rmt】%s 目錄不存在" % org_path)
        return False

    def get_dest_path_by_info(self, dest, meta_info):
        """
        拼裝轉移重新命名後的新檔案地址
        :param dest: 目的目錄
        :param meta_info: 媒體資訊
        """
        if not dest or not meta_info:
            return None
        if meta_info.type == MediaType.MOVIE:
            dir_name, _ = self.get_moive_dest_path(meta_info)
            if self._movie_category_flag:
                return os.path.join(dest, meta_info.category, dir_name)
            else:
                return os.path.join(dest, dir_name)
        else:
            dir_name, season_name, _ = self.get_tv_dest_path(meta_info)
            if self._tv_category_flag:
                return os.path.join(dest, meta_info.category, dir_name, season_name)
            else:
                return os.path.join(dest, dir_name, season_name)

    def get_no_exists_medias(self, meta_info, season=None, total_num=None):
        """
        根據媒體庫目錄結構，判斷媒體是否存在
        :param meta_info: 已識別的媒體資訊
        :param season: 季號，數字，劇集時需要
        :param total_num: 該季總集數，劇集時需要
        :return: 如果是電影返回已存在的電影清單：title、year，如果是劇集，則返回不存在的集的清單
        """
        # 電影
        if meta_info.type == MediaType.MOVIE:
            dir_name, _ = self.get_moive_dest_path(meta_info)
            for dest_path in self._movie_path:
                # 判斷精選
                fav_path = os.path.join(dest_path, RMT_FAVTYPE, dir_name)
                fav_files = PathUtils.get_dir_files(fav_path, RMT_MEDIAEXT)
                # 其它分類
                if self._movie_category_flag:
                    dest_path = os.path.join(dest_path, meta_info.category, dir_name)
                else:
                    dest_path = os.path.join(dest_path, dir_name)
                files = PathUtils.get_dir_files(dest_path, RMT_MEDIAEXT)
                if len(files) > 0 or len(fav_files) > 0:
                    return [{'title': meta_info.title, 'year': meta_info.year}]
            return []
        # 電視劇
        else:
            dir_name, season_name, _ = self.get_tv_dest_path(meta_info)
            if not season or not total_num:
                return []
            if meta_info.type == MediaType.ANIME:
                dest_paths = self._anime_path
                category_flag = self._anime_category_flag
            else:
                dest_paths = self._tv_path
                category_flag = self._tv_category_flag
            # 總需要的集
            total_episodes = [episode for episode in range(1, total_num + 1)]
            # 已存在的集
            exists_episodes = []
            for dest_path in dest_paths:
                if category_flag:
                    dest_path = os.path.join(dest_path, meta_info.category, dir_name, season_name)
                else:
                    dest_path = os.path.join(dest_path, dir_name, season_name)
                # 目錄不存在
                if not os.path.exists(dest_path):
                    continue
                files = PathUtils.get_dir_files(dest_path, RMT_MEDIAEXT)
                for file in files:
                    file_meta_info = MetaInfo(os.path.basename(file))
                    if not file_meta_info.get_season_list() or not file_meta_info.get_episode_list():
                        continue
                    if file_meta_info.get_name() != meta_info.title:
                        continue
                    if not file_meta_info.is_in_season(season):
                        continue
                    exists_episodes = list(set(exists_episodes).union(set(file_meta_info.get_episode_list())))
            return list(set(total_episodes).difference(set(exists_episodes)))

    def __get_best_target_path(self, mtype, in_path=None, size=0):
        """
        查詢一個最好的目錄返回，有in_path時找與in_path同路徑的，沒有in_path時，順序查詢1個符合大小要求的，沒有in_path和size時，返回第1個
        :param mtype: 媒體型別：電影、電視劇、動漫
        :param in_path: 源目錄
        :param size: 檔案大小
        """
        if not mtype:
            return None
        if mtype == MediaType.MOVIE:
            dest_paths = self._movie_path
        elif mtype == MediaType.TV:
            dest_paths = self._tv_path
        else:
            dest_paths = self._anime_path
        if not dest_paths:
            return None
        if not isinstance(dest_paths, list):
            return dest_paths
        if isinstance(dest_paths, list) and len(dest_paths) == 1:
            return dest_paths[0]
        # 有輸入路徑的，匹配有共同上級路徑的
        if in_path:
            # 先用自定義規則匹配 找同級目錄最多的路徑
            max_return_path = None
            max_path_len = 0
            for dest_path in dest_paths:
                try:
                    path_len = len(os.path.commonpath([in_path, dest_path]))
                    if path_len > max_path_len:
                        max_path_len = path_len
                        max_return_path = dest_path
                except Exception as err:
                    ExceptionUtils.exception_traceback(err)
                    continue
            if max_return_path:
                return max_return_path
        # 有輸入大小的，匹配第1個滿足空間儲存要求的
        if size:
            for path in dest_paths:
                disk_free_size = SystemUtils.get_free_space_gb(path)
                if float(disk_free_size) > float(size / 1024 / 1024 / 1024):
                    return path
        # 預設返回第1個
        return dest_paths[0]

    def __get_best_unknown_path(self, in_path):
        """
        查詢最合適的unknown目錄
        :param in_path: 源目錄
        """
        if not self._unknown_path:
            return None
        for unknown_path in self._unknown_path:
            if os.path.commonpath([in_path, unknown_path]) not in ["/", "\\"]:
                return unknown_path
        return self._unknown_path[0]

    def link_sync_file(self, src_path, in_file, target_dir, sync_transfer_mode):
        """
        對檔案做純連結處理，不做識別重新命名，則監控模組呼叫
        :param : 來源渠道
        :param src_path: 源目錄
        :param in_file: 原始檔
        :param target_dir: 目的目錄
        :param sync_transfer_mode: 明確的轉移方式
        """
        new_file = in_file.replace(src_path, target_dir)
        new_file_list, msg = self.check_ignore(file_list=[new_file])
        if not new_file_list:
            return 0, msg
        else:
            new_file = new_file_list[0]
        new_dir = os.path.dirname(new_file)
        if not os.path.exists(new_dir):
            os.makedirs(new_dir)
        return self.__transfer_command(file_item=in_file,
                                       target_file=new_file,
                                       rmt_mode=sync_transfer_mode), ""

    @staticmethod
    def get_format_dict(media):
        """
        根據媒體資訊，返回Format字典
        """
        if not media:
            return {}
        return {
            "title": StringUtils.clear_file_name(media.title),
            "en_title": StringUtils.clear_file_name(media.en_name),
            "original_name": StringUtils.clear_file_name(os.path.splitext(media.org_string or "")[0]),
            "original_title": StringUtils.clear_file_name(media.original_title),
            "name": StringUtils.clear_file_name(media.get_name()),
            "year": media.year,
            "edition": media.get_edtion_string() or None,
            "videoFormat": media.resource_pix,
            "releaseGroup": media.resource_team,
            "videoCodec": media.video_encode,
            "audioCodec": media.audio_encode,
            "tmdbid": media.tmdb_id,
            "season": media.get_season_seq(),
            "episode": media.get_episode_seqs(),
            "season_episode": "%s%s" % (media.get_season_item(), media.get_episode_items()),
            "part": media.part
        }

    def get_moive_dest_path(self, media_info):
        """
        計算電影檔案路徑
        :return: 電影目錄、電影名稱
        """
        format_dict = self.get_format_dict(media_info)
        dir_name = re.sub(r"[-_\s.]*None", "", self._movie_dir_rmt_format.format(**format_dict))
        file_name = re.sub(r"[-_\s.]*None", "", self._movie_file_rmt_format.format(**format_dict))
        return dir_name, file_name

    def get_tv_dest_path(self, media_info):
        """
        計算電視劇檔案路徑
        :return: 電視劇目錄、季目錄、集名稱
        """
        format_dict = self.get_format_dict(media_info)
        dir_name = re.sub(r"[-_\s.]*None", "", self._tv_dir_rmt_format.format(**format_dict))
        season_name = re.sub(r"[-_\s.]*None", "", self._tv_season_rmt_format.format(**format_dict))
        file_name = re.sub(r"[-_\s.]*None", "", self._tv_file_rmt_format.format(**format_dict))
        return dir_name, season_name, file_name

    def check_ignore(self, file_list):
        """
        檢查過濾檔案列表中忽略專案
        :param file_list: 檔案路徑列表
        """
        if not file_list:
            return [], ""
        #  過濾掉檔案列表中上級資料夾在黑名單中的
        if self._ignored_paths:
            try:
                for file in file_list[:]:
                    if file.replace('\\', '/').split('/')[-2] in self._ignored_paths:
                        log.info("【Rmt】%s 檔案上級資料夾名稱在黑名單中，已忽略轉移" % file)
                        file_list.remove(file)
                if not file_list:
                    return [], "排除轉移資料夾黑名單後，沒有新檔案需要處理"
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error("【Rmt】轉移資料夾黑名單設定有誤：%s" % str(err))

        #  過濾掉檔案列表中包含檔案轉移忽略詞的
        if self._ignored_files:
            try:
                for file in file_list[:]:
                    if re.findall(self._ignored_files, file.replace('\\', '/').split('/')[-1]):
                        log.info("【Rmt】%s 檔名包含檔案轉移忽略詞，已忽略轉移" % file)
                        file_list.remove(file)
                if not file_list:
                    return [], "排除檔案轉移忽略詞後，沒有新檔案需要處理"
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                log.error("【Rmt】檔案轉移忽略詞設定有誤：%s" % str(err))

        return file_list, ""


if __name__ == "__main__":
    """
    手工轉移時，使用命名行呼叫
    """
    parser = argparse.ArgumentParser(description='檔案轉移工具')
    parser.add_argument('-m', '--mode', dest='mode', required=True,
                        help='轉移模式：link copy softlink move rclone rclonecopy minio miniocopy')
    parser.add_argument('-s', '--source', dest='s_path', required=True, help='硬連結源目錄路徑')
    parser.add_argument('-d', '--target', dest='t_path', required=False, help='硬連結目的目錄路徑')
    args = parser.parse_args()
    if os.environ.get('NASTOOL_CONFIG'):
        print("【Rmt】配置檔案地址：%s" % os.environ.get('NASTOOL_CONFIG'))
        print("【Rmt】源目錄路徑：%s" % args.s_path)
        if args.t_path:
            print("【Rmt】目的目錄路徑：%s" % args.t_path)
        else:
            print("【Rmt】目的目錄為配置檔案中的電影、電視劇媒體庫目錄")
        FileTransfer().transfer_manually(args.s_path, args.t_path, args.mode)
    else:
        print("【Rmt】未設定環境變數，請先設定 NASTOOL_CONFIG 環境變數為配置檔案地址")
