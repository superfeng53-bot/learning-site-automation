"""HttpClient — 通用 HTTP 会话封装（站点无关）。

站点定制点（少量）：
- `is_logged_in()`：phase 1 侦察出真实会话校验接口后覆盖。
- 默认 header / charset：个别站点需要 `charset=UTF-8` 或特定 Referer。

其余（cookie 管理、安全重试 form_post_safe / json_post_safe / form_get_html）通用，直接用。
"""
from __future__ import annotations

import random
import time
from typing import Any

import requests

from .config import BASE_URL, DEFAULT_USER_AGENT


class HttpClient:
    def __init__(self, base_url: str = BASE_URL, user_id: str | None = None) -> None:
        self.user_id = user_id or str(id(self))
        self.base_url = base_url.rstrip("/")
        self.user_profile: dict[str, Any] | None = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": f"{self.base_url}/",
        })

    # ---- cookie ----
    def load_cookies(self, cookies: dict[str, str]) -> None:
        self.session.cookies.clear()
        for k, v in cookies.items():
            self.session.cookies.set(k, v)

    def export_cookies(self) -> dict[str, str]:
        return self.session.cookies.get_dict()

    def _cookie(self, name: str) -> str:
        return self.session.cookies.get_dict().get(name, "")

    # ---- raw ----
    def json_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = self.session.post(f"{self.base_url}{path}", json=payload,
                              headers={"Content-Type": "application/json;charset=UTF-8"},
                              timeout=30)
        r.raise_for_status()
        return r.json()

    def form_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = self.session.post(f"{self.base_url}{path}", data=payload, timeout=30)
        r.raise_for_status()
        return r.json()

    def get(self, path: str, params: dict[str, Any] | None = None) -> requests.Response:
        r = self.session.get(f"{self.base_url}{path}", params=params, timeout=30)
        r.raise_for_status()
        return r

    # ---- 安全重试（瞬时网络错误，3-4 次指数退避 + 抖动；不重试 4xx 业务失败） ----
    def form_post_safe(self, path: str, payload: dict[str, Any], *, attempts: int = 3) -> dict[str, Any]:
        last: Exception | None = None
        for i in range(attempts):
            try:
                return self.form_post(path, payload)
            except requests.RequestException as exc:
                last = exc
                if i + 1 == attempts:
                    break
                time.sleep(2.0 * (2 ** i) + random.uniform(0, 0.5))
        raise last  # type: ignore[misc]

    def json_post_safe(self, path: str, payload: dict[str, Any], *, attempts: int = 3) -> dict[str, Any]:
        last: Exception | None = None
        for i in range(attempts):
            try:
                return self.json_post(path, payload)
            except requests.RequestException as exc:
                last = exc
                if i + 1 == attempts:
                    break
                time.sleep(2.0 * (2 ** i) + random.uniform(0, 0.5))
        raise last  # type: ignore[misc]

    def form_get_html(self, path: str, params: dict[str, Any] | None = None, *, attempts: int = 4) -> str:
        last: Exception | None = None
        for i in range(attempts):
            try:
                return self.get(path, params).text
            except requests.RequestException as exc:
                last = exc
                if i + 1 == attempts:
                    break
                time.sleep(1.5 * (2 ** i) + random.uniform(0, 0.5))
        raise last  # type: ignore[misc]

    # ---- 站点定制点：phase 1 后用真实会话校验接口覆盖 ----
    def is_logged_in(self) -> bool:
        """默认仅判断是否有 cookie。phase 1 侦察出 `isLogin` 类接口后覆盖为真实探活。"""
        return bool(self.export_cookies())
