import os
import shutil
from threading import Lock
import ruamel.yaml

# 選單對應關係，配置WeChat應用中配置的選單ID與執行命令的對應關係，需要手工修改
# 選單序號在https://work.weixin.qq.com/wework_admin/frame#apps 應用自定義選單中維護，然後看日誌輸出的選單序號是啥（按順利能猜到的）....
# 命令對應關係：/ptt 下載檔案轉移；/ptr 刪種；/pts 站點簽到；/rst 目錄同步；/rss RSS下載
WECHAT_MENU = {'_0_0': '/ptt', '_0_1': '/ptr', '_0_2': '/rss', '_1_0': '/rst', '_1_1': '/db', '_2_0': '/pts'}
# 種子名/檔名要素分隔字元
SPLIT_CHARS = r"\.|\s+|\(|\)|\[|]|-|\+|【|】|/|～|;|&|\||#|_|「|」|（|）|~"
# 預設User-Agent
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"
# 收藏了的媒體的目錄名，名字可以改，在Emby中點選紅星則會自動將電影轉移到此分類下，需要在Emby Webhook中配置使用者行為通知
RMT_FAVTYPE = '精選'
# 支援的媒體檔案字尾格式
RMT_MEDIAEXT = ['.mp4', '.mkv', '.ts', '.iso', '.rmvb', '.avi', '.mov', '.mpeg', '.mpg', '.wmv', '.3gp', '.asf', '.m4v',
                '.flv', '.m2ts']
# 支援的字幕檔案字尾格式
RMT_SUBEXT = ['.srt', '.ass', '.ssa']
# 電視劇動漫的分類genre_ids
ANIME_GENREIDS = ['16']
# 預設過濾的檔案大小，150M
RMT_MIN_FILESIZE = 150 * 1024 * 1024
# 刪種檢查時間間隔
AUTO_REMOVE_TORRENTS_INTERVAL = 1800
# 下載檔案轉移檢查時間間隔，
PT_TRANSFER_INTERVAL = 300
# TMDB資訊快取定時儲存時間
METAINFO_SAVE_INTERVAL = 600
# SYNC目錄同步聚合轉移時間
SYNC_TRANSFER_INTERVAL = 60
# RSS佇列中處理時間間隔
RSS_CHECK_INTERVAL = 300
# 站點流量資料重新整理時間間隔（小時）
REFRESH_PT_DATA_INTERVAL = 6
# 重新整理訂閱TMDB資料的時間間隔（小時）
RSS_REFRESH_TMDB_INTERVAL = 6
# 刷流刪除的檢查時間間隔
BRUSH_REMOVE_TORRENTS_INTERVAL = 300
# 定時清除未識別的快取時間間隔（小時）
META_DELETE_UNKNOWN_INTERVAL = 12
# 定時重新整理桌布的間隔（小時）
REFRESH_WALLPAPER_INTERVAL = 1
# fanart的api，用於拉取封面圖片
FANART_MOVIE_API_URL = 'https://webservice.fanart.tv/v3/movies/%s?api_key=d2d31f9ecabea050fc7d68aa3146015f'
FANART_TV_API_URL = 'https://webservice.fanart.tv/v3/tv/%s?api_key=d2d31f9ecabea050fc7d68aa3146015f'
# 預設背景圖地址
DEFAULT_TMDB_IMAGE = 'https://s3.bmp.ovh/imgs/2022/07/10/77ef9500c851935b.webp'
# 預設微信訊息代理伺服器地址
DEFAULT_WECHAT_PROXY = 'https://wechat.nastool.cn'
# 預設OCR識別服務地址
DEFAULT_OCR_SERVER = 'https://nastool.cn'
# 預設TMDB代理服務地址
DEFAULT_TMDB_PROXY = 'https://tmdb.nastool.cn'
# TMDB圖片地址
TMDB_IMAGE_W500_URL = 'https://image.tmdb.org/t/p/w500%s'
TMDB_IMAGE_ORIGINAL_URL = 'https://image.tmdb.org/t/p/original/%s'
# 新增下載時增加的標籤，開始只監控NASTool新增的下載時有效
PT_TAG = "NASTOOL"
# 搜尋種子過濾屬性
TORRENT_SEARCH_PARAMS = {
    "restype": {
        "BLURAY": r"Blu-?Ray|BD|BDRIP",
        "REMUX": r"REMUX",
        "DOLBY": r"DOLBY|DOVI|\s+DV$|\s+DV\s+",
        "WEB": r"WEB-?DL|WEBRIP",
        "HDTV": r"U?HDTV",
        "UHD": r"UHD",
        "HDR": r"HDR",
        "3D": r"3D"
    },
    "pix": {
        "8k": r"8K",
        "4k": r"4K|2160P|X2160",
        "1080p": r"1080[PIX]|X1080",
        "720p": r"720P"
    }
}
# 電影預設命名格式
DEFAULT_MOVIE_FORMAT = '{title} ({year})/{title} ({year})-{part} - {videoFormat}'
# 電視劇預設命名格式
DEFAULT_TV_FORMAT = '{title} ({year})/Season {season}/{title} - {season_episode}-{part} - 第 {episode} 集'
# 輔助識別引數
KEYWORD_SEARCH_WEIGHT_1 = [10, 3, 2, 0.5, 0.5]
KEYWORD_SEARCH_WEIGHT_2 = [10, 2, 1]
KEYWORD_SEARCH_WEIGHT_3 = [10, 2]
KEYWORD_STR_SIMILARITY_THRESHOLD = 0.2
KEYWORD_DIFF_SCORE_THRESHOLD = 30
KEYWORD_BLACKLIST = ['中字', '韓語', '雙字', '中英', '日語', '雙語', '國粵', 'HD', 'BD', '中日', '粵語', '完全版',
                     '法語',
                     '西班牙語', 'HRHDTVAC3264', '未刪減版', '未刪減', '國語', '字幕組', '人人影視', 'www66ystv',
                     '人人影視製作', '英語', 'www6vhaotv', '無刪減版', '完成版', '德意']
