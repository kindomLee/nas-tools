from threading import Event, Lock
from urllib.parse import urlencode

import requests

import log
from app.helper import ThreadHelper
from app.message.message_client import IMessageClient
from app.utils import RequestUtils
from app.utils.exception_utils import ExceptionUtils
from config import Config

lock = Lock()
WEBHOOK_STATUS = False


class Telegram(IMessageClient):
    _telegram_token = None
    _telegram_chat_id = None
    _webhook = None
    _webhook_url = None
    _telegram_user_ids = []
    _domain = None
    _config = None
    _message_proxy_event = None
    _client_config = {}
    _interactive = False
    _enabled = True

    def __init__(self, config, interactive=False):
        self._config = Config()
        self._client_config = config
        self._interactive = interactive
        self._domain = self._config.get_domain()
        if self._domain and self._domain.endswith("/"):
            self._domain = self._domain[:-1]
        self.init_config()

    def init_config(self):
        if self._client_config:
            self._telegram_token = self._client_config.get('token')
            self._telegram_chat_id = self._client_config.get('chat_id')
            self._webhook = self._client_config.get('webhook')
            telegram_user_ids = self._client_config.get('user_ids')
            if telegram_user_ids:
                self._telegram_user_ids = telegram_user_ids.split(",")
            else:
                self._telegram_user_ids = []
            if self._telegram_token and self._telegram_chat_id:
                if self._webhook:
                    if self._domain:
                        self._webhook_url = "%s/telegram" % self._domain
                        self.__set_bot_webhook()
                    if self._message_proxy_event:
                        self._message_proxy_event.set()
                        self._message_proxy_event = None
                elif self._interactive:
                    self.__del_bot_webhook()
                    if not self._message_proxy_event:
                        event = Event()
                        self._message_proxy_event = event
                        ThreadHelper().start_thread(self.__start_telegram_message_proxy, [event])

    def get_admin_user(self):
        """
        獲取Telegram配置檔案中的ChatId，即管理員使用者ID
        """
        return str(self._telegram_chat_id)

    def send_msg(self, title, text="", image="", url="", user_id=""):
        """
        傳送Telegram訊息
        :param title: 訊息標題
        :param text: 訊息內容
        :param image: 訊息圖片地址
        :param url: 點選訊息轉轉的URL
        :param user_id: 使用者ID，如有則只發訊息給該使用者
        :user_id: 傳送訊息的目標使用者ID，為空則發給管理員
        """
        if not title and not text:
            return False, "標題和內容不能同時為空"
        try:
            if not self._telegram_token or not self._telegram_chat_id:
                return False, "引數未配置"

            # 拼裝訊息內容
            titles = str(title).split('\n')
            if len(titles) > 1:
                title = titles[0]
                if not text:
                    text = "\n".join(titles[1:])
                else:
                    text = "%s\n%s" % ("\n".join(titles[1:]), text)
            if text:
                caption = "*%s*\n%s" % (title, text.replace("\n\n", "\n"))
            else:
                caption = title
            if image and url:
                caption = "%s\n\n[檢視詳情](%s)" % (caption, url)
            if user_id:
                chat_id = user_id
            else:
                chat_id = self._telegram_chat_id
            if image:
                # 傳送圖文訊息
                values = {"chat_id": chat_id, "photo": image, "caption": caption, "parse_mode": "Markdown"}
                sc_url = "https://api.telegram.org/bot%s/sendPhoto?" % self._telegram_token
            else:
                # 傳送文字
                values = {"chat_id": chat_id, "text": caption, "parse_mode": "Markdown"}
                sc_url = "https://api.telegram.org/bot%s/sendMessage?" % self._telegram_token
            return self.__send_request(sc_url, values)

        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def send_list_msg(self, medias: list, user_id="", title="", **kwargs):
        """
        傳送列表類訊息
        """
        try:
            if not self._telegram_token or not self._telegram_chat_id:
                return False, "引數未配置"
            if not title or not isinstance(medias, list):
                return False, "資料錯誤"
            index, image, caption = 1, "", "*%s*" % title
            for media in medias:
                if not image:
                    image = media.get_message_image()
                if media.get_vote_string():
                    caption = "%s\n%s. [%s](%s)\n%s，%s" % (caption,
                                                           index,
                                                           media.get_title_string(),
                                                           media.get_detail_url(),
                                                           media.get_type_string(),
                                                           media.get_vote_string())
                else:
                    caption = "%s\n%s. [%s](%s)\n%s" % (caption,
                                                        index,
                                                        media.get_title_string(),
                                                        media.get_detail_url(),
                                                        media.get_type_string())
                index += 1

            if user_id:
                chat_id = user_id
            else:
                chat_id = self._telegram_chat_id

            # 傳送圖文訊息
            values = {"chat_id": chat_id, "photo": image, "caption": caption, "parse_mode": "Markdown"}
            sc_url = "https://api.telegram.org/bot%s/sendPhoto?" % self._telegram_token
            return self.__send_request(sc_url, values)

        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def __send_request(self, sc_url, values):
        """
        向Telegram傳送報文
        """
        res = RequestUtils(proxies=self._config.get_proxies()).get_res(sc_url + urlencode(values))
        if res:
            ret_json = res.json()
            status = ret_json.get("ok")
            if status:
                return True, ""
            else:
                return False, ret_json.get("description")
        else:
            return False, "未獲取到返回資訊"

    def __set_bot_webhook(self):
        """
        設定Telegram Webhook
        """
        if not self._webhook_url:
            return

        try:
            lock.acquire()
            global WEBHOOK_STATUS
            if not WEBHOOK_STATUS:
                WEBHOOK_STATUS = True
            else:
                return
        finally:
            lock.release()

        status = self.__get_bot_webhook()
        if status and status != 1:
            if status == 2:
                self.__del_bot_webhook()
            values = {"url": self._webhook_url, "allowed_updates": ["message"]}
            sc_url = "https://api.telegram.org/bot%s/setWebhook?" % self._telegram_token
            res = RequestUtils(proxies=self._config.get_proxies()).get_res(sc_url + urlencode(values))
            if res is not None:
                json = res.json()
                if json.get("ok"):
                    log.info("【Telegram】Webhook 設定成功，地址為：%s" % self._webhook_url)
                else:
                    log.error("【Telegram】Webhook 設定失敗：" % json.get("description"))
            else:
                log.error("【Telegram】Webhook 設定失敗：網路連線故障！")

    def __get_bot_webhook(self):
        """
        獲取Telegram已設定的Webhook
        :return: 狀態：1-存在且相等，2-存在不相等，3-不存在，0-網路出錯
        """
        sc_url = "https://api.telegram.org/bot%s/getWebhookInfo" % self._telegram_token
        res = RequestUtils(proxies=self._config.get_proxies()).get_res(sc_url)
        if res is not None and res.json():
            if res.json().get("ok"):
                result = res.json().get("result") or {}
                webhook_url = result.get("url") or ""
                if webhook_url:
                    log.info("【Telegram】Webhook 地址為：%s" % webhook_url)
                pending_update_count = result.get("pending_update_count")
                last_error_message = result.get("last_error_message")
                if pending_update_count and last_error_message:
                    log.warn("【Telegram】Webhook 有 %s 條訊息掛起，最後一次失敗原因為：%s" % (
                        pending_update_count, last_error_message))
                if webhook_url == self._webhook_url:
                    return 1
                else:
                    return 2
            else:
                return 3
        else:
            return 0

    def __del_bot_webhook(self):
        """
        刪除Telegram Webhook
        :return: 是否成功
        """
        sc_url = "https://api.telegram.org/bot%s/deleteWebhook" % self._telegram_token
        res = RequestUtils(proxies=self._config.get_proxies()).get_res(sc_url)
        if res and res.json() and res.json().get("ok"):
            return True
        else:
            return False

    def get_users(self):
        """
        獲取Telegram配置檔案中的User Ids，即允許使用telegram機器人的user_id列表
        """
        return self._telegram_user_ids

    def __start_telegram_message_proxy(self, event: Event):
        log.info("Telegram訊息接收服務啟動")

        long_poll_timeout = 5

        def consume_messages(_config, _offset, _sc_url, _ds_url):
            try:
                values = {"timeout": long_poll_timeout, "offset": _offset}
                res = RequestUtils(proxies=_config.get_proxies()).get_res(_sc_url + urlencode(values))
                if res and res.json():
                    for msg in res.json().get("result", []):
                        # 無論本地是否成功，先更新offset，即訊息最多成功消費一次
                        _offset = msg["update_id"] + 1
                        log.info("【Telegram】接收到訊息: %s" % msg)
                        local_res = requests.post(_ds_url, json=msg, timeout=10)
                        log.debug("【Telegram】message: %s processed, response is: %s" % (msg, local_res.text))
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                log.error("【Telegram】訊息接收出現錯誤: %s" % e)
            return _offset

        offset = 0
        while True:
            _config = Config()
            web_port = _config.get_config("app").get("web_port")
            sc_url = "https://api.telegram.org/bot%s/getUpdates?" % self._telegram_token
            ds_url = "http://127.0.0.1:%s/telegram" % web_port
            if not self._enabled:
                log.info("Telegram訊息接收服務已停止")
                break

            i = 0
            while i < 20 and not event.is_set():
                offset = consume_messages(_config, offset, sc_url, ds_url)
                i = i + 1

    def stop_service(self):
        """
        停止服務
        """
        self._enabled = False
