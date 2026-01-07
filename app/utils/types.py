from enum import Enum


class MediaType(Enum):
    TV = '電視劇'
    MOVIE = '電影'
    ANIME = '動漫'
    UNKNOWN = '未知'


class DownloaderType(Enum):
    QB = 'Qbittorrent'
    TR = 'Transmission'
    Client115 = '115網盤'
    Aria2 = 'Aria2'


class SyncType(Enum):
    MAN = "手動整理"
    MON = "目錄同步"


class SearchType(Enum):
    WX = "微信"
    WEB = "WEB"
    DB = "豆瓣"
    RSS = "電影/電視劇訂閱"
    USERRSS = "自定義訂閱"
    OT = "手動下載"
    TG = "Telegram"
    API = "第三方API請求"
    SLACK = "Slack"


class RmtMode(Enum):
    LINK = "硬連結"
    SOFTLINK = "軟連結"
    COPY = "複製"
    MOVE = "移動"
    RCLONECOPY = "Rclone複製"
    RCLONE = "Rclone移動"
    MINIOCOPY = "Minio複製"
    MINIO = "Minio移動"


class MatchMode(Enum):
    NORMAL = "正常模式"
    STRICT = "嚴格模式"


class OsType(Enum):
    WINDOWS = "Windows"
    LINUX = "Linux"
    SYNOLOGY = "Synology"
    MACOS = "MacOS"
    DOCKER = "Docker"


class IndexerType(Enum):
    JACKETT = "Jackett"
    PROWLARR = "Prowlarr"
    BUILTIN = "Indexer"


class MediaServerType(Enum):
    JELLYFIN = "Jellyfin"
    EMBY = "Emby"
    PLEX = "Plex"


class BrushDeleteType(Enum):
    NOTDELETE = "不刪除"
    SEEDTIME = "做種時間"
    RATIO = "分享率"
    UPLOADSIZE = "上傳量"
    DLTIME = "下載耗時"
    AVGUPSPEED = "平均上傳速度"


class SystemDictType(Enum):
    BrushMessageSwitch = "刷流訊息開關"
    BrushForceUpSwitch = "刷流強制做種開關"


# 轉移模式
RMT_MODES = {
    "copy": RmtMode.COPY,
    "link": RmtMode.LINK,
    "softlink": RmtMode.SOFTLINK,
    "move": RmtMode.MOVE,
    "rclone": RmtMode.RCLONE,
    "rclonecopy": RmtMode.RCLONECOPY,
    "minio": RmtMode.MINIO,
    "miniocopy": RmtMode.MINIOCOPY
}


# 站點框架
class SiteSchema(Enum):
    DiscuzX = "Discuz!"
    Gazelle = "Gazelle"
    Ipt = "IPTorrents"
    NexusPhp = "NexusPhp"
    NexusProject = "NexusProject"
    NexusRabbit = "NexusRabbit"
    SmallHorse = "Small Horse"
    Unit3d = "Unit3d"
