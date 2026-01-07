# -*- coding: utf-8 -*-
import threading

# 執行緒鎖
lock = threading.RLock()

# 全域性例項
INSTANCES = {}


# 單例模式註解
def singleton(cls):
    # 建立字典用來儲存類的例項物件
    global INSTANCES

    def _singleton(*args, **kwargs):
        # 先判斷這個類有沒有物件
        if cls not in INSTANCES:
            with lock:
                if cls not in INSTANCES:
                    INSTANCES[cls] = cls(*args, **kwargs)
                    pass
        # 將例項物件返回
        return INSTANCES[cls]

    return _singleton
