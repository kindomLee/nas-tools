import importlib
import pkgutil

import requests

import log
from app.helper import ChromeHelper, CHROME_LOCK, SiteHelper
from app.utils import RequestUtils
from app.utils.commons import singleton
from app.utils.exception_utils import ExceptionUtils
from app.utils.types import SiteSchema
from config import Config


@singleton
class SiteUserInfoFactory(object):

    def __init__(self):
        self.__site_schema = {}

        # 從 app.sites.siteuserinfo 下載入所有的站點資訊類
        packages = importlib.import_module('app.sites.siteuserinfo').__path__
        for importer, package_name, _ in pkgutil.iter_modules(packages):
            full_package_name = f'app.sites.siteuserinfo.{package_name}'
            if full_package_name.startswith('_'):
                continue
            module = importlib.import_module(full_package_name)
            for name, obj in module.__dict__.items():
                if name.startswith('_'):
                    continue
                if isinstance(obj, type) and hasattr(obj, 'schema'):
                    self.__site_schema[obj.schema] = obj

    def _build_class(self, schema):
        if schema not in self.__site_schema:
            return self.__site_schema.get(SiteSchema.NexusPhp)
        return self.__site_schema[schema]

    def build(self, url, site_name, site_cookie=None, ua=None, emulate=None, proxy=False):
        if not site_cookie:
            return None
        log.debug(f"【Sites】站點 {site_name} url={url} site_cookie={site_cookie} ua={ua}")
        session = requests.Session()
        # 檢測環境，有瀏覽器核心的優先使用模擬簽到
        chrome = ChromeHelper()
        if emulate and chrome.get_status():
            with CHROME_LOCK:
                try:
                    chrome.visit(url=url, ua=ua, cookie=site_cookie)
                except Exception as err:
                    ExceptionUtils.exception_traceback(err)
                    log.error("【Sites】%s 無法開啟網站" % site_name)
                    return None
                # 迴圈檢測是否過cf
                cloudflare = chrome.pass_cloudflare()
                if not cloudflare:
                    log.error("【Sites】%s 跳轉站點失敗" % site_name)
                    return None
                # 判斷是否已簽到
                html_text = chrome.get_html()
        else:
            proxies = Config().get_proxies() if proxy else None
            res = RequestUtils(cookies=site_cookie,
                               session=session,
                               headers=ua,
                               proxies=proxies
                               ).get_res(url=url)
            if res and res.status_code == 200:
                if "charset=utf-8" in res.text or "charset=UTF-8" in res.text:
                    res.encoding = "UTF-8"
                else:
                    res.encoding = res.apparent_encoding
                html_text = res.text
                # 第一次登入反爬
                if html_text.find("title") == -1:
                    i = html_text.find("window.location")
                    if i == -1:
                        return None
                    tmp_url = url + html_text[i:html_text.find(";")] \
                        .replace("\"", "").replace("+", "").replace(" ", "").replace("window.location=", "")
                    res = RequestUtils(cookies=site_cookie,
                                       session=session,
                                       headers=ua,
                                       proxies=proxies
                                       ).get_res(url=tmp_url)
                    if res and res.status_code == 200:
                        if "charset=utf-8" in res.text or "charset=UTF-8" in res.text:
                            res.encoding = "UTF-8"
                        else:
                            res.encoding = res.apparent_encoding
                        html_text = res.text
                        if not html_text:
                            return None
                    else:
                        log.error("【Sites】站點 %s 被反爬限制：%s, 狀態碼：%s" % (site_name, url, res.status_code))
                        return None

                # 相容假首頁情況，假首頁通常沒有 <link rel="search" 屬性
                if '"search"' not in html_text and '"csrf-token"' not in html_text:
                    res = RequestUtils(cookies=site_cookie,
                                       session=session,
                                       headers=ua,
                                       proxies=proxies
                                       ).get_res(url=url + "/index.php")
                    if res and res.status_code == 200:
                        if "charset=utf-8" in res.text or "charset=UTF-8" in res.text:
                            res.encoding = "UTF-8"
                        else:
                            res.encoding = res.apparent_encoding
                        html_text = res.text
                        if not html_text:
                            return None
            elif not res:
                log.error("【Sites】站點 %s 連線失敗：%s" % (site_name, url))
                return None
            else:
                log.error("【Sites】站點 %s 獲取流量資料失敗，狀態碼：%s" % (site_name, res.status_code))
                return None

        # 解析站點型別
        site_schema = self._build_class(SiteHelper.schema(html_text))
        return site_schema(site_name, url, site_cookie, html_text, session=session, ua=ua)
