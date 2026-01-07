import os.path
import regex as re

import log
from app.helper import WordsHelper
from app.media.meta.metaanime import MetaAnime
from app.media.meta.metavideo import MetaVideo
from app.utils.types import MediaType
from config import RMT_MEDIAEXT


def MetaInfo(title, subtitle=None, mtype=None):
    """
    媒體整理入口，根據名稱和副標題，判斷是哪種型別的識別，返回對應物件
    :param title: 標題、種子名、檔名
    :param subtitle: 副標題、描述
    :param mtype: 指定識別型別，為空則自動識別型別
    :return: MetaAnime、MetaVideo
    """

    # 應用自定義識別詞
    if subtitle and title not in subtitle:
        name = f'{title}@@@{subtitle}'
        name, msg, used_info = WordsHelper().process(name)
        title = name.split('@@@')[0]
        subtitle = name.split('@@@')[-1]
    else:
        title, msg, used_info = WordsHelper().process(title)

    if msg:
        log.warn("【Meta】%s" % msg)

    # 判斷是否處理檔案
    if title and os.path.splitext(title)[-1] in RMT_MEDIAEXT:
        fileflag = True
    else:
        fileflag = False

    if mtype == MediaType.ANIME or is_anime(title):
        meta_info = MetaAnime(title, subtitle, fileflag)
    else:
        meta_info = MetaVideo(title, subtitle, fileflag)

    meta_info.ignored_words = used_info.get("ignored")
    meta_info.replaced_words = used_info.get("replaced")
    meta_info.offset_words = used_info.get("offset")

    return meta_info


def is_anime(name):
    """
    判斷是否為動漫
    :param name: 名稱
    :return: 是否動漫
    """
    if not name:
        return False
    if re.search(r'【[+0-9XVPI-]+】\s*【', name, re.IGNORECASE):
        return True
    if re.search(r'\s+-\s+[\dv]{1,4}\s+', name, re.IGNORECASE):
        return True
    if re.search(r"S\d{2}\s*-\s*S\d{2}|S\d{2}|\s+S\d{1,2}|EP?\d{2,4}\s*-\s*EP?\d{2,4}|EP?\d{2,4}|\s+EP?\d{1,4}", name,
                 re.IGNORECASE):
        return False
    if re.search(r'\[[+0-9XVPI-]+]\s*\[', name, re.IGNORECASE):
        return True
    return False
