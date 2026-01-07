#!/usr/bin/env python
# -*- encoding:utf-8 -*-

""" 對企業微信傳送給企業後臺的訊息加解密示例程式碼.
@copyright: Copyright (c) 1998-2014 Tencent Inc.

"""
import base64
import hashlib
# ------------------------------------------------------------------------
import logging
import random
import socket
import struct
import time
import xml.etree.cElementTree as ET

from Crypto.Cipher import AES

# Description:定義錯誤碼含義
#########################################################################
WXBizMsgCrypt_OK = 0
WXBizMsgCrypt_ValidateSignature_Error = -40001
WXBizMsgCrypt_ParseXml_Error = -40002
WXBizMsgCrypt_ComputeSignature_Error = -40003
WXBizMsgCrypt_IllegalAesKey = -40004
WXBizMsgCrypt_ValidateCorpid_Error = -40005
WXBizMsgCrypt_EncryptAES_Error = -40006
WXBizMsgCrypt_DecryptAES_Error = -40007
WXBizMsgCrypt_IllegalBuffer = -40008
WXBizMsgCrypt_EncodeBase64_Error = -40009
WXBizMsgCrypt_DecodeBase64_Error = -40010
WXBizMsgCrypt_GenReturnXml_Error = -40011

"""
關於Crypto.Cipher模組，ImportError: No module named 'Crypto'解決方案
請到官方網站 https://www.dlitz.net/software/pycrypto/ 下載pycrypto。
下載後，按照README中的“Installation”小節的提示進行pycrypto安裝。
"""


class FormatException(Exception):
    pass


def throw_exception(message, exception_class=FormatException):
    """my define raise exception function"""
    raise exception_class(message)


class SHA1:
    """計算企業微信的訊息簽名介面"""

    @staticmethod
    def getSHA1(token, timestamp, nonce, encrypt):
        """用SHA1演算法生成安全簽名
        @param token:  票據
        @param timestamp: 時間戳
        @param encrypt: 密文
        @param nonce: 隨機字串
        @return: 安全簽名
        """
        try:
            sortlist = [token, timestamp, nonce, encrypt]
            sortlist.sort()
            sha = hashlib.sha1()
            sha.update("".join(sortlist).encode())
            return WXBizMsgCrypt_OK, sha.hexdigest()
        except Exception as e:
            logger = logging.getLogger()
            logger.error(e)
            return WXBizMsgCrypt_ComputeSignature_Error, None


class XMLParse:
    """提供提取訊息格式中的密文及生成回覆訊息格式的介面"""

    # xml訊息模板
    AES_TEXT_RESPONSE_TEMPLATE = """<xml>
<Encrypt><![CDATA[%(msg_encrypt)s]]></Encrypt>
<MsgSignature><![CDATA[%(msg_signaturet)s]]></MsgSignature>
<TimeStamp>%(timestamp)s</TimeStamp>
<Nonce><![CDATA[%(nonce)s]]></Nonce>
</xml>"""

    @staticmethod
    def extract(xmltext):
        """提取出xml資料包中的加密訊息
        @param xmltext: 待提取的xml字串
        @return: 提取出的加密訊息字串
        """
        try:
            xml_tree = ET.fromstring(xmltext)
            encrypt = xml_tree.find("Encrypt")
            return WXBizMsgCrypt_OK, encrypt.text
        except Exception as e:
            logger = logging.getLogger()
            logger.error(e)
            return WXBizMsgCrypt_ParseXml_Error, None

    def generate(self, encrypt, signature, timestamp, nonce):
        """生成xml訊息
        @param encrypt: 加密後的訊息密文
        @param signature: 安全簽名
        @param timestamp: 時間戳
        @param nonce: 隨機字串
        @return: 生成的xml字串
        """
        resp_dict = {
            'msg_encrypt': encrypt,
            'msg_signaturet': signature,
            'timestamp': timestamp,
            'nonce': nonce,
        }
        resp_xml = self.AES_TEXT_RESPONSE_TEMPLATE % resp_dict
        return resp_xml


class PKCS7Encoder:
    """提供基於PKCS7演算法的加解密介面"""

    block_size = 32

    def encode(self, text):
        """ 對需要加密的明文進行填充補位
        @param text: 需要進行填充補位操作的明文
        @return: 補齊明文字串
        """
        text_length = len(text)
        # 計算需要填充的位數
        amount_to_pad = self.block_size - (text_length % self.block_size)
        if amount_to_pad == 0:
            amount_to_pad = self.block_size
        # 獲得補位所用的字元
        pad = chr(amount_to_pad)
        return text + (pad * amount_to_pad).encode()

    @staticmethod
    def decode(decrypted):
        """刪除解密後明文的補位字元
        @param decrypted: 解密後的明文
        @return: 刪除補位字元後的明文
        """
        pad = ord(decrypted[-1])
        if pad < 1 or pad > 32:
            pad = 0
        return decrypted[:-pad]


