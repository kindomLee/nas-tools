from pypushdeer import PushDeer

from app.message.message_client import IMessageClient
from app.utils import StringUtils
from app.utils.exception_utils import ExceptionUtils


class PushDeerClient(IMessageClient):
    _server = None
    _apikey = None
    _client_config = {}

    def __init__(self, config):
        self._client_config = config
        self.init_config()

    def init_config(self):
        if self._client_config:
            self._server = StringUtils.get_base_url(self._client_config.get('server'))
            self._apikey = self._client_config.get('apikey')

    def send_msg(self, title, text="", image="", url="", user_id=""):
        """
        傳送PushDeer訊息
        :param title: 訊息標題
        :param text: 訊息內容
        :param image: 未使用
        :param url: 未使用
        :param user_id: 未使用
        :return: 傳送狀態、錯誤資訊
        """
        if not title and not text:
            return False, "標題和內容不能同時為空"
        try:
            if not self._server or not self._apikey:
                return False, "引數未配置"
            pushdeer = PushDeer(server=self._server, pushkey=self._apikey)
            res = pushdeer.send_markdown(title, desp=text)
            if res:
                return True, "成功"
            else:
                return False, "失敗"
        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def send_list_msg(self, **kwargs):
        pass
