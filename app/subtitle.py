import datetime
import os.path
import re
import shutil

from lxml import etree

import log
from app.helper import SubHelper
from app.utils import RequestUtils, PathUtils, SystemUtils, StringUtils
from app.utils.commons import singleton
from app.utils.exception_utils import ExceptionUtils
from app.utils.types import MediaType
from config import Config, RMT_SUBEXT, SITE_SUBTITLE_XPATH


@singleton
class Subtitle:
    subhelper = None
    _save_tmp_path = None
    _server = None
    _host = None
    _api_key = None
    _remote_path = None
    _local_path = None
    _opensubtitles_enable = False

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.subhelper = SubHelper()
        self._save_tmp_path = os.path.join(Config().get_config_path(), "temp")
        if not os.path.exists(self._save_tmp_path):
            os.makedirs(self._save_tmp_path)
        subtitle = Config().get_config('subtitle')
        if subtitle:
            self._server = subtitle.get("server")
            if self._server == "chinesesubfinder":
                self._api_key = subtitle.get("chinesesubfinder", {}).get("api_key")
                self._host = subtitle.get("chinesesubfinder", {}).get('host')
                if self._host:
                    if not self._host.startswith('http'):
                        self._host = "http://" + self._host
                    if not self._host.endswith('/'):
                        self._host = self._host + "/"
                self._local_path = subtitle.get("chinesesubfinder", {}).get("local_path")
                self._remote_path = subtitle.get("chinesesubfinder", {}).get("remote_path")
            else:
                self._opensubtitles_enable = subtitle.get("opensubtitles", {}).get("enable")

    def download_subtitle(self, items, server=None):
        """
        字幕下載入口
        :param items: {"type":, "file", "file_ext":, "name":, "title", "year":, "season":, "episode":, "bluray":}
        :param server: 字幕下載伺服器
        :return: 是否成功，訊息內容
        """
        if not items:
            return False, "引數有誤"
        _server = self._server if not server else server
        if not _server:
            return False, "未配置字幕下載器"
        if _server == "opensubtitles":
            if server or self._opensubtitles_enable:
                return self.__download_opensubtitles(items)
        elif _server == "chinesesubfinder":
            return self.__download_chinesesubfinder(items)
        return False, "未配置字幕下載器"

    def __search_opensubtitles(self, item):
        """
        爬取OpenSubtitles.org字幕
        """
        if not self.subhelper:
            return []
        return self.subhelper.search_subtitles(item)

    def __download_opensubtitles(self, items):
        """
        呼叫OpenSubtitles Api下載字幕
        """
        if not self.subhelper:
            return False, "未配置OpenSubtitles"
        subtitles_cache = {}
        success = False
        ret_msg = ""
        for item in items:
            if not item:
                continue
            if not item.get("name") or not item.get("file"):
                continue
            if item.get("type") == MediaType.TV and not item.get("imdbid"):
                log.warn("【Subtitle】電視劇型別需要imdbid檢索字幕，跳過...")
                ret_msg = "電視劇需要imdbid檢索字幕"
                continue
            subtitles = subtitles_cache.get(item.get("name"))
            if subtitles is None:
                log.info(
                    "【Subtitle】開始從Opensubtitle.org檢索字幕: %s，imdbid=%s" % (item.get("name"), item.get("imdbid")))
                subtitles = self.__search_opensubtitles(item)
                if not subtitles:
                    subtitles_cache[item.get("name")] = []
                    log.info("【Subtitle】%s 未檢索到字幕" % item.get("name"))
                    ret_msg = "%s 未檢索到字幕" % item.get("name")
                else:
                    subtitles_cache[item.get("name")] = subtitles
                    log.info("【Subtitle】opensubtitles.org返回資料：%s" % len(subtitles))
            if not subtitles:
                continue
            # 成功數
            subtitle_count = 0
            for subtitle in subtitles:
                # 標題
                if not item.get("imdbid"):
                    if str(subtitle.get('title')) != "%s (%s)" % (item.get("name"), item.get("year")):
                        continue
                # 季
                if item.get('season') \
                        and str(subtitle.get('season').replace("Season", "").strip()) != str(item.get('season')):
                    continue
                # 集
                if item.get('episode') \
                        and str(subtitle.get('episode')) != str(item.get('episode')):
                    continue
                # 字幕檔名
                SubFileName = subtitle.get('description')
                # 下載連結
                Download_Link = subtitle.get('link')
                # 下載後的字幕檔案路徑
                Media_File = "%s.chi.zh-cn%s" % (item.get("file"), item.get("file_ext"))
                log.info("【Subtitle】正在從opensubtitles.org下載字幕 %s 到 %s " % (SubFileName, Media_File))
                # 下載
                ret = RequestUtils(cookies=self.subhelper.get_cookie(),
                                   headers=self.subhelper.get_ua()).get_res(Download_Link)
                if ret and ret.status_code == 200:
                    # 儲存ZIP
                    file_name = self.__get_url_subtitle_name(ret.headers.get('content-disposition'), Download_Link)
                    if not file_name:
                        continue
                    zip_file = os.path.join(self._save_tmp_path, file_name)
                    zip_path = os.path.splitext(zip_file)[0]
                    with open(zip_file, 'wb') as f:
                        f.write(ret.content)
                    # 解壓檔案
                    shutil.unpack_archive(zip_file, zip_path, format='zip')
                    # 遍歷轉移檔案
                    for sub_file in PathUtils.get_dir_files(in_path=zip_path, exts=RMT_SUBEXT):
                        self.__transfer_subtitle(sub_file, Media_File)
                    # 刪除臨時檔案
                    try:
                        shutil.rmtree(zip_path)
                        os.remove(zip_file)
                    except Exception as err:
                        ExceptionUtils.exception_traceback(err)
                else:
                    log.error("【Subtitle】下載字幕檔案失敗：%s" % Download_Link)
                    continue
                # 最多下載3個字幕
                subtitle_count += 1
                if subtitle_count > 2:
                    break
            if not subtitle_count:
                if item.get('episode'):
                    log.info("【Subtitle】%s 第%s季 第%s集 未找到符合條件的字幕" % (
                        item.get("name"), item.get("season"), item.get("episode")))
                    ret_msg = "%s 第%s季 第%s集 未找到符合條件的字幕" % (
                        item.get("name"), item.get("season"), item.get("episode"))
                else:
                    log.info("【Subtitle】%s 未找到符合條件的字幕" % item.get("name"))
                    ret_msg = "%s 未找到符合條件的字幕" % item.get("name")
            else:
                log.info("【Subtitle】%s 共下載了 %s 個字幕" % (item.get("name"), subtitle_count))
                ret_msg = "%s 共下載了 %s 個字幕" % (item.get("name"), subtitle_count)
                success = True
        if success:
            return True, ret_msg
        else:
            return False, ret_msg

    def __download_chinesesubfinder(self, items):
        """
        呼叫ChineseSubFinder下載字幕
        """
        if not self._host or not self._api_key:
            return False, "未配置ChineseSubFinder"
        req_url = "%sapi/v1/add-job" % self._host
        notify_items = []
        success = False
        ret_msg = ""
        for item in items:
            if not item:
                continue
            if not item.get("name") or not item.get("file"):
                continue
            if item.get("bluray"):
                file_path = "%s.mp4" % item.get("file")
            else:
                if os.path.splitext(item.get("file"))[-1] != item.get("file_ext"):
                    file_path = "%s%s" % (item.get("file"), item.get("file_ext"))
                else:
                    file_path = item.get("file")

            # 路徑替換
            if self._local_path and self._remote_path and file_path.startswith(self._local_path):
                file_path = file_path.replace(self._local_path, self._remote_path).replace('\\', '/')

            # 一個名稱只建一個任務
            if file_path not in notify_items:
                notify_items.append(file_path)
                log.info("【Subtitle】通知ChineseSubFinder下載字幕: %s" % file_path)
                params = {
                    "video_type": 0 if item.get("type") == MediaType.MOVIE else 1,
                    "physical_video_file_full_path": file_path,
                    "task_priority_level": 3,
                    "media_server_inside_video_id": "",
                    "is_bluray": item.get("bluray")
                }
                try:
                    res = RequestUtils(headers={
                        "Authorization": "Bearer %s" % self._api_key
                    }).post(req_url, json=params)
                    if not res or res.status_code != 200:
                        log.error("【Subtitle】呼叫ChineseSubFinder API失敗！")
                        ret_msg = "呼叫ChineseSubFinder API失敗"
                    else:
                        # 如果檔案目錄沒有識別的nfo後設資料， 此介面會返回控制符，推測是ChineseSubFinder的原因
                        # emby refresh後設資料時非同步的
                        if res.text:
                            job_id = res.json().get("job_id")
                            message = res.json().get("message")
                            if not job_id:
                                log.warn("【Subtitle】ChineseSubFinder下載字幕出錯：%s" % message)
                                ret_msg = "ChineseSubFinder下載字幕出錯：%s" % message
                            else:
                                log.info("【Subtitle】ChineseSubFinder任務新增成功：%s" % job_id)
                                ret_msg = "ChineseSubFinder任務新增成功：%s" % job_id
                        else:
                            log.error("【Subtitle】%s 目錄缺失nfo後設資料" % file_path)
                            ret_msg = "%s 目錄下缺失nfo後設資料：" % file_path
                except Exception as e:
                    ExceptionUtils.exception_traceback(e)
                    log.error("【Subtitle】連線ChineseSubFinder出錯：" + str(e))
                    ret_msg = "連線ChineseSubFinder出錯：%s" % str(e)
        if success:
            return True, ret_msg
        else:
            return False, ret_msg

    @staticmethod
    def __transfer_subtitle(sub_file, media_file):
        """
        轉移字幕
        """
        new_sub_file = "%s%s" % (os.path.splitext(media_file)[0], os.path.splitext(sub_file)[-1])
        if os.path.exists(new_sub_file):
            return 1
        else:
            return SystemUtils.copy(sub_file, new_sub_file)

    def download_subtitle_from_site(self, media_info, cookie, ua, download_dir):
        """
        從站點下載字幕檔案，並儲存到本地
        """
        if not media_info.page_url:
            return
        # 字幕下載目錄
        log.info("【Subtitle】開始從站點下載字幕: %s" % media_info.page_url)
        if not download_dir:
            log.warn("【Subtitle】未找到字幕下載目錄")
            return
        # 讀取網站程式碼
        request = RequestUtils(cookies=cookie, headers=ua)
        res = request.get_res(media_info.page_url)
        if res and res.status_code == 200:
            if not res.text:
                log.warn(f"【Subtitle】讀取頁面程式碼失敗：{media_info.page_url}")
                return
            html = etree.HTML(res.text)
            sublink = None
            for xpath in SITE_SUBTITLE_XPATH:
                sublinks = html.xpath(xpath)
                if sublinks:
                    sublink = sublinks[0]
                    if not sublink.startswith("http"):
                        base_url = StringUtils.get_base_url(media_info.page_url)
                        if sublink.startswith("/"):
                            sublink = "%s%s" % (base_url, sublink)
                        else:
                            sublink = "%s/%s" % (base_url, sublink)
                    break
            if sublink:
                log.info(f"【Subtitle】找到字幕下載連結: {sublink}，開始下載...")
                # 下載
                ret = request.get_res(sublink)
                if ret and ret.status_code == 200:
                    # 如果目錄不存在,則先建立
                    if not os.path.isdir(download_dir):
                        os.makedirs(download_dir)
                    # 儲存ZIP
                    file_name = self.__get_url_subtitle_name(ret.headers.get('content-disposition'), sublink)
                    if not file_name:
                        log.warn(f"【Subtitle】連結不是字幕檔案：{sublink}")
                        return
                    if file_name.lower().endswith(".zip"):
                        # ZIP包
                        zip_file = os.path.join(self._save_tmp_path, file_name)
                        # 解壓路徑
                        zip_path = os.path.splitext(zip_file)[0]
                        with open(zip_file, 'wb') as f:
                            f.write(ret.content)
                        # 解壓檔案
                        shutil.unpack_archive(zip_file, zip_path, format='zip')
                        # 遍歷轉移檔案
                        for sub_file in PathUtils.get_dir_files(in_path=zip_path, exts=RMT_SUBEXT):
                            media_file = os.path.join(download_dir, os.path.basename(sub_file))
                            log.info(f"【Subtitle】轉移字幕 {sub_file} 到 {media_file}")
                            self.__transfer_subtitle(sub_file, media_file)
                        # 刪除臨時檔案
                        try:
                            shutil.rmtree(zip_path)
                            os.remove(zip_file)
                        except Exception as err:
                            ExceptionUtils.exception_traceback(err)
                    else:
                        sub_file = os.path.join(self._save_tmp_path, file_name)
                        # 儲存
                        with open(sub_file, 'wb') as f:
                            f.write(ret.content)
                        media_file = os.path.join(download_dir, os.path.basename(sub_file))
                        log.info(f"【Subtitle】轉移字幕 {sub_file} 到 {media_file}")
                        self.__transfer_subtitle(sub_file, media_file)
                else:
                    log.error(f"【Subtitle】下載字幕檔案失敗：{sublink}")
                    return
            else:
                return
        elif res is not None:
            log.warn(f"【Subtitle】連線 {media_info.page_url} 失敗，狀態碼：{res.status_code}")
        else:
            log.warn(f"【Subtitle】無法開啟連結：{media_info.page_url}")

    @staticmethod
    def __get_url_subtitle_name(disposition, url):
        """
        從下載請求中獲取字幕檔名
        """
        file_name = re.findall(r"filename=\"?(.+)\"?", disposition or "")
        if file_name:
            file_name = str(file_name[0].encode('ISO-8859-1').decode()).split(";")[0].strip()
            if file_name.endswith('"'):
                file_name = file_name[:-1]
        elif url and os.path.splitext(url)[-1] in (RMT_SUBEXT + ['.zip']):
            file_name = url.split("/")[-1]
        else:
            file_name = str(datetime.datetime.now())
        return file_name
