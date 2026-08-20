"""面向未来多人房间、网页实时对战和外部客户端的稳定接口层。

当前 ``GameEngine`` 是 A/B 双角色实现；未来可以用多人引擎替换它，只要继续实现
``BattleSessionProtocol``，网页、强化学习和桌面客户端的调用方式就不需要重写。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Callable, Protocol, runtime_checkable

from engine import GameEngine, RuleError


@dataclass(frozen=True)
class GameCommand:
    """客户端发给服务器/引擎的动作命令。"""

    actor: str
    action_id: str
    destination: str | None = None
    client_action_id: str | None = None


@dataclass(frozen=True)
class CommandResult:
    """一次命令的可序列化结果，可直接作为WebSocket消息体。"""

    accepted: bool
    actor: str
    client_action_id: str | None
    events: tuple[str, ...]
    snapshot: dict[str, Any]
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))


@runtime_checkable
class BattleSessionProtocol(Protocol):
    """未来任何双人/多人规则引擎对外都应保留的最小协议。"""

    def snapshot(self, viewer: str | None = None) -> dict[str, Any]: ...

    def available_commands(self, actor: str | None = None) -> list[dict[str, Any]]: ...

    def submit(self, command: GameCommand) -> CommandResult: ...

    def subscribe(self, callback: Callable[[CommandResult], None]) -> Callable[[], None]: ...


class GameSessionAdapter:
    """把当前A/B引擎包装成网络/客户端友好的会话。

    - 不引用Tkinter；
    - 输入输出可JSON序列化；
    - 命令显式携带actor，便于服务器做身份校验；
    - 订阅机制可连接桌面刷新、WebSocket广播或回放记录器。
    """

    protocol_version = "shai-session/1"

    def __init__(self, engine: GameEngine):
        self.engine = engine
        self._subscribers: list[Callable[[CommandResult], None]] = []

    def snapshot(self, viewer: str | None = None) -> dict[str, Any]:
        state = self.engine.observation()
        return {
            "protocol": self.protocol_version,
            "viewer": viewer,
            "state": state,
            "capabilities": {
                "players": ["A", "B"],
                "simultaneous_selection": True,
                "simultaneous_resolution": True,
                "hidden_information": False,
                "realtime_transport": False,
                "headless": True,
                "deterministic_seed": True,
            },
        }

    def available_commands(self, actor: str | None = None) -> list[dict[str, Any]]:
        actor = actor or self.engine.current_side
        return self.engine.legal_actions(actor)

    def submit(self, command: GameCommand) -> CommandResult:
        if command.actor != self.engine.current_side:
            result = CommandResult(
                accepted=False,
                actor=command.actor,
                client_action_id=command.client_action_id,
                events=(),
                snapshot=self.snapshot(command.actor),
                error=f"当前应由{self.engine.current_side}行动。",
            )
            self._publish(result)
            return result
        try:
            outcome = self.engine.step(command.action_id, command.destination)
            result = CommandResult(
                accepted=True,
                actor=command.actor,
                client_action_id=command.client_action_id,
                events=tuple(outcome["events"]),
                snapshot=self.snapshot(command.actor),
            )
        except RuleError as exc:
            result = CommandResult(
                accepted=False,
                actor=command.actor,
                client_action_id=command.client_action_id,
                events=(),
                snapshot=self.snapshot(command.actor),
                error=str(exc),
            )
        self._publish(result)
        return result

    def subscribe(self, callback: Callable[[CommandResult], None]) -> Callable[[], None]:
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def _publish(self, result: CommandResult) -> None:
        for callback in tuple(self._subscribers):
            callback(result)
