"""Translation providers for autrau (v1.5).

Поддерживает несколько провайдеров:
  - LibreTranslate (HTTP, public или self-hosted)
  - MiniMax (OpenAI-compatible API, платный)

Fallback chain: MiniMax → LibreTranslate (если ключ есть — MiniMax первый).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional

log = logging.getLogger("autrau.translation")

# ----- Helpers -----

def _http_post_json(url: str, body: dict, headers: Optional[dict] = None,
                    timeout: int = 30) -> dict:
    """HTTP POST с JSON-телом, возвращает JSON-ответ или бросает."""
    data = json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, method="POST", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", "replace")
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:300]}")


# ----- Abstract -----

class TranslationProvider(ABC):
    name: str = "?"

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """(True, "") если может работать; иначе (False, "почему")."""

    @abstractmethod
    def translate(self, text: str, source: str = "auto", target: str = "en") -> str:
        """Переводит text → язык target. source="auto" для авто-определения."""


# ----- Argos Translate (local, lightweight, no GPU needed) -----

class ArgosTranslateProvider(TranslationProvider):
    """Локальный перевод через argostranslate (тот же движок, что в LibreTranslate).

    ~280 МБ на языковую пару en↔ru, 0.5-1.5 сек на короткий текст, чисто CPU.
    Установка:
      - pip install argostranslate
      - пакетная модель: en→ru и ru→en (~336 МБ суммарно, скачивается в фоне)
    """
    name = "argos"

    def __init__(self, from_code: str = "en", to_code: str = "ru") -> None:
        self._from = from_code
        self._to = to_code
        self._installed_langs = None
        self._translation = None
        self._loaded_pair = None

    def is_available(self) -> tuple[bool, str]:
        """Только лёгкая проверка: пакет импортируется + модели en_ru / ru_en стоят.

        Не загружаем модели в память (это занимает 5-15 сек).
        """
        try:
            import argostranslate  # noqa: F401
        except ImportError as e:
            return False, f"pip install argostranslate ({e})"
        # Проверяем что модели en_ru + ru_en скачаны (без загрузки в RAM)
        try:
            from argostranslate import package as _pkg
            installed = {p.from_code + "_" + p.to_code for p in _pkg.get_installed_packages()}
        except Exception as e:
            return True, f"пакет OK, но не удалось прочитать список моделей: {e}"
        missing = []
        for pair in ("en_ru", "ru_en"):
            if pair not in installed:
                missing.append(pair)
        if missing:
            return True, f"пакет OK, модели отсутствуют: {','.join(missing)} (вызови /api/translate/install-argos)"
        return True, "en_ru+ru_en модели установлены"

    def _ensure_translator(self):
        # Проверяем модели в отдельном потоке с таймаутом, чтобы не зависнуть
        from argostranslate import translate
        import threading
        if self._installed_langs is None:
            result = [None, None]
            def worker():
                try:
                    result[0] = translate.get_installed_languages()
                except Exception as e:
                    result[1] = e
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            t.join(10)  # 10 секунд максимум
            if t.is_alive():
                raise RuntimeError("argostranslate.get_installed_languages() завис (таймаут 10с). "
                                   "Скорее всего повреждена установка. Переустановите: pip install --force-reinstall argostranslate")
            if result[1]:
                raise RuntimeError(f"argostranslate ошибка: {result[1]}")
            self._installed_langs = result[0]
        codes = [l.code for l in self._installed_langs]
        if self._from not in codes or self._to not in codes:
            raise RuntimeError(
                f"Языковая пара {self._from}↔{self._to} не установлена. "
                f"Выполните: py -3.13 -m argostranslate.package install translate-{self._from}_{self._to}"
            )
        if self._loaded_pair == (self._from, self._to):
            return self._translation
        from_lang = next(l for l in self._installed_langs if l.code == self._from)
        to_lang = next(l for l in self._installed_langs if l.code == self._to)
        self._translation = translate.get_translation_from_codes(
            self._from, self._to
        ) or translate.Translation(from_lang, to_lang)
        self._loaded_pair = (self._from, self._to)
        return self._translation

    def translate(self, text: str, source: str = "auto", target: str = "en") -> str:
        if not text or not text.strip():
            return text
        # Argos жёстко привязан к паре (from, to), игнорируем source/target от API.
        # Для авто-определения: langdetect (если есть), иначе эвристика по Cyrillic.
        from_code = self._from
        to_code = self._to
        if source == "auto" and not text.strip().isascii():
            detected = None
            try:
                from langdetect import detect
                d = detect(text)
                if d in ("ru", "en"):
                    detected = d
            except Exception:
                pass
            if detected is None:
                # Fallback: эвристика — есть кириллица → ru
                if any("\u0400" <= ch <= "\u04FF" for ch in text):
                    detected = "ru"
                else:
                    detected = "en"
            from_code = detected
            to_code = "en" if detected == "ru" else "ru"
        if (from_code, to_code) != (self._from, self._to):
            p = ArgosTranslateProvider(from_code=from_code, to_code=to_code)
            p._installed_langs = self._installed_langs
            p._ensure_translator()
            return p._translation.translate(text)
        self._ensure_translator()
        return self._translation.translate(text)



class TranslationProvider(ABC):
    name: str = "?"

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """(True, "") если может работать; иначе (False, "почему")."""

    @abstractmethod
    def translate(self, text: str, source: str = "auto", target: str = "en") -> str:
        """Переводит text → язык target. source="auto" для авто-определения."""


# ----- LibreTranslate -----

class LibreTranslateProvider(TranslationProvider):
    name = "libretranslate"

    def __init__(self, url: str = "", api_key: str = "") -> None:
        # Если url пустой — пробуем публичные
        self._url = (url or "https://libretranslate.com/").rstrip("/")
        self._api_key = api_key

    def is_available(self) -> tuple[bool, str]:
        # LibreTranslate не требует ключа на некоторых публичных инстансах.
        # Если есть URL или публичный доступен — ok.
        return True, ""  # допустим, может упасть в translate()

    def translate(self, text: str, source: str = "auto", target: str = "en") -> str:
        if not text or not text.strip():
            return text
        body = {"q": text, "source": source, "target": target, "format": "text"}
        if self._api_key:
            body["api_key"] = self._api_key
        out = _http_post_json(self._url + "/translate", body, timeout=60)
        translated = out.get("translatedText", "")
        if not translated:
            raise RuntimeError("Пустой ответ от LibreTranslate")
        return translated


# ----- MiniMax (OpenAI-compatible) -----

class MiniMaxProvider(TranslationProvider):
    name = "minimax"

    def __init__(self, api_key: str, base_url: str = "https://api.minimax.io/v1",
                 model: str = "MiniMax-M2.7-highspeed") -> None:
        self._key = api_key
        self._url = (base_url or "https://api.minimax.io/v1").rstrip("/")
        self._model = model

    def is_available(self) -> tuple[bool, str]:
        if not self._key:
            return False, "MiniMax: не задан api_key"
        return True, ""

    def translate(self, text: str, source: str = "auto", target: str = "en") -> str:
        if not text or not text.strip():
            return text
        if not self._key:
            raise RuntimeError("MiniMax: не задан api_key")
        # OpenAI-compatible chat completion: просим модель перевести
        sys_prompt = (
            "You are a translation engine. Translate the user's text into the "
            "requested target language. Preserve meaning, formatting, and named "
            "entities. Output ONLY the translated text, no commentary."
        )
        user_prompt = f"Target language: {target}\n\nText:\n{text}"
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }
        headers = {"Authorization": f"Bearer {self._key}"}
        out = _http_post_json(self._url + "/chat/completions", body,
                              headers=headers, timeout=60)
        try:
            translated = out["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"MiniMax: неожиданный ответ: {e}")
        if not translated:
            raise RuntimeError("MiniMax: пустой ответ")
        return translated


# ----- Auto-discover MiniMax key from auth.json -----

def _try_load_minimax_key() -> str:
    """Читает ~/.minimax/auth.json если есть, ищет minimax.api_key или похожее."""
    candidates = [
        os.path.expanduser("~/.minimax/auth.json"),
        os.path.expanduser("~/.minimax/auth.json".replace("~", os.environ.get("USERPROFILE", "~"))),
    ]
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # Поддерживаем разные ключи
            for k in ("minimax.api_key", "minimax_api_key", "api_key", "key"):
                if k in data:
                    val = data[k]
                    if isinstance(val, str) and val.strip():
                        return val.strip()
                if "." in k:
                    top, sub = k.split(".", 1)
                    if top in data and isinstance(data[top], dict) and sub in data[top]:
                        val = data[top][sub]
                        if isinstance(val, str) and val.strip():
                            return val.strip()
        except (OSError, json.JSONDecodeError):
            continue
    return ""


# ----- Public API -----

def get_provider(name: str, libretranslate_url: str = "",
                 libretranslate_key: str = "", minimax_key: str = "") -> Optional[TranslationProvider]:
    """Возвращает провайдер по имени, или None если недоступен.

    Приоритет: явный minimax_key > ~/.minimax/auth.json > config.
    """
    if name == "minimax":
        key = minimax_key or _try_load_minimax_key()
        if not key:
            return None
        return MiniMaxProvider(api_key=key)
    if name == "libretranslate":
        return LibreTranslateProvider(url=libretranslate_url, api_key=libretranslate_key)
    if name == "argos":
        prov = ArgosTranslateProvider()
        avail, why = prov.is_available()
        if not avail:
            log.info("Argos unavailable: %s", why)
            return None
        return prov
    return None


def translate(text: str, target: str, *, provider_name: str = "minimax",
              fallback_provider: str = "libretranslate",
              libretranslate_url: str = "", libretranslate_key: str = "",
              minimax_key: str = "") -> tuple[str, str]:
    """Переводит text → target через цепочку provider → fallback.

    Возвращает (translated_text, provider_name_used).
    Бросает RuntimeError если оба провайдера не сработали.
    """
    chain = [provider_name]
    if fallback_provider and fallback_provider != provider_name:
        chain.append(fallback_provider)

    last_err: Optional[Exception] = None
    for pname in chain:
        prov = get_provider(pname, libretranslate_url, libretranslate_key, minimax_key)
        if prov is None:
            log.debug("Translation provider %s unavailable", pname)
            continue
        avail, why = prov.is_available()
        if not avail:
            log.info("Translation provider %s: %s", pname, why)
            continue
        try:
            translated = prov.translate(text, source="auto", target=target)
            return translated, pname
        except Exception as e:
            log.warning("Translation %s failed: %s", pname, e)
            last_err = e
    raise RuntimeError(f"Не удалось перевести: все провайдеры недоступны ({last_err})")
