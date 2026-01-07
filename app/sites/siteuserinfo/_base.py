# -*- coding: utf-8 -*-
import base64
import json
import re
from abc import ABCMeta, abstractmethod
from urllib.parse import urljoin, urlsplit

import requests
from lxml import etree

import log
from app.helper import SiteHelper
from app.utils import RequestUtils
from app.utils.types import SiteSchema


class _ISiteUserInfo(metaclass=ABCMeta):
    # 站點模版
    schema = SiteSchema.NexusPhp

    def __init__(self, site_name, url, site_cookie, index_html, session=None, ua=None):
        super().__init__()
        # 站點資訊
        self.site_name = None
        self.site_url = None
        self.site_favicon = None
        # 使用者資訊
        self.username = None
        self.userid = None
        # 未讀訊息
        self.message_unread = 0
        self.message_unread_contents = []

        # 流量資訊
        self.upload = 0
        self.download = 0
        self.ratio = 0

        # 種子資訊
        self.seeding = 0
        self.leeching = 0
        self.uploaded = 0
        self.completed = 0
        self.incomplete = 0
        self.seeding_size = 0
        self.leeching_size = 0
        self.uploaded_size = 0
        self.completed_size = 0
        self.incomplete_size = 0
        # 做種人數, 種子大小
        self.seeding_info = []

        # 使用者詳細資訊
        self.user_level = None
        self.join_at = None
        self.bonus = 0.0

        # 錯誤資訊
        self.err_msg = None
        # 內部資料
        self._base_url = None
        self._site_cookie = None
        self._index_html = None

        # 站點頁面
        self._brief_page = "index.php"
        self._user_detail_page = "userdetails.php?id="
        self._user_traffic_page = "index.php"
        self._torrent_seeding_page = "getusertorrentlistajax.php?userid="
        self._user_mail_unread_page = "messages.php?action=viewmailbox&box=1&unread=yes"
        self._sys_mail_unread_page = "messages.php?action=viewmailbox&box=-2&unread=yes"
        self._torrent_seeding_params = None
        self._torrent_seeding_headers = None

        split_url = urlsplit(url)
        self.site_name = site_name
        self.site_url = url
        self._base_url = f"{split_url.scheme}://{split_url.netloc}"
        self._favicon_url = urljoin(self._base_url, "favicon.ico")
        self.site_favicon = ""
        self._site_cookie = site_cookie
        self._index_html = index_html
        self._session = session if session else requests.Session()
        self._ua = ua

    def site_schema(self):
        """
        站點解析模型
        :return:
        """
        return self.schema

    def parse(self):
        """
        解析站點資訊
        :return:
        """
        self._parse_favicon(self._index_html)
        if not self._parse_logged_in(self._index_html):
            return

        self._parse_site_page(self._index_html)
        self._parse_user_base_info(self._index_html)
        self._pase_unread_msgs()
        if self._user_traffic_page:
            self._parse_user_traffic_info(self._get_page_content(urljoin(self._base_url, self._user_traffic_page)))
        if self._user_detail_page:
            self._parse_user_detail_info(self._get_page_content(urljoin(self._base_url, self._user_detail_page)))

        self._parse_seeding_pages()
        self.seeding_info = json.dumps(self.seeding_info)

    def _pase_unread_msgs(self):
        """
        解析所有未讀訊息標題和內容
        :return:
        """
        unread_msg_links = []
        if self.message_unread > 0:
            links = {self._user_mail_unread_page, self._sys_mail_unread_page}
            for link in links:
                if not link:
                    continue

                msg_links = []
                next_page = self._parse_message_unread_links(
                    self._get_page_content(urljoin(self._base_url, link)), msg_links)
                while next_page:
                    next_page = self._parse_message_unread_links(
                        self._get_page_content(urljoin(self._base_url, next_page)), msg_links)

                unread_msg_links.extend(msg_links)

        for msg_link in unread_msg_links:
            print(msg_link)
            log.debug(f"【Sites】{self.site_name} 資訊連結 {msg_link}")
            head, date, content = self._parse_message_content(self._get_page_content(urljoin(self._base_url, msg_link)))
            log.debug(f"【Sites】{self.site_name} 標題 {head} 時間 {date} 內容 {content}")
            self.message_unread_contents.append((head, date, content))

    def _parse_seeding_pages(self):
        seeding_pages = []
        if self._torrent_seeding_page:
            if isinstance(self._torrent_seeding_page, list):
                seeding_pages.extend(self._torrent_seeding_page)
            else:
                seeding_pages.append(self._torrent_seeding_page)

            for seeding_page in seeding_pages:
                # 第一頁
                next_page = self._parse_user_torrent_seeding_info(
                    self._get_page_content(urljoin(self._base_url, seeding_page),
                                           self._torrent_seeding_params,
                                           self._torrent_seeding_headers))

                # 其他頁處理
                while next_page:
                    next_page = self._parse_user_torrent_seeding_info(
                        self._get_page_content(urljoin(urljoin(self._base_url, seeding_page), next_page),
                                               self._torrent_seeding_params,
                                               self._torrent_seeding_headers),
                        multi_page=True)

    @staticmethod
    def _prepare_html_text(html_text):
        """
        處理掉HTML中的干擾部分
        """
        return re.sub(r"#\d+", "", re.sub(r"\d+px", "", html_text))

    @abstractmethod
    def _parse_message_unread_links(self, html_text, msg_links):
        """
        獲取未閱讀訊息連結
        :param html_text:
        :return:
        """
        pass

    def _parse_favicon(self, html_text):
        """
        解析站點favicon,返回base64 fav圖示
        :param html_text:
        :return:
        """
        html = etree.HTML(html_text)
        if html:
            fav_link = html.xpath('//head/link[contains(@rel, "icon")]/@href')
            if fav_link:
                self._favicon_url = urljoin(self._base_url, fav_link[0])

        res = RequestUtils(cookies=self._site_cookie, session=self._session, timeout=60, headers=self._ua).get_res(
            url=self._favicon_url)
        if res:
            self.site_favicon = base64.b64encode(res.content).decode()

    def _get_page_content(self, url, params=None, headers=None):
        """
        :param url: 網頁地址
        :param params: post引數
        :param headers: 額外的請求頭
        :return:
        """
        req_headers = None
        if self._ua or headers:
            req_headers = {}
            if headers:
                req_headers.update(headers)

            if isinstance(self._ua, str):
                req_headers.update({
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "User-Agent": f"{self._ua}"
                })
            else:
                req_headers.update(self._ua)

        if params:
            res = RequestUtils(cookies=self._site_cookie, session=self._session, timeout=60,
                               headers=req_headers).post_res(
                url=url, params=params)
        else:
            res = RequestUtils(cookies=self._site_cookie, session=self._session, timeout=60,
                               headers=req_headers).get_res(
                url=url)
        if res is not None and res.status_code in (200, 500):
            if "charset=utf-8" in res.text or "charset=UTF-8" in res.text:
                res.encoding = "UTF-8"
            else:
                res.encoding = res.apparent_encoding
            return res.text

        return ""

    @abstractmethod
    def _parse_site_page(self, html_text):
        """
        解析站點相關資訊頁面
        :param html_text:
        :return:
        """
        pass

    @abstractmethod
    def _parse_user_base_info(self, html_text):
        """
        解析使用者基礎資訊
        :param html_text:
        :return:
        """
        pass

    def _parse_logged_in(self, html_text):
        """
        解析使用者是否已經登陸
        :param html_text:
        :return: True/False
        """
        logged_in = SiteHelper.is_logged_in(html_text)
        if not logged_in:
            self.err_msg = "未檢測到已登陸，請檢查cookies是否過期"
            log.warn(f"【Sites】{self.site_name} 未登入，跳過後續操作")

        return logged_in

    @abstractmethod
    def _parse_user_traffic_info(self, html_text):
        """
        解析使用者的上傳，下載，分享率等資訊
        :param html_text:
        :return:
        """
        pass

    @abstractmethod
    def _parse_user_torrent_seeding_info(self, html_text, multi_page=False):
        """
        解析使用者的做種相關資訊
        :param html_text:
        :param multi_page: 是否多頁資料
        :return: 下頁地址
        """
        pass

    @abstractmethod
    def _parse_user_detail_info(self, html_text):
        """
        解析使用者的詳細資訊
        加入時間/等級/魔力值等
        :param html_text:
        :return:
        """
        pass

    @abstractmethod
    def _parse_message_content(self, html_text):
        """
        解析短訊息內容
        :param html_text:
        :return:  head: message, date: time, content: message content
        """
        pass
