from flask import Blueprint, request
from flask_restx import Api, reqparse, Resource

from app.brushtask import BrushTask
from app.rsschecker import RssChecker
from app.sites import Sites
from app.utils import TokenCache
from config import Config
from web.action import WebAction
from web.backend.user import User
from web.security import require_auth, login_required, generate_access_token

apiv1_bp = Blueprint("apiv1",
                     __name__,
                     static_url_path='',
                     static_folder='./frontend/static/',
                     template_folder='./frontend/', )
Apiv1 = Api(apiv1_bp,
            version="1.0",
            title="NAStool Api",
            description="POST介面呼叫 /user/login 獲取Token，GET介面使用 基礎設定->安全->Api Key 呼叫",
            doc="/",
            security='Bearer Auth',
            authorizations={"Bearer Auth": {"type": "apiKey", "name": "Authorization", "in": "header"}},
            )
# API分組
user = Apiv1.namespace('user', description='使用者')
system = Apiv1.namespace('system', description='系統')
config = Apiv1.namespace('config', description='設定')
site = Apiv1.namespace('site', description='站點')
service = Apiv1.namespace('service', description='服務')
subscribe = Apiv1.namespace('subscribe', description='訂閱')
rss = Apiv1.namespace('rss', description='自定義RSS')
recommend = Apiv1.namespace('recommend', description='推薦')
search = Apiv1.namespace('search', description='搜尋')
download = Apiv1.namespace('download', description='下載')
organization = Apiv1.namespace('organization', description='整理')
torrentremover = Apiv1.namespace('torrentremover', description='自動刪種')
library = Apiv1.namespace('library', description='媒體庫')
brushtask = Apiv1.namespace('brushtask', description='刷流')
media = Apiv1.namespace('media', description='媒體')
sync = Apiv1.namespace('sync', description='目錄同步')
filterrule = Apiv1.namespace('filterrule', description='過濾規則')
words = Apiv1.namespace('words', description='識別詞')
message = Apiv1.namespace('message', description='訊息通知')
douban = Apiv1.namespace('douban', description='豆瓣')


class ApiResource(Resource):
    """
    API 認證
    """
    method_decorators = [require_auth]


class ClientResource(Resource):
    """
    登入認證
    """
    method_decorators = [login_required]


def Failed():
    """
    返回失敗報名
    """
    return {
        "code": -1,
        "success": False,
        "data": {}
    }


