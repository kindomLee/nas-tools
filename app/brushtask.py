import re
import sys
import time
import pytz
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

import log
from app.downloader.client import Qbittorrent, Transmission
from app.filter import Filter
from app.helper import DbHelper, DictHelper
from app.message import Message
from app.rss import Rss
from app.sites import Sites
from app.utils import StringUtils
from app.utils.commons import singleton
from app.utils.exception_utils import ExceptionUtils
from app.utils.types import BrushDeleteType, SystemDictType
from config import BRUSH_REMOVE_TORRENTS_INTERVAL


@singleton
class BrushTask(object):
    message = None
    sites = None
    filter = None
    dbhelper = None
    _scheduler = None
    _brush_tasks = []
    _torrents_cache = []
    _downloader_infos = []
    _qb_client = "qbittorrent"
    _tr_client = "transmission"

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.dbhelper = DbHelper()
        self.message = Message()
        self.sites = Sites()
        self.filter = Filter()
        # 移除現有任務
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
        # 讀取下載器列表
        downloaders = self.dbhelper.get_user_downloaders()
        self._downloader_infos = []
        for downloader_info in downloaders:
            self._downloader_infos.append(
                {
                    "id": downloader_info.ID,
                    "name": downloader_info.NAME,
                    "type": downloader_info.TYPE,
                    "host": downloader_info.HOST,
                    "port": downloader_info.PORT,
                    "username": downloader_info.USERNAME,
                    "password": downloader_info.PASSWORD,
                    "save_dir": downloader_info.SAVE_DIR
                }
            )
        # 讀取刷流任務列表
        self._brush_tasks = self.get_brushtask_info()
        if not self._brush_tasks:
            return
        # 啟動RSS任務
        task_flag = False
        self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        for task in self._brush_tasks:
            if task.get("state") == "Y" and task.get("interval") and str(task.get("interval")).isdigit():
                task_flag = True
                self._scheduler.add_job(func=self.check_task_rss,
                                        args=[task.get("id")],
                                        trigger='interval',
                                        seconds=int(task.get("interval")) * 60)
        # 啟動刪種任務
        if task_flag:
            self._scheduler.add_job(func=self.remove_tasks_torrents,
                                    trigger='interval',
                                    seconds=BRUSH_REMOVE_TORRENTS_INTERVAL)
            # 啟動
            self._scheduler.print_jobs()
            self._scheduler.start()
            log.info("刷流服務啟動")

    def get_brushtask_info(self, taskid=None):
        """
        讀取刷流任務列表
        """
        brushtasks = self.dbhelper.get_brushtasks()
        _brush_tasks = []
        for task in brushtasks:
            sendmessage_switch = DictHelper().get(SystemDictType.BrushMessageSwitch.value, task.SITE)
            forceupload_switch = DictHelper().get(SystemDictType.BrushForceUpSwitch.value, task.SITE)
            site_info = self.sites.get_sites(siteid=task.SITE)
            if site_info:
                site_url = StringUtils.get_base_url(site_info.get("signurl") or site_info.get("rssurl"))
            else:
                site_url = ""
            downloader_info = self.get_downloader_info(task.DOWNLOADER)
            _brush_tasks.append({
                "id": task.ID,
                "name": task.NAME,
                "site": site_info.get("name"),
                "site_id": site_info.get("id"),
                "interval": task.INTEVAL,
                "state": task.STATE,
                "downloader": task.DOWNLOADER,
                "downloader_name": downloader_info.get("name"),
                "transfer": task.TRANSFER,
                "free": task.FREELEECH,
                "rss_rule": eval(task.RSS_RULE),
                "remove_rule": eval(task.REMOVE_RULE),
                "seed_size": task.SEED_SIZE,
                "rss_url": site_info.get("rssurl"),
                "cookie": site_info.get("cookie"),
                "sendmessage": sendmessage_switch,
                "forceupload": forceupload_switch,
                "ua": site_info.get("ua"),
                "download_count": task.DOWNLOAD_COUNT,
                "remove_count": task.REMOVE_COUNT,
                "download_size": StringUtils.str_filesize(task.DOWNLOAD_SIZE),
                "upload_size": StringUtils.str_filesize(task.UPLOAD_SIZE),
                "lst_mod_date": task.LST_MOD_DATE,
                "site_url": site_url
            })
        if taskid:
            for task in _brush_tasks:
                if task.get("id") == int(taskid):
                    return task
            return {}
        else:
            return _brush_tasks

    def check_task_rss(self, taskid):
        """
        檢查RSS並新增下載，由定時服務呼叫
        :param taskid: 刷流任務的ID
        """
        if not taskid:
            return
        # 任務資訊
        taskinfo = self.get_brushtask_info(taskid)
        if not taskinfo:
            return
        # 檢索RSS
        seed_size = taskinfo.get("seed_size")
        task_name = taskinfo.get("name")
        site_id = taskinfo.get("site_id")
        site_name = taskinfo.get("site")
        rss_url = taskinfo.get("rss_url")
        rss_rule = taskinfo.get("rss_rule")
        cookie = taskinfo.get("cookie")
        rss_free = taskinfo.get("free")
        ua = taskinfo.get("ua")
        log.info("【Brush】開始站點 %s 的刷流任務：%s..." % (site_name, task_name))
        if not site_id:
            log.error("【Brush】刷流任務 %s 的站點已不存在，無法刷流！" % task_name)
            return
        if not rss_url:
            log.error("【Brush】站點 %s 未配置RSS訂閱地址，無法刷流！" % site_name)
            return
        if rss_free and not cookie:
            log.warn("【Brush】站點 %s 未配置Cookie，無法開啟促銷刷流" % site_name)
            return
        # 下載器引數
        downloader_cfg = self.get_downloader_info(taskinfo.get("downloader"))
        if not downloader_cfg:
            log.error("【Brush】任務 %s 下載器不存在，無法刷流！" % task_name)
            return
        # 檢查是否達到保種體積
        if not self.__is_allow_new_torrent(taskid=taskid,
                                           taskname=task_name,
                                           seedsize=seed_size,
                                           downloadercfg=downloader_cfg,
                                           dlcount=rss_rule.get("dlcount")):
            return
        rss_result = Rss.parse_rssxml(rss_url)
        if len(rss_result) == 0:
            log.warn("【Brush】%s RSS未下載到資料" % site_name)
            return
        else:
            log.info("【Brush】%s RSS獲取資料：%s" % (site_name, len(rss_result)))
        success_count = 0

        for res in rss_result:
            try:
                # 種子名
                torrent_name = res.get('title')
                # 種子連結
                enclosure = res.get('enclosure')
                # 種子頁面
                page_url = res.get('link')
                # 副標題
                description = res.get('description')
                # 種子大小
                size = res.get('size')
                # 釋出時間
                pubdate = res.get('pubdate')

                if enclosure not in self._torrents_cache:
                    self._torrents_cache.append(enclosure)
                else:
                    log.debug("【Brush】%s 已處理過" % torrent_name)
                    continue

                # 檢查種子是否符合選種規則
                if not self.__check_rss_rule(rss_rule=rss_rule,
                                             title=torrent_name,
                                             description=description,
                                             torrent_url=page_url,
                                             torrent_size=size,
                                             pubdate=pubdate,
                                             cookie=cookie,
                                             ua=ua):
                    continue
                # 開始下載
                log.debug("【Brush】%s 符合條件，開始下載..." % torrent_name)
                if self.__download_torrent(downloadercfg=downloader_cfg,
                                           title=torrent_name,
                                           enclosure=enclosure,
                                           size=size,
                                           taskid=taskid,
                                           transfer=True if taskinfo.get("transfer") == 'Y' else False,
                                           sendmessage=True if taskinfo.get("sendmessage") == 'Y' else False,
                                           forceupload=True if taskinfo.get("forceupload") == 'Y' else False,
                                           upspeed=rss_rule.get("upspeed"),
                                           downspeed=rss_rule.get("downspeed"),
                                           taskname=task_name,
                                           site_id=site_id):
                    # 計數
                    success_count += 1
                    # 再判斷一次
                    if not self.__is_allow_new_torrent(taskid=taskid,
                                                       taskname=task_name,
                                                       seedsize=seed_size,
                                                       dlcount=rss_rule.get("dlcount"),
                                                       downloadercfg=downloader_cfg):
                        break
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                continue
        log.info("【Brush】任務 %s 本次新增了 %s 個下載" % (task_name, success_count))

    def remove_tasks_torrents(self):
        """
        根據條件檢查所有任務下載完成的種子，按條件進行刪除，並更新任務資料
        由定時服務呼叫
        """

        def __send_message(_task_name, _delete_type, _torrent_name):
            """
            傳送刪種訊息
            """
            _msg_title = "【刷流任務 {} 刪除做種】".format(_task_name)
            _msg_text = "刪除原因：{}\n種子名稱：{}".format(_delete_type.value, _torrent_name)
            self.message.send_brushtask_remove_message(title=_msg_title, text=_msg_text)

        # 遍歷所有任務
        for taskinfo in self._brush_tasks:
            if taskinfo.get("state") != "Y":
                continue
            try:
                # 總上傳量
                total_uploaded = 0
                # 總下載量
                total_downloaded = 0
                # 可以刪種的種子
                delete_ids = []
                # 需要更新狀態的種子
                update_torrents = []
                # 任務資訊
                taskid = taskinfo.get("id")
                task_name = taskinfo.get("name")
                download_id = taskinfo.get("downloader")
                remove_rule = taskinfo.get("remove_rule")
                sendmessage = True if taskinfo.get("sendmessage") == "Y" else False
                # 當前任務種子詳情
                task_torrents = self.dbhelper.get_brushtask_torrents(taskid)
                torrent_ids = [item.DOWNLOAD_ID for item in task_torrents if item.DOWNLOAD_ID]
                if not torrent_ids:
                    continue
                # 下載器引數
                downloader_cfg = self.get_downloader_info(download_id)
                if not downloader_cfg:
                    log.warn("【Brush】任務 %s 下載器不存在" % task_name)
                    continue
                # 下載器型別
                client_type = downloader_cfg.get("type")
                # qbittorrent
                if client_type == self._qb_client:
                    downloader = Qbittorrent(user_config=downloader_cfg)
                    # 檢查完成狀態的
                    torrents, has_err = downloader.get_torrents(ids=torrent_ids, status=["completed"])
                    # 看看是否有錯誤, 有錯誤的話就不處理了
                    if has_err:
                        log.warn("【BRUSH】任務 %s 獲取種子狀態失敗" % task_name)
                        continue
                    remove_torrent_ids = list(
                        set(torrent_ids).difference(set([torrent.get("hash") for torrent in torrents])))
                    for torrent in torrents:
                        # ID
                        torrent_id = torrent.get("hash")
                        # 已開始時間 秒
                        dltime = int(time.time() - torrent.get("added_on"))
                        # 已做種時間 秒
                        date_done = torrent.completion_on if torrent.completion_on > 0 else torrent.added_on
                        date_now = int(time.mktime(datetime.now().timetuple()))
                        seeding_time = date_now - date_done if date_done else 0
                        # 分享率
                        ratio = torrent.get("ratio") or 0
                        # 上傳量
                        uploaded = torrent.get("uploaded") or 0
                        total_uploaded += uploaded
                        # 平均上傳速度 Byte/s
                        avg_upspeed = int(uploaded / dltime)
                        # 下載量
                        downloaded = torrent.get("downloaded")
                        total_downloaded += downloaded
                        need_delete, delete_type = self.__check_remove_rule(remove_rule=remove_rule,
                                                                            seeding_time=seeding_time,
                                                                            ratio=ratio,
                                                                            uploaded=uploaded,
                                                                            avg_upspeed=avg_upspeed)
                        if need_delete:
                            log.info(
                                "【Brush】%s 做種達到刪種條件：%s，刪除任務..." % (torrent.get('name'), delete_type.value))
                            if sendmessage:
                                __send_message(task_name, delete_type, torrent.get('name'))

                            if torrent_id not in delete_ids:
                                delete_ids.append(torrent_id)
                                update_torrents.append(("%s,%s" % (uploaded, downloaded), taskid, torrent_id))
                    # 檢查下載中狀態的
                    torrents, has_err = downloader.get_torrents(ids=torrent_ids, status=["downloading"])
                    # 看看是否有錯誤, 有錯誤的話就不處理了
                    if has_err:
                        log.warn("【BRUSH】任務 %s 獲取種子狀態失敗" % task_name)
                        continue
                    remove_torrent_ids = list(
                        set(remove_torrent_ids).difference(set([torrent.get("hash") for torrent in torrents])))
                    for torrent in torrents:
                        # ID
                        torrent_id = torrent.get("hash")
                        # 下載耗時 秒
                        dltime = int(time.time() - torrent.get("added_on"))
                        # 上傳量 Byte
                        uploaded = torrent.get("uploaded") or 0
                        total_uploaded += uploaded
                        # 平均上傳速度 Byte/s
                        avg_upspeed = int(uploaded / dltime)
                        # 下載量
                        downloaded = torrent.get("downloaded")
                        total_downloaded += downloaded
                        need_delete, delete_type = self.__check_remove_rule(remove_rule=remove_rule,
                                                                            dltime=dltime,
                                                                            avg_upspeed=avg_upspeed)
                        if need_delete:
                            log.info(
                                "【Brush】%s 達到刪種條件：%s，刪除下載任務..." % (torrent.get('name'), delete_type.value))
                            if sendmessage:
                                __send_message(task_name, delete_type, torrent.get('name'))

                            if torrent_id not in delete_ids:
                                delete_ids.append(torrent_id)
                                update_torrents.append(("%s,%s" % (uploaded, downloaded), taskid, torrent_id))
                # transmission
                else:
                    # 將查詢的torrent_ids轉為數字型
                    torrent_ids = [int(x) for x in torrent_ids if str(x).isdigit()]
                    # 檢查完成狀態
                    downloader = Transmission(user_config=downloader_cfg)
                    torrents, has_err = downloader.get_torrents(ids=torrent_ids, status=["seeding", "seed_pending"])
                    # 看看是否有錯誤, 有錯誤的話就不處理了
                    if has_err:
                        log.warn("【BRUSH】任務 %s 獲取種子狀態失敗" % task_name)
                        continue
                    remove_torrent_ids = list(set(torrent_ids).difference(set([torrent.id for torrent in torrents])))
                    for torrent in torrents:
                        # ID
                        torrent_id = torrent.id
                        # 做種時間
                        date_done = torrent.date_done or torrent.date_added
                        date_now = int(time.mktime(datetime.now().timetuple()))
                        dltime = date_now - int(time.mktime(torrent.date_added.timetuple()))
                        seeding_time = date_now - int(time.mktime(date_done.timetuple()))
                        # 下載量
                        downloaded = int(torrent.total_size * torrent.progress / 100)
                        total_downloaded += downloaded
                        # 分享率
                        ratio = torrent.ratio or 0
                        # 上傳量
                        uploaded = int(downloaded * torrent.ratio)
                        total_uploaded += uploaded
                        # 平均上傳速度
                        avg_upspeed = int(uploaded / dltime)
                        need_delete, delete_type = self.__check_remove_rule(remove_rule=remove_rule,
                                                                            seeding_time=seeding_time,
                                                                            ratio=ratio,
                                                                            uploaded=uploaded,
                                                                            avg_upspeed=avg_upspeed)
                        if need_delete:
                            log.info("【Brush】%s 做種達到刪種條件：%s，刪除任務..." % (torrent.name, delete_type.value))
                            if sendmessage:
                                __send_message(task_name, delete_type, torrent.name)

                            if torrent_id not in delete_ids:
                                delete_ids.append(torrent_id)
                                update_torrents.append(("%s,%s" % (uploaded, downloaded), taskid, torrent_id))
                    # 檢查下載狀態
                    torrents, has_err = downloader.get_torrents(ids=torrent_ids,
                                                                status=["downloading", "download_pending", "stopped"])
                    # 看看是否有錯誤, 有錯誤的話就不處理了
                    if has_err:
                        log.warn("【BRUSH】任務 %s 獲取種子狀態失敗" % task_name)
                        continue
                    remove_torrent_ids = list(
                        set(remove_torrent_ids).difference(set([torrent.id for torrent in torrents])))
                    for torrent in torrents:
                        # ID
                        torrent_id = torrent.id
                        # 下載耗時
                        dltime = (datetime.now().astimezone() - torrent.date_added).seconds
                        # 下載量
                        downloaded = int(torrent.total_size * torrent.progress / 100)
                        total_downloaded += downloaded
                        # 上傳量
                        uploaded = int(downloaded * torrent.ratio)
                        total_uploaded += uploaded
                        # 平均上傳速度
                        avg_upspeed = int(uploaded / dltime)
                        need_delete, delete_type = self.__check_remove_rule(remove_rule=remove_rule,
                                                                            dltime=dltime,
                                                                            avg_upspeed=avg_upspeed)
                        if need_delete:
                            log.info("【Brush】%s 達到刪種條件：%s，刪除下載任務..." % (torrent.name, delete_type.value))
                            if sendmessage:
                                __send_message(task_name, delete_type, torrent.name)

                            if torrent_id not in delete_ids:
                                delete_ids.append(torrent_id)
                                update_torrents.append(("%s,%s" % (uploaded, downloaded), taskid, torrent_id))
                # 手工刪除的種子，清除對應記錄
                if remove_torrent_ids:
                    log.info("【Brush】任務 %s 的這些下載任務在下載器中不存在，將刪除任務記錄：%s" % (
                        task_name, remove_torrent_ids))
                    for remove_torrent_id in remove_torrent_ids:
                        self.dbhelper.delete_brushtask_torrent(taskid, remove_torrent_id)
                # 更新種子狀態為已刪除
                self.dbhelper.update_brushtask_torrent_state(update_torrents)
                # 刪除下載器種子
                if delete_ids:
                    downloader.delete_torrents(delete_file=True, ids=delete_ids)
                    log.info("【Brush】任務 %s 共刪除 %s 個刷流下載任務" % (task_name, len(delete_ids)))
                else:
                    log.info("【Brush】任務 %s 本次檢查未刪除下載任務" % task_name)
                # 更新上傳下載量和刪除種子數
                self.dbhelper.add_brushtask_upload_count(brush_id=taskid,
                                                         upload_size=total_uploaded,
                                                         download_size=total_downloaded,
                                                         remove_count=len(delete_ids) + len(remove_torrent_ids))
            except Exception as e:
                ExceptionUtils.exception_traceback(e)

    def __is_allow_new_torrent(self, taskid, taskname, downloadercfg, seedsize, dlcount):
        """
        檢查是否還能新增新的下載
        """
        if not taskid:
            return False
        # 判斷大小
        total_size = self.dbhelper.get_brushtask_totalsize(taskid)
        if seedsize:
            if float(seedsize) * 1024 ** 3 <= int(total_size):
                log.warn("【Brush】刷流任務 %s 當前保種體積 %sGB，不再新增下載"
                         % (taskname, round(int(total_size) / 1024 / 1024 / 1024, 1)))
                return False
        # 檢查正在下載的任務數
        if dlcount:
            downloading_count = self.__get_downloading_count(downloadercfg)
            if downloading_count is None:
                log.error("【Brush】任務 %s 下載器 %s 無法連線" % (taskname, downloadercfg.get("name")))
                return False
            if int(downloading_count) >= int(dlcount):
                log.warn("【Brush】下載器 %s 正在下載任務數：%s，超過設定上限，暫不新增下載" % (
                    downloadercfg.get("name"), downloading_count))
                return False
        return True

    def get_downloader_info(self, dlid=None):
        """
        獲取下載器的引數
        """
        if dlid:
            for downloader in self._downloader_infos:
                if downloader.get('id') == int(dlid):
                    return downloader
            return {}
        else:
            return self._downloader_infos

    def __get_downloading_count(self, downloadercfg):
        """
        查詢當前正在下載的任務數
        """
        if not downloadercfg:
            return 0
        if downloadercfg.get("type") == self._qb_client:
            downloader = Qbittorrent(user_config=downloadercfg)
            if not downloader.qbc:
                return None
            dlitems = downloader.get_downloading_torrents()
            if dlitems is not None:
                return int(len(dlitems))
        else:
            downloader = Transmission(user_config=downloadercfg)
            if not downloader.trc:
                return None
            dlitems = downloader.get_downloading_torrents()
            if dlitems is not None:
                return int(len(dlitems))
        return None

    def __download_torrent(self,
                           downloadercfg,
                           title,
                           enclosure,
                           size,
                           taskid,
                           transfer,
                           sendmessage,
                           forceupload,
                           upspeed,
                           downspeed,
                           taskname,
                           site_id):
        """
        新增下載任務，更新任務資料
        :param downloadercfg: 下載器的所有引數
        :param title: 種子名稱
        :param enclosure: 種子地址
        :param size: 種子大小
        :param taskid: 任務ID
        :param transfer: 是否要轉移，為False時直接新增已整理的標籤
        :param sendmessage: 是否需要訊息推送
        :param forceupload: 是否需要將新增的刷流任務設定為強制做種(僅針對qBittorrent)
        :param upspeed: 上傳限速
        :param downspeed: 下載限速
        :param taskname: 任務名稱
        :param site_id: 站點ID
        """
        if not downloadercfg:
            return False
        # 標籤
        tag = "已整理" if not transfer else None
        # 下載任務ID
        download_id = None
        # 查詢站點資訊
        site_info = self.sites.get_sites(siteid=site_id)
        # 新增下載
        if downloadercfg.get("type") == self._qb_client:
            # 初始化下載器
            downloader = Qbittorrent(user_config=downloadercfg)
            if not downloader.qbc:
                log.error("【Brush】任務 %s 下載器 %s 無法連線" % (taskname, downloadercfg.get("name")))
                return False
            torrent_tag = "NT" + StringUtils.generate_random_str(5)
            if tag:
                tags = [tag, torrent_tag]
            else:
                tags = torrent_tag
            ret = downloader.add_torrent(content=enclosure,
                                         tag=tags,
                                         download_dir=downloadercfg.get("save_dir"),
                                         upload_limit=upspeed,
                                         download_limit=downspeed,
                                         cookie=site_info.get("cookie"))
            if ret:
                # QB新增下載後需要時間，重試5次每次等待5秒
                download_id = downloader.get_torrent_id_by_tag(torrent_tag)
                if download_id:
                    # 開始下載
                    downloader.start_torrents(download_id)
                    # 強制做種
                    if forceupload:
                        downloader.torrents_set_force_start(download_id)
        else:
            # 初始化下載器
            downloader = Transmission(user_config=downloadercfg)
            if not downloader.trc:
                log.error("【Brush】任務 %s 下載器 %s 無法連線" % (taskname, downloadercfg.get("name")))
                return False
            ret = downloader.add_torrent(content=enclosure,
                                         download_dir=downloadercfg.get("save_dir"),
                                         upload_limit=upspeed,
                                         download_limit=downspeed,
                                         cookie=site_info.get("cookie")
                                         )
            if ret:
                download_id = ret.id
                # 設定標籤
                if download_id and tag:
                    downloader.set_torrent_tag(tid=download_id, tag=tag)
        if not download_id:
            log.warn(f"【Brush】{taskname} 新增下載任務出錯：{title}，"
                     f"可能原因：Cookie過期/任務已存在/觸發了站點首次種子下載，"
                     f"種子連結：{enclosure}")
            return False
        else:
            log.info("【Brush】成功新增下載：%s" % title)
            if sendmessage:
                msg_title = "【刷流任務 {} 新增下載】".format(taskname)
                msg_text = "種子名稱：{}\n種子大小：{}".format(title, StringUtils.str_filesize(size))
                self.message.send_brushtask_added_message(title=msg_title, text=msg_text)
        # 插入種子資料
        if self.dbhelper.insert_brushtask_torrent(brush_id=taskid,
                                                  title=title,
                                                  enclosure=enclosure,
                                                  downloader=downloadercfg.get("id"),
                                                  download_id=download_id,
                                                  size=size):
            # 更新下載次數
            self.dbhelper.add_brushtask_download_count(brush_id=taskid)
        else:
            log.info("【Brush】%s 已下載過" % title)

        return True

    def __check_rss_rule(self,
                         rss_rule,
                         title,
                         description,
                         torrent_url,
                         torrent_size,
                         pubdate,
                         cookie,
                         ua):
        """
        檢查種子是否符合刷流過濾條件
        :param rss_rule: 過濾條件字典
        :param title: 種子名稱
        :param description: 種子副標題
        :param torrent_url: 種子頁面地址
        :param torrent_size: 種子大小
        :param pubdate: 釋出時間
        :param cookie: Cookie
        :param ua: User-Agent
        :return: 是否命中
        """
        if not rss_rule:
            return True
        # 檢查種子大小
        try:
            if rss_rule.get("size"):
                rule_sizes = rss_rule.get("size").split("#")
                if rule_sizes[0]:
                    if len(rule_sizes) > 1 and rule_sizes[1]:
                        min_max_size = rule_sizes[1].split(',')
                        min_size = min_max_size[0]
                        if len(min_max_size) > 1:
                            max_size = min_max_size[1]
                        else:
                            max_size = 0
                        if rule_sizes[0] == "gt" and float(torrent_size) < float(min_size) * 1024 ** 3:
                            return False
                        if rule_sizes[0] == "lt" and float(torrent_size) > float(min_size) * 1024 ** 3:
                            return False
                        if rule_sizes[0] == "bw" and not float(min_size) * 1024 ** 3 < float(torrent_size) < float(
                                max_size) * 1024 ** 3:
                            return False

            # 檢查包含規則
            if rss_rule.get("include"):
                if not re.search(r"%s" % rss_rule.get("include"), "%s %s" % (title, description), re.IGNORECASE):
                    return False

            # 檢查排除規則
            if rss_rule.get("exclude"):
                if re.search(r"%s" % rss_rule.get("exclude"), "%s %s" % (title, description), re.IGNORECASE):
                    return False

            torrent_attr = self.sites.check_torrent_attr(torrent_url=torrent_url, cookie=cookie, ua=ua)
            torrent_peer_count = torrent_attr.get("peer_count")
            log.debug("【Brush】%s 解析詳情, %s" % (title, torrent_attr))

            # 檢查免費狀態
            if rss_rule.get("free") == "FREE":
                if not torrent_attr.get("free"):
                    log.debug("【Brush】不是一個FREE資源，跳過")
                    return False
            elif rss_rule.get("free") == "2XFREE":
                if not torrent_attr.get("2xfree"):
                    log.debug("【Brush】不是一個2XFREE資源，跳過")
                    return False

            # 檢查HR狀態
            if rss_rule.get("hr"):
                if torrent_attr.get("hr"):
                    log.debug("【Brush】這是一個H&R資源，跳過")
                    return False

            # 檢查做種人數
            if rss_rule.get("peercount"):
                # 相容舊版本
                peercount_str = rss_rule.get("peercount")
                if not peercount_str:
                    peercount_str = "#"
                elif "#" not in peercount_str:
                    peercount_str = "lt#" + peercount_str
                else:
                    pass
                peer_counts = peercount_str.split("#")
                if len(peer_counts) >= 2 and peer_counts[1]:
                    min_max_count = peer_counts[1].split(',')
                    min_count = int(min_max_count[0])
                    if len(min_max_count) > 1:
                        max_count = int(min_max_count[1])
                    else:
                        max_count = sys.maxsize
                    if peer_counts[0] == "gt" and torrent_peer_count <= min_count:
                        log.debug("【Brush】%s `判斷做種數, 判斷條件: peer_count:%d %s threshold:%d" % (
                            title, torrent_peer_count, peer_counts[0], min_count))
                        return False
                    if peer_counts[0] == "lt" and torrent_peer_count >= min_count:
                        log.debug("【Brush】%s `判斷做種數, 判斷條件: peer_count:%d %s threshold:%d" % (
                            title, torrent_peer_count, peer_counts[0], min_count))
                        return False
                    if peer_counts[0] == "bw" and not (min_count <= torrent_peer_count <= max_count):
                        log.debug("【Brush】%s `判斷做種數, 判斷條件: left:%d %s peer_count:%d %s right:%d" % (
                            title, min_count, peer_counts[0], torrent_peer_count, peer_counts[0], max_count))
                        return False

            # 檢查釋出時間
            if rss_rule.get("pubdate") and pubdate:
                rule_pubdates = rss_rule.get("pubdate").split("#")
                if len(rule_pubdates) >= 2 and rule_pubdates[1]:
                    localtz = pytz.timezone('Asia/Shanghai')
                    localnowtime = datetime.now().astimezone(localtz)
                    localpubdate = pubdate.astimezone(localtz)
                    log.debug('【Brush】釋出時間：%s，當前時間：%s' % (localpubdate.isoformat(), localnowtime.isoformat()))
                    if (localnowtime - localpubdate).seconds / 3600 > float(rule_pubdates[1]):
                        log.debug("【Brush】釋出時間不符合條件。")
                        return False

        except Exception as err:
            ExceptionUtils.exception_traceback(err)

        return True

    @staticmethod
    def __check_remove_rule(remove_rule, seeding_time=None, ratio=None, uploaded=None, dltime=None, avg_upspeed=None):
        """
        檢查是否符合刪種規則
        :param remove_rule: 刪種規則
        :param seeding_time: 做種時間
        :param ratio: 分享率
        :param uploaded: 上傳量
        :param dltime: 下載耗時
        :param avg_upspeed: 上傳平均速度
        """
        if not remove_rule:
            return False
        try:
            if remove_rule.get("time") and seeding_time:
                rule_times = remove_rule.get("time").split("#")
                if rule_times[0]:
                    if len(rule_times) > 1 and rule_times[1]:
                        if float(seeding_time) > float(rule_times[1]) * 3600:
                            return True, BrushDeleteType.SEEDTIME
            if remove_rule.get("ratio") and ratio:
                rule_ratios = remove_rule.get("ratio").split("#")
                if rule_ratios[0]:
                    if len(rule_ratios) > 1 and rule_ratios[1]:
                        if float(ratio) > float(rule_ratios[1]):
                            return True, BrushDeleteType.RATIO
            if remove_rule.get("uploadsize") and uploaded:
                rule_uploadsizes = remove_rule.get("uploadsize").split("#")
                if rule_uploadsizes[0]:
                    if len(rule_uploadsizes) > 1 and rule_uploadsizes[1]:
                        if float(uploaded) > float(rule_uploadsizes[1]) * 1024 ** 3:
                            return True, BrushDeleteType.UPLOADSIZE
            if remove_rule.get("dltime") and dltime:
                rule_times = remove_rule.get("dltime").split("#")
                if rule_times[0]:
                    if len(rule_times) > 1 and rule_times[1]:
                        if float(dltime) > float(rule_times[1]) * 3600:
                            return True, BrushDeleteType.DLTIME
            if remove_rule.get("avg_upspeed") and avg_upspeed:
                rule_avg_upspeeds = remove_rule.get("avg_upspeed").split("#")
                if rule_avg_upspeeds[0]:
                    if len(rule_avg_upspeeds) > 1 and rule_avg_upspeeds[1]:
                        if float(avg_upspeed) < float(rule_avg_upspeeds[1]) * 1024:
                            return True, BrushDeleteType.AVGUPSPEED
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
        return False, BrushDeleteType.NOTDELETE
