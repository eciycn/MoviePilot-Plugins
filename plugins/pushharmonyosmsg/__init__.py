import threading
import requests
import json
from queue import Queue
from time import time, sleep
from typing import Any, List, Dict, Tuple
from urllib.parse import quote, urlencode


from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.utils.http import RequestUtils


class PushHarmonyOsMsg(_PluginBase):
    # 插件名称
    plugin_name = "鸿蒙Next消息推送"
    # 插件描述
    plugin_desc = "借助MeoW应用实现鸿蒙原生Push推送。"
    # 插件图标
    plugin_icon = "Pushplus_A.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "eciycn"
    # 作者主页
    author_url = "https://github.com/eciycn/MoviePilot-Plugins"
    # 插件配置项ID前缀
    plugin_config_prefix = "pushharmonyosmsg_"
    # 加载顺序
    plugin_order = 29
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _token = None
    _msgtypes = []

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
                                            'placeholder': 'MeoW Id',
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
                # sc_url = "http://api.chuckfang.com/%s/%s/%s" % (self._token, quote(title), quote(safe_text))
                sc_url = "http://api.chuckfang.com/%s" % (self._token)
                #msg_str = title if not text else f"{title}\n{text}"
                title_new = "[MP消息]" + title
                text_new = title if not text else text

                # 构造请求参数
                payload = {
                    "title": title_new,       # 消息标题
                    "msg": text_new       # 消息内容
                }
                # 请求头设置，指定发送JSON格式数据
                headers = {
                    "Content-Type": "application/json"
                }

                # 发送POST请求
                response = requests.post(sc_url, data=json.dumps(payload), headers=headers)
                
                # 解析响应结果
                result = response.json()

                # 打印响应状态和消息
                print(f"请求状态码: {response.status_code}")
                print(f"响应内容: {result}")

                # 根据状态码判断请求是否成功
                if response.status_code == 200:
                    print("消息发送成功!")
                else:
                    print(f"消息发送失败: {result.get('msg', '未知错误')}")

            except requests.exceptions.RequestException as e:
                print(f"请求异常: {e}")
            except json.JSONDecodeError as e:
                print(f"响应解析异常: {e}")

            # 标记任务完成
            self.message_queue.task_done()

    def stop_service(self):
        """
        退出插件
        """
        self.__event.set()