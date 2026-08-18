# Research: Translation Providers (Phase 3)

> Сравнение провайдеров перевода для REQ-v1.5-004. Trade-offs, стоимость, качество.

## Date: 2026-08-19
## Status: Research, awaiting user decision

---

## Candidates

### 1. LibreTranslate (HTTP API)

**Описание:** Open-source self-hosted OR публичный инстанс. REST API: `POST /translate`.

**Плюсы:**
- ✅ Бесплатно (если self-hosted) или условно-бесплатно (публичный)
- ✅ Приватно (если self-hosted) — текст не уходит в облако
- ✅ MIT license
- ✅ Много языков (ru, en, de, fr, es, zh, ...)
- ✅ Простой API: `{"q": "Привет", "source": "ru", "target": "en"}` → `{"translatedText": "Hello"}`

**Минусы:**
- ❌ Публичный инстанс `libretranslate.com` rate-limited (~10 req/min free)
- ❌ Self-hosted требует Docker + ~2GB RAM + 5 мин setup
- ❌ Качество среднее (Argos Translate под капотом)
- ❌ Медленно на длинных текстах (5-10 сек на 1KB)

**Public instances:**
- `https://libretranslate.com/` (rate-limited)
- `https://translate.argosopentech.com/`
- `https://libretranslate.pussthecat.org/`

**Decision fit:** v1.5 ✅ (как default + fallback на MiniMax)

---

### 2. MiniMax API (OpenAI-compatible)

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

### 3. NLLB-200 (Local, ONNX)

**Описание:** Meta's No Language Left Behind, distilled 600M variant. Open-source, ONNX export доступен.

**Плюсы:**
- ✅ Полностью локально
- ✅ 200 языков
- ✅ Хорошее качество
- ✅ Privacy-perfect

**Минусы:**
- ❌ ~600MB model size (тяжело)
- ❌ ONNX runtime + tokenizer setup
- ❌ Первый запуск медленный (загрузка модели)
- ❌ Требует CPU с AVX2 или любой GPU (DirectML)

**Decision fit:** v1.5 ❌ (слишком heavy для default), возможно v2 как opt-in для "я хочу всё локально"

---

### 4. Whisper-style inline (не подходит)

Whisper сам по себе НЕ переводит, только транскрибирует. Можно использовать для English transcription напрямую (если source = en, no translation needed).

**Decision fit:** N/A

---

## Comparison matrix

| Provider | Cost | Privacy | Quality | Speed | Setup | v1.5? |
|----------|------|---------|---------|-------|-------|-------|
| LibreTranslate public | Free (rate-limited) | Cloud | Medium | Slow | None | ✅ fallback |
| LibreTranslate self-hosted | Free (CPU/RAM) | Local | Medium | Medium | 5 min | ✅ opt-in |
| MiniMax API | ~$0.001/transcript | Cloud | High | Fast | API key | ✅ default |
| NLLB-200 local | Free (disk+RAM) | Local | High | Slow first, then fast | 600MB DL | ❌ v2 |

---

## Recommended config

```jsonc
{
  "translate_to_en": false,                  // opt-in
  "translation_provider": "minimax",         // default (быстрый, качественный)
  "translation_fallback": "libretranslate",  // если MiniMax quota exceeded
  "libretranslate_url": "",                  // пустой = public; заполнить если self-hosted
  "minimax_api_key": ""                      // из auth.json
}
```

**UX:**
- В настройках чекбокс «Автоматически переводить на английский»
- Под чекбоксом: select с провайдерами (Minimax / LibreTranslate)
- Ссылка "проверить доступ" — вызывает тестовый перевод короткой фразы

**Fallback chain:**
1. MiniMax (если есть key + не quota exceeded)
2. LibreTranslate (если URL или public)
3. NLLB-200 local (если opt-in)
4. None — перевод пропускается, warning в логе

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
