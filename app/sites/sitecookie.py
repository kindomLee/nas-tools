import base64
import time

from lxml import etree
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as es
from selenium.webdriver.support.wait import WebDriverWait

import log
from app.helper import ChromeHelper, ProgressHelper, CHROME_LOCK, DbHelper, OcrHelper, SiteHelper
from app.sites import Sites
from app.utils import StringUtils, RequestUtils
from app.utils.commons import singleton
from app.utils.exception_utils import ExceptionUtils
from config import SITE_LOGIN_XPATH


@singleton
class SiteCookie(object):
    progress = None
    sites = None
    ocrhelper = None
    dbhelpter = None
    captcha_code = {}

    def __init__(self):
        self.init_config()

    def init_config(self):
        self.dbhelpter = DbHelper()
        self.progress = ProgressHelper()
        self.sites = Sites()
        self.ocrhelper = OcrHelper()
        self.captcha_code = {}

    def set_code(self, code, value):
        """
        設定驗證碼的值
        """
        self.captcha_code[code] = value

    def get_code(self, code):
        """
        獲取驗證碼的值
        """
        return self.captcha_code.get(code)

    def __get_site_cookie_ua(self,
                             url,
                             username,
                             password,
                             twostepcode=None,
                             ocrflag=False,
                             chrome=None):
        """
        獲取站點cookie和ua
        :param url: 站點地址
        :param username: 使用者名稱
        :param password: 密碼
        :param twostepcode: 兩步驗證
        :param ocrflag: 是否開啟OCR識別
        :param chrome: ChromeHelper
        :return: cookie、ua、message
        """
        if not url or not username or not password:
            return None, None, "引數錯誤"
        if not chrome:
            chrome = ChromeHelper()
            if not chrome.get_status():
                return None, None, "需要瀏覽器核心環境才能更新站點資訊"
        # 全域性鎖
        with CHROME_LOCK:
            try:
                chrome.visit(url=url)
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                return None, None, "Chrome模擬訪問失敗"
            # 迴圈檢測是否過cf
            cloudflare = chrome.pass_cloudflare()
            if not cloudflare:
                return None, None, "跳轉站點失敗，無法透過Cloudflare驗證"
            # 登入頁面程式碼
            html_text = chrome.get_html()
            if not html_text:
                return None, None, "獲取原始碼失敗"
            if SiteHelper.is_logged_in(html_text):
                return chrome.get_cookies(), chrome.get_ua(), "已經登入過且Cookie未失效"
            # 查詢使用者名稱輸入框
            html = etree.HTML(html_text)
            username_xpath = None
            for xpath in SITE_LOGIN_XPATH.get("username"):
                if html.xpath(xpath):
                    username_xpath = xpath
                    break
            if not username_xpath:
                return None, None, "未找到使用者名稱輸入框"
            # 查詢密碼輸入框
            password_xpath = None
            for xpath in SITE_LOGIN_XPATH.get("password"):
                if html.xpath(xpath):
                    password_xpath = xpath
                    break
            if not password_xpath:
                return None, None, "未找到密碼輸入框"
            # 查詢兩步驗證碼
            twostepcode_xpath = None
            for xpath in SITE_LOGIN_XPATH.get("twostep"):
                if html.xpath(xpath):
                    twostepcode_xpath = xpath
                    break
            # 查詢驗證碼輸入框
            captcha_xpath = None
            for xpath in SITE_LOGIN_XPATH.get("captcha"):
                if html.xpath(xpath):
                    captcha_xpath = xpath
                    break
            if captcha_xpath:
                # 查詢驗證碼圖片
                captcha_img_url = None
                for xpath in SITE_LOGIN_XPATH.get("captcha_img"):
                    if html.xpath(xpath):
                        captcha_img_url = html.xpath(xpath)[0]
                        break
                if not captcha_img_url:
                    return None, None, "未找到驗證碼圖片"
            # 查詢登入按鈕
            submit_xpath = None
            for xpath in SITE_LOGIN_XPATH.get("submit"):
                if html.xpath(xpath):
                    submit_xpath = xpath
                    break
            if not submit_xpath:
                return None, None, "未找到登入按鈕"
            # 點選登入按鈕
            try:
                submit_obj = WebDriverWait(driver=chrome.browser,
                                           timeout=6).until(es.element_to_be_clickable((By.XPATH,
                                                                                        submit_xpath)))
                if submit_obj:
                    # 輸入使用者名稱
                    chrome.browser.find_element(By.XPATH, username_xpath).send_keys(username)
                    # 輸入密碼
                    chrome.browser.find_element(By.XPATH, password_xpath).send_keys(password)
                    # 輸入兩步驗證碼
                    if twostepcode and twostepcode_xpath:
                        twostepcode_element = chrome.browser.find_element(By.XPATH, twostepcode_xpath)
                        if twostepcode_element.is_displayed():
                            twostepcode_element.send_keys(twostepcode)
                    # 識別驗證碼
                    if captcha_xpath:
                        captcha_element = chrome.browser.find_element(By.XPATH, captcha_xpath)
                        if captcha_element.is_displayed():
                            code_url = self.__get_captcha_url(url, captcha_img_url)
                            if ocrflag:
                                # 自動OCR識別驗證碼
                                captcha = self.get_captcha_text(chrome, code_url)
                                if captcha:
                                    log.info("【Sites】驗證碼地址為：%s，識別結果：%s" % (code_url, captcha))
                                else:
                                    return None, None, "驗證碼識別失敗"
                            else:
                                # 等待使用者輸入
                                captcha = None
                                code_key = StringUtils.generate_random_str(5)
                                for sec in range(30, 0, -1):
                                    if self.get_code(code_key):
                                        # 使用者輸入了
                                        captcha = self.get_code(code_key)
                                        log.info("【Sites】接收到驗證碼：%s" % captcha)
                                        self.progress.update(ptype='sitecookie',
                                                             text="接收到驗證碼：%s" % captcha)
                                        break
                                    else:
                                        # 獲取驗證碼圖片base64
                                        code_bin = self.get_captcha_base64(chrome, code_url)
                                        if not code_bin:
                                            return None, None, "獲取驗證碼圖片資料失敗"
                                        else:
                                            code_bin = f"data:image/png;base64,{code_bin}"
                                        # 推送到前端
                                        self.progress.update(ptype='sitecookie',
                                                             text=f"{code_bin}|{code_key}")
                                        time.sleep(1)
                                if not captcha:
                                    return None, None, "驗證碼輸入超時"
                            # 輸入驗證碼
                            captcha_element.send_keys(captcha)
                        else:
                            # 不可見元素不處理
                            pass
                    # 提交登入
                    submit_obj.click()
                else:
                    return None, None, "未找到登入按鈕"
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return None, None, "模擬登入失敗：%s" % str(e)
            # 登入後的原始碼
            html_text = chrome.get_html()
            if not html_text:
                return None, None, "獲取原始碼失敗"
            if SiteHelper.is_logged_in(html_text):
                return chrome.get_cookies(), chrome.get_ua(), ""
            else:
                # 讀取錯誤資訊
                error_xpath = None
                for xpath in SITE_LOGIN_XPATH.get("error"):
                    if html.xpath(xpath):
                        error_xpath = xpath
                        break
                if not error_xpath:
                    return None, None, "登入失敗"
                else:
                    error_msg = html.xpath(error_xpath)[0]
                    return None, None, error_msg

    def get_captcha_text(self, chrome, code_url):
        """
        識別驗證碼圖片的內容
        """
        code_b64 = self.get_captcha_base64(chrome=chrome,
                                           image_url=code_url)
        if not code_b64:
            return ""
        return self.ocrhelper.get_captcha_text(image_b64=code_b64)

    @staticmethod
    def __get_captcha_url(siteurl, imageurl):
        """
        獲取驗證碼圖片的URL
        """
        if not siteurl or not imageurl:
            return ""
        return "%s/%s" % (StringUtils.get_base_url(siteurl), imageurl)

    def update_sites_cookie_ua(self,
                               username,
                               password,
                               twostepcode=None,
                               siteid=None,
                               ocrflag=False):
        """
        更新所有站點Cookie和ua
        """
        chrome = ChromeHelper()
        if not chrome.get_status():
            return -1, ["需要瀏覽器核心環境才能更新站點資訊"]
        # 獲取站點列表
        sites = self.sites.get_sites(siteid=siteid)
        if siteid:
            sites = [sites]
        # 總數量
        site_num = len(sites)
        # 當前數量
        curr_num = 0
        # 返回碼、返回訊息
        retcode = 0
        messages = []
        # 開始進度
        self.progress.start('sitecookie')
        for site in sites:
            if not site.get("signurl") and not site.get("rssurl"):
                log.info("【Sites】%s 未設定地址，跳過" % site.get("name"))
                continue
            log.info("【Sites】開始更新 %s Cookie和User-Agent ..." % site.get("name"))
            self.progress.update(ptype='sitecookie',
                                 text="開始更新 %s Cookie和User-Agent ..." % site.get("name"))
            # 登入頁面地址
            login_url = "%s/login.php" % StringUtils.get_base_url(site.get("signurl") or site.get("rssurl"))
            # 獲取Cookie和User-Agent
            cookie, ua, msg = self.__get_site_cookie_ua(url=login_url,
                                                        username=username,
                                                        password=password,
                                                        twostepcode=twostepcode,
                                                        ocrflag=ocrflag,
                                                        chrome=chrome)
            # 更新進度
            curr_num += 1
            if not cookie:
                log.error("【Sites】獲取 %s 資訊失敗：%s" % (site.get("name"), msg))
                messages.append("%s %s" % (site.get("name"), msg))
                self.progress.update(ptype='sitecookie',
                                     value=round(100 * (curr_num / site_num)),
                                     text="%s %s" % (site.get("name"), msg))
                retcode = 1
            else:
                self.dbhelpter.update_site_cookie_ua(site.get("id"), cookie, ua)
                log.info("【Sites】更新 %s 的Cookie和User-Agent成功" % site.get("name"))
                messages.append("%s %s" % (site.get("name"), msg or "更新Cookie和User-Agent成功"))
                self.progress.update(ptype='sitecookie',
                                     value=round(100 * (curr_num / site_num)),
                                     text="%s %s" % (site.get("name"), msg or "更新Cookie和User-Agent成功"))
        self.progress.end('sitecookie')
        return retcode, messages

    @staticmethod
    def get_captcha_base64(chrome, image_url):
        """
        根據圖片地址，獲取驗證碼圖片base64編碼
        """
        if not image_url:
            return ""
        ret = RequestUtils(headers=chrome.get_ua(),
                           cookies=chrome.get_cookies()).get_res(image_url)
        if ret:
            return base64.b64encode(ret.content).decode()
        return ""
