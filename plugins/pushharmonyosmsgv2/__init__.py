import threading
from queue import Queue
from time import time, sleep
from typing import Any, List, Dict, Tuple
import json

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.http import RequestUtils


class PushHarmonyOsMsgV2(_PluginBase):
    # 插件名称
    plugin_name = "鸿蒙Next消息推送v2"
    # 插件描述
    plugin_desc = "借助MeoW应用实现鸿蒙原生Push推送。"
    # 插件图标
    plugin_icon = "Pushplus_A.png"
    # 插件版本
    plugin_version = "0.2"
    # 插件作者
    plugin_author = "eciycn"
    # 作者主页
    author_url = "https://github.com/eciycn/MoviePilot-Plugins"
    # 插件配置项ID前缀
    plugin_config_prefix = "pushharmonyosmsgv2_"
    # 加载顺序
    plugin_order = 29
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _token = None
    _msgtypes = []
    # API 基础 URL（token将拼接到路径中）
    base_url = "http://api.chuckfang.com/"

    # 消息处理线程
    processing_thread = None
    # 上次发送时间
    last_send_time = 0
    # 消息队列
    message_queue = Queue()
    # 消息发送间隔（秒）
    send_interval = 5
    # 退出事件
    __event = threading.Event()

    def init_plugin(self, config: dict = None):
        self.__event.clear()
        if config:
            self._enabled = config.get("enabled")
            self._token = config.get("token")
            self._msgtypes = config.get("msgtypes") or []

            if self._enabled and self._token:
                # 启动处理队列的后台线程
                self.processing_thread = threading.Thread(target=self.process_queue)
                self.processing_thread.daemon = True
                self.processing_thread.start()

    def get_state(self) -> bool:
        return self._enabled and self._token

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """拼装插件配置页面"""
        MsgTypeOptions = []
        for item in NotificationType:
            MsgTypeOptions.append({"title": item.value, "value": item.name})
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {'component': 'VSwitch', 'props': {'model': 'enabled', 'label': '启用插件'}}
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'token',
                                            'label': 'Token',
                                            'placeholder': '请输入Token（如IYUUxxx）'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'model': 'msgtypes',
                                            'label': '消息类型',
                                            'items': MsgTypeOptions
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                ]
            }
        ], {
            "enabled": False,
            'token': '',
            'msgtypes': []
        }

    def get_page(self) -> List[dict]:
        pass

    @eventmanager.register(EventType.NoticeMessage)
    def send(self, event: Event):
        """消息发送事件，将消息加入队列"""
        if not self.get_state() or not event.event_data:
            return

        msg_body = event.event_data
        if not msg_body.get("title") and not msg_body.get("text"):
            logger.warn("标题和内容不能同时为空")
            return

        self.message_queue.put(msg_body)
        logger.info("消息已加入队列等待发送")

    def process_queue(self):
        """处理队列中的消息，按间隔时间发送"""
        while True:
            if self.__event.is_set():
                logger.info("消息发送线程正在退出...")
                break
            msg_body = self.message_queue.get()

            # 检查发送间隔
            current_time = time()
            time_since_last_send = current_time - self.last_send_time
            if time_since_last_send < self.send_interval:
                sleep(self.send_interval - time_since_last_send)

            # 处理消息内容
            channel = msg_body.get("channel")
            if channel:
                continue
            msg_type = msg_body.get("type")
            title = msg_body.get("title")
            text = msg_body.get("text")

            if msg_type and self._msgtypes and msg_type.name not in self._msgtypes:
                logger.info(f"消息类型 {msg_type.value} 未开启发送")
                self.message_queue.task_done()
                continue

            logger.info(f"准备发送消息 - 标题: {title}, 内容: {text[:30]}...")

            try:
                # 构造完整URL（token拼接到路径中）
                api_url = f"{self.base_url}{self._token}"
                
                # 构造请求体（确保title和msg不为空）
                safe_title = title if title else ""
                safe_text = text if text else ""
                if not safe_title and not safe_text:
                    logger.error("标题和内容均为空，无法发送")
                    self.message_queue.task_done()
                    continue

                logger.info(f"title: {safe_title}; text: {safe_text}")

                post_data = {
                    "title": safe_title,
                    "msg": safe_text
                }
                
                # 发送POST请求
                res = RequestUtils().post_res(
                    url=api_url,
                    json=post_data,
                    headers={"Content-Type": "application/json"}
                )
                
                # 处理响应
                if res and res.status_code == 200:
                    try:
                        ret_json = res.json()
                        if ret_json.get("status") == 200:
                            logger.info("消息发送成功")
                            self.last_send_time = time()
                        else:
                            err_msg = ret_json.get("msg", "未知错误")
                            logger.warn(f"发送失败: {err_msg}")
                    except json.JSONDecodeError:
                        logger.error("响应非JSON格式，但状态码200，假设发送成功")
                        self.last_send_time = time()
                elif res and res.status_code == 400:
                    logger.info("参数错误（如内容为空）")
                elif res and res.status_code == 500:
                    logger.info("服务器错误")
                else:
                    logger.warn(f"发送失败，状态码: {res.status_code if res else '无响应'}")
            except Exception as e:
                logger.error(f"发送异常: {str(e)}")
            finally:
                self.message_queue.task_done()

    def stop_service(self):
        """退出插件"""
        self.__event.set()