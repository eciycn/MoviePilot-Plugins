import threading
from queue import Queue
from time import time, sleep
from typing import Any, List, Dict, Tuple
from urllib.parse import quote, urlencode
import json

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.http import RequestUtils


class PushHarmonyOsMsgV2(_PluginBase):
    # 插件名称
    plugin_name = "鸿蒙Next消息推送V2"
    # 插件描述
    plugin_desc = "借助MeoW应用实现鸿蒙原生Push推送。"
    # 插件图标
    plugin_icon = "Pushplus_A.png"
    # 插件版本
    plugin_version = "0.1"
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
    # API 端点 URL（假设为 /send）
    api_endpoint = "http://api.chuckfang.com/send"

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
            # 从配置中获取API端点（可选）
            self.api_endpoint = config.get("api_endpoint", self.api_endpoint)

            if self._enabled and self._token:
                # 启动处理队列的后台线程
                self.processing_thread = threading.Thread(target=self.process_queue)
                self.processing_thread.daemon = True
                self.processing_thread.start()

    def get_state(self) -> bool:
        return self._enabled and (True if self._token else False)

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        # 编历 NotificationType 枚举，生成消息类型选项
        MsgTypeOptions = []
        for item in NotificationType:
            MsgTypeOptions.append({
                "title": item.value,
                "value": item.name
            })
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
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
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'token',
                                            'label': 'ID',
                                            'placeholder': 'IYUUxxx',
                                        }
                                    },
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'api_endpoint',
                                            'label': 'API 端点',
                                            'placeholder': 'http://api.chuckfang.com/send',
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
                                'props': {
                                    'cols': 12
                                },
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
            'api_endpoint': 'http://api.chuckfang.com/send',
            'msgtypes': []
        }

    def get_page(self) -> List[dict]:
        pass

    @eventmanager.register(EventType.NoticeMessage)
    def send(self, event: Event):
        """
        消息发送事件，将消息加入队列
        """
        if not self.get_state() or not event.event_data:
            return

        msg_body = event.event_data
        # 验证消息的有效性
        if not msg_body.get("title") and not msg_body.get("text"):
            logger.warn("标题和内容不能同时为空")
            return

        # 将消息加入队列
        self.message_queue.put(msg_body)
        logger.info("消息已加入队列等待发送")

    def process_queue(self):
        """
        处理队列中的消息，按间隔时间发送
        """
        while True:
            if self.__event.is_set():
                logger.info("消息发送线程正在退出...")
                break
            # 获取队列中的下一条消息
            msg_body = self.message_queue.get()

            # 检查是否满足发送间隔时间
            current_time = time()
            time_since_last_send = current_time - self.last_send_time
            if time_since_last_send < self.send_interval:
                sleep(self.send_interval - time_since_last_send)

            # 处理消息内容
            channel = msg_body.get("channel")
            if channel:
                continue
            msg_type: NotificationType = msg_body.get("type")
            title = msg_body.get("title")
            text = msg_body.get("text")

            # 检查消息类型是否已启用
            if msg_type and self._msgtypes and msg_type.name not in self._msgtypes:
                logger.info(f"消息类型 {msg_type.value} 未开启消息发送")
                continue

            logger.info(f"title: {title}; text: {text}")

            # 尝试发送消息
            try:
                safe_text = text if text is not None else ""  # 将 None 转为空字符串
                
                # 构造 POST 请求体（JSON 格式）
                payload = {
                    "token": self._token,
                    "title": title,
                    "text": safe_text
                }
                
                # 发送 POST 请求
                res = RequestUtils().post_res(
                    url=self.api_endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                # 处理响应
                if res and res.status_code == 200:
                    try:
                        ret_json = res.json()
                        errno = ret_json.get('errcode', 0)
                        error = ret_json.get('errmsg', '')
                        
                        if errno == 0:
                            logger.info("消息发送成功")
                            # 更新上次发送时间
                            self.last_send_time = time()
                        else:
                            logger.warn(f"消息发送失败，错误码：{errno}，错误原因：{error}")
                    except json.JSONDecodeError:
                        logger.error("响应不是合法的JSON格式")
                        logger.info("消息发送成功（假设200状态码表示成功）")
                        self.last_send_time = time()
                elif res and res.status_code == 400:
                    logger.info("参数错误")
                elif res and res.status_code == 500:
                    logger.info("服务器错误")
                else:
                    logger.warn("消息发送失败，未获取到返回信息")
            except Exception as msg_e:
                logger.error(f"消息发送失败，{str(msg_e)}")

            # 标记任务完成
            self.message_queue.task_done()

    def stop_service(self):
        """
        退出插件
        """
        self.__event.set()