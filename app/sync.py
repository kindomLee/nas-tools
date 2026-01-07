import os
import threading
import traceback

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

import log
from app.helper import DbHelper
from app.utils.exception_utils import ExceptionUtils
from config import RMT_MEDIAEXT, Config
from app.filetransfer import FileTransfer
from app.utils.commons import singleton
from app.utils import PathUtils
from app.utils.types import SyncType, OsType, RMT_MODES

lock = threading.Lock()


class FileMonitorHandler(FileSystemEventHandler):
    """
    目錄監控響應類
    """

    def __init__(self, monpath, sync, **kwargs):
        super(FileMonitorHandler, self).__init__(**kwargs)
        self._watch_path = monpath
        self.sync = sync

    def on_created(self, event):
        self.sync.file_change_handler(event, "建立", event.src_path)

    def on_moved(self, event):
        self.sync.file_change_handler(event, "移動", event.dest_path)

    """
    def on_modified(self, event):
        self.sync.file_change_handler(event, "修改", event.src_path)
    """


@singleton
class Sync(object):
    filetransfer = None
    dbhelper = None

    sync_dir_config = {}
    _observer = []
    _sync_paths = []
    _sync_sys = OsType.LINUX
    _synced_files = []
    _need_sync_paths = {}

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.dbhelper = DbHelper()
        self.filetransfer = FileTransfer()
        sync = Config().get_config('sync')
        sync_paths = self.dbhelper.get_config_sync_paths()
        if sync and sync_paths:
            if sync.get('nas_sys') == "windows":
                self._sync_sys = OsType.WINDOWS
            self._sync_paths = sync_paths
            self.init_sync_dirs()

    def init_sync_dirs(self):
        """
        初始化監控檔案配置
        """
        self.sync_dir_config = {}
        if self._sync_paths:
            for sync_item in self._sync_paths:
                if not sync_item:
                    continue
                # 啟用標誌
                enabled = True if sync_item.ENABLED else False
                # 僅硬連結標誌
                only_link = False if sync_item.RENAME else True
                # 轉移方式
                path_syncmode = RMT_MODES.get(sync_item.MODE)
                # 源目錄|目的目錄|未知目錄
                monpath = sync_item.SOURCE
                target_path = sync_item.DEST
                unknown_path = sync_item.UNKNOWN
                if target_path and unknown_path:
                    log.info("【Sync】讀取到監控目錄：%s，目的目錄：%s，未識別目錄：%s，轉移方式：%s" % (
                        monpath, target_path, unknown_path, path_syncmode.value))
                elif target_path:
                    log.info(
                        "【Sync】讀取到監控目錄：%s，目的目錄：%s，轉移方式：%s" % (monpath, target_path, path_syncmode.value))
                else:
                    log.info("【Sync】讀取到監控目錄：%s，轉移方式：%s" % (monpath, path_syncmode.value))
                if not enabled:
                    log.info("【Sync】%s 不進行監控和同步：手動關閉" % monpath)
                    continue
                if only_link:
                    log.info("【Sync】%s 不進行識別和重新命名" % monpath)
                if target_path and not os.path.exists(target_path):
                    log.info("【Sync】目的目錄不存在，正在建立：%s" % target_path)
                    os.makedirs(target_path)
                if unknown_path and not os.path.exists(unknown_path):
                    log.info("【Sync】未識別目錄不存在，正在建立：%s" % unknown_path)
                    os.makedirs(unknown_path)
                # 登記關係
                if os.path.exists(monpath):
                    self.sync_dir_config[monpath] = {'target': target_path, 'unknown': unknown_path,
                                                     'onlylink': only_link, 'syncmod': path_syncmode}
                else:
                    log.error("【Sync】%s 目錄不存在！" % monpath)

    def get_sync_dirs(self):
        """
        返回所有的同步監控目錄
        """
        if not self.sync_dir_config:
            return []
        return [os.path.normpath(key) for key in self.sync_dir_config.keys()]

    def file_change_handler(self, event, text, event_path):
        """
        處理檔案變化
        :param event: 事件
        :param text: 事件描述
        :param event_path: 事件檔案路徑
        """
        if not event.is_directory:
            # 檔案發生變化
            try:
                if not os.path.exists(event_path):
                    return
                log.debug("【Sync】檔案%s：%s" % (text, event_path))
                # 判斷是否處理過了
                need_handler_flag = False
                try:
                    lock.acquire()
                    if event_path not in self._synced_files:
                        self._synced_files.append(event_path)
                        need_handler_flag = True
                finally:
                    lock.release()
                if not need_handler_flag:
                    log.debug("【Sync】檔案已處理過：%s" % event_path)
                    return
                # 不是監控目錄下的檔案不處理
                is_monitor_file = False
                for tpath in self.sync_dir_config.keys():
                    if PathUtils.is_path_in_path(tpath, event_path):
                        is_monitor_file = True
                        break
                if not is_monitor_file:
                    return
                # 目的目錄的子檔案不處理
                for tpath in self.sync_dir_config.values():
                    if not tpath:
                        continue
                    if PathUtils.is_path_in_path(tpath.get('target'), event_path):
                        return
                    if PathUtils.is_path_in_path(tpath.get('unknown'), event_path):
                        return
                # 媒體庫目錄及子目錄不處理
                if self.filetransfer.is_target_dir_path(event_path):
                    return
                # 回收站及隱藏的檔案不處理
                if PathUtils.is_invalid_path(event_path):
                    return
                # 上級目錄
                from_dir = os.path.dirname(event_path)
                # 找到是哪個監控目錄下的
                monitor_dir = event_path
                is_root_path = False
                for m_path in self.sync_dir_config.keys():
                    if PathUtils.is_path_in_path(m_path, event_path):
                        monitor_dir = m_path
                    if m_path == from_dir:
                        is_root_path = True

                # 查詢目的目錄
                target_dirs = self.sync_dir_config.get(monitor_dir)
                target_path = target_dirs.get('target')
                unknown_path = target_dirs.get('unknown')
                onlylink = target_dirs.get('onlylink')
                sync_mode = target_dirs.get('syncmod')

                # 只做硬連結，不做識別重新命名
                if onlylink:
                    if self.dbhelper.is_sync_in_history(event_path, target_path):
                        return
                    log.info("【Sync】開始同步 %s" % event_path)
                    ret, msg = self.filetransfer.link_sync_file(src_path=monitor_dir,
                                                                in_file=event_path,
                                                                target_dir=target_path,
                                                                sync_transfer_mode=sync_mode)
                    if ret != 0:
                        log.warn("【Sync】%s 同步失敗，錯誤碼：%s" % (event_path, ret))
                    elif not msg:
                        self.dbhelper.insert_sync_history(event_path, monitor_dir, target_path)
                        log.info("【Sync】%s 同步完成" % event_path)
                # 識別轉移
                else:
                    # 不是媒體檔案不處理
                    name = os.path.basename(event_path)
                    if not name:
                        return
                    if name.lower() != "index.bdmv":
                        ext = os.path.splitext(name)[-1]
                        if ext.lower() not in RMT_MEDIAEXT:
                            return
                    # 監控根目錄下的檔案發生變化時直接發走
                    if is_root_path:
                        ret, ret_msg = self.filetransfer.transfer_media(in_from=SyncType.MON,
                                                                        in_path=event_path,
                                                                        target_dir=target_path,
                                                                        unknown_dir=unknown_path,
                                                                        rmt_mode=sync_mode)
                        if not ret:
                            log.warn("【Sync】%s 轉移失敗：%s" % (event_path, ret_msg))
                    else:
                        try:
                            lock.acquire()
                            if self._need_sync_paths.get(from_dir):
                                files = self._need_sync_paths[from_dir].get('files')
                                if not files:
                                    files = [event_path]
                                else:
                                    if event_path not in files:
                                        files.append(event_path)
                                    else:
                                        return
                                self._need_sync_paths[from_dir].update({'files': files})
                            else:
                                self._need_sync_paths[from_dir] = {'target': target_path,
                                                                   'unknown': unknown_path,
                                                                   'syncmod': sync_mode,
                                                                   'files': [event_path]}
                        finally:
                            lock.release()
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error("【Sync】發生錯誤：%s - %s" % (str(e), traceback.format_exc()))

    def transfer_mon_files(self):
        """
        批次轉移檔案，由定時服務定期呼叫執行
        """
        try:
            lock.acquire()
            finished_paths = []
            for path in list(self._need_sync_paths):
                if not PathUtils.is_invalid_path(path) and os.path.exists(path):
                    log.info("【Sync】開始轉移監控目錄檔案...")
                    target_info = self._need_sync_paths.get(path)
                    bluray_dir = PathUtils.get_bluray_dir(path)
                    if not bluray_dir:
                        src_path = path
                        files = target_info.get('files')
                    else:
                        src_path = bluray_dir
                        files = []
                    if src_path not in finished_paths:
                        finished_paths.append(src_path)
                    else:
                        continue
                    target_path = target_info.get('target')
                    unknown_path = target_info.get('unknown')
                    sync_mode = target_info.get('syncmod')
                    ret, ret_msg = self.filetransfer.transfer_media(in_from=SyncType.MON,
                                                                    in_path=src_path,
                                                                    files=files,
                                                                    target_dir=target_path,
                                                                    unknown_dir=unknown_path,
                                                                    rmt_mode=sync_mode)
                    if not ret:
                        log.warn("【Sync】%s轉移失敗：%s" % (path, ret_msg))
                self._need_sync_paths.pop(path)
        finally:
            lock.release()

    def run_service(self):
        """
        啟動監控服務
        """
        self._observer = []
        for monpath in self.sync_dir_config.keys():
            if monpath and os.path.exists(monpath):
                try:
                    if self._sync_sys == OsType.WINDOWS:
                        # 考慮到windows的docker需要直接指定才能生效(修改配置檔案為windows)
                        observer = PollingObserver(timeout=10)
                    else:
                        # 內部處理系統操作型別選擇最優解
                        observer = Observer(timeout=10)
                    self._observer.append(observer)
                    observer.schedule(FileMonitorHandler(monpath, self), path=monpath, recursive=True)
                    observer.setDaemon(True)
                    observer.start()
                    log.info("%s 的監控服務啟動" % monpath)
                except Exception as e:
                    ExceptionUtils.exception_traceback(e)
                    log.error("%s 啟動目錄監控失敗：%s" % (monpath, str(e)))

    def stop_service(self):
        """
        關閉監控服務
        """
        if self._observer:
            for observer in self._observer:
                observer.stop()
        self._observer = []

    def transfer_all_sync(self):
        """
        全量轉移Sync目錄下的檔案，WEB介面點選目錄同步時獲發
        """
        for monpath, target_dirs in self.sync_dir_config.items():
            if not monpath:
                continue
            target_path = target_dirs.get('target')
            unknown_path = target_dirs.get('unknown')
            onlylink = target_dirs.get('onlylink')
            sync_mode = target_dirs.get('syncmod')
            # 只做硬連結，不做識別重新命名
            if onlylink:
                for link_file in PathUtils.get_dir_files(monpath):
                    if self.dbhelper.is_sync_in_history(link_file, target_path):
                        continue
                    log.info("【Sync】開始同步 %s" % link_file)
                    ret, msg = self.filetransfer.link_sync_file(src_path=monpath,
                                                                in_file=link_file,
                                                                target_dir=target_path,
                                                                sync_transfer_mode=sync_mode)
                    if ret != 0:
                        log.warn("【Sync】%s 同步失敗，錯誤碼：%s" % (link_file, ret))
                    elif not msg:
                        self.dbhelper.insert_sync_history(link_file, monpath, target_path)
                        log.info("【Sync】%s 同步完成" % link_file)
            else:
                for path in PathUtils.get_dir_level1_medias(monpath, RMT_MEDIAEXT):
                    if PathUtils.is_invalid_path(path):
                        continue
                    ret, ret_msg = self.filetransfer.transfer_media(in_from=SyncType.MON,
                                                                    in_path=path,
                                                                    target_dir=target_path,
                                                                    unknown_dir=unknown_path,
                                                                    rmt_mode=sync_mode)
                    if not ret:
                        log.error("【Sync】%s 處理失敗：%s" % (monpath, ret_msg))


def run_monitor():
    """
    啟動監控
    """
    try:
        Sync().run_service()
    except Exception as err:
        ExceptionUtils.exception_traceback(err)
        log.error("啟動目錄同步服務失敗：%s" % str(err))


def stop_monitor():
    """
    停止監控
    """
    try:
        Sync().stop_service()
    except Exception as err:
        ExceptionUtils.exception_traceback(err)
        log.error("停止目錄同步服務失敗：%s" % str(err))


def restart_monitor():
    """
    重啟監控
    """
    stop_monitor()
    run_monitor()
