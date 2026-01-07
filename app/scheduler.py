import datetime
import math
import random
import traceback

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

import log
from app.doubansync import DoubanSync
from app.downloader import Downloader
from app.helper import MetaHelper
from app.mediaserver import MediaServer
from app.rss import Rss
from app.sites import Sites
from app.subscribe import Subscribe
from app.sync import Sync
from app.utils.commons import singleton
from app.utils.exception_utils import ExceptionUtils
from config import PT_TRANSFER_INTERVAL, METAINFO_SAVE_INTERVAL, \
    SYNC_TRANSFER_INTERVAL, RSS_CHECK_INTERVAL, REFRESH_PT_DATA_INTERVAL, \
    RSS_REFRESH_TMDB_INTERVAL, META_DELETE_UNKNOWN_INTERVAL, REFRESH_WALLPAPER_INTERVAL, Config
from web.backend.wallpaper import get_login_wallpaper


@singleton
class Scheduler:
    SCHEDULER = None
    _pt = None
    _douban = None
    _media = None

    def __init__(self):
        self.init_config()

    def init_config(self):
        self._pt = Config().get_config('pt')
        self._media = Config().get_config('media')
        self._douban = Config().get_config('douban')

    def run_service(self):
        """
        讀取配置，啟動定時服務
        """
        self.SCHEDULER = BackgroundScheduler(timezone="Asia/Shanghai",
                                             executors={
                                                 'default': ThreadPoolExecutor(20)
                                             })
        if not self.SCHEDULER:
            return
        if self._pt:
            # 站點簽到
            ptsignin_cron = str(self._pt.get('ptsignin_cron'))
            if ptsignin_cron:
                if '-' in ptsignin_cron:
                    try:
                        time_range = ptsignin_cron.split("-")
                        start_time_range_str = time_range[0]
                        end_time_range_str = time_range[1]
                        start_time_range_array = start_time_range_str.split(":")
                        end_time_range_array = end_time_range_str.split(":")
                        start_hour = int(start_time_range_array[0])
                        start_minute = int(start_time_range_array[1])
                        end_hour = int(end_time_range_array[0])
                        end_minute = int(end_time_range_array[1])

                        def start_random_job():
                            task_time_count = random.randint(start_hour * 60 + start_minute, end_hour * 60 + end_minute)
                            self.start_data_site_signin_job(math.floor(task_time_count / 60), task_time_count % 60)

                        self.SCHEDULER.add_job(start_random_job,
                                               "cron",
                                               hour=start_hour,
                                               minute=start_minute)
                        log.info("站點自動簽到服務時間範圍隨機模式啟動，起始時間於%s:%s" % (
                            str(start_hour).rjust(2, '0'), str(start_minute).rjust(2, '0')))
                    except Exception as e:
                        ExceptionUtils.exception_traceback(e)
                        log.info("站點自動簽到時間 時間範圍隨機模式 配置格式錯誤：%s %s" % (ptsignin_cron, str(e)))
                elif ptsignin_cron.find(':') != -1:
                    try:
                        hour = int(ptsignin_cron.split(":")[0])
                        minute = int(ptsignin_cron.split(":")[1])
                    except Exception as e:
                        ExceptionUtils.exception_traceback(e)
                        log.info("站點自動簽到時間 配置格式錯誤：%s" % str(e))
                        hour = minute = 0
                    self.SCHEDULER.add_job(Sites().signin,
                                           "cron",
                                           hour=hour,
                                           minute=minute)
                    log.info("站點自動簽到服務啟動")
                else:
                    try:
                        hours = float(ptsignin_cron)
                    except Exception as e:
                        ExceptionUtils.exception_traceback(e)
                        log.info("站點自動簽到時間 配置格式錯誤：%s" % str(e))
                        hours = 0
                    if hours:
                        self.SCHEDULER.add_job(Sites().signin,
                                               "interval",
                                               hours=hours)
                        log.info("站點自動簽到服務啟動")

            # 下載檔案轉移
            pt_monitor = self._pt.get('pt_monitor')
            if pt_monitor:
                self.SCHEDULER.add_job(Downloader().transfer, 'interval', seconds=PT_TRANSFER_INTERVAL)
                log.info("下載檔案轉移服務啟動")

            # RSS下載器
            pt_check_interval = self._pt.get('pt_check_interval')
            if pt_check_interval:
                if isinstance(pt_check_interval, str) and pt_check_interval.isdigit():
                    pt_check_interval = int(pt_check_interval)
                else:
                    try:
                        pt_check_interval = round(float(pt_check_interval))
                    except Exception as e:
                        ExceptionUtils.exception_traceback(e)
                        log.error("RSS訂閱週期 配置格式錯誤：%s" % str(e))
                        pt_check_interval = 0
                if pt_check_interval:
                    self.SCHEDULER.add_job(Rss().rssdownload, 'interval', seconds=round(pt_check_interval))
                    log.info("RSS訂閱服務啟動")

            # RSS訂閱定時檢索
            search_rss_interval = self._pt.get('search_rss_interval')
            if search_rss_interval:
                if isinstance(search_rss_interval, str) and search_rss_interval.isdigit():
                    search_rss_interval = int(search_rss_interval)
                else:
                    try:
                        search_rss_interval = round(float(search_rss_interval))
                    except Exception as e:
                        ExceptionUtils.exception_traceback(e)
                        log.error("訂閱定時搜尋週期 配置格式錯誤：%s" % str(e))
                        search_rss_interval = 0
                if search_rss_interval:
                    self.SCHEDULER.add_job(Subscribe().subscribe_search_all, 'interval', hours=search_rss_interval * 24)
                    log.info("訂閱定時搜尋服務啟動")

        # 豆瓣電影同步
        if self._douban:
            douban_interval = self._douban.get('interval')
            if douban_interval:
                if isinstance(douban_interval, str):
                    if douban_interval.isdigit():
                        douban_interval = int(douban_interval)
                    else:
                        try:
                            douban_interval = float(douban_interval)
                        except Exception as e:
                            ExceptionUtils.exception_traceback(e)
                            log.info("豆瓣同步服務啟動失敗：%s" % str(e))
                            douban_interval = 0
                if douban_interval:
                    self.SCHEDULER.add_job(DoubanSync().sync, 'interval', hours=douban_interval)
                    log.info("豆瓣同步服務啟動")

        # 媒體庫同步
        if self._media:
            mediasync_interval = self._media.get("mediasync_interval")
            if mediasync_interval:
                if isinstance(mediasync_interval, str):
                    if mediasync_interval.isdigit():
                        mediasync_interval = int(mediasync_interval)
                    else:
                        try:
                            mediasync_interval = round(float(mediasync_interval))
                        except Exception as e:
                            ExceptionUtils.exception_traceback(e)
                            log.info("豆瓣同步服務啟動失敗：%s" % str(e))
                            mediasync_interval = 0
                if mediasync_interval:
                    self.SCHEDULER.add_job(MediaServer().sync_mediaserver, 'interval', hours=mediasync_interval)
                    log.info("媒體庫同步服務啟動")

        # 後設資料定時儲存
        self.SCHEDULER.add_job(MetaHelper().save_meta_data, 'interval', seconds=METAINFO_SAVE_INTERVAL)

        # 定時把佇列中的監控檔案轉移走
        self.SCHEDULER.add_job(Sync().transfer_mon_files, 'interval', seconds=SYNC_TRANSFER_INTERVAL)

        # RSS佇列中檢索
        self.SCHEDULER.add_job(Subscribe().subscribe_search, 'interval', seconds=RSS_CHECK_INTERVAL)

        # 站點資料重新整理
        self.SCHEDULER.add_job(Sites().refresh_pt_date_now,
                               'interval',
                               hours=REFRESH_PT_DATA_INTERVAL,
                               next_run_time=datetime.datetime.now() + datetime.timedelta(minutes=1))

        # 豆瓣RSS轉TMDB，定時更新TMDB資料
        self.SCHEDULER.add_job(Subscribe().refresh_rss_metainfo, 'interval', hours=RSS_REFRESH_TMDB_INTERVAL)

        # 定時清除未識別的快取
        self.SCHEDULER.add_job(MetaHelper().delete_unknown_meta, 'interval', hours=META_DELETE_UNKNOWN_INTERVAL)

        # 定時重新整理桌布
        self.SCHEDULER.add_job(get_login_wallpaper,
                               'interval',
                               hours=REFRESH_WALLPAPER_INTERVAL,
                               next_run_time=datetime.datetime.now())

        self.SCHEDULER.print_jobs()

        self.SCHEDULER.start()

    def stop_service(self):
        """
        停止定時服務
        """
        try:
            if self.SCHEDULER:
                self.SCHEDULER.remove_all_jobs()
                self.SCHEDULER.shutdown()
                self.SCHEDULER = None
        except Exception as e:
            ExceptionUtils.exception_traceback(e)

    def start_data_site_signin_job(self, hour, minute):
        year = datetime.datetime.now().year
        month = datetime.datetime.now().month
        day = datetime.datetime.now().day
        # 隨機數從1秒開始，不在整點簽到
        second = random.randint(1, 59)
        log.info("站點自動簽到時間 即將在%s-%s-%s,%s:%s:%s簽到" % (
            str(year), str(month), str(day), str(hour), str(minute), str(second)))
        if hour < 0 or hour > 24:
            hour = -1
        if minute < 0 or minute > 60:
            minute = -1
        if hour < 0 or minute < 0:
            log.warn("站點自動簽到時間 配置格式錯誤：不啟動任務")
            return
        self.SCHEDULER.add_job(Sites().signin,
                               "date",
                               run_date=datetime.datetime(year, month, day, hour, minute, second))


def run_scheduler():
    """
    啟動定時服務
    """
    try:
        Scheduler().run_service()
    except Exception as err:
        ExceptionUtils.exception_traceback(err)
        log.error("啟動定時服務失敗：%s - %s" % (str(err), traceback.format_exc()))


def stop_scheduler():
    """
    停止定時服務
    """
    try:
        Scheduler().stop_service()
    except Exception as err:
        ExceptionUtils.exception_traceback(err)
        log.debug("停止定時服務失敗：%s" % str(err))


def restart_scheduler():
    """
    重啟定時服務
    """
    stop_scheduler()
    run_scheduler()
