import json
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler

import log
from app.downloader import Downloader
from app.helper import DbHelper
from app.message import Message
from app.utils.commons import singleton
from app.utils.exception_utils import ExceptionUtils
from app.utils.types import DownloaderType

lock = Lock()


@singleton
class TorrentRemover(object):
    message = None
    downloader = None
    dbhelper = None

    _scheduler = None
    _remove_tasks = {}

    # 適用下載器
    TORRENTREMOVER_DICT = {
        "Qb": {
            "name": "Qbittorrent",
            "img_url": "../static/img/qbittorrent.png",
            "downloader_type": DownloaderType.QB,
            "torrent_state": {
                "downloading": "正在下載_傳輸資料",
                "stalledDL": "正在下載_未建立連線",
                "uploading": "正在上傳_傳輸資料",
                "stalledUP": "正在上傳_未建立連線",
                "error": "暫停_發生錯誤",
                "pausedDL": "暫停_下載未完成",
                "pausedUP": "暫停_下載完成",
                "missingFiles": "暫停_檔案丟失",
                "checkingDL": "檢查中_下載未完成",
                "checkingUP": "檢查中_下載完成",
                "checkingResumeData": "檢查中_啟動時恢復資料",
                "forcedDL": "強制下載_忽略佇列",
                "queuedDL": "等待下載_排隊",
                "forcedUP": "強制上傳_忽略佇列",
                "queuedUP": "等待上傳_排隊",
                "allocating": "分配磁碟空間",
                "metaDL": "獲取後設資料",
                "moving": "移動檔案",
                "unknown": "未知狀態",
            }
        },
        "Tr": {
            "name": "Transmission",
            "img_url": "../static/img/transmission.png",
            "downloader_type": DownloaderType.TR,
            "torrent_state": {
                "downloading": "正在下載",
                "seeding": "正在上傳",
                "download_pending": "等待下載_排隊",
                "seed_pending": "等待上傳_排隊",
                "checking": "正在檢查",
                "check_pending": "等待檢查_排隊",
                "stopped": "暫停",
            }
        }
    }

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.message = Message()
        self.downloader = Downloader()
        self.dbhelper = DbHelper()
        # 移出現有任務
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
        # 讀取任務任務列表
        removetasks = self.dbhelper.get_torrent_remove_tasks()
        self._remove_tasks = {}
        for task in removetasks:
            config = task.CONFIG
            self._remove_tasks[str(task.ID)] = {
                "id": task.ID,
                "name": task.NAME,
                "downloader": task.DOWNLOADER,
                "onlynastool": task.ONLYNASTOOL,
                "samedata": task.SAMEDATA,
                "action": task.ACTION,
                "config": json.loads(config) if config else {},
                "interval": task.INTERVAL,
                "enabled": task.ENABLED,
            }
        if not self._remove_tasks:
            return
        # 啟動刪種任務
        self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        remove_flag = False
        for task in self._remove_tasks.values():
            if task.get("enabled") and task.get("interval") and task.get("config"):
                remove_flag = True
                self._scheduler.add_job(func=self.auto_remove_torrents,
                                        args=[task.get("id")],
                                        trigger='interval',
                                        seconds=int(task.get("interval")) * 60)
        if remove_flag:
            self._scheduler.print_jobs()
            self._scheduler.start()
            log.info("自動刪種服務啟動")

    def get_torrent_remove_tasks(self, taskid=None):
        """
        獲取刪種任務詳細資訊
        """
        if taskid:
            task = self._remove_tasks.get(str(taskid))
            return task if task else {}
        return self._remove_tasks

    def auto_remove_torrents(self, taskids=None):
        """
        處理自動刪種任務，由定時服務呼叫
        :param taskids: 自動刪種任務的ID
        """
        # 獲取自動刪種任務
        tasks = []
        # 如果沒有指定任務ID，則處理所有啟用任務
        if not taskids:
            for task in self._remove_tasks.values():
                if task.get("enabled") and task.get("interval") and task.get("config"):
                    tasks.append(task)
        # 如果指定任務id，則處理指定任務無論是否啟用
        elif isinstance(taskids, list):
            for taskid in taskids:
                task = self._remove_tasks.get(str(taskid))
                if task:
                    tasks.append(task)
        else:
            task = self._remove_tasks.get(str(taskids))
            tasks = [task] if task else []
        if not tasks:
            return
        for task in tasks:
            try:
                lock.acquire()
                # 獲取需刪除種子列表
                downloader_type = self.TORRENTREMOVER_DICT.get(task.get("downloader")).get("downloader_type")
                task.get("config")["samedata"] = task.get("samedata")
                task.get("config")["onlynastool"] = task.get("onlynastool")
                torrents = self.downloader.get_remove_torrents(
                    downloader=downloader_type,
                    config=task.get("config")
                )
                log.info(f"【TorrentRemover】自動刪種任務：{task.get('name')} 獲取符合處理條件種子數 {len(torrents)}")
                title = f"自動刪種任務：{task.get('name')}"
                text = ""
                if task.get("action") == 1:
                    text = f"共暫停{len(torrents)}個種子"
                    for torrent in torrents:
                        name = torrent.get("name")
                        site = torrent.get("site")
                        size = round(torrent.get("size")/1021/1024/1024, 3)
                        text_item = f"{name} 來自站點：{site} 大小：{size} GB"
                        log.info(f"【TorrentRemover】暫停種子：{text_item}")
                        text = f"{text}\n{text_item}"
                        # 暫停種子
                        self.downloader.stop_torrents(downloader=downloader_type,
                                                      ids=[torrent.get("id")])
                elif task.get("action") == 2:
                    text = f"共刪除{len(torrents)}個種子"
                    for torrent in torrents:
                        name = torrent.get("name")
                        site = torrent.get("site")
                        size = round(torrent.get("size") / 1021 / 1024 / 1024, 3)
                        text_item = f"{name} 來自站點：{site} 大小：{size} GB"
                        log.info(f"【TorrentRemover】刪除種子：{text_item}")
                        text = f"{text}\n{text_item}"
                        # 刪除種子
                        self.downloader.delete_torrents(downloader=downloader_type,
                                                        delete_file=False,
                                                        ids=[torrent.get("id")])
                elif task.get("action") == 3:
                    text = f"共刪除{len(torrents)}個種子（及檔案）"
                    for torrent in torrents:
                        name = torrent.get("name")
                        site = torrent.get("site")
                        size = round(torrent.get("size") / 1021 / 1024 / 1024, 3)
                        text_item = f"{name} 來自站點：{site} 大小：{size} GB"
                        log.info(f"【TorrentRemover】刪除種子及檔案：{text_item}")
                        text = f"{text}\n{text_item}"
                        # 刪除種子
                        self.downloader.delete_torrents(downloader=downloader_type,
                                                        delete_file=True,
                                                        ids=[torrent.get("id")])
                if torrents and title and text:
                    self.message.send_brushtask_remove_message(title=title, text=text)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error(f"【TorrentRemover】自動刪種任務：{task.get('name')}異常：{str(e)}")
            finally:
                lock.release()

    def update_torrent_remove_task(self, data):
        """
        更新自動刪種任務
        """
        tid = data.get("tid")
        name = data.get("name")
        if not name:
            return False, "名稱引數不合法"
        action = data.get("action")
        if not str(action).isdigit() or int(action) not in [1, 2, 3]:
            return False, "動作引數不合法"
        else:
            action = int(action)
        interval = data.get("interval")
        if not str(interval).isdigit():
            return False, "執行間隔引數不合法"
        else:
            interval = int(interval)
        enabled = data.get("enabled")
        if not str(enabled).isdigit() or int(enabled) not in [0, 1]:
            return False, "狀態引數不合法"
        else:
            enabled = int(enabled)
        samedata = data.get("samedata")
        if not str(enabled).isdigit() or int(samedata) not in [0, 1]:
            return False, "處理輔種引數不合法"
        else:
            samedata = int(samedata)
        onlynastool = data.get("onlynastool")
        if not str(enabled).isdigit() or int(onlynastool) not in [0, 1]:
            return False, "僅處理NASTOOL新增種子引數不合法"
        else:
            onlynastool = int(onlynastool)
        ratio = data.get("ratio") or 0
        if not str(ratio).replace(".", "").isdigit():
            return False, "分享率引數不合法"
        else:
            ratio = round(float(ratio), 2)
        seeding_time = data.get("seeding_time") or 0
        if not str(seeding_time).isdigit():
            return False, "做種時間引數不合法"
        else:
            seeding_time = int(seeding_time)
        upload_avs = data.get("upload_avs") or 0
        if not str(upload_avs).isdigit():
            return False, "平均上傳速度引數不合法"
        else:
            upload_avs = int(upload_avs)
        size = data.get("size")
        size = str(size).split("-") if size else []
        if size and (len(size) != 2 or not str(size[0]).isdigit() or not str(size[-1]).isdigit()):
            return False, "種子大小引數不合法"
        else:
            size = [int(size[0]), int(size[-1])] if size else []
        tags = data.get("tags")
        tags = tags.split(";") if tags else []
        tags = [tag for tag in tags if tag]
        savepath_key = data.get("savepath_key")
        tracker_key = data.get("tracker_key")
        downloader = data.get("downloader")
        if downloader not in self.TORRENTREMOVER_DICT.keys():
            return False, "下載器引數不合法"
        if downloader == "Qb":
            qb_state = data.get("qb_state")
            qb_state = qb_state.split(";") if qb_state else []
            qb_state = [state for state in qb_state if state]
            if qb_state:
                for qb_state_item in qb_state:
                    if qb_state_item not in self.TORRENTREMOVER_DICT.get("Qb").get("torrent_state").keys():
                        return False, "種子狀態引數不合法"
            qb_category = data.get("qb_category")
            qb_category = qb_category.split(";") if qb_category else []
            qb_category = [category for category in qb_category if category]
            tr_state = []
            tr_error_key = ""
        else:
            qb_state = []
            qb_category = []
            tr_state = data.get("tr_state")
            tr_state = tr_state.split(";") if tr_state else []
            tr_state = [state for state in tr_state if state]
            if tr_state:
                for tr_state_item in tr_state:
                    if tr_state_item not in self.TORRENTREMOVER_DICT.get("Tr").get("torrent_state").keys():
                        return False, "種子狀態引數不合法"
            tr_error_key = data.get("tr_error_key")
        config = {
            "ratio": ratio,
            "seeding_time": seeding_time,
            "upload_avs": upload_avs,
            "size": size,
            "tags": tags,
            "savepath_key": savepath_key,
            "tracker_key": tracker_key,
            "qb_state": qb_state,
            "qb_category": qb_category,
            "tr_state": tr_state,
            "tr_error_key": tr_error_key,
        }
        if tid:
            self.dbhelper.delete_torrent_remove_task(tid=tid)
        self.dbhelper.insert_torrent_remove_task(
            name=name,
            action=action,
            interval=interval,
            enabled=enabled,
            samedata=samedata,
            onlynastool=onlynastool,
            downloader=downloader,
            config=config,
        )
        return True, "更新成功"

    def delete_torrent_remove_task(self, taskid=None):
        """
        刪除自動刪種任務
        """
        if not taskid:
            return False
        else:
            self.dbhelper.delete_torrent_remove_task(tid=taskid)
            return True

    def get_remove_torrents(self, taskid):
        """
        獲取滿足自動刪種任務的種子
        """
        task = self._remove_tasks.get(str(taskid))
        if not task:
            return False, []
        else:
            task.get("config")["samedata"] = task.get("samedata")
            task.get("config")["onlynastool"] = task.get("onlynastool")
            torrents = self.downloader.get_remove_torrents(
                downloader=self.TORRENTREMOVER_DICT.get(task.get("downloader")).get("downloader_type"),
                config=task.get("config")
            )
            return True, torrents
