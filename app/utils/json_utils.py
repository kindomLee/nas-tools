import json
from enum import Enum

from app.utils.exception_utils import ExceptionUtils


class JsonUtils:

    @staticmethod
    def json_serializable(obj):
        """
        將普通物件轉化為支援json序列化的物件
        @param obj: 待轉化的物件
        @return: 支援json序列化的物件
        """

        def _try(o):
            if isinstance(o, Enum):
                return o.value
            try:
                return o.__dict__
            except Exception as err:
                ExceptionUtils.exception_traceback(err)
                return str(o)

        return json.loads(json.dumps(obj, default=lambda o: _try(o)))