class Prpcrypt(object):
    """提供接收和推送給企業微信訊息的加解密介面"""

    def __init__(self, key):

        # self.key = base64.b64decode(key+"=")
        self.key = key
        # 設定加解密模式為AES的CBC模式
        self.mode = AES.MODE_CBC

    def encrypt(self, text, receiveid):
        """對明文進行加密
        @param text: 需要加密的明文
        @param receiveid: receiveid
        @return: 加密得到的字串
        """
        # 16位隨機字串新增到明文開頭
        text = text.encode()
        text = self.get_random_str() + struct.pack("I", socket.htonl(len(text))) + text + receiveid.encode()

        # 使用自定義的填充方式對明文進行補位填充
        pkcs7 = PKCS7Encoder()
        text = pkcs7.encode(text)
        # 加密
        cryptor = AES.new(self.key, self.mode, self.key[:16])
        try:
            ciphertext = cryptor.encrypt(text)
            # 使用BASE64對加密後的字串進行編碼
            return WXBizMsgCrypt_OK, base64.b64encode(ciphertext)
        except Exception as e:
            logger = logging.getLogger()
            logger.error(e)
            return WXBizMsgCrypt_EncryptAES_Error, None

    def decrypt(self, text, receiveid):
        """對解密後的明文進行補位刪除
        @param text: 密文
        @param receiveid: receiveid
        @return: 刪除填充補位後的明文
        """
        try:
            cryptor = AES.new(self.key, self.mode, self.key[:16])
            # 使用BASE64對密文進行解碼，然後AES-CBC解密
            plain_text = cryptor.decrypt(base64.b64decode(text))
        except Exception as e:
            logger = logging.getLogger()
            logger.error(e)
            return WXBizMsgCrypt_DecryptAES_Error, None
        try:
            pad = plain_text[-1]
            # 去掉補位字串
            # pkcs7 = PKCS7Encoder()
            # plain_text = pkcs7.encode(plain_text)
            # 去除16位隨機字串
            content = plain_text[16:-pad]
            xml_len = socket.ntohl(struct.unpack("I", content[: 4])[0])
            xml_content = content[4: xml_len + 4]
            from_receiveid = content[xml_len + 4:]
        except Exception as e:
            logger = logging.getLogger()
            logger.error(e)
            return WXBizMsgCrypt_IllegalBuffer, None

        if from_receiveid.decode('utf8') != receiveid:
            return WXBizMsgCrypt_ValidateCorpid_Error, None
        return 0, xml_content

    @staticmethod
    def get_random_str():
        """ 隨機生成16位字串
        @return: 16位字串
        """
        return str(random.randint(1000000000000000, 9999999999999999)).encode()


class WXBizMsgCrypt(object):
    # 建構函式
    def __init__(self, sToken, sEncodingAESKey, sReceiveId):
        try:
            self.key = base64.b64decode(sEncodingAESKey + "=")
            assert len(self.key) == 32
        except Exception as err:
            throw_exception("[error]: EncodingAESKey unvalid !", FormatException)
            # return WXBizMsgCrypt_IllegalAesKey,None
        self.m_sToken = sToken
        self.m_sReceiveId = sReceiveId

        # 驗證URL
        # @param sMsgSignature: 簽名串，對應URL引數的msg_signature
        # @param sTimeStamp: 時間戳，對應URL引數的timestamp
        # @param sNonce: 隨機串，對應URL引數的nonce
        # @param sEchoStr: 隨機串，對應URL引數的echostr
        # @param sReplyEchoStr: 解密之後的echostr，當return返回0時有效
        # @return：成功0，失敗返回對應的錯誤碼

    def VerifyURL(self, sMsgSignature, sTimeStamp, sNonce, sEchoStr):
        sha1 = SHA1()
        ret, signature = sha1.getSHA1(self.m_sToken, sTimeStamp, sNonce, sEchoStr)
        if ret != 0:
            return ret, None
        if not signature == sMsgSignature:
            return WXBizMsgCrypt_ValidateSignature_Error, None
        pc = Prpcrypt(self.key)
        ret, sReplyEchoStr = pc.decrypt(sEchoStr, self.m_sReceiveId)
        return ret, sReplyEchoStr

    def EncryptMsg(self, sReplyMsg, sNonce, timestamp=None):
        # 將企業回覆使用者的訊息加密打包
        # @param sReplyMsg: 企業號待回覆使用者的訊息，xml格式的字串
        # @param sTimeStamp: 時間戳，可以自己生成，也可以用URL引數的timestamp,如為None則自動用當前時間
        # @param sNonce: 隨機串，可以自己生成，也可以用URL引數的nonce
        # sEncryptMsg: 加密後的可以直接回複使用者的密文，包括msg_signature, timestamp, nonce, encrypt的xml格式的字串,
        # return：成功0，sEncryptMsg,失敗返回對應的錯誤碼None
        pc = Prpcrypt(self.key)
        ret, encrypt = pc.encrypt(sReplyMsg, self.m_sReceiveId)
        encrypt = encrypt.decode('utf8')
        if ret != 0:
            return ret, None
        if timestamp is None:
            timestamp = str(int(time.time()))
        # 生成安全簽名
        sha1 = SHA1()
        ret, signature = sha1.getSHA1(self.m_sToken, timestamp, sNonce, encrypt)
        if ret != 0:
            return ret, None
        xmlParse = XMLParse()
        return ret, xmlParse.generate(encrypt, signature, timestamp, sNonce)

    def DecryptMsg(self, sPostData, sMsgSignature, sTimeStamp, sNonce):
        # 檢驗訊息的真實性，並且獲取解密後的明文
        # @param sMsgSignature: 簽名串，對應URL引數的msg_signature
        # @param sTimeStamp: 時間戳，對應URL引數的timestamp
        # @param sNonce: 隨機串，對應URL引數的nonce
        # @param sPostData: 密文，對應POST請求的資料
        #  xml_content: 解密後的原文，當return返回0時有效
        # @return: 成功0，失敗返回對應的錯誤碼
        # 驗證安全簽名
        xmlParse = XMLParse()
        ret, encrypt = xmlParse.extract(sPostData)
        if ret != 0:
            return ret, None
        sha1 = SHA1()
        ret, signature = sha1.getSHA1(self.m_sToken, sTimeStamp, sNonce, encrypt)
        if ret != 0:
            return ret, None
        if not signature == sMsgSignature:
            return WXBizMsgCrypt_ValidateSignature_Error, None
        pc = Prpcrypt(self.key)
        ret, xml_content = pc.decrypt(encrypt, self.m_sReceiveId)
        return ret, xml_content
