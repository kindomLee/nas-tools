import re
import json
from enum import Enum

import log
from app.utils.commons import singleton
from config import Config
from app.helper import DbHelper
from app.message.client import Bark, IyuuMsg, PushDeerClient, PushPlus, ServerChan, Telegram, WeChat, Slack, Gotify
from app.utils import StringUtils
from app.message.message_center import MessageCenter
from app.utils.types import SearchType, MediaType


@singleton
class Message:
    _active_clients = []
    _client_configs = {}
    _webhook_ignore = None
    _domain = None
    dbhelper = None
    messagecenter = None

    # 訊息通知型別
    MESSAGE_DICT = {
        "client": {
            "telegram": {"name": "Telegram", "img_url": "../static/img/telegram.png", "search_type": SearchType.TG},
            "wechat": {"name": "微信", "img_url": "../static/img/wechat.png", "search_type": SearchType.WX},
            "serverchan": {"name": "Server醬", "img_url": "../static/img/serverchan.png"},
            "bark": {"name": "Bark", "img_url": "../static/img/bark.webp"},
            "pushdeer": {"name": "PushDeer", "img_url": "../static/img/pushdeer.png"},
            "pushplus": {"name": "PushPlus", "img_url": "../static/img/pushplus.jpg"},
            "iyuu": {"name": "愛語飛飛", "img_url": "../static/img/iyuu.png"},
            "slack": {"name": "Slack", "img_url": "../static/img/slack.png", "search_type": SearchType.SLACK},
            "gotify": {"name": "Gotify", "img_url": "../static/img/gotify.png"},
        },
        "switch": {
            "download_start": {"name": "新增下載", "fuc_name": "download_start"},
            "download_fail": {"name": "下載失敗", "fuc_name": "download_fail"},
            "transfer_finished": {"name": "入庫完成", "fuc_name": "transfer_finished"},
            "transfer_fail": {"name": "入庫失敗", "fuc_name": "transfer_fail"},
            "rss_added": {"name": "新增訂閱", "fuc_name": "rss_added"},
            "rss_finished": {"name": "訂閱完成", "fuc_name": "rss_finished"},
            "site_signin": {"name": "站點簽到", "fuc_name": "site_signin"},
            "site_message": {"name": "站點訊息", "fuc_name": "site_message"},
            "brushtask_added": {"name": "刷流下種", "fuc_name": "brushtask_added"},
            "brushtask_remove": {"name": "刷流刪種", "fuc_name": "brushtask_remove"},
            "mediaserver_message": {"name": "媒體服務", "fuc_name": "mediaserver_message"},
        }
    }

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.dbhelper = DbHelper()
        self.messagecenter = MessageCenter()
        self._domain = Config().get_domain()
        # 停止舊服務
        if self._active_clients:
            for active_client in self._active_clients:
                if active_client.get("search_type") in [SearchType.TG, SearchType.SLACK]:
                    client = active_client.get("client")
                    if client:
                        client.stop_service()
        # 初始化訊息客戶端
        self._active_clients = []
        self._client_configs = {}
        for client_config in self.dbhelper.get_message_client() or []:
            cid = client_config.ID
            name = client_config.NAME
            enabled = client_config.ENABLED
            config = json.loads(client_config.CONFIG) if client_config.CONFIG else {}
            ctype = client_config.TYPE
            switchs = json.loads(client_config.SWITCHS) if client_config.SWITCHS else []
            interactive = client_config.INTERACTIVE
            self._client_configs[str(cid)] = {
                "id": cid,
                "name": name,
                "type": ctype,
                "config": config,
                "switchs": switchs,
                "interactive": interactive,
                "enabled": enabled,
            }
            if not enabled or not config:
                continue
            self._active_clients.append({
                "name": name,
                "type": ctype,
                "search_type": self.MESSAGE_DICT.get('client').get(ctype, {}).get('search_type'),
                "client": self.__build_client(ctype, config, interactive),
                "config": config,
                "switchs": switchs,
                "interactive": interactive
            })

    @staticmethod
    def __build_client(ctype, conf, interactive=False):
        """
        構造客戶端例項
        """
        if ctype == "wechat":
            return WeChat(conf, interactive)
        elif ctype == "telegram":
            return Telegram(conf, interactive)
        elif ctype == "serverchan":
            return ServerChan(conf)
        elif ctype == "bark":
            return Bark(conf)
        elif ctype == "pushdeer":
            return PushDeerClient(conf)
        elif ctype == "pushplus":
            return PushPlus(conf)
        elif ctype == "iyuu":
            return IyuuMsg(conf)
        elif ctype == "slack":
            return Slack(conf, interactive)
        elif ctype == "gotify":
            return Gotify(conf)
        else:
            return None

    def get_webhook_ignore(self):
        """
        獲取Emby/Jellyfin不通知的裝置清單
        """
        return self._webhook_ignore or []

    def __sendmsg(self, client, title, text="", image="", url="", user_id=""):
        """
        通用訊息傳送
        :param client: 訊息端
        :param title: 訊息標題
        :param text: 訊息內容
        :param image: 圖片URL
        :param url: 訊息跳轉地址
        :param user_id: 使用者ID，如有則只發給這個使用者
        :return: 傳送狀態、錯誤資訊
        """
        if not client or not client.get('client'):
            return None
        cname = client.get('name')
        log.info(f"【Message】傳送訊息 {cname}：title={title}, text={text}")
        if self._domain:
            if url:
                if not url.startswith("http"):
                    url = "%s?next=%s" % (self._domain, url)
            else:
                url = self._domain
        else:
            url = ""
        state, ret_msg = client.get('client').send_msg(title=title,
                                                       text=text,
                                                       image=image,
                                                       url=url,
                                                       user_id=user_id)
        if not state:
            log.error(f"【Message】{cname} 訊息傳送失敗：%s" % ret_msg)
        return state

    def send_channel_msg(self, channel, title, text="", image="", url="", user_id=""):
        """
        按渠道傳送訊息，用於訊息互動
        :param channel: 訊息渠道
        :param title: 訊息標題
        :param text: 訊息內容
        :param image: 圖片URL
        :param url: 訊息跳轉地址
        :param user_id: 使用者ID，如有則只發給這個使用者
        :return: 傳送狀態、錯誤資訊
        """
        # 插入訊息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 傳送訊息
        for client in self._active_clients:
            if client.get("search_type") == channel:
                state = self.__sendmsg(client=client,
                                       title=title,
                                       text=text,
                                       image=image,
                                       url=url,
                                       user_id=user_id)
                return state
        return False

    def __send_list_msg(self, client, medias, user_id, title):
        """
        傳送選擇類訊息
        """
        if not client or not client.get('client'):
            return False, ""
        return client.get('client').send_list_msg(medias=medias,
                                                  user_id=user_id,
                                                  title=title,
                                                  url=self._domain)

    def send_channel_list_msg(self, channel, title, medias: list, user_id=""):
        """
        傳送列表選擇訊息，用於訊息互動
        :param channel: 訊息渠道
        :param title: 訊息標題
        :param medias: 媒體資訊列表
        :param user_id: 使用者ID，如有則只發給這個使用者
        :return: 傳送狀態、錯誤資訊
        """
        for client in self._active_clients:
            if client.get("search_type") == channel:
                state, ret_msg = self.__send_list_msg(client=client,
                                                      title=title,
                                                      medias=medias,
                                                      user_id=user_id)
                if not state:
                    log.error(f"【Message】{client.get('name')} 傳送訊息失敗：%s" % ret_msg)
                return state
        return False

    def send_download_message(self, in_from: SearchType, can_item):
        """
        傳送下載的訊息
        :param in_from: 下載來源
        :param can_item: 下載的媒體資訊
        :return: 傳送狀態、錯誤資訊
        """
        msg_title = f"{can_item.get_title_ep_string()} 開始下載"
        msg_text = f"{can_item.get_star_string()}"
        msg_text = f"{msg_text}\n來自：{in_from.value}"
        if can_item.user_name:
            msg_text = f"{msg_text}\n使用者：{can_item.user_name}"
        if can_item.site:
            if in_from == SearchType.USERRSS:
                msg_text = f"{msg_text}\n任務：{can_item.site}"
            else:
                msg_text = f"{msg_text}\n站點：{can_item.site}"
        if can_item.get_resource_type_string():
            msg_text = f"{msg_text}\n質量：{can_item.get_resource_type_string()}"
        if can_item.size:
            if str(can_item.size).isdigit():
                size = StringUtils.str_filesize(can_item.size)
            else:
                size = can_item.size
            msg_text = f"{msg_text}\n大小：{size}"
        if can_item.org_string:
            msg_text = f"{msg_text}\n種子：{can_item.org_string}"
        if can_item.seeders:
            msg_text = f"{msg_text}\n做種數：{can_item.seeders}"
        msg_text = f"{msg_text}\n促銷：{can_item.get_volume_factor_string()}"
        if can_item.hit_and_run:
            msg_text = f"{msg_text}\nHit&Run：是"
        if can_item.description:
            html_re = re.compile(r'<[^>]+>', re.S)
            description = html_re.sub('', can_item.description)
            can_item.description = re.sub(r'<[^>]+>', '', description)
            msg_text = f"{msg_text}\n描述：{can_item.description}"
        # 插入訊息中心
        self.messagecenter.insert_system_message(level="INFO", title=msg_title, content=msg_text)
        # 傳送訊息
        for client in self._active_clients:
            if "download_start" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_text,
                    image=can_item.get_message_image(),
                    url='downloading'
                )

    def send_transfer_movie_message(self, in_from: Enum, media_info, exist_filenum, category_flag):
        """
        傳送轉移電影的訊息
        :param in_from: 轉移來源
        :param media_info: 轉移的媒體資訊
        :param exist_filenum: 已存在的檔案數
        :param category_flag: 二級分類開關
        :return: 傳送狀態、錯誤資訊
        """
        msg_title = f"{media_info.get_title_string()} 已入庫"
        if media_info.vote_average:
            msg_str = f"{media_info.get_vote_string()}，型別：電影"
        else:
            msg_str = "型別：電影"
        if media_info.category:
            if category_flag:
                msg_str = f"{msg_str}，類別：{media_info.category}"
        if media_info.get_resource_type_string():
            msg_str = f"{msg_str}，質量：{media_info.get_resource_type_string()}"
        msg_str = f"{msg_str}，大小：{StringUtils.str_filesize(media_info.size)}，來自：{in_from.value}"
        if exist_filenum != 0:
            msg_str = f"{msg_str}，{exist_filenum}個檔案已存在"
        # 插入訊息中心
        self.messagecenter.insert_system_message(level="INFO", title=msg_title, content=msg_str)
        # 傳送訊息
        for client in self._active_clients:
            if "transfer_finished" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_str,
                    image=media_info.get_message_image(),
                    url='history'
                )

    def send_transfer_tv_message(self, message_medias: dict, in_from: Enum):
        """
        傳送轉移電視劇/動漫的訊息
        """
        for item_info in message_medias.values():
            if item_info.total_episodes == 1:
                msg_title = f"{item_info.get_title_string()} {item_info.get_season_episode_string()} 已入庫"
            else:
                msg_title = f"{item_info.get_title_string()} {item_info.get_season_string()} 共{item_info.total_episodes}集 已入庫"
            if item_info.vote_average:
                msg_str = f"{item_info.get_vote_string()}，型別：{item_info.type.value}"
            else:
                msg_str = f"型別：{item_info.type.value}"
            if item_info.category:
                msg_str = f"{msg_str}，類別：{item_info.category}"
            if item_info.total_episodes == 1:
                msg_str = f"{msg_str}，大小：{StringUtils.str_filesize(item_info.size)}，來自：{in_from.value}"
            else:
                msg_str = f"{msg_str}，總大小：{StringUtils.str_filesize(item_info.size)}，來自：{in_from.value}"
            # 插入訊息中心
            self.messagecenter.insert_system_message(level="INFO", title=msg_title, content=msg_str)
            # 傳送訊息
            for client in self._active_clients:
                if "transfer_finished" in client.get("switchs"):
                    self.__sendmsg(
                        client=client,
                        title=msg_title,
                        text=msg_str,
                        image=item_info.get_message_image(),
                        url='history')

    def send_download_fail_message(self, item, error_msg):
        """
        傳送下載失敗的訊息
        """
        title = "新增下載任務失敗：%s %s" % (item.get_title_string(), item.get_season_episode_string())
        text = f"站點：{item.site}\n種子名稱：{item.org_string}\n種子連結：{item.enclosure}\n錯誤資訊：{error_msg}"
        # 插入訊息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 傳送訊息
        for client in self._active_clients:
            if "download_fail" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    image=item.get_message_image()
                )

    def send_rss_success_message(self, in_from: Enum, media_info):
        """
        傳送訂閱成功的訊息
        """
        if media_info.type == MediaType.MOVIE:
            msg_title = f"{media_info.get_title_string()} 已新增訂閱"
        else:
            msg_title = f"{media_info.get_title_string()} {media_info.get_season_string()} 已新增訂閱"
        msg_str = f"型別：{media_info.type.value}"
        if media_info.vote_average:
            msg_str = f"{msg_str}，{media_info.get_vote_string()}"
        msg_str = f"{msg_str}，來自：{in_from.value}"
        if media_info.user_name:
            msg_str = f"{msg_str}，使用者：{media_info.user_name}"
        # 插入訊息中心
        self.messagecenter.insert_system_message(level="INFO", title=msg_title, content=msg_str)
        # 傳送訊息
        for client in self._active_clients:
            if "rss_added" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_str,
                    image=media_info.get_message_image(),
                    url='movie_rss' if media_info.type == MediaType.MOVIE else 'tv_rss'
                )

    def send_rss_finished_message(self, media_info):
        """
        傳送訂閱完成的訊息，只針對電視劇
        """
        if media_info.type == MediaType.MOVIE:
            return
        else:
            msg_title = f"{media_info.get_title_string()} {media_info.get_season_string()} 已完成訂閱"
        msg_str = f"型別：{media_info.type.value}"
        if media_info.vote_average:
            msg_str = f"{msg_str}，{media_info.get_vote_string()}"
        # 插入訊息中心
        self.messagecenter.insert_system_message(level="INFO", title=msg_title, content=msg_str)
        # 傳送訊息
        for client in self._active_clients:
            if "rss_finished" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=msg_title,
                    text=msg_str,
                    image=media_info.get_message_image(),
                    url='downloaded'
                )

    def send_site_signin_message(self, msgs: list):
        """
        傳送站點簽到訊息
        """
        if not msgs:
            return
        title = "站點簽到"
        text = "\n".join(msgs)
        # 插入訊息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 傳送訊息
        for client in self._active_clients:
            if "site_signin" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text
                )

    def send_site_message(self, title=None, text=None):
        """
        傳送站點訊息
        """
        if not title:
            return
        if not text:
            text = ""
        # 插入訊息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 傳送訊息
        for client in self._active_clients:
            if "site_message" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text
                )

    def send_transfer_fail_message(self, path, count, text):
        """
        傳送轉移失敗的訊息
        """
        if not path or not count:
            return
        title = f"【{count} 個檔案入庫失敗】"
        text = f"源路徑：{path}\n原因：{text}"
        # 插入訊息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 傳送訊息
        for client in self._active_clients:
            if "transfer_fail" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="unidentification"
                )

    def send_brushtask_remove_message(self, title, text):
        """
        傳送刷流刪種的訊息
        """
        if not title or not text:
            return
        # 插入訊息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 傳送訊息
        for client in self._active_clients:
            if "brushtask_remove" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="brushtask"
                )

    def send_brushtask_added_message(self, title, text):
        """
        傳送刷流下種的訊息
        """
        if not title or not text:
            return
        # 插入訊息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 傳送訊息
        for client in self._active_clients:
            if "brushtask_added" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    url="brushtask"
                )

    def send_mediaserver_message(self, title, text, image):
        """
        傳送媒體伺服器的訊息
        """
        if not title or not text or not image:
            return
        # 插入訊息中心
        self.messagecenter.insert_system_message(level="INFO", title=title, content=text)
        # 傳送訊息
        for client in self._active_clients:
            if "mediaserver_message" in client.get("switchs"):
                self.__sendmsg(
                    client=client,
                    title=title,
                    text=text,
                    image=image
                )

    def get_message_client_info(self, cid=None):
        """
        獲取訊息端資訊
        """
        if cid:
            return self._client_configs.get(str(cid))
        return self._client_configs

    def get_interactive_client(self, client_type=None):
        """
        查詢當前可以互動的渠道
        """
        if client_type:
            for client in Message().get_interactive_client():
                if client.get("search_type") == client_type:
                    return client
            return None
        else:
            ret_clients = []
            for client in self._active_clients:
                if client.get('interactive'):
                    ret_clients.append(client)
            return ret_clients

    def get_status(self, ctype=None, config=None):
        """
        測試訊息設定狀態
        """
        if not config or not ctype:
            return False
        # 測試狀態不啟動監聽服務
        state, ret_msg = self.__build_client(ctype=ctype,
                                             conf=config,
                                             interactive=False).send_msg(title="測試",
                                                                         text="這是一條測試訊息",
                                                                         url="https://github.com/kindomLee/nas-tools")
        if not state:
            log.error(f"【Message】{ctype} 傳送測試訊息失敗：%s" % ret_msg)
        return state
