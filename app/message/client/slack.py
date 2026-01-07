import re
from threading import Lock

import requests
from slack_sdk.errors import SlackApiError

import log
from app.message.message_client import IMessageClient
from app.utils.exception_utils import ExceptionUtils
from config import Config
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

lock = Lock()


class Slack(IMessageClient):
    _client_config = {}
    _interactive = False
    _ds_url = None
    _service = None
    _client = None

    def __init__(self, config, interactive=False):
        self._config = Config()
        self._client_config = config
        self._interactive = interactive
        self.init_config()

    def init_config(self):
        self._ds_url = "http://127.0.0.1:%s/slack" % self._config.get_config("app").get("web_port")
        if self._client_config:
            try:
                slack_app = App(token=self._client_config.get("bot_token"))
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                return
            self._client = slack_app.client

            # 註冊訊息響應
            @slack_app.event("message")
            def slack_message(message):
                local_res = requests.post(self._ds_url, json=message, timeout=10)
                log.debug("【Slack】message: %s processed, response is: %s" % (message, local_res.text))

            @slack_app.action(re.compile(r"actionId-\d+"))
            def slack_action(ack, body):
                ack()
                local_res = requests.post(self._ds_url, json=body, timeout=60)
                log.debug("【Slack】message: %s processed, response is: %s" % (body, local_res.text))

            @slack_app.event("app_mention")
            def slack_mention(say, body):
                say(f"收到，請稍等... <@{body.get('event', {}).get('user')}>")
                local_res = requests.post(self._ds_url, json=body, timeout=10)
                log.debug("【Slack】message: %s processed, response is: %s" % (body, local_res.text))

            @slack_app.shortcut(re.compile(r"/*"))
            def slack_shortcut(ack, body):
                ack()
                local_res = requests.post(self._ds_url, json=body, timeout=10)
                log.debug("【Slack】message: %s processed, response is: %s" % (body, local_res.text))

            # 啟動服務
            if self._interactive:
                try:
                    self._service = SocketModeHandler(
                        slack_app,
                        self._client_config.get("app_token")
                    )
                    self._service.connect()
                    log.info("Slack訊息接收服務啟動")
                except Exception as err:
                    ExceptionUtils.exception_traceback(err)
                    log.error("Slack訊息接收服務啟動失敗: %s" % str(err))

    def stop_service(self):
        if self._service:
            self._service.close()
            log.info("Slack訊息接收服務已停止")

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
        if not self._client:
            return False, "訊息客戶端未就緒"
        try:
            if user_id:
                channel = user_id
            else:
                # 訊息廣播
                channel = self.__find_public_channel()
            # 拼裝訊息內容
            titles = str(title).split('\n')
            if len(titles) > 1:
                title = titles[0]
                if not text:
                    text = "\n".join(titles[1:])
                else:
                    text = "%s\n%s" % ("\n".join(titles[1:]), text)
            block = {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title}*\n{text}"
                }
            }
            # 訊息圖片
            if image:
                block['accessory'] = {
                    "type": "image",
                    "image_url": f"{image}",
                    "alt_text": f"{title}"
                }
            blocks = [block]
            # 連結
            if image and url:
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "檢視詳情",
                                "emoji": True
                            },
                            "value": "click_me_url",
                            "url": f"{url}",
                            "action_id": "actionId-url"
                        }
                    ]
                })
            # 傳送
            result = self._client.chat_postMessage(
                channel=channel,
                blocks=blocks
            )
            return True, result
        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def send_list_msg(self, medias: list, user_id="", **kwargs):
        """
        傳送列表類訊息
        """
        if not medias:
            return False, "引數有誤"
        if not self._client:
            return False, "訊息客戶端未就緒"
        try:
            if user_id:
                channel = user_id
            else:
                # 訊息廣播
                channel = self.__find_public_channel()
            title = f"共找到{len(medias)}條相關資訊，請選擇"
            # 訊息主體
            title_section = {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title}*"
                }
            }
            blocks = [title_section]
            # 列表
            if medias:
                blocks.append({
                    "type": "divider"
                })
                index = 1
                for media in medias:
                    if media.get_poster_image():
                        if media.get_star_string():
                            text = f"{index}. *<{media.get_detail_url()}|{media.get_title_string()}>*" \
                                   f"\n{media.get_type_string()}" \
                                   f"\n{media.get_star_string()}" \
                                   f"\n{media.get_overview_string(50)}"
                        else:
                            text = f"{index}. *<{media.get_detail_url()}|{media.get_title_string()}>*" \
                                   f"\n{media.get_type_string()}" \
                                   f"\n{media.get_overview_string(50)}"
                        blocks.append(
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": text
                                },
                                "accessory": {
                                    "type": "image",
                                    "image_url": f"{media.get_poster_image()}",
                                    "alt_text": f"{media.get_title_string()}"
                                }
                            }
                        )
                        blocks.append(
                            {
                                "type": "actions",
                                "elements": [
                                    {
                                        "type": "button",
                                        "text": {
                                            "type": "plain_text",
                                            "text": "選擇",
                                            "emoji": True
                                        },
                                        "value": f"{index}",
                                        "action_id": f"actionId-{index}"
                                    }
                                ]
                            }
                        )
                        index += 1
            # 傳送
            result = self._client.chat_postMessage(
                channel=channel,
                blocks=blocks
            )
            return True, result
        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def __find_public_channel(self):
        """
        查詢公共頻道
        """
        if not self._client:
            return ""
        conversation_id = ""
        try:
            for result in self._client.conversations_list():
                if conversation_id:
                    break
                for channel in result["channels"]:
                    if channel.get("name") == "全體":
                        conversation_id = channel.get("id")
                        break
        except SlackApiError as e:
            print(f"Slack Error: {e}")
        return conversation_id
