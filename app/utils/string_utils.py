import bisect
import random
import re
from urllib import parse

import cn2an
import dateutil.parser
from delorean import parse as delorean_parse

from app.utils.exception_utils import ExceptionUtils
from app.utils.types import MediaType


class StringUtils:

    @staticmethod
    def num_filesize(text):
        """
        將檔案大小文字轉化為位元組
        """
        if not text:
            return 0
        if not isinstance(text, str):
            text = str(text)
        text = text.replace(",", "").replace(" ", "").upper()
        size = re.sub(r"[KMGTPI]*B?", "", text, flags=re.IGNORECASE)
        try:
            size = float(size)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return 0
        if text.find("PB") != -1 or text.find("PIB") != -1:
            size *= 1024 ** 5
        elif text.find("TB") != -1 or text.find("TIB") != -1:
            size *= 1024 ** 4
        elif text.find("GB") != -1 or text.find("GIB") != -1:
            size *= 1024 ** 3
        elif text.find("MB") != -1 or text.find("MIB") != -1:
            size *= 1024 ** 2
        elif text.find("KB") != -1 or text.find("KIB") != -1:
            size *= 1024
        return round(size)

    @staticmethod
    def str_timelong(time_sec):
        """
        將數字轉換為時間描述
        """
        if not isinstance(time_sec, int) or not isinstance(time_sec, float):
            try:
                time_sec = float(time_sec)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return ""
        d = [(0, '秒'), (60 - 1, '分'), (3600 - 1, '小時'), (86400 - 1, '天')]
        s = [x[0] for x in d]
        index = bisect.bisect_left(s, time_sec) - 1
        if index == -1:
            return str(time_sec)
        else:
            b, u = d[index]
        return str(round(time_sec / (b + 1))) + u

    @staticmethod
    def is_chinese(word):
        """
        判斷是否含有中文
        """
        chn = re.compile(r'[\u4e00-\u9fff]')
        if chn.search(word):
            return True
        else:
            return False

    @staticmethod
    def is_japanese(word):
        jap = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')
        if jap.search(word):
            return True
        else:
            return False

    @staticmethod
    def is_korean(word):
        kor = re.compile(r'[\uAC00-\uD7FF]')
        if kor.search(word):
            return True
        else:
            return False

    @staticmethod
    def is_all_chinese(word):
        """
        判斷是否全是中文
        """
        for ch in word:
            if ch == ' ':
                continue
            if '\u4e00' <= ch <= '\u9fff':
                continue
            else:
                return False
        return True

    @staticmethod
    def xstr(s):
        """
        字串None輸出為空
        """
        return s if s else ''

    @staticmethod
    def str_sql(in_str):
        """
        轉化SQL字元
        """
        return "" if not in_str else str(in_str)

    @staticmethod
    def str_int(text):
        """
        web字串轉int
        :param text:
        :return:
        """
        int_val = 0
        try:
            int_val = int(text.strip().replace(',', ''))
        except Exception as e:
            ExceptionUtils.exception_traceback(e)

        return int_val

    @staticmethod
    def str_float(text):
        """
        web字串轉float
        :param text:
        :return:
        """
        float_val = 0.0
        try:
            float_val = float(text.strip().replace(',', ''))
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
        return float_val

    @staticmethod
    def handler_special_chars(text, replace_word="", allow_space=False):
        """
        忽略特殊字元
        """
        # 需要忽略的特殊字元
        CONVERT_EMPTY_CHARS = r"\.|\(|\)|\[|]|-|\+|【|】|/|～|;|&|\||#|_|「|」|（|）|'|’|!|！|,|～|·|:|：|\-|~"
        if not text:
            return ""
        text = re.sub(r"[\u200B-\u200D\uFEFF]", "", re.sub(r"%s" % CONVERT_EMPTY_CHARS, replace_word, text),
                      flags=re.IGNORECASE)
        if not allow_space:
            return re.sub(r"\s+", "", text)
        else:
            return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def str_filesize(size, pre=2):
        """
        將位元組計算為檔案大小描述
        """
        if not isinstance(size, int) or not isinstance(size, float):
            try:
                size = float(size)
            except Exception as e:
                ExceptionUtils.exception_traceback(e)
                return ""
        d = [(1024 - 1, 'K'), (1024 ** 2 - 1, 'M'), (1024 ** 3 - 1, 'G'), (1024 ** 4 - 1, 'T')]
        s = [x[0] for x in d]
        index = bisect.bisect_left(s, size) - 1
        if index == -1:
            return str(size)
        else:
            b, u = d[index]
        return str(round(size / (b + 1), pre)) + u

    @staticmethod
    def url_equal(url1, url2):
        """
        比較兩個地址是否為同一個網站
        """
        if not url1 or not url2:
            return False
        if url1.startswith("http"):
            url1 = parse.urlparse(url1).netloc
        if url2.startswith("http"):
            url2 = parse.urlparse(url2).netloc
        if url1.replace("www.", "") == url2.replace("www.", ""):
            return True
        return False

    @staticmethod
    def get_url_netloc(url):
        """
        獲取URL的協議和域名部分
        """
        if not url:
            return "", ""
        if not url.startswith("http"):
            return "http", url
        addr = parse.urlparse(url)
        return addr.scheme, addr.netloc

    @staticmethod
    def get_url_domain(url):
        """
        獲取URL的域名部分，不含WWW和HTTP
        """
        _, netloc = StringUtils.get_url_netloc(url)
        if netloc:
            return netloc.lower().replace("www.", "")
        return ""

    @staticmethod
    def get_base_url(url):
        """
        獲取URL根地址
        """
        scheme, netloc = StringUtils.get_url_netloc(url)
        return f"{scheme}://{netloc}"

    @staticmethod
    def clear_file_name(name):
        if not name:
            return None
        return re.sub(r"[*?\\/\"<>~]", "", name, flags=re.IGNORECASE).replace(":", "：")

    @staticmethod
    def get_keyword_from_string(content):
        """
        從檢索關鍵字中拆分中年份、季、集、型別
        """
        if not content:
            return None, None, None, None, None
        # 去掉查詢中的電影或電視劇關鍵字
        if re.search(r'^電視劇|\s+電視劇|^動漫|\s+動漫', content):
            mtype = MediaType.TV
        else:
            mtype = None
        content = re.sub(r'^電影|^電視劇|^動漫|\s+電影|\s+電視劇|\s+動漫', '', content).strip()
        # 稍微切一下劇集吧
        season_num = None
        episode_num = None
        year = None
        season_re = re.search(r"第\s*([0-9一二三四五六七八九十]+)\s*季", content, re.IGNORECASE)
        if season_re:
            mtype = MediaType.TV
            season_num = int(cn2an.cn2an(season_re.group(1), mode='smart'))
        episode_re = re.search(r"第\s*([0-9一二三四五六七八九十]+)\s*集", content, re.IGNORECASE)
        if episode_re:
            mtype = MediaType.TV
            episode_num = int(cn2an.cn2an(episode_re.group(1), mode='smart'))
            if episode_num and not season_num:
                season_num = 1
        year_re = re.search(r"[\s(]+(\d{4})[\s)]*", content)
        if year_re:
            year = year_re.group(1)
        key_word = re.sub(r'第\s*[0-9一二三四五六七八九十]+\s*季|第\s*[0-9一二三四五六七八九十]+\s*集|[\s(]+(\d{4})[\s)]*', '',
                          content,
                          flags=re.IGNORECASE).strip()
        if key_word:
            key_word = re.sub(r'\s+', ' ', key_word)
        if not key_word:
            key_word = year

        return mtype, key_word, season_num, episode_num, year, content

    @staticmethod
    def generate_random_str(randomlength=16):
        """
        生成一個指定長度的隨機字串
        """
        random_str = ''
        base_str = 'ABCDEFGHIGKLMNOPQRSTUVWXYZabcdefghigklmnopqrstuvwxyz0123456789'
        length = len(base_str) - 1
        for i in range(randomlength):
            random_str += base_str[random.randint(0, length)]
        return random_str

    @staticmethod
    def get_time_stamp(date):
        tempsTime = None
        try:
            tempsTime = dateutil.parser.parse(date)
        except Exception as err:
            ExceptionUtils.exception_traceback(err)
        return tempsTime

    @staticmethod
    def unify_datetime_str(datetime_str):
        """
        日期時間格式化 統一轉成 2020-10-14 07:48:04 這種格式
        :param datetime_str:
        :return:
        """
        # 傳入的引數如果是None 或者空字串 直接返回
        if not datetime_str:
            return datetime_str

        try:
            return delorean_parse(datetime_str, dayfirst=False).format_datetime('yyyy-MM-dd HH:mm:ss')
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            return datetime_str

    @staticmethod
    def to_bool(text, default_val: bool = False) -> bool:
        """
        字串轉bool
        :param text: 要轉換的值
        :param default_val: 預設值
        :return:
        """
        if isinstance(text, str) and not text:
            return default_val
        if isinstance(text, bool):
            return text
        if isinstance(text, int) or isinstance(text, float):
            return True if text > 0 else False
        if isinstance(text, str) and text.lower() in ['y', 'true', '1']:
            return True
        return False

    @staticmethod
    def str_from_cookiejar(cj):
        """
        將cookiejar轉換為字串
        :param cj:
        :return:
        """
        return '; '.join(['='.join(item) for item in cj.items()])

    @staticmethod
    def get_idlist_from_string(content, dicts):
        """
        從字串中提取id列表
        :param content: 字串
        :param dicts: 字典
        :return:
        """
        if not content:
            return []
        id_list = []
        content_list = content.split()
        for dic in dicts:
            if dic.get('name') in content_list and dic.get('id') not in id_list:
                id_list.append(dic.get('id'))
                content = content.replace(dic.get('name'), '')
        return id_list, re.sub(r'\s+', ' ', content).strip()

    @staticmethod
    def str_title(s):
        """
        講英文的首字母大寫
        :param s: en_name string
        :return: string title
        """
        return s.title() if s else s
