"""
任务队列管理
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from enum import IntEnum
from typing import Optional, List, Tuple
import uuid

import redis.asyncio as redis

from writeflow.config import get_settings


class PriorityLevel(IntEnum):
    """优先级等级"""

    CRITICAL = 0  # 最高优先级
    HIGH = 1
    NORMAL = 2
    LOW = 3


class TaskQueueManager:
    """
    基于优先级的任务队列管理器
    使用Redis Sorted Set实现优先级队列，支持多级优先级
    """

    QUEUE_KEYS = {
        PriorityLevel.CRITICAL: "writeflow:queue:critical",
        PriorityLevel.HIGH: "writeflow:queue:high",
        PriorityLevel.NORMAL: "writeflow:queue:normal",
        PriorityLevel.LOW: "writeflow:queue:low",
    }

    TASK_PAYLOAD_PREFIX = "writeflow:task:payload:"
    TASK_STATE_PREFIX = "writeflow:task:state:"

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.settings = get_settings()

    async def enqueue(
        self,
        task_id: uuid.UUID,
        priority: int,
        payload: dict,
        content_type: str = "general",
    ) -> None:
        """
        添加任务到队列

        Args:
            task_id: 任务ID
            priority: 优先级 (0-100, 0为最高)
            payload: 任务数据
            content_type: 内容类型
        """
        queue_key = self._priority_to_queue(priority)
        # 优先级分数，时间戳作为二级排序保证FIFO
        score = priority + (datetime.utcnow().timestamp() / 1e9)

        # 存储任务数据
        payload_key = f"{self.TASK_PAYLOAD_PREFIX}{task_id}"
        await self.redis.hset(
            payload_key,
            mapping={
                "priority": str(priority),
                "payload": json.dumps(payload),
                "content_type": content_type,
                "enqueued_at": datetime.utcnow().isoformat(),
            },
        )
        # 设置过期时间（7天）
        await self.redis.expire(payload_key, 86400 * 7)

        # 添加到优先级队列
        await self.redis.zadd(queue_key, {str(task_id): score})

    async def dequeue(self, timeout: int = 5) -> Optional[Tuple[uuid.UUID, dict]]:
        """
        阻塞式获取最高优先级任务

        Args:
            timeout: 等待超时（秒）

        Returns:
            (task_id, payload) 或 None
        """
        # 按优先级顺序等待多个队列
        result = await self.redis.blpop(
            [
                self.QUEUE_KEYS[PriorityLevel.CRITICAL],
                self.QUEUE_KEYS[PriorityLevel.HIGH],
                self.QUEUE_KEYS[PriorityLevel.NORMAL],
                self.QUEUE_KEYS[PriorityLevel.LOW],
            ],
            timeout=timeout,
        )

        if result:
            queue_name, task_id = result
            payload_key = f"{self.TASK_PAYLOAD_PREFIX}{task_id}"
            payload_data = await self.redis.hgetall(payload_key)
            if payload_data:
                return (
                    uuid.UUID(task_id),
                    json.loads(payload_data[b"payload"].decode()),
                )

        return None

    async def get_queue_depth(self) -> dict:
        """获取各队列深度"""
        depths = {}
        for level, key in self.QUEUE_KEYS.items():
            depths[key.split(":")[-1]] = await self.redis.zcard(key)
        return depths

    async def get_total_depth(self) -> int:
        """获取队列总深度"""
        total = 0
        for key in self.QUEUE_KEYS.values():
            total += await self.redis.zcard(key)
        return total

    async def peek(
        self, priority: Optional[int] = None, limit: int = 10
    ) -> List[uuid.UUID]:
        """
        查看队列头部的任务

        Args:
            priority: 如果指定，只看该优先级队列
            limit: 返回数量

        Returns:
            任务ID列表
        """
        if priority is not None:
            queue_key = self._priority_to_queue(priority)
            items = await self.redis.zrange(queue_key, 0, limit - 1)
            return [uuid.UUID(item.decode()) for item in items]

        # 看所有队列
        result = []
        for level in PriorityLevel:
            items = await self.redis.zrange(self.QUEUE_KEYS[level], 0, limit - 1)
            result.extend([uuid.UUID(item.decode()) for item in items])
            if len(result) >= limit:
                break
        return result[:limit]

    async def remove(self, task_id: uuid.UUID) -> bool:
        """从所有队列中移除任务"""
        task_id_str = str(task_id)
        removed = False

        for key in self.QUEUE_KEYS.values():
            count = await self.redis.zrem(key, task_id_str)
            if count > 0:
                removed = True

        # 删除任务数据
        await self.redis.delete(f"{self.TASK_PAYLOAD_PREFIX}{task_id}")

        return removed

    async def requeue(self, task_id: uuid.UUID, new_priority: int) -> None:
        """重新调整任务优先级"""
        # 先从所有队列移除
        await self.remove(task_id)

        # 获取原任务数据
        payload_key = f"{self.TASK_PAYLOAD_PREFIX}{task_id}"
        payload_data = await self.redis.hgetall(payload_key)
        if payload_data:
            payload = json.loads(payload_data[b"payload"].decode())
            payload["priority"] = str(new_priority)
            await self.redis.hset(payload_key, mapping={"priority": str(new_priority)})

            # 重新加入队列
            queue_key = self._priority_to_queue(new_priority)
            score = new_priority + (datetime.utcnow().timestamp() / 1e9)
            await self.redis.zadd(queue_key, {str(task_id): score})

    async def get_task_payload(self, task_id: uuid.UUID) -> Optional[dict]:
        """获取任务载荷"""
        payload_key = f"{self.TASK_PAYLOAD_PREFIX}{task_id}"
        data = await self.redis.hgetall(payload_key)
        if data:
            return json.loads(data[b"payload"].decode())
        return None

    async def update_task_state(self, task_id: uuid.UUID, state: str) -> None:
        """更新任务状态"""
        state_key = f"{self.TASK_STATE_PREFIX}{task_id}"
        await self.redis.hset(
            state_key,
            mapping={
                "state": state,
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
        await self.redis.expire(state_key, 86400 * 7)

    def _priority_to_queue(self, priority: int) -> str:
        """将优先级转换为队列key"""
        if priority < 20:
            return self.QUEUE_KEYS[PriorityLevel.CRITICAL]
        elif priority < 50:
            return self.QUEUE_KEYS[PriorityLevel.HIGH]
        elif priority < 80:
            return self.QUEUE_KEYS[PriorityLevel.NORMAL]
        return self.QUEUE_KEYS[PriorityLevel.LOW]


class ContinuousProductionBuffer:
    """
    连续生产Buffer
    确保队列始终有任务待处理，防止断档
    """

    def __init__(
        self,
        queue_manager: TaskQueueManager,
        worker_count: int,
        buffer_size: int = 10,
    ):
        self.queue = queue_manager
        self.worker_count = worker_count
        self.buffer_size = buffer_size
        self._pending: asyncio.Queue = asyncio.Queue(maxsize=buffer_size)
        self._running = False
        self._refill_task: Optional[asyncio.Task] = None

    @property
    def buffer_level(self) -> int:
        """当前buffer级别"""
        return self._pending.qsize()

    async def start(self) -> None:
        """启动buffer预热"""
        self._running = True
        await self._prefill_buffer()
        self._refill_task = asyncio.create_task(self._refill_loop())

    async def stop(self) -> None:
        """停止buffer"""
        self._running = False
        if self._refill_task:
            self._refill_task.cancel()
            try:
                await self._refill_task
            except asyncio.CancelledError:
                pass

    async def _prefill_buffer(self) -> None:
        """预填充buffer"""
        while not self._pending.full():
            task = await self.queue.dequeue(timeout=1)
            if task:
                await self._pending.put(task)
            else:
                break

    async def _refill_loop(self) -> None:
        """后台补充循环"""
        while self._running:
            try:
                if self._pending.qsize() < self.buffer_size // 2:
                    await self._refill_buffer()
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception:
                # 日志记录错误，继续
                await asyncio.sleep(5)

    async def _refill_buffer(self) -> None:
        """补充buffer到满"""
        while not self._pending.full():
            task = await self.queue.dequeue(timeout=1)
            if task:
                await self._pending.put(task)
            else:
                break

    async def get_task(self, timeout: int = 5) -> Optional[Tuple[uuid.UUID, dict]]:
        """获取任务"""
        try:
            return await asyncio.wait_for(
                self._pending.get(), timeout=timeout
            )
        except asyncio.TimeoutError:
            return None

    async def return_task(self, task_id: uuid.UUID, payload: dict) -> None:
        """任务处理失败，归还队列"""
        try:
            self._pending.put_nowait((task_id, payload))
        except asyncio.QueueFull:
            # 队列满，放回主队列
            await self.queue.enqueue(task_id, 50, payload)
