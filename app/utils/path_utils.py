import os


class PathUtils:

    @staticmethod
    def get_dir_files(in_path, exts="", filesize=0, episode_format=None):
        """
        獲得目錄下的媒體檔案列表List ，按字尾、大小、格式過濾
        """
        if not in_path:
            return []
        if not os.path.exists(in_path):
            return []
        ret_list = []
        if os.path.isdir(in_path):
            for root, dirs, files in os.walk(in_path):
                for file in files:
                    cur_path = os.path.join(root, file)
                    # 檢查路徑是否合法
                    if PathUtils.is_invalid_path(cur_path):
                        continue
                    # 檢查格式匹配
                    if episode_format and not episode_format.match(file):
                        continue
                    # 檢查字尾
                    if exts and os.path.splitext(file)[-1].lower() not in exts:
                        continue
                    # 檢查檔案大小
                    if filesize and os.path.getsize(cur_path) < filesize:
                        continue
                    # 命中
                    if cur_path not in ret_list:
                        ret_list.append(cur_path)
        else:
            # 檢查路徑是否合法
            if PathUtils.is_invalid_path(in_path):
                return []
            # 檢查字尾
            if exts and os.path.splitext(in_path)[-1].lower() not in exts:
                return []
            # 檢查格式
            if episode_format and not episode_format.match(os.path.basename(in_path)):
                return []
            # 檢查檔案大小
            if filesize and os.path.getsize(in_path) < filesize:
                return []
            ret_list.append(in_path)
        return ret_list

    @staticmethod
    def get_dir_level1_files(in_path, exts=""):
        """
        查詢目錄下的檔案（只查詢一級）
        """
        ret_list = []
        if not os.path.exists(in_path):
            return []
        for file in os.listdir(in_path):
            path = os.path.join(in_path, file)
            if os.path.isfile(path):
                if not exts or os.path.splitext(file)[-1].lower() in exts:
                    ret_list.append(path)
        return ret_list

    @staticmethod
    def get_dir_level1_medias(in_path, exts=""):
        """
        根據字尾，返回目錄下所有的檔案及資料夾列表（只查詢一級）
        """
        ret_list = []
        if not os.path.exists(in_path):
            return []
        if os.path.isdir(in_path):
            for file in os.listdir(in_path):
                path = os.path.join(in_path, file)
                if os.path.isfile(path):
                    if not exts or os.path.splitext(file)[-1].lower() in exts:
                        ret_list.append(path)
                else:
                    ret_list.append(path)
        else:
            ret_list.append(in_path)
        return ret_list

    @staticmethod
    def is_invalid_path(path):
        """
        判斷是否不能處理的路徑
        """
        if not path:
            return True
        if path.find('/@Recycle/') != -1 or path.find('/#recycle/') != -1 or path.find('/.') != -1 or path.find(
                '/@eaDir') != -1:
            return True
        return False

    @staticmethod
    def is_path_in_path(path1, path2):
        """
        判斷兩個路徑是否包含關係 path1 in path2
        """
        if not path1 or not path2:
            return False
        path1 = os.path.normpath(path1)
        path2 = os.path.normpath(path2)
        if path1 == path2:
            return True
        path = os.path.dirname(path2)
        while True:
            if path == path1:
                return True
            path = os.path.dirname(path)
            if path == os.path.dirname(path):
                break
        return False

    @staticmethod
    def get_bluray_dir(path):
        """
        判斷是否藍光原盤目錄，是則返回原盤的根目錄，否則返回空
        """
        if not path or not os.path.exists(path):
            return None
        if os.path.isdir(path):
            if os.path.exists(os.path.join(path, "BDMV", "index.bdmv")):
                return path
            elif os.path.normpath(path).endswith("BDMV") \
                    and os.path.exists(os.path.join(path, "index.bdmv")):
                return os.path.dirname(path)
            elif os.path.normpath(path).endswith("STREAM") \
                    and os.path.exists(os.path.join(os.path.dirname(path), "index.bdmv")):
                return PathUtils.get_parent_paths(path, 2)
            else:
                return None
        else:
            if str(os.path.splitext(path)[-1]).lower() in [".m2ts", ".ts"] \
                    and os.path.normpath(os.path.dirname(path)).endswith("STREAM") \
                    and os.path.exists(os.path.join(PathUtils.get_parent_paths(path, 2), "index.bdmv")):
                return PathUtils.get_parent_paths(path, 3)
            else:
                return None

    @staticmethod
    def get_parent_paths(path, level: int = 1):
        """
        獲取父目錄路徑，level為向上查詢的層數
        """
        for lv in range(0, level):
            path = os.path.dirname(path)
        return path
