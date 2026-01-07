from urllib.parse import urlencode

from app.message.message_client import IMessageClient
from app.utils import RequestUtils
from app.utils.exception_utils import ExceptionUtils


class ServerChan(IMessageClient):
    _sckey = None
    _client_config = {}

    def __init__(self, config):
        self._client_config = config
        self.init_config()

    def init_config(self):
        if self._client_config:
            self._sckey = self._client_config.get('sckey')

    def send_msg(self, title, text="", image="", url="", user_id=""):
        """
        傳送ServerChan訊息
        :param title: 訊息標題
        :param text: 訊息內容
        :param image: 未使用
        :param url: 未使用
        :param user_id: 未使用
        """
        if not title and not text:
            return False, "標題和內容不能同時為空"
        if not self._sckey:
            return False, "引數未配置"
        try:
            sc_url = "https://sctapi.ftqq.com/%s.send?%s" % (self._sckey, urlencode({"title": title, "desp": text}))
            res = RequestUtils().get_res(sc_url)
            if res:
                ret_json = res.json()
                errno = ret_json.get('code')
                error = ret_json.get('message')
                if errno == 0:
                    return True, error
                else:
                    return False, error
            else:
                return False, "未獲取到返回資訊"
        except Exception as msg_e:
            ExceptionUtils.exception_traceback(msg_e)
            return False, str(msg_e)

    def send_list_msg(self, **kwargs):
        pass