# 網路測試物件
NETTEST_TARGETS = ["www.themoviedb.org",
                   "api.themoviedb.org",
                   "api.tmdb.org",
                   "image.tmdb.org",
                   "webservice.fanart.tv",
                   "api.telegram.org",
                   "qyapi.weixin.qq.com",
                   "www.opensubtitles.org"]

# 站點簽到支援的識別XPATH
SITE_CHECKIN_XPATH = [
    '//a[@id="signed"]',
    '//a[contains(@href, "attendance")]',
    '//a[contains(text(), "簽到")]',
    '//a/b[contains(text(), "籤 到")]',
    '//span[@id="sign_in"]/a',
    '//a[contains(@href, "addbonus")]',
    '//input[@class="dt_button"][contains(@value, "打卡")]',
    '//a[contains(@href, "sign_in")]',
    '//a[@id="do-attendance"]'
]

# 站點詳情頁字幕下載連結識別XPATH
SITE_SUBTITLE_XPATH = [
    '//td[@class="rowhead"][text()="字幕"]/following-sibling::td//a/@href',
]

# 站點登入介面元素XPATH
SITE_LOGIN_XPATH = {
    "username": [
        '//input[@name="username"]'
    ],
    "password": [
        '//input[@name="password"]'
    ],
    "captcha": [
        '//input[@name="imagestring"]'
    ],
    "captcha_img": [
        '//img[@alt="CAPTCHA"]/@src',
        '//img[@alt="SECURITY CODE"]/@src'
    ],
    "submit": [
        '//input[@type="submit"]',
        '//button[@type="submit"]'
    ],
    "error": [
        "//table[@class='main']//td[@class='text']/text()"
    ],
    "twostep": [
        '//input[@name="two_step_code"]',
        '//input[@name="2fa_secret"]'
    ]
}

# WebDriver路徑
WEBDRIVER_PATH = {
    "Docker": "/usr/lib/chromium/chromedriver",
    "Synology": "/var/packages/NASTool/target/bin/chromedriver"
}

# Xvfb虛擬顯示路程
XVFB_PATH = [
    "/usr/bin/Xvfb",
    "/usr/local/bin/Xvfb"
]

# 執行緒鎖
lock = Lock()

# 全域性例項
_CONFIG = None


def singleconfig(cls):
    def _singleconfig(*args, **kwargs):
        global _CONFIG
        if not _CONFIG:
            with lock:
                _CONFIG = cls(*args, **kwargs)
        return _CONFIG

    return _singleconfig


@singleconfig
class Config(object):
    _config = {}
    _config_path = None

    def __init__(self):
        self._config_path = os.environ.get('NASTOOL_CONFIG')
        os.environ['TZ'] = 'Asia/Shanghai'
        self.init_config()

    def init_config(self):
        try:
            if not self._config_path:
                print("【Config】NASTOOL_CONFIG 環境變數未設定，程式無法工作，正在退出...")
                quit()
            if not os.path.exists(self._config_path):
                cfg_tp_path = os.path.join(self.get_inner_config_path(), "config.yaml")
                cfg_tp_path = cfg_tp_path.replace("\\", "/")
                shutil.copy(cfg_tp_path, self._config_path)
                print("【Config】config.yaml 配置檔案不存在，已將配置檔案模板複製到配置目錄...")
            with open(self._config_path, mode='r', encoding='utf-8') as cf:
                try:
                    # 讀取配置
                    print("正在載入配置：%s" % self._config_path)
                    self._config = ruamel.yaml.YAML().load(cf)
                except Exception as e:
                    print("【Config】配置檔案 config.yaml 格式出現嚴重錯誤！請檢查：%s" % str(e))
                    self._config = {}
        except Exception as err:
            print("【Config】載入 config.yaml 配置出錯：%s" % str(err))
            return False

    def get_proxies(self):
        return self.get_config('app').get("proxies")

    def get_ua(self):
        return self.get_config('app').get("user_agent") or DEFAULT_UA

    def get_config(self, node=None):
        if not node:
            return self._config
        return self._config.get(node, {})

    def save_config(self, new_cfg):
        self._config = new_cfg
        with open(self._config_path, mode='w', encoding='utf-8') as sf:
            yaml = ruamel.yaml.YAML()
            return yaml.dump(new_cfg, sf)

    def get_config_path(self):
        return os.path.dirname(self._config_path)

    @staticmethod
    def get_root_path():
        return os.path.dirname(os.path.realpath(__file__))

    def get_inner_config_path(self):
        return os.path.join(self.get_root_path(), "config")

    def get_domain(self):
        domain = (self.get_config('app') or {}).get('domain')
        if domain and not domain.startswith('http'):
            domain = "http://" + domain
        return domain
