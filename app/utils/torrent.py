import os.path
import re
import datetime
from urllib.parse import quote

from app.utils.exception_utils import ExceptionUtils
from app.utils.torrentParser import TorrentParser
from app.utils import RequestUtils
from config import Config


class Torrent:

    _torrent_path = None

    def __init__(self):
        self._torrent_path = os.path.join(Config().get_config_path(), "temp")
        if not os.path.exists(self._torrent_path):
            os.makedirs(self._torrent_path)

    def get_torrent_info(self, url, cookie=None, ua=None, referer=None):
        """
        把種子下載到本地，返回種子內容
        :param url: 種子連結
        :param cookie: 站點Cookie
        :param ua: 站點UserAgent
        :param referer: 關聯地址，有的網站需要這個否則無法下載
        :return: 種子儲存路徑、種子內容、種子檔案列表主目錄、種子檔案列表、錯誤資訊
        """
        if not url:
            return None, None, "", [], "URL為空"
        if url.startswith("magnet:"):
            return None, url, "", [], f"{url} 為磁力連結"
        try:
            req = RequestUtils(headers=ua, cookies=cookie, referer=referer).get_res(url=url, allow_redirects=False)
            while req and req.status_code in [301, 302]:
                url = req.headers['Location']
                if url and url.startswith("magnet:"):
                    return None, url, "", [], f"獲取到磁力連結：{url}"
                req = RequestUtils(headers=ua, cookies=cookie, referer=referer).get_res(url=url, allow_redirects=False)
            if req and req.status_code == 200:
                if not req.content:
                    return None, None, "", [], "未下載到種子資料"
                # 讀取種子檔名
                file_name = self.__get_url_torrent_name(req.headers.get('content-disposition'), url)
                # 種子檔案路徑
                file_path = os.path.join(self._torrent_path, file_name)
                with open(file_path, 'wb') as f:
                    f.write(req.content)
                # 解析種子檔案
                files_folder, files, retmsg = self.__get_torrent_files(file_path)
                # 種子檔案路徑、種子內容、種子檔案列表主目錄、種子檔案列表、錯誤資訊
                return file_path, req.content, files_folder, files, retmsg
            elif req is None:
                return None, None, "", [], "無法開啟連結：%s" % url
            else:
                return None, None, "", [], "下載種子出錯，狀態碼：%s" % req.status_code
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return None, None, "", [], "下載種子檔案出現異常：%s，請檢查是否站點Cookie已過期，或觸發了站點首次種子下載" % str(err)

    @staticmethod
    def convert_hash_to_magnet(hash_text, title):
        """
        根據hash值，轉換為磁力鏈，自動新增tracker
        :param hash_text: 種子Hash值
        :param title: 種子標題
        """
        if not hash_text or not title:
            return None
        hash_text = re.search(r'[0-9a-z]+', hash_text, re.IGNORECASE)
        if not hash_text:
            return None
        hash_text = hash_text.group(0)
        return f'magnet:?xt=urn:btih:{hash_text}&dn={quote(title)}&tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A80' \
               '&tr=udp%3A%2F%2Fopentor.org%3A2710' \
               '&tr=udp%3A%2F%2Ftracker.ccc.de%3A80' \
               '&tr=udp%3A%2F%2Ftracker.blackunicorn.xyz%3A6969' \
               '&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969' \
               '&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969'

    @staticmethod
    def __get_torrent_files(path):
        """
        解析Torrent檔案，獲取檔案清單
        :return: 種子檔案列表主目錄、種子檔案列表、錯誤資訊
        """
        if not path or not os.path.exists(path):
            return "", [], f"種子檔案不存在：{path}"
        file_names = []
        file_folder = ""
        try:
            torrent = TorrentParser().readFile(path=path)
            if torrent.get("torrent"):
                file_folder = torrent.get("torrent").get("info", {}).get("name") or ""
                files = torrent.get("torrent").get("info", {}).get("files") or []
                if not files and file_folder:
                    file_names.append(file_folder)
                else:
                    for item in files:
                        if item.get("path"):
                            file_names.append(item["path"][0])
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
            return file_folder, file_names, "解析種子檔案異常：%s" % str(err)
        return file_folder, file_names, ""

    def read_torrent_file(self, path):
        """
        讀取本地種子檔案的內容
        :return: 種子內容、種子檔案列表主目錄、種子檔案列表、錯誤資訊
        """
        if not path or not os.path.exists(path):
            return None, "", "種子檔案不存在：%s" % path
        content, retmsg, file_folder, files = None, "", "", []
        try:
            # 讀取種子檔案內容
            with open(path, 'rb') as f:
                content = f.read()
            # 解析種子檔案
            file_folder, files, retmsg = self.__get_torrent_files(path)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            retmsg = "讀取種子檔案出錯：%s" % str(e)
        return content, file_folder, files, retmsg

    @staticmethod
    def __get_url_torrent_name(disposition, url):
        """
        從下載請求中獲取種子檔名
        """
        file_name = re.findall(r"filename=\"?(.+)\"?", disposition or "")
        if file_name:
            file_name = str(file_name[0].encode('ISO-8859-1').decode()).split(";")[0].strip()
            if file_name.endswith('"'):
                file_name = file_name[:-1]
        elif url and url.endswith(".torrent"):
            file_name = url.split("/")[-1]
        else:
            file_name = str(datetime.datetime.now())
        return file_name
