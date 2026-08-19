# Research: Translation Providers (Phase 3)

> Сравнение провайдеров перевода для REQ-v1.5-004. Trade-offs, стоимость, качество.

## Date: 2026-08-19
## Status: Research, awaiting user decision

---

## Candidates

### 1. LibreTranslate (HTTP API) ⚠️ DEAD

**Описание:** Open-source self-hosted OR публичный инстанс. REST API: `POST /translate`.

**Плюсы:**
- ✅ Бесплатно (если self-hosted) или условно-бесплатно (публичный)
- ✅ Приватно (если self-hosted) — текст не уходит в облако
- ✅ MIT license
- ✅ Много языков (ru, en, de, fr, es, zh, ...)
- ✅ Простой API: `{"q": "Привет", "source": "ru", "target": "en"}` → `{"translatedText": "Hello"}`

**Минусы:**
- ❌ **Публичные инстансы мертвы в 2025** (проверено 2026-08-19):
  - `libretranslate.com` → HTTP 502 / 404
  - `translate.argosopentech.com` → DNS fail
  - `libretranslate.de` → 403 (Cloudflare block)
  - `lt.vern.cc` → 502
  - `libretranslate.pussthecat.org` → 404
- ❌ Self-hosted требует Docker + ~2GB RAM + 5 мин setup
- ❌ Качество среднее (Argos Translate под капотом)
- ❌ Медленно на длинных текстах (5-10 сек на 1KB)

**Decision fit (v1.5):** ❌ НЕ ИСПОЛЬЗУЕМ как default. Публичные инстансы мертвы, self-hosted слишком heavy для v1.5. Остаётся в коде для пользователей, у которых есть свой self-hosted инстанс.

---

### 2. Argos Translate (local, ~280 МБ) ⚠️ СЛОЖНО В 2025

**Описание:** Python-библиотека, обёртка над OpenNMT/CTranslate2. Модели скачиваются отдельно.

**Плюсы:**
- ✅ Бесплатно
- ✅ Локально (без облака)
- ✅ ~280 МБ на языковую пару en↔ru
- ✅ 0.5-1.5 сек на короткий текст
- ✅ Качество: ~85% NLLB (хорошее для UI)

**Минусы:**
- ❌ **`pip install argostranslate` ставит, но `import argostranslate.translate` виснет** на некоторых системах (невозможно диагностировать — зависает без вывода)
- ❌ **API argosopentech.com (для скачивания моделей) → HTTP 404** (проверено 2026-08-19)
- ❌ **GitHub repo argosopentech/argos-translate → last release v1.4.0 (старый), модельный репозиторий не активен**
- ❌ После установки пакета нужно отдельно скачивать модели (отдельная команда)
- ❌ Размер модели зависит от языковой пары: 50-300 МБ

**Реальная установка (2026-08-19):**
```bash
py -3.13 -m pip install argostranslate  # OK
py -3.13 -m argostranslate.package install translate-ru_en  # ЗАВИСАЕТ
```

