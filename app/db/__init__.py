import os
import log
from config import Config
from .main_db import MainDb
from .media_db import MediaDb
from alembic.config import Config as AlembicConfig
from alembic.command import upgrade as alembic_upgrade


def init_db():
    """
    初始化資料庫
    """
    log.console('開始初始化資料庫...')
    MediaDb().init_db()
    MainDb().init_db()
    MainDb().init_data()
    log.console('資料庫初始化完成')


def update_db():
    """
    更新資料庫
    """
    db_location = os.path.join(Config().get_config_path(), 'user.db')
    script_location = os.path.join(Config().get_root_path(), 'db_scripts')
    log.console('開始更新資料庫...')
    try:
        alembic_cfg = AlembicConfig()
        alembic_cfg.set_main_option('script_location', script_location)
        alembic_cfg.set_main_option('sqlalchemy.url', f"sqlite:///{db_location}")
        alembic_upgrade(alembic_cfg, 'head')
    except Exception as e:
        print(str(e))
    log.console('資料庫更新完成')
