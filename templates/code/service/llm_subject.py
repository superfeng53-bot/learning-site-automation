"""
单条学科 LLM 映射 — 默认 qwen3.5-flash（DashScope OpenAI 兼容接口）。

复制到 <svc>/llm_subject.py。
凭证：`.run/ai_config.json`（服务级）或环境变量 `DASHSCOPE_API_KEY`。

DashScope Chat Completions（OpenAI 兼容）：
  POST {base_url}/chat/completions
  国内: https://dashscope.aliyuncs.com/compatible-mode/v1
  国际: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
  模型: qwen3.5-flash，temperature=0
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import requests

from .subject_mapper import PerCategoryLlmMapper, SubjectMappingError


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


DEFAULT_CONFIG_PATH = _project_root() / ".run" / "ai_config.json"

DEFAULT_AI_CONFIG: dict[str, Any] = {
    "provider": "dashscope",
    "model": "qwen3.5-flash",
    "api_key": "",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "temperature": 0,
    "timeout_sec": 60,
    "max_retries": 2,
}


def load_ai_config(path: Path | str | None = None) -> dict[str, Any]:
    """读取 .run/ai_config.json；api_key 可留空并从 DASHSCOPE_API_KEY 补全。"""
    cfg = dict(DEFAULT_AI_CONFIG)
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update(raw)
        except (OSError, json.JSONDecodeError) as e:
            raise SubjectMappingError(f"无法读取 AI 配置 {p}: {e}") from e

    if not str(cfg.get("api_key") or "").strip():
        env_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        if env_key:
            cfg["api_key"] = env_key

    if not str(cfg.get("api_key") or "").strip():
        raise SubjectMappingError(
            "LLM 未配置：请在 .run/ai_config.json 填写 api_key 或设置环境变量 DASHSCOPE_API_KEY"
        )
    if not str(cfg.get("model") or "").strip():
        raise SubjectMappingError("LLM 未配置 model")
    if not str(cfg.get("base_url") or "").strip():
        raise SubjectMappingError("LLM 未配置 base_url")
    return cfg


def _extract_json_object(text: str) -> dict[str, Any]:
    """从模型回复中解析 JSON（容忍 markdown 代码块）。"""
    t = (text or "").strip()
    if not t:
        raise SubjectMappingError("LLM 返回为空")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t, re.I)
    if fence:
        t = fence.group(1).strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(t[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    raise SubjectMappingError(f"LLM 返回非 JSON：{text[:200]}")


def _build_messages(
    category: str,
    category_names: Sequence[str],
    *,
    account_name: str = "",
    account_username: str = "",
    rule_preset: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    preset = ""
    if rule_preset:
        preset = str(rule_preset.get("label") or rule_preset.get("id") or "").strip() or "无"
    else:
        preset = "无"

    system = (
        "你是继教平台「人员类别 → 平台主学科」映射助手。\n"
        "规则：\n"
        "1. 只能从用户给出的「平台主学科列表」中【原样拷贝】一个名称作为 selected_category；\n"
        "2. 优先选择与人员类别最直接对应的主学科，不要随意泛化到「全科医学」；\n"
        "3. 若列表中确实没有合理项，selected_category 返回空字符串；\n"
        "4. 只输出一个 JSON 对象，不要 markdown，不要解释。格式："
        '{"selected_category":"列表中的名称"}'
    )
    user = (
        f"人员类别：{category}\n"
        f"账号：{account_name or '-'}（{account_username or '-'}）\n"
        f"平台主学科列表（只能从中原样选一个）：\n"
        f"{json.dumps(list(category_names), ensure_ascii=False)}\n"
        f"本地规则预估计（仅供参考，可不采纳）：{preset}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


@dataclass
class PerCategoryLlmSubjectMapper:
    """实现 subject_mapper.PerCategoryLlmMapper；学科1/学科2 各调一次。"""

    api_key: str
    model: str
    base_url: str
    provider: str = "dashscope"
    temperature: float = 0
    timeout_sec: int = 60
    max_retries: int = 2
    _process_cache: dict[str, dict[str, str]] | None = None

    @classmethod
    def from_config(cls, cfg: Mapping[str, Any] | None = None, *, path: Path | str | None = None) -> PerCategoryLlmSubjectMapper:
        data = load_ai_config(path) if cfg is None else {**load_ai_config(path), **dict(cfg)}
        return cls(
            api_key=str(data["api_key"]),
            model=str(data["model"]),
            base_url=str(data["base_url"]).rstrip("/"),
            provider=str(data.get("provider") or "dashscope"),
            temperature=float(data.get("temperature", 0)),
            timeout_sec=int(data.get("timeout_sec", 60)),
            max_retries=int(data.get("max_retries", 2)),
        )

    @classmethod
    def from_config_file(cls, path: Path | str | None = None) -> PerCategoryLlmSubjectMapper:
        return cls.from_config(path=path)

    def _cache_key(
        self,
        category: str,
        platform_subjects: Sequence[Mapping[str, str]],
    ) -> str:
        names = sorted({str(s.get("label") or "").strip() for s in platform_subjects if str(s.get("label") or "").strip()})
        payload = json.dumps(
            {"category": category.strip(), "names": names, "model": self.model, "provider": self.provider},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        import hashlib
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _call_chat(self, messages: list[dict[str, str]]) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        last_err: Exception | None = None
        for attempt in range(max(1, self.max_retries)):
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=self.timeout_sec)
                if resp.status_code >= 400:
                    raise SubjectMappingError(
                        f"DashScope HTTP {resp.status_code}: {resp.text[:300]}"
                    )
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise SubjectMappingError(f"LLM 无 choices：{data}")
                content = (choices[0].get("message") or {}).get("content") or ""
                if not str(content).strip():
                    raise SubjectMappingError("LLM content 为空")
                return str(content)
            except (requests.RequestException, SubjectMappingError) as e:
                last_err = e
                if attempt + 1 >= self.max_retries:
                    break
        raise SubjectMappingError(f"LLM 调用失败：{last_err}")

    def map_one_category(
        self,
        category: str,
        *,
        platform_subjects: Sequence[Mapping[str, str]],
        account_name: str = "",
        account_username: str = "",
        rule_preset: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        cat = str(category or "").strip()
        if not cat:
            raise SubjectMappingError("空 category 不应走 LLM")

        if self._process_cache is None:
            self._process_cache = {}
        ck = self._cache_key(cat, platform_subjects)
        if ck in self._process_cache:
            return dict(self._process_cache[ck])

        labels = [str(s.get("label") or "").strip() for s in platform_subjects if str(s.get("label") or "").strip()]
        if not labels:
            raise SubjectMappingError("平台学科列表为空，无法 LLM 映射")

        messages = _build_messages(
            cat,
            labels,
            account_name=account_name,
            account_username=account_username,
            rule_preset=rule_preset,
        )
        raw_text = self._call_chat(messages)
        parsed = _extract_json_object(raw_text)
        selected = str(parsed.get("selected_category") or parsed.get("selected") or "").strip()
        if not selected:
            raise SubjectMappingError(f"LLM 未选出有效学科：{cat}")

        label_to_id = {str(s.get("label") or "").strip(): str(s.get("id") or "").strip() for s in platform_subjects}
        sid = label_to_id.get(selected, "")
        if not sid:
            compact = re.sub(r"\s+|学科", "", selected)
            for lab, lid in label_to_id.items():
                if re.sub(r"\s+|学科", "", lab) == compact:
                    selected, sid = lab, lid
                    break
        if not sid:
            raise SubjectMappingError(f"LLM 选出项不在平台列表中：{selected!r}")

        result = {"id": sid, "label": selected}
        self._process_cache[ck] = result
        return result


def build_llm_mapper(path: Path | str | None = None) -> PerCategoryLlmMapper:
    """site_adapter / worker 入口：USE_LLM_SUBJECT_MAPPING=True 时调用。"""
    return PerCategoryLlmSubjectMapper.from_config_file(path)