@user.route('/login')
class UserLogin(Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('username', type=str, help='使用者名稱', location='form', required=True)
    parser.add_argument('password', type=str, help='密碼', location='form', required=True)

    @user.doc(parser=parser)
    def post(self):
        """
        使用者登入
        """
        args = self.parser.parse_args()
        username = args.get('username')
        password = args.get('password')
        if not username or not password:
            return {"code": 1, "success": False, "message": "使用者名稱或密碼錯誤"}
        user_info = User().get_user(username)
        if not user_info:
            return {"code": 1, "success": False, "message": "使用者名稱或密碼錯誤"}
        # 校驗密碼
        if not user_info.verify_password(password):
            return {"code": 1, "success": False, "message": "使用者名稱或密碼錯誤"}
        # 快取Token
        token = generate_access_token(username)
        TokenCache.set(token, token)
        return {
            "code": 0,
            "success": True,
            "data": {
                "token": token,
                "apikey": Config().get_config("security").get("api_key"),
                "userinfo": {
                    "userid": user_info.id,
                    "username": user_info.username,
                    "userpris": str(user_info.pris).split(",")
                }
            }
        }


@user.route('/info')
class UserInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('username', type=str, help='使用者名稱', location='form', required=True)

    @user.doc(parser=parser)
    def post(self):
        """
        獲取使用者資訊
        """
        args = self.parser.parse_args()
        username = args.get('username')
        user_info = User().get_user(username)
        if not user_info:
            return {"code": 1, "success": False, "message": "使用者名稱不正確"}
        return {
            "code": 0,
            "success": True,
            "data": {
                "userid": user_info.id,
                "username": user_info.username,
                "userpris": str(user_info.pris).split(",")
            }
        }


@user.route('/manage')
class UserManage(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('oper', type=str, help='操作型別（add 新增/del刪除）', location='form', required=True)
    parser.add_argument('name', type=str, help='使用者名稱', location='form', required=True)
    parser.add_argument('pris', type=str, help='許可權', location='form')

    @user.doc(parser=parser)
    def post(self):
        """
        使用者管理
        """
        return WebAction().api_action(cmd='user_manager', data=self.parser.parse_args())


@user.route('/list')
class UserList(ClientResource):
    @staticmethod
    def post():
        """
        查詢所有使用者
        """
        return WebAction().api_action(cmd='get_users')


@service.route('/mediainfo')
class ServiceMediaInfo(ApiResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='名稱', location='args', required=True)

    @service.doc(parser=parser)
    def get(self):
        """
        識別媒體資訊（金鑰認證）
        """
        return WebAction().api_action(cmd='name_test', data=self.parser.parse_args())


@service.route('/name/test')
class ServiceNameTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='名稱', location='form', required=True)

    @service.doc(parser=parser)
    def post(self):
        """
        名稱識別測試
        """
        return WebAction().api_action(cmd='name_test', data=self.parser.parse_args())


@service.route('/rule/test')
class ServiceRuleTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('title', type=str, help='名稱', location='form', required=True)
    parser.add_argument('subtitle', type=str, help='描述', location='form')
    parser.add_argument('size', type=float, help='大小（GB）', location='form')

    @service.doc(parser=parser)
    def post(self):
        """
        過濾規則測試
        """
        return WebAction().api_action(cmd='rule_test', data=self.parser.parse_args())


@service.route('/network/test')
class ServiceNetworkTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('url', type=str, help='URL地址', location='form', required=True)

    @service.doc(parser=parser)
    def post(self):
        """
        網路連線性測試
        """
        return WebAction().api_action(cmd='net_test', data=self.parser.parse_args().get("url"))


@service.route('/run')
class ServiceRun(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('item', type=str,
                        help='服務名稱（autoremovetorrents、pttransfer、ptsignin、sync、rssdownload、douban、subscribe_search_all）',
                        location='form',
                        required=True)

    @service.doc(parser=parser)
    def post(self):
        """
        執行服務
        """
        return WebAction().api_action(cmd='sch', data=self.parser.parse_args())


@site.route('/statistics')
class SiteStatistic(ApiResource):
    @staticmethod
    def get():
        """
        獲取站點資料明細（金鑰認證）
        """
        # 返回站點資訊
        return {
            "code": 0,
            "success": True,
            "data": {
                "user_statistics": Sites().get_site_user_statistics(encoding="DICT")
            }
        }


@site.route('/sites')
class SiteSites(ApiResource):
    @staticmethod
    def get():
        """
        獲取所有站點配置（金鑰認證）
        """
        return {
            "code": 0,
            "success": True,
            "data": {
                "user_sites": Sites().get_sites()
            }
        }


@site.route('/update')
class SiteUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('site_name', type=str, help='站點名稱', location='form', required=True)
    parser.add_argument('site_id', type=int, help='更新站點ID', location='form')
    parser.add_argument('site_pri', type=str, help='優先順序', location='form')
    parser.add_argument('site_rssurl', type=str, help='RSS地址', location='form')
    parser.add_argument('site_signurl', type=str, help='站點地址', location='form')
    parser.add_argument('site_cookie', type=str, help='Cookie', location='form')
    parser.add_argument('site_note', type=str, help='站點屬性', location='form')
    parser.add_argument('site_include', type=str, help='站點用途', location='form')

    @site.doc(parser=parser)
    def post(self):
        """
        新增/刪除站點
        """
        return WebAction().api_action(cmd='update_site', data=self.parser.parse_args())


@site.route('/info')
class SiteInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='站點ID', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        查詢單個站點詳情
        """
        return WebAction().api_action(cmd='get_site', data=self.parser.parse_args())


@site.route('/favicon')
class SiteFavicon(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='站點名稱', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        獲取站點圖示(Base64)
        """
        return WebAction().api_action(cmd='get_site_favicon', data=self.parser.parse_args())


@site.route('/test')
class SiteTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='站點ID', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        測試站點連通性
        """
        return WebAction().api_action(cmd='test_site', data=self.parser.parse_args())


@site.route('/delete')
class SiteDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='站點ID', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        刪除站點
        """
        return WebAction().api_action(cmd='del_site', data=self.parser.parse_args())


@site.route('/statistics/activity')
class SiteStatisticsActivity(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='站點名稱', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        查詢站點 上傳/下載/做種資料
        """
        return WebAction().api_action(cmd='get_site_activity', data=self.parser.parse_args())


@site.route('/check')
class SiteCheck(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('url', type=str, help='站點地址', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        檢查站點是否支援FREE/HR檢測
        """
        return WebAction().api_action(cmd='check_site_attr', data=self.parser.parse_args())


@site.route('/statistics/history')
class SiteStatisticsHistory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('days', type=int, help='時間範圍（天）', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        查詢所有站點歷史資料
        """
        return WebAction().api_action(cmd='get_site_history', data=self.parser.parse_args())


@site.route('/statistics/seedinfo')
class SiteStatisticsSeedinfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='站點名稱', location='form', required=True)

    @site.doc(parser=parser)
    def post(self):
        """
        查詢站點做種分佈
        """
        return WebAction().api_action(cmd='get_site_seeding_info', data=self.parser.parse_args())


@site.route('/resources')
class SiteResources(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='站點索引ID', location='form', required=True)
    parser.add_argument('page', type=int, help='頁碼', location='form')
    parser.add_argument('keyword', type=str, help='站點名稱', location='form')

    @site.doc(parser=parser)
    def post(self):
        """
        查詢站點資源列表
        """
        return WebAction().api_action(cmd='list_site_resources', data=self.parser.parse_args())


@site.route('/list')
class SiteList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('basic', type=int, help='只查詢基本資訊（0-否/1-是）', location='form')
    parser.add_argument('rss', type=int, help='訂閱（0-否/1-是）', location='form')
    parser.add_argument('brush', type=int, help='刷流（0-否/1-是）', location='form')
    parser.add_argument('signin', type=int, help='簽到（0-否/1-是）', location='form')
    parser.add_argument('statistic', type=int, help='資料統計（0-否/1-是）', location='form')

    def post(self):
        """
        查詢站點列表
        """
        return WebAction().api_action(cmd='get_sites', data=self.parser.parse_args())


@site.route('/indexers')
class SiteIndexers(ClientResource):

    @staticmethod
    def post():
        """
        查詢站點索引列表
        """
        return WebAction().api_action(cmd='get_indexers')


@search.route('/keyword')
class SearchKeyword(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('search_word', type=str, help='搜尋關鍵字', location='form', required=True)
    parser.add_argument('unident', type=int, help='快速模式（0-否/1-是）', location='form')
    parser.add_argument('filters', type=str, help='過濾條件', location='form')
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form')
    parser.add_argument('media_type', type=str, help='型別（電影/電視劇）', location='form')

    @search.doc(parser=parser)
    def post(self):
        """
        根據關鍵字/TMDBID搜尋
        """
        return WebAction().api_action(cmd='search', data=self.parser.parse_args())


@search.route('/result')
class SearchResult(ClientResource):
    @staticmethod
    def post():
        """
        查詢搜尋結果
        """
        return WebAction().api_action(cmd='get_search_result')


@download.route('/search')
class DownloadSearch(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='搜尋結果ID', location='form', required=True)
    parser.add_argument('dir', type=str, help='儲存目錄', location='form')
    parser.add_argument('setting', type=str, help='下載設定', location='form')

    @download.doc(parser=parser)
    def post(self):
        """
        下載搜尋結果
        """
        return WebAction().api_action(cmd='download', data=self.parser.parse_args())


@download.route('/item')
class DownloadItem(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('enclosure', type=str, help='連結URL', location='form', required=True)
    parser.add_argument('title', type=str, help='標題', location='form', required=True)
    parser.add_argument('site', type=str, help='站點名稱', location='form')
    parser.add_argument('description', type=str, help='描述', location='form')
    parser.add_argument('page_url', type=str, help='詳情頁面URL', location='form')
    parser.add_argument('size', type=str, help='大小', location='form')
    parser.add_argument('seeders', type=str, help='做種數', location='form')
    parser.add_argument('uploadvolumefactor', type=float, help='上傳因子', location='form')
    parser.add_argument('downloadvolumefactor', type=float, help='下載因子', location='form')
    parser.add_argument('dl_dir', type=str, help='儲存目錄', location='form')

    @download.doc(parser=parser)
    def post(self):
        """
        下載連結
        """
        return WebAction().api_action(cmd='download_link', data=self.parser.parse_args())


@download.route('/start')
class DownloadStart(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='任務ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        開始下載任務
        """
        return WebAction().api_action(cmd='pt_start', data=self.parser.parse_args())


@download.route('/stop')
class DownloadStop(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='任務ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        暫停下載任務
        """
        return WebAction().api_action(cmd='pt_stop', data=self.parser.parse_args())


@download.route('/info')
class DownloadInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('ids', type=str, help='任務IDS', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        查詢下載進度
        """
        return WebAction().api_action(cmd='pt_info', data=self.parser.parse_args())


@download.route('/remove')
class DownloadRemove(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='任務ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        刪除下載任務
        """
        return WebAction().api_action(cmd='pt_remove', data=self.parser.parse_args())


@download.route('/history')
class DownloadHistory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('page', type=str, help='第幾頁', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        查詢下載歷史
        """
        return WebAction().api_action(cmd='get_downloaded', data=self.parser.parse_args())


@download.route('/now')
class DownloadNow(ClientResource):
    @staticmethod
    def post():
        """
        查詢正在下載的任務
        """
        return WebAction().api_action(cmd='get_downloading')


@download.route('/config/info')
class DownloadConfigInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='下載設定ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        查詢下載設定
        """
        return WebAction().api_action(cmd='get_download_setting', data=self.parser.parse_args())


@download.route('/config/update')
class DownloadConfigUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='下載設定ID', location='form', required=True)
    parser.add_argument('name', type=str, help='名稱', location='form', required=True)
    parser.add_argument('category', type=str, help='分類', location='form')
    parser.add_argument('tags', type=str, help='標籤', location='form')
    parser.add_argument('content_layout', type=int, help='佈局（0-全域性/1-原始/2-建立子資料夾/3-不建子資料夾）', location='form')
    parser.add_argument('is_paused', type=int, help='動作（0-新增後開始/1-新增後暫停）', location='form')
    parser.add_argument('upload_limit', type=int, help='上傳速度限制', location='form')
    parser.add_argument('download_limit', type=int, help='下載速度限制', location='form')
    parser.add_argument('ratio_limit', type=int, help='分享率限制', location='form')
    parser.add_argument('seeding_time_limit', type=int, help='做種時間限制', location='form')
    parser.add_argument('downloader', type=str, help='下載器（Qbittorrent/Transmission/115網盤/Aria2）', location='form')

    @download.doc(parser=parser)
    def post(self):
        """
        新增/修改下載設定
        """
        return WebAction().api_action(cmd='update_download_setting', data=self.parser.parse_args())


@download.route('/config/delete')
class DownloadConfigDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='下載設定ID', location='form', required=True)

    @download.doc(parser=parser)
    def post(self):
        """
        刪除下載設定
        """
        return WebAction().api_action(cmd='delete_download_setting', data=self.parser.parse_args())


@download.route('/config/list')
class DownloadConfigList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='ID', location='form')

    def post(self):
        """
        查詢下載設定
        """
        return WebAction().api_action(cmd="get_download_setting", data=self.parser.parse_args())


@download.route('/config/directory')
class DownloadConfigDirectory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=str, help='下載設定ID', location='form')

    def post(self):
        """
        查詢下載儲存目錄
        """
        return WebAction().api_action(cmd="get_download_dirs", data=self.parser.parse_args())


@organization.route('/unknown/delete')
class UnknownDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='未識別記錄ID', location='form', required=True)

    @organization.doc(parser=parser)
    def post(self):
        """
        刪除未識別記錄
        """
        return WebAction().api_action(cmd='del_unknown_path', data=self.parser.parse_args())


@organization.route('/unknown/rename')
class UnknownRename(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('logid', type=str, help='轉移歷史記錄ID', location='form')
    parser.add_argument('unknown_id', type=str, help='未識別記錄ID', location='form')
    parser.add_argument('syncmod', type=str, help='轉移模式', location='form', required=True)
    parser.add_argument('tmdb', type=int, help='TMDB ID', location='form')
    parser.add_argument('title', type=str, help='標題', location='form')
    parser.add_argument('year', type=str, help='年份', location='form')
    parser.add_argument('type', type=str, help='型別（MOV/TV/ANIME）', location='form')
    parser.add_argument('season', type=int, help='季號', location='form')
    parser.add_argument('episode_format', type=str, help='集數定位', location='form')
    parser.add_argument('min_filesize', type=int, help='最小檔案大小', location='form')

    @organization.doc(parser=parser)
    def post(self):
        """
        手動識別
        """
        return WebAction().api_action(cmd='rename', data=self.parser.parse_args())


@organization.route('/unknown/renameudf')
class UnknownRenameUDF(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('inpath', type=str, help='源目錄', location='form', required=True)
    parser.add_argument('outpath', type=str, help='目的目錄', location='form', required=True)
    parser.add_argument('syncmod', type=str, help='轉移模式', location='form', required=True)
    parser.add_argument('tmdb', type=int, help='TMDB ID', location='form')
    parser.add_argument('title', type=str, help='標題', location='form')
    parser.add_argument('year', type=str, help='年份', location='form')
    parser.add_argument('type', type=str, help='型別（MOV/TV/ANIME）', location='form')
    parser.add_argument('season', type=int, help='季號', location='form')
    parser.add_argument('episode_format', type=str, help='集數定位', location='form')
    parser.add_argument('episode_details', type=str, help='集數範圍', location='form')
    parser.add_argument('episode_offset', type=str, help='集數偏移', location='form')
    parser.add_argument('min_filesize', type=int, help='最小檔案大小', location='form')

    @organization.doc(parser=parser)
    def post(self):
        """
        自定義識別
        """
        return WebAction().api_action(cmd='rename_udf', data=self.parser.parse_args())


@organization.route('/unknown/redo')
class UnknownRedo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('flag', type=str, help='型別（unknow/history）', location='form', required=True)
    parser.add_argument('ids', type=list, help='記錄ID', location='form', required=True)

    @organization.doc(parser=parser)
    def post(self):
        """
        重新識別
        """
        return WebAction().api_action(cmd='re_identification', data=self.parser.parse_args())


@organization.route('/history/delete')
class TransferHistoryDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('logids', type=list, help='記錄IDS', location='form', required=True)

    @organization.doc(parser=parser)
    def post(self):
        """
        刪除媒體整理歷史記錄
        """
        return WebAction().api_action(cmd='delete_history', data=self.parser.parse_args())


@organization.route('/unknown/list')
class TransferUnknownList(ClientResource):
    @staticmethod
    def post():
        """
        查詢所有未識別記錄
        """
        return WebAction().api_action(cmd='get_unknown_list')


@organization.route('/history/list')
class TransferHistoryList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('page', type=int, help='頁碼', location='form', required=True)
    parser.add_argument('pagenum', type=int, help='每頁條數', location='form', required=True)
    parser.add_argument('keyword', type=str, help='過濾關鍵字', location='form')

    @organization.doc(parser=parser)
    def post(self):
        """
        查詢媒體整理歷史記錄
        """
        return WebAction().api_action(cmd='get_transfer_history', data=self.parser.parse_args())


@organization.route('/history/statistics')
class HistoryStatistics(ClientResource):

    @staticmethod
    def post():
        """
        查詢轉移歷史統計資料
        """
        return WebAction().api_action(cmd='get_transfer_statistics')


@organization.route('/cache/empty')
class TransferCacheEmpty(ClientResource):

    @staticmethod
    def post():
        """
        清空檔案轉移快取
        """
        return WebAction().api_action(cmd='truncate_blacklist')


@library.route('/library/start')
class LibrarySyncStart(ClientResource):

    @staticmethod
    def post():
        """
        開始媒體庫同步
        """
        return WebAction().api_action(cmd='start_mediasync')


@library.route('/library/status')
class LibrarySyncStatus(ClientResource):

    @staticmethod
    def post():
        """
        查詢媒體庫同步狀態
        """
        return WebAction().api_action(cmd='mediasync_state')


@library.route('/library/playhistory')
class LibraryPlayHistory(ClientResource):

    @staticmethod
    def post():
        """
        查詢媒體庫播放歷史
        """
        return WebAction().api_action(cmd='get_library_playhistory')


@library.route('/library/statistics')
class LibraryStatistics(ClientResource):

    @staticmethod
    def post():
        """
        查詢媒體庫統計資料
        """
        return WebAction().api_action(cmd="get_library_mediacount")


@library.route('/library/space')
class LibrarySpace(ClientResource):

    @staticmethod
    def post():
        """
        查詢媒體庫儲存空間
        """
        return WebAction().api_action(cmd='get_library_spacesize')


@system.route('/logging')
class SystemLogging(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('refresh_new', type=int, help='是否重新整理增量日誌（0-否/1-是）', location='form', required=True)

    @system.doc(parser=parser)
    def post(self):
        """
        獲取實時日誌
        """
        return WebAction().api_action(cmd='logging', data=self.parser.parse_args())


@system.route('/version')
class SystemVersion(ClientResource):

    @staticmethod
    def post():
        """
        查詢最新版本號
        """
        return WebAction().api_action(cmd='version')


@system.route('/path')
class SystemPath(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('dir', type=str, help='路徑', location='form', required=True)
    parser.add_argument('filter', type=str, help='過濾器（ONLYFILE/ONLYDIR/MEDIAFILE/SUBFILE/ALL）', location='form', required=True)

    @system.doc(parser=parser)
    def post(self):
        """
        查詢目錄的子目錄/檔案
        """
        return WebAction().api_action(cmd='get_sub_path', data=self.parser.parse_args())


@system.route('/restart')
class SystemRestart(ClientResource):

    @staticmethod
    def post():
        """
        重啟
        """
        return WebAction().api_action(cmd='restart')


@system.route('/update')
class SystemUpdate(ClientResource):

    @staticmethod
    def post():
        """
        升級
        """
        return WebAction().api_action(cmd='update_system')


@system.route('/logout')
class SystemUpdate(ClientResource):

    @staticmethod
    def post():
        """
        登出
        """
        token = request.headers.get("Authorization", default=None)
        if token:
            TokenCache.delete(token)
        return {
            "code": 0,
            "success": True
        }


@system.route('/message')
class SystemMessage(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('lst_time', type=str, help='時間（YYYY-MM-DD HH24:MI:SS）', location='form')

    @system.doc(parser=parser)
    def post(self):
        """
        查詢訊息中心訊息
        """
        return WebAction().get_system_message(lst_time=self.parser.parse_args().get("lst_time"))


@system.route('/progress')
class SystemProgress(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='型別（search/mediasync）', location='form', required=True)

    @system.doc(parser=parser)
    def post(self):
        """
        查詢搜尋/媒體同步等進度
        """
        return WebAction().api_action(cmd='refresh_process', data=self.parser.parse_args())


@config.route('/update')
class ConfigUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('items', type=dict, help='配置項', location='form', required=True)

    @config.doc(parser=parser)
    def post(self):
        """
        新增/修改配置
        """
        return WebAction().api_action(cmd='update_config', data=self.parser.parse_args().get("items"))


@config.route('/test')
class ConfigTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('command', type=str, help='測試命令', location='form', required=True)

    @config.doc(parser=parser)
    def post(self):
        """
        測試配置連通性
        """
        return WebAction().api_action(cmd='test_connection', data=self.parser.parse_args())


@config.route('/restore')
class ConfigRestore(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('file_name', type=str, help='備份檔名', location='form', required=True)

    @config.doc(parser=parser)
    def post(self):
        """
        恢復備份的配置
        """
        return WebAction().api_action(cmd='restory_backup', data=self.parser.parse_args())


@config.route('/info')
class ConfigInfo(ClientResource):
    @staticmethod
    def post():
        """
        獲取所有配置資訊
        """
        return {
            "code": 0,
            "success": True,
            "data": Config().get_config()
        }


@config.route('/directory')
class ConfigDirectory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('oper', type=str, help='操作型別（add/sub/set）', location='form', required=True)
    parser.add_argument('key', type=str, help='配置項', location='form', required=True)
    parser.add_argument('value', type=str, help='配置值', location='form', required=True)

    @config.doc(parser=parser)
    def post(self):
        """
        配置媒體庫目錄
        """
        return WebAction().api_action(cmd='update_directory', data=self.parser.parse_args())


@subscribe.route('/delete')
class SubscribeDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='名稱', location='form')
    parser.add_argument('type', type=str, help='型別（MOV/TV）', location='form')
    parser.add_argument('year', type=str, help='發行年份', location='form')
    parser.add_argument('season', type=int, help='季號', location='form')
    parser.add_argument('rssid', type=int, help='已有訂閱ID', location='form')
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form')

    @subscribe.doc(parser=parser)
    def post(self):
        """
        刪除訂閱
        """
        return WebAction().api_action(cmd='remove_rss_media', data=self.parser.parse_args())


@subscribe.route('/add')
class SubscribeAdd(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='名稱', location='form', required=True)
    parser.add_argument('type', type=str, help='型別（MOV/TV）', location='form', required=True)
    parser.add_argument('year', type=str, help='發行年份', location='form')
    parser.add_argument('season', type=int, help='季號', location='form')
    parser.add_argument('rssid', type=int, help='已有訂閱ID', location='form')
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form')
    parser.add_argument('doubanid', type=str, help='豆瓣ID', location='form')
    parser.add_argument('match', type=int, help='模糊匹配（0-否/1-是）', location='form')
    parser.add_argument('sites', type=list, help='RSS站點', location='form')
    parser.add_argument('search_sites', type=list, help='搜尋站點', location='form')
    parser.add_argument('over_edition', type=int, help='洗版（0-否/1-是）', location='form')
    parser.add_argument('rss_restype', type=str, help='資源型別', location='form')
    parser.add_argument('rss_pix', type=str, help='解析度', location='form')
    parser.add_argument('rss_team', type=str, help='字幕組/釋出組', location='form')
    parser.add_argument('rss_rule', type=str, help='過濾規則', location='form')
    parser.add_argument('total_ep', type=int, help='總集數', location='form')
    parser.add_argument('current_ep', type=int, help='開始集數', location='form')

    @subscribe.doc(parser=parser)
    def post(self):
        """
        新增/修改訂閱
        """
        return WebAction().api_action(cmd='add_rss_media', data=self.parser.parse_args())


@subscribe.route('/movie/date')
class SubscribeMovieDate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='TMDBID/DB:豆瓣ID', location='form', required=True)

    @subscribe.doc(parser=parser)
    def post(self):
        """
        電影上映日期
        """
        return WebAction().api_action(cmd='movie_calendar_data', data=self.parser.parse_args())


@subscribe.route('/tv/date')
class SubscribeTVDate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='TMDBID/DB:豆瓣ID', location='form', required=True)
    parser.add_argument('season', type=int, help='季號', location='form', required=True)
    parser.add_argument('name', type=str, help='名稱', location='form')

    @subscribe.doc(parser=parser)
    def post(self):
        """
        電視劇上映日期
        """
        return WebAction().api_action(cmd='tv_calendar_data', data=self.parser.parse_args())


@subscribe.route('/search')
class SubscribeSearch(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='型別（MOV/TV）', location='form', required=True)
    parser.add_argument('rssid', type=int, help='訂閱ID', location='form', required=True)

    @subscribe.doc(parser=parser)
    def post(self):
        """
        訂閱重新整理搜尋
        """
        return WebAction().api_action(cmd='refresh_rss', data=self.parser.parse_args())


@subscribe.route('/info')
class SubscribeInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('rssid', type=int, help='訂閱ID', location='form', required=True)
    parser.add_argument('type', type=str, help='訂閱型別（MOV/TV）', location='form', required=True)

    @subscribe.doc(parser=parser)
    def post(self):
        """
        訂閱詳情
        """
        return WebAction().api_action(cmd='rss_detail', data=self.parser.parse_args())


@subscribe.route('/redo')
class SubscribeRedo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('rssid', type=int, help='訂閱歷史ID', location='form', required=True)
    parser.add_argument('type', type=str, help='訂閱型別（MOV/TV）', location='form', required=True)

    @subscribe.doc(parser=parser)
    def post(self):
        """
        歷史重新訂閱
        """
        return WebAction().api_action(cmd='re_rss_history', data=self.parser.parse_args())


@subscribe.route('/history/delete')
class SubscribeHistoryDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('rssid', type=int, help='訂閱ID', location='form', required=True)

    @subscribe.doc(parser=parser)
    def post(self):
        """
        刪除訂閱歷史
        """
        return WebAction().api_action(cmd='delete_rss_history', data=self.parser.parse_args())


@subscribe.route('/history')
class SubscribeHistory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='型別（MOV/TV）', location='form', required=True)

    @subscribe.doc(parser=parser)
    def post(self):
        """
        查詢訂閱歷史
        """
        return WebAction().api_action(cmd='get_rss_history', data=self.parser.parse_args())


@subscribe.route('/cache/delete')
class SubscribeCacheDelete(ClientResource):
    @staticmethod
    def post():
        """
        清理訂閱快取
        """
        return WebAction().api_action(cmd='truncate_rsshistory')


@subscribe.route('/movie/list')
class SubscribeMovieList(ClientResource):
    @staticmethod
    def post():
        """
        查詢所有電影訂閱
        """
        return WebAction().api_action(cmd='get_movie_rss_list')


@subscribe.route('/tv/list')
class SubscribeTvList(ClientResource):
    @staticmethod
    def post():
        """
        查詢所有電視劇訂閱
        """
        return WebAction().api_action(cmd='get_tv_rss_list')


@recommend.route('/list')
class RecommendList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str,
                        help='型別（hm/ht/nm/nt/dbom/dbhm/dbht/dbdh/dbnm/dbtop/dbzy/bangumi）',
                        location='form', required=True)
    parser.add_argument('page', type=int, help='頁碼', location='form', required=True)

    @recommend.doc(parser=parser)
    def post(self):
        """
        推薦列表
        """
        return WebAction().api_action(cmd='get_recommend', data=self.parser.parse_args())


@rss.route('/info')
class RssInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='任務ID', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        自定義訂閱任務詳情
        """
        return WebAction().api_action(cmd='get_userrss_task', data=self.parser.parse_args())


@rss.route('/delete')
class RssDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='任務ID', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        刪除自定義訂閱任務
        """
        return WebAction().api_action(cmd='delete_userrss_task', data=self.parser.parse_args())


@rss.route('/update')
class RssUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='任務ID', location='form')
    parser.add_argument('name', type=str, help='任務名稱', location='form', required=True)
    parser.add_argument('address', type=str, help='RSS地址', location='form', required=True)
    parser.add_argument('parser', type=int, help='解析器ID', location='form', required=True)
    parser.add_argument('interval', type=int, help='重新整理間隔（分鐘）', location='form', required=True)
    parser.add_argument('uses', type=str, help='動作', location='form', required=True)
    parser.add_argument('state', type=str, help='狀態（Y/N）', location='form', required=True)
    parser.add_argument('include', type=str, help='包含', location='form')
    parser.add_argument('exclude', type=str, help='排除', location='form')
    parser.add_argument('filterrule', type=int, help='過濾規則', location='form')
    parser.add_argument('note', type=str, help='備註', location='form')

    @rss.doc(parser=parser)
    def post(self):
        """
        新增/修改自定義訂閱任務
        """
        return WebAction().api_action(cmd='update_userrss_task', data=self.parser.parse_args())


@rss.route('/parser/info')
class RssParserInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='解析器ID', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        解析器詳情
        """
        return WebAction().api_action(cmd='get_rssparser', data=self.parser.parse_args())


@rss.route('/parser/delete')
class RssParserDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='解析器ID', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        刪除解析器
        """
        return WebAction().api_action(cmd='delete_rssparser', data=self.parser.parse_args())


@rss.route('/parser/update')
class RssParserUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='解析器ID', location='form', required=True)
    parser.add_argument('name', type=str, help='名稱', location='form', required=True)
    parser.add_argument('type', type=str, help='型別（JSON/XML）', location='form', required=True)
    parser.add_argument('format', type=str, help='解析格式', location='form', required=True)
    parser.add_argument('params', type=str, help='附加引數', location='form')

    @rss.doc(parser=parser)
    def post(self):
        """
        新增/修改解析器
        """
        return WebAction().api_action(cmd='update_rssparser', data=self.parser.parse_args())


@rss.route('/parser/list')
class RssParserList(ClientResource):
    @staticmethod
    def post():
        """
        查詢所有解析器
        """
        return {
            "code": 0,
            "success": True,
            "data": {
                "parsers": RssChecker().get_userrss_parser()
            }
        }


@rss.route('/list')
class RssList(ClientResource):
    @staticmethod
    def post():
        """
        查詢所有自定義訂閱任務
        """
        return {
            "code": 0,
            "success": False,
            "data": {
                "tasks": RssChecker().get_rsstask_info(),
                "parsers": RssChecker().get_userrss_parser()
            }
        }


@rss.route('/preview')
class RssPreview(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='任務ID', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        自定義訂閱預覽
        """
        return WebAction().api_action(cmd='list_rss_articles', data=self.parser.parse_args())


@rss.route('/name/test')
class RssNameTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('taskid', type=int, help='任務ID', location='form', required=True)
    parser.add_argument('title', type=str, help='名稱', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        自定義訂閱名稱測試
        """
        return WebAction().api_action(cmd='rss_article_test', data=self.parser.parse_args())


@rss.route('/item/history')
class RssItemHistory(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='任務ID', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        自定義訂閱任務條目處理記錄
        """
        return WebAction().api_action(cmd='list_rss_history', data=self.parser.parse_args())


@rss.route('/item/set')
class RssItemSet(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('flag', type=str, help='操作型別（set_finished/set_unfinish）', location='form', required=True)
    parser.add_argument('articles', type=list, help='條目（{title/enclosure}）', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        自定義訂閱任務條目狀態調整
        """
        return WebAction().api_action(cmd='rss_articles_check', data=self.parser.parse_args())


@rss.route('/item/download')
class RssItemDownload(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('taskid', type=int, help='任務ID', location='form', required=True)
    parser.add_argument('articles', type=list, help='條目（{title/enclosure}）', location='form', required=True)

    @rss.doc(parser=parser)
    def post(self):
        """
        自定義訂閱任務條目下載
        """
        return WebAction().api_action(cmd='rss_articles_download', data=self.parser.parse_args())


@media.route('/search')
class MediaSearch(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('keyword', type=str, help='關鍵字', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        搜尋TMDB/豆瓣詞條
        """
        return WebAction().api_action(cmd='search_media_infos', data=self.parser.parse_args())


@media.route('/cache/update')
class MediaCacheUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('key', type=str, help='快取Key值', location='form', required=True)
    parser.add_argument('title', type=str, help='標題', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        修改TMDB快取標題
        """
        return WebAction().api_action(cmd='modify_tmdb_cache', data=self.parser.parse_args())


@media.route('/cache/delete')
class MediaCacheDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cache_key', type=str, help='快取Key值', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        刪除TMDB快取
        """
        return WebAction().api_action(cmd='delete_tmdb_cache', data=self.parser.parse_args())


@media.route('/cache/clear')
class MediaCacheClear(ClientResource):

    @staticmethod
    def post():
        """
        清空TMDB快取
        """
        return WebAction().api_action(cmd='clear_tmdb_cache')


@media.route('/tv/seasons')
class MediaTvSeasons(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tmdbid', type=str, help='TMDBID', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        查詢電視劇季列表
        """
        return WebAction().api_action(cmd='get_tvseason_list', data=self.parser.parse_args())


@media.route('/category/list')
class MediaCategoryList(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='型別（電影/電視劇/動漫）', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        查詢二級分類配置
        """
        return WebAction().api_action(cmd='get_categories', data=self.parser.parse_args())


@media.route('/info')
class MediaInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='型別（MOV/TV）', location='form', required=True)
    parser.add_argument('id', type=str, help='TMDBID', location='form')
    parser.add_argument('doubanid', type=str, help='豆瓣ID', location='form')
    parser.add_argument('title', type=str, help='標題', location='form')
    parser.add_argument('year', type=str, help='年份', location='form')
    parser.add_argument('rssid', type=str, help='訂閱ID', location='form')

    @media.doc(parser=parser)
    def post(self):
        """
        識別媒體資訊
        """
        return WebAction().api_action(cmd='media_info', data=self.parser.parse_args())


@media.route('/subtitle/download')
class MediaSubtitleDownload(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('path', type=str, help='檔案路徑（含檔名）', location='form', required=True)
    parser.add_argument('name', type=str, help='名稱（用於識別）', location='form', required=True)

    @media.doc(parser=parser)
    def post(self):
        """
        下載單個檔案字幕
        """
        return WebAction().api_action(cmd='download_subtitle', data=self.parser.parse_args())


@brushtask.route('/update')
class BrushTaskUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('brushtask_id', type=str, help='刷流任務ID', location='form')
    parser.add_argument('brushtask_name', type=str, help='任務名稱', location='form', required=True)
    parser.add_argument('brushtask_site', type=int, help='站點', location='form', required=True)
    parser.add_argument('brushtask_interval', type=int, help='重新整理間隔(分鐘)', location='form', required=True)
    parser.add_argument('brushtask_downloader', type=int, help='下載器', location='form', required=True)
    parser.add_argument('brushtask_totalsize', type=int, help='保種體積(GB)', location='form', required=True)
    parser.add_argument('brushtask_state', type=str, help='狀態（Y/N）', location='form', required=True)
    parser.add_argument('brushtask_transfer', type=str, help='轉移到媒體庫（Y/N）', location='form')
    parser.add_argument('brushtask_sendmessage', type=str, help='訊息推送（Y/N）', location='form')
    parser.add_argument('brushtask_forceupload', type=str, help='強制做種（Y/N）', location='form')
    parser.add_argument('brushtask_free', type=str, help='促銷（FREE/2XFREE）', location='form')
    parser.add_argument('brushtask_hr', type=str, help='Hit&Run（HR）', location='form')
    parser.add_argument('brushtask_torrent_size', type=int, help='種子大小(GB)', location='form')
    parser.add_argument('brushtask_include', type=str, help='包含', location='form')
    parser.add_argument('brushtask_exclude', type=str, help='排除', location='form')
    parser.add_argument('brushtask_dlcount', type=int, help='同時下載任務數', location='form')
    parser.add_argument('brushtask_peercount', type=int, help='做種人數限制', location='form')
    parser.add_argument('brushtask_seedtime', type=float, help='做種時間(小時)', location='form')
    parser.add_argument('brushtask_seedratio', type=float, help='分享率', location='form')
    parser.add_argument('brushtask_seedsize', type=int, help='上傳量(GB)', location='form')
    parser.add_argument('brushtask_dltime', type=float, help='下載耗時(小時)', location='form')
    parser.add_argument('brushtask_avg_upspeed', type=int, help='平均上傳速度(KB/S)', location='form')
    parser.add_argument('brushtask_pubdate', type=int, help='釋出時間（小時）', location='form')
    parser.add_argument('brushtask_upspeed', type=int, help='上傳限速（KB/S）', location='form')
    parser.add_argument('brushtask_downspeed', type=int, help='下載限速（KB/S）', location='form')

    @brushtask.doc(parser=parser)
    def post(self):
        """
        新增/修改刷流任務
        """
        return WebAction().api_action(cmd='add_brushtask', data=self.parser.parse_args())


@brushtask.route('/delete')
class BrushTaskDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='刷流任務ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        刪除刷流任務
        """
        return WebAction().api_action(cmd='del_brushtask', data=self.parser.parse_args())


@brushtask.route('/info')
class BrushTaskInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='刷流任務ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        刷流任務詳情
        """
        return WebAction().api_action(cmd='brushtask_detail', data=self.parser.parse_args())


@brushtask.route('/list')
class BrushTasklist(ClientResource):
    @staticmethod
    def post():
        """
        查詢所有刷流任務
        """
        return {
            "code": 0,
            "success": True,
            "data": {
                "tasks": BrushTask().get_brushtask_info()
            }
        }


@brushtask.route('/downloader/update')
class BrushTaskDownloaderUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('test', type=int, help='測試（0-否/1-是）', location='form', required=True)
    parser.add_argument('id', type=int, help='下載器ID', location='form')
    parser.add_argument('name', type=str, help='名稱', location='form', required=True)
    parser.add_argument('type', type=str, help='型別（qbittorrent/transmission）', location='form', required=True)
    parser.add_argument('host', type=str, help='地址', location='form', required=True)
    parser.add_argument('port', type=int, help='埠', location='form', required=True)
    parser.add_argument('username', type=str, help='使用者名稱', location='form')
    parser.add_argument('password', type=str, help='密碼', location='form')
    parser.add_argument('save_dir', type=str, help='儲存目錄', location='form')

    @brushtask.doc(parser=parser)
    def post(self):
        """
        新增/修改刷流下載器
        """
        return WebAction().api_action(cmd='add_downloader', data=self.parser.parse_args())


@brushtask.route('/downloader/delete')
class BrushTaskDownloaderDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='下載器ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        刪除刷流下載器
        """
        return WebAction().api_action(cmd='delete_downloader', data=self.parser.parse_args())


@brushtask.route('/downloader/info')
class BrushTaskDownloaderInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='下載器ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        刷流下載器詳情
        """
        return WebAction().api_action(cmd='get_downloader', data=self.parser.parse_args())


@brushtask.route('/downloader/list')
class BrushTaskDownloaderList(ClientResource):
    @staticmethod
    def post():
        """
        查詢所有刷流下載器
        """
        return {
            "code": 0,
            "success": True,
            "data": {
                "downloaders": BrushTask().get_downloader_info()
            }
        }


@brushtask.route('/run')
class BrushTaskRun(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='刷流任務ID', location='form', required=True)

    @brushtask.doc(parser=parser)
    def post(self):
        """
        刷流下載器詳情
        """
        return WebAction().api_action(cmd='run_brushtask', data=self.parser.parse_args())


@filterrule.route('/list')
class FilterRuleList(ClientResource):
    @staticmethod
    def post():
        """
        查詢所有過濾規則
        """
        return WebAction().api_action(cmd='get_filterrules')


@filterrule.route('/group/add')
class FilterRuleGroupAdd(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, help='名稱', location='form', required=True)
    parser.add_argument('default', type=str, help='預設（Y/N）', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        新增規則組
        """
        return WebAction().api_action(cmd='add_filtergroup', data=self.parser.parse_args())


@filterrule.route('/group/restore')
class FilterRuleGroupRestore(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('groupids', type=list, help='規則組ID', location='form', required=True)
    parser.add_argument('init_rulegroups', type=list, help='規則組指令碼', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        恢復預設規則組
        """
        return WebAction().api_action(cmd='restore_filtergroup', data=self.parser.parse_args())


@filterrule.route('/group/default')
class FilterRuleGroupDefault(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='規則組ID', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        設定預設規則組
        """
        return WebAction().api_action(cmd='set_default_filtergroup', data=self.parser.parse_args())


@filterrule.route('/group/delete')
class FilterRuleGroupDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=str, help='規則組ID', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        刪除規則組
        """
        return WebAction().api_action(cmd='del_filtergroup', data=self.parser.parse_args())


@filterrule.route('/rule/update')
class FilterRuleUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('rule_id', type=int, help='規則ID', location='form')
    parser.add_argument('group_id', type=int, help='規則組ID', location='form', required=True)
    parser.add_argument('rule_name', type=str, help='規則名稱', location='form', required=True)
    parser.add_argument('rule_pri', type=str, help='優先順序', location='form', required=True)
    parser.add_argument('rule_include', type=str, help='包含', location='form')
    parser.add_argument('rule_exclude', type=str, help='排除', location='form')
    parser.add_argument('rule_sizelimit', type=str, help='大小限制', location='form')
    parser.add_argument('rule_free', type=str, help='促銷（FREE/2XFREE）', location='form')

    @filterrule.doc(parser=parser)
    def post(self):
        """
        新增/修改規則
        """
        return WebAction().api_action(cmd='add_filterrule', data=self.parser.parse_args())


@filterrule.route('/rule/delete')
class FilterRuleDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='規則ID', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        刪除規則
        """
        return WebAction().api_action(cmd='del_filterrule', data=self.parser.parse_args())


@filterrule.route('/rule/info')
class FilterRuleInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('ruleid', type=int, help='規則ID', location='form', required=True)
    parser.add_argument('groupid', type=int, help='規則組ID', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        規則詳情
        """
        return WebAction().api_action(cmd='filterrule_detail', data=self.parser.parse_args())


@filterrule.route('/rule/share')
class FilterRuleShare(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='規則組ID', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        分享規則組
        """
        return WebAction().api_action(cmd='share_filtergroup', data=self.parser.parse_args())


@filterrule.route('/rule/import')
class FilterRuleImport(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('content', type=str, help='規則內容', location='form', required=True)

    @filterrule.doc(parser=parser)
    def post(self):
        """
        匯入規則組
        """
        return WebAction().api_action(cmd='import_filtergroup', data=self.parser.parse_args())


@words.route('/group/add')
class WordsGroupAdd(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tmdb_id', type=str, help='TMDBID', location='form', required=True)
    parser.add_argument('tmdb_type', type=str, help='型別（movie/tv）', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        新增識別片語
        """
        return WebAction().api_action(cmd='add_custom_word_group', data=self.parser.parse_args())


@words.route('/group/delete')
class WordsGroupDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('gid', type=int, help='識別片語ID', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        刪除識別片語
        """
        return WebAction().api_action(cmd='delete_custom_word_group', data=self.parser.parse_args())


@words.route('/item/update')
class WordItemUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='識別詞ID', location='form', required=True)
    parser.add_argument('gid', type=int, help='識別片語ID', location='form', required=True)
    parser.add_argument('group_type', type=str, help='媒體型別（1-電影/2-電視劇）', location='form', required=True)
    parser.add_argument('new_replaced', type=str, help='被替換詞', location='form')
    parser.add_argument('new_replace', type=str, help='替換詞', location='form')
    parser.add_argument('new_front', type=str, help='前定位詞', location='form')
    parser.add_argument('new_back', type=str, help='後定位詞', location='form')
    parser.add_argument('new_offset', type=str, help='偏移集數', location='form')
    parser.add_argument('new_help', type=str, help='備註', location='form')
    parser.add_argument('type', type=str, help='識別詞型別（1-遮蔽/2-替換/3-替換+集偏移/4-集偏移）', location='form', required=True)
    parser.add_argument('season', type=str, help='季', location='form')
    parser.add_argument('enabled', type=str, help='狀態（1-啟用/0-停用）', location='form', required=True)
    parser.add_argument('regex', type=str, help='正規表示式（1-使用/0-不使用）', location='form')

    @words.doc(parser=parser)
    def post(self):
        """
        新增/修改識別詞
        """
        return WebAction().api_action(cmd='add_or_edit_custom_word', data=self.parser.parse_args())


@words.route('/item/info')
class WordItemInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('wid', type=int, help='識別詞ID', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        識別詞詳情
        """
        return WebAction().api_action(cmd='get_custom_word', data=self.parser.parse_args())


@words.route('/item/delete')
class WordItemDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='識別詞ID', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        刪除識別詞
        """
        return WebAction().api_action(cmd='delete_custom_word', data=self.parser.parse_args())


@words.route('/item/status')
class WordItemStatus(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('ids_info', type=list, help='識別詞IDS', location='form', required=True)
    parser.add_argument('flag', type=int, help='狀態（1/0）', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        設定識別詞狀態
        """
        return WebAction().api_action(cmd='check_custom_words', data=self.parser.parse_args())


@words.route('/item/export')
class WordItemExport(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('note', type=str, help='備註', location='form', required=True)
    parser.add_argument('ids_info', type=str, help='識別詞IDS（@_）', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        匯出識別詞
        """
        return WebAction().api_action(cmd='export_custom_words', data=self.parser.parse_args())


@words.route('/item/analyse')
class WordItemAnalyse(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('import_code', type=str, help='識別詞程式碼', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        分析識別詞
        """
        return WebAction().api_action(cmd='analyse_import_custom_words_code', data=self.parser.parse_args())


@words.route('/item/import')
class WordItemImport(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('import_code', type=str, help='識別詞程式碼', location='form', required=True)
    parser.add_argument('ids_info', type=list, help='識別詞IDS', location='form', required=True)

    @words.doc(parser=parser)
    def post(self):
        """
        分析識別詞
        """
        return WebAction().api_action(cmd='import_custom_words', data=self.parser.parse_args())


@words.route('/list')
class WordList(ClientResource):
    @staticmethod
    def post():
        """
        查詢所有自定義識別詞
        """
        return WebAction().api_action(cmd='get_customwords')


@sync.route('/directory/update')
class SyncDirectoryUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=int, help='同步目錄ID', location='form')
    parser.add_argument('from', type=str, help='源目錄', location='form', required=True)
    parser.add_argument('to', type=str, help='目的目錄', location='form')
    parser.add_argument('unknown', type=str, help='未知目錄', location='form')
    parser.add_argument('syncmod', type=str, help='同步模式', location='form')
    parser.add_argument('rename', type=str, help='重新命名', location='form')
    parser.add_argument('enabled', type=str, help='開啟', location='form')

    @sync.doc(parser=parser)
    def post(self):
        """
        新增/修改同步目錄
        """
        return WebAction().api_action(cmd='add_or_edit_sync_path', data=self.parser.parse_args())


@sync.route('/directory/info')
class SyncDirectoryInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=int, help='同步目錄ID', location='form', required=True)

    @sync.doc(parser=parser)
    def post(self):
        """
        同步目錄詳情
        """
        return WebAction().api_action(cmd='get_sync_path', data=self.parser.parse_args())


@sync.route('/directory/delete')
class SyncDirectoryDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=int, help='同步目錄ID', location='form', required=True)

    @sync.doc(parser=parser)
    def post(self):
        """
        刪除同步目錄
        """
        return WebAction().api_action(cmd='delete_sync_path', data=self.parser.parse_args())


@sync.route('/directory/status')
class SyncDirectoryStatus(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('sid', type=int, help='同步目錄ID', location='form', required=True)
    parser.add_argument('flag', type=str, help='操作（rename/enable）', location='form', required=True)
    parser.add_argument('checked', type=int, help='狀態（0-否/1-是）', location='form', required=True)

    @sync.doc(parser=parser)
    def post(self):
        """
        設定同步目錄狀態
        """
        return WebAction().api_action(cmd='check_sync_path', data=self.parser.parse_args())


@sync.route('/directory/list')
class SyncDirectoryList(ClientResource):
    @staticmethod
    def post():
        """
        查詢所有同步目錄
        """
        return WebAction().api_action(cmd='get_directorysync')


@sync.route('/run')
class SyncRun(ApiResource):
    @staticmethod
    def get():
        """
        立即執行目錄同步服務（金鑰認證）
        """
        # 返回站點資訊
        return WebAction().api_action(cmd='sch', data={"item": "sync"})


@message.route('/client/update')
class MessageClientUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cid', type=int, help='ID', location='form')
    parser.add_argument('name', type=str, help='名稱', location='form', required=True)
    parser.add_argument('type', type=str, help='型別（wechat/telegram/serverchan/bark/pushplus/iyuu/slack/gotify）',
                        location='form', required=True)
    parser.add_argument('config', type=str, help='配置項（JSON）', location='form', required=True)
    parser.add_argument('switchs', type=list, help='開關', location='form', required=True)
    parser.add_argument('interactive', type=int, help='是否開啟互動（0/1）', location='form', required=True)
    parser.add_argument('enabled', type=int, help='是否啟用（0/1）', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        新增/修改通知訊息服務渠道
        """
        return WebAction().api_action(cmd='update_message_client', data=self.parser.parse_args())


@message.route('/client/delete')
class MessageClientDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cid', type=int, help='ID', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        刪除通知訊息服務渠道
        """
        return WebAction().api_action(cmd='delete_message_client', data=self.parser.parse_args())


@message.route('/client/status')
class MessageClientStatus(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('flag', type=str, help='操作型別（interactive/enable）', location='form', required=True)
    parser.add_argument('cid', type=int, help='ID', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        設定通知訊息服務渠道狀態
        """
        return WebAction().api_action(cmd='check_message_client', data=self.parser.parse_args())


@message.route('/client/info')
class MessageClientInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('cid', type=int, help='ID', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        查詢通知訊息服務渠道設定
        """
        return WebAction().api_action(cmd='get_message_client', data=self.parser.parse_args())


@message.route('/client/test')
class MessageClientTest(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('type', type=str, help='型別（wechat/telegram/serverchan/bark/pushplus/iyuu/slack/gotify）', location='form', required=True)
    parser.add_argument('config', type=str, help='配置（JSON）', location='form', required=True)

    @message.doc(parser=parser)
    def post(self):
        """
        測試通知訊息服務配置正確性
        """
        return WebAction().api_action(cmd='test_message_client', data=self.parser.parse_args())


@torrentremover.route('/task/info')
class TorrentRemoverTaskInfo(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tid', type=int, help='任務ID', location='form', required=True)

    @torrentremover.doc(parser=parser)
    def post(self):
        """
        查詢自動刪種任務詳情
        """
        return WebAction().api_action(cmd='get_torrent_remove_task', data=self.parser.parse_args())


@torrentremover.route('/task/list')
class TorrentRemoverTaskList(ClientResource):
    @staticmethod
    @torrentremover.doc()
    def post():
        """
        查詢所有自動刪種任務
        """
        return WebAction().api_action(cmd='get_torrent_remove_task')


@torrentremover.route('/task/delete')
class TorrentRemoverTaskDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tid', type=int, help='任務ID', location='form', required=True)

    @torrentremover.doc(parser=parser)
    def post(self):
        """
        刪除自動刪種任務
        """
        return WebAction().api_action(cmd='delete_torrent_remove_task', data=self.parser.parse_args())


@torrentremover.route('/task/update')
class TorrentRemoverTaskUpdate(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('tid', type=int, help='任務ID', location='form')
    parser.add_argument('name', type=str, help='名稱', location='form', required=True)
    parser.add_argument('action', type=int, help='動作(1-暫停/2-刪除種子/3-刪除種子及檔案)', location='form', required=True)
    parser.add_argument('interval', type=int, help='執行間隔（分鐘）', location='form', required=True)
    parser.add_argument('enabled', type=int, help='狀態（0-停用/1-啟用）', location='form', required=True)
    parser.add_argument('samedata', type=int, help='處理輔種（0-否/1-是）', location='form', required=True)
    parser.add_argument('onlynastool', type=int, help='只管理NASTool新增的下載（0-否/1-是）', location='form', required=True)
    parser.add_argument('ratio', type=float, help='分享率', location='form')
    parser.add_argument('seeding_time', type=int, help='做種時間（小時）', location='form')
    parser.add_argument('upload_avs', type=int, help='平均上傳速度（KB/S）', location='form')
    parser.add_argument('size', type=str, help='種子大小（GB）', location='form')
    parser.add_argument('savepath_key', type=str, help='儲存路徑關鍵詞', location='form')
    parser.add_argument('tracker_key', type=str, help='tracker關鍵詞', location='form')
    parser.add_argument('downloader', type=str, help='下載器（Qb/Tr）', location='form')
    parser.add_argument('qb_state', type=str, help='Qb種子狀態（多個用;分隔）', location='form')
    parser.add_argument('qb_category', type=str, help='Qb分類（多個用;分隔）', location='form')
    parser.add_argument('tr_state', type=str, help='Tr種子狀態（多個用;分隔）', location='form')
    parser.add_argument('tr_error_key', type=str, help='Tr錯誤資訊關鍵詞', location='form')

    @torrentremover.doc(parser=parser)
    def post(self):
        """
        新增/修改自動刪種任務
        """
        return WebAction().api_action(cmd='update_torrent_remove_task', data=self.parser.parse_args())


@douban.route('/history/list')
class DoubanHistoryList(ClientResource):

    @staticmethod
    def post():
        """
        查詢豆瓣同步歷史記錄
        """
        return WebAction().api_action(cmd='get_douban_history')


@douban.route('/history/delete')
class DoubanHistoryDelete(ClientResource):
    parser = reqparse.RequestParser()
    parser.add_argument('id', type=int, help='ID', location='form', required=True)

    @douban.doc(parser=parser)
    def post(self):
        """
        刪除豆瓣同步歷史記錄
        """
        return WebAction().api_action(cmd='delete_douban_history', data=self.parser.parse_args())


@douban.route('/run')
class DoubanRun(ClientResource):
    @staticmethod
    def post():
        """
        立即同步豆瓣資料
        """
        # 返回站點資訊
        return WebAction().api_action(cmd='sch', data={"item": "douban"})