**Можно ли установить вручную:** можно, но модель придётся качать с [libretranslate/argospm](https://github.com/argosopentech/argospm-index) (архив). Размер ~280 МБ.

**Decision fit (v1.5):** 🟡 ЧАСТИЧНО. Код в `tools/translation.py` готов, но реально установить пользователю придётся вручную. Default в config — `argos` (когда работает), fallback `libretranslate`.

---

### 3. MiniMax API (OpenAI-compatible)

**Описание:** Платный LLM API от MiniMax. Может переводить через LLM-модель.

**Плюсы:**
- ✅ SOTA качество перевода (даже для technical texts)
- ✅ Быстро (1-2 сек)
- ✅ OpenAI-compatible API (легко интегрировать)
- ✅ Может также делать summary, grammar fix, etc.
- ✅ Ключ уже в `~/.minimax/auth.json` (если есть)

**Минусы:**
- ❌ Платный (~$0.0001-0.001 за 1K tokens)
- ❌ Данные уходят в облако
- ❌ Зависимость от external service

**Decision fit:** v1.5 ✅ (как fallback если LibreTranslate недоступен)

---

### 4. NLLB-200 (Local, CTranslate2) — не реализовано в v1.5

**Описание:** Meta's No Language Left Behind, distilled 600M variant. Можно через CTranslate2 (который уже есть в faster-whisper).

**Плюсы:**
- ✅ Полностью локально
- ✅ 200 языков
- ✅ Качество SOTA (95% от full NLLB)
- ✅ CTranslate2 inference быстрый
- ✅ Не зависит от argosopentech

**Минусы:**
- ❌ ~300 МБ distilled 600M, ~600 МБ distilled 1.3B
- ❌ Нужен скачивание модели вручную (HuggingFace)
- ❌ Tokenizer + setup сложнее чем у Argos
- ❌ v1.5 фокус на "быстрое рабочее решение", NLLB — v2 candidate

**Decision fit:** v1.5 ❌, v2 ✅. Если Argos не пошёл — NLLB-200 будет планом B.

---

### 5. Whisper-style inline (не подходит)

Whisper сам по себе НЕ переводит, только транскрибирует. Можно использовать для English transcription напрямую (если source = en, no translation needed).

**Decision fit:** N/A

---

## Comparison matrix (обновлено 2026-08-19)

| Provider | Cost | Privacy | Quality | Speed | Setup | v1.5? | Статус |
|----------|------|---------|---------|-------|-------|-------|--------|
| LibreTranslate public | Free | Cloud | Medium | Slow | None | ❌ | **мертвы** в 2025 (HTTP 502/404) |
| LibreTranslate self-hosted | Free | Local | Medium | Medium | 5 min | 🟡 | остался в коде (если есть URL) |
| Argos Translate | Free | Local | Good | 0.5-1.5s | 280MB model | 🟡 | **import зависает** на 2026-08-19, нужно чинить |
| MiniMax API | ~$0.001/tx | Cloud | High | Fast | API key | ✅ | работает, но нужен ключ |
| NLLB-200 (CTranslate2) | Free | Local | High | 200-500ms | 300MB model | ❌ v2 | не реализован в v1.5 |

**Реальность на 2026-08-19:**
- Нет "из коробки работающего" бесплатного локального провайдера
- Argos — самый близкий, но install проблемный
- NLLB-200 (через CTranslate2) — лучший кандидат для v2

---

## Recommended config (v1.5)

```jsonc
{
  "translate_to_en": false,                  // OFF по умолчанию (провайдеры мертвы/нужен ключ)
  "translation_provider": "argos",           // primary, но сейчас не работает из коробки
  "translation_fallback": "libretranslate",  // fallback (тоже мертв)
  "libretranslate_url": "",                  // свой self-hosted URL
  "minimax_key": ""                          // пустой = из auth.json
}
```

**UX (v1.5):**
- 🌐 Отдельная карточка "Перевод на английский" (всегда видна, не в шестерёнке)
- Чекбокс + select провайдера + 💾 Сохранить + 🧪 Тест
- Под карточкой `<details>` с инструкцией по установке Argos
- Если ни один провайдер не работает — перевод просто пропускается, оригинал остаётся

**Fallback chain (текущий):**
1. `translation_provider` (argos / libretranslate / minimax)
2. `translation_fallback` (если primary не сработал)
3. None — перевод пропускается, в лог пишется warning, юзер не видит ошибку

---

## Open questions

1. **MiniMax key location** — брать из `~/.minimax/auth.json` автоматически? Или требовать ввод в UI?
   - Decision: auto-discover from `auth.json` (если есть файл), allow manual override в UI
2. **Cost per transcript** — насколько частый перевод? Один транскрипт = 1K-10K tokens. С MiniMax = $0.0001-0.001. На 1000 расшифровок = $0.10-1.00. Acceptable.
3. **Translation quality for technical audio** — MiniMax LLM лучше для IT/научных терминов. Whisper → MiniMax = отличная комбинация.
4. **What to do if translation fails** — original stays, log warning, no UI noise. Don't bother user with "translation failed" toast.

---

## v1.5 minimal implementation

```python
# tools/translation.py
class TranslationProvider(abc.ABC):
    def translate(self, text: str, source: str = "auto", target: str = "en") -> str: ...

class LibreTranslate(TranslationProvider):
    def __init__(self, url: str = ""): ...
    def translate(self, text, source, target) -> str: ...

class MiniMax(TranslationProvider):
    def __init__(self, api_key: str): ...
    def translate(self, text, source, target) -> str: ...

def get_provider(name: str) -> TranslationProvider:
    """Returns the configured provider. Falls back if not available."""
    ...
```

```python
# server.py: in transcribe() after save_transcript
if cfg.get("translate_to_en") and out.get("text"):
    try:
        provider = translation.get_provider(cfg.get("translation_provider", "minimax"))
        if provider:
            translated = provider.translate(out["text"], source="auto", target="en")
            clean.save_translated(file.filename, translated, out.get("info", {}))
    except Exception as e:
        log.warning("Translation failed: %s", e)
        # original still saved, no UI noise
```

```python
# tools/cleanup.py
def save_translated(original_name: str, translated_text: str, info: dict) -> Path:
    """Save translated version as <original_name>.en.txt (или <source.ext>.en.txt)."""
    src = Path(original_name or "audio")
    base = f"{src.stem}.{src.suffix.lstrip('.')}" if src.suffix else src.stem
    path = TRANSCRIPTS_DIR / f"{base}.en.txt"
    ...
```

---

*Author: AI-агент mavis. Date: 2026-08-19.*
