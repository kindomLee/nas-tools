import time

from app.message import Message
from app.mediaserver import MediaServer
from app.utils import WebUtils


class WebhookEvent:
    message = None
    mediaserver = None

    def __init__(self):
        self.message = Message()
        self.mediaserver = MediaServer()

    @staticmethod
    def __parse_plex_msg(message):
        """
        解析Plex報文
        """
        eventItem = {'event': message.get('event', {}),
                     'item_name': message.get('Metadata', {}).get('title'),
                     'user_name': message.get('Account', {}).get('title')
                     }
        return eventItem

    @staticmethod
    def __parse_jellyfin_msg(message):
        """
        解析Jellyfin報文
        """
        eventItem = {'event': message.get('NotificationType', {}),
                     'item_name': message.get('Name'),
                     'user_name': message.get('NotificationUsername')
                     }
        return eventItem

    @staticmethod
    def __parse_emby_msg(message):
        """
        解析Emby報文
        """
        eventItem = {'event': message.get('Event', {})}
        if message.get('Item'):
            if message.get('Item', {}).get('Type') == 'Episode':
                eventItem['item_type'] = "TV"
                eventItem['item_name'] = "%s %s" % (
                    message.get('Item', {}).get('SeriesName'), message.get('Item', {}).get('Name'))
                eventItem['item_id'] = message.get('Item', {}).get('SeriesId')
                eventItem['tmdb_id'] = message.get('Item', {}).get('ProviderIds', {}).get('Tmdb')
            else:
                eventItem['item_type'] = "MOV"
                eventItem['item_name'] = message.get('Item', {}).get('Name')
                eventItem['item_path'] = message.get('Item', {}).get('Path')
                eventItem['item_id'] = message.get('Item', {}).get('Id')
                eventItem['tmdb_id'] = message.get('Item', {}).get('ProviderIds', {}).get('Tmdb')
        if message.get('Session'):
            eventItem['ip'] = message.get('Session').get('RemoteEndPoint')
            eventItem['device_name'] = message.get('Session').get('DeviceName')
            eventItem['client'] = message.get('Session').get('Client')
        if message.get("User"):
            eventItem['user_name'] = message.get("User").get('Name')

        return eventItem

    def plex_action(self, message):
        """
        執行Plex webhook動作
        """
        event_info = self.__parse_plex_msg(message)
        if event_info.get("event") in ["media.play", "media.stop"]:
            self.send_webhook_message(event_info, 'plex')

    def jellyfin_action(self, message):
        """
        執行Jellyfin webhook動作
        """
        event_info = self.__parse_jellyfin_msg(message)
        if event_info.get("event") in ["PlaybackStart", "PlaybackStop"]:
            self.send_webhook_message(event_info, 'jellyfin')

    def emby_action(self, message):
        """
        執行Emby webhook動作
        """
        event_info = self.__parse_emby_msg(message)
        if event_info.get("event") == "system.webhooktest":
            return
        elif event_info.get("event") in ["playback.start", "playback.stop"]:
            self.send_webhook_message(event_info, 'emby')

    def send_webhook_message(self, event_info, channel):
        """
        傳送訊息
        """
        _webhook_actions = {
            "system.webhooktest": "測試",
            "playback.start": "開始播放",
            "media.play": "開始播放",
            "PlaybackStart": "開始播放",
            "PlaybackStop": "停止播放",
            "playback.stop": "停止播放",
            "media.stop": "停止播放",
            "item.rate": "標記了",
        }
        _webhook_images = {
            "emby": "https://emby.media/notificationicon.png",
            "plex": "https://www.plex.tv/wp-content/uploads/2022/04/new-logo-process-lines-gray.png",
            "jellyfin": "https://play-lh.googleusercontent.com/SCsUK3hCCRqkJbmLDctNYCfehLxsS4ggD1ZPHIFrrAN1Tn9yhjmGMPep2D9lMaaa9eQi"
        }

        if self.is_ignore_webhook_message(event_info.get('user_name'), event_info.get('device_name')):
            return
        # 訊息標題
        message_title = f"使用者 {event_info.get('user_name')} {_webhook_actions.get(event_info.get('event'))} {event_info.get('item_name')}"
        # 訊息內容
        message_texts = []
        if event_info.get('device_name'):
            message_texts.append(f"裝置：{event_info.get('device_name')}")
        if event_info.get('client'):
            message_texts.append(f"客戶端：{event_info.get('client')}")
        if event_info.get('ip'):
            message_texts.append(f"IP地址：{event_info.get('ip')}")
            message_texts.append(f"位置：{WebUtils.get_location(event_info.get('ip'))}")
        message_texts.append(f"時間：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}")
        # 訊息圖片
        if event_info.get('item_id'):
            image_url = self.mediaserver.get_image_by_id(event_info.get('item_id'), "Backdrop") or _webhook_images.get(
                channel)
        else:
            image_url = _webhook_images.get(channel)
        # 傳送訊息
        self.message.send_mediaserver_message(title=message_title, text="\n".join(message_texts), image=image_url)

    def is_ignore_webhook_message(self, user_name, device_name):
        """
        判斷是否忽略通知
        """
        if not user_name and not device_name:
            return False
        webhook_ignore = self.message.get_webhook_ignore()
        if not webhook_ignore:
            return False
        if user_name in webhook_ignore or \
                device_name in webhook_ignore or \
                (user_name + ':' + device_name) in webhook_ignore:
            return True
        return False
