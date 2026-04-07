
import json
import os
import io
import zipfile
import re
import httpx
from typing import Optional

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o-mini"  


def _build_system_prompt(has_reference: bool) -> str:
    ref_block = ""
    if has_reference:
        ref_block = """
ЭТАЛОННОЕ РЕШЕНИЕ:
- Учитель предоставил эталонное решение — сравни работу студента с ним по смыслу и полноте.
- Не требуй дословного совпадения — важно смысловое соответствие и понимание темы.
- Укажи конкретно: что совпадает с эталоном, что упущено или раскрыто недостаточно.
"""
    return f"""Ты — объективный и справедливый преподаватель. Твоя задача — оценить работу студента строго по заданным критериям, без предвзятости в любую сторону.
{ref_block}
ПРАВИЛА ОЦЕНИВАНИЯ:
1. Оценивай ТОЛЬКО то, что реально написано в работе — не додумывай и не домысливай за студента
2. Каждый критерий оценивай пропорционально тому, насколько он раскрыт: полно → полный балл, частично → часть балла, не раскрыт → 0
3. Если студент прикрепил файл — его содержимое учитывается наравне с текстом
4. Если работа пустая или не по теме — ставь 0, это честно
5. Если файл не удалось прочитать — выставь 50% и укажи причину в фидбеке
6. Пиши комментарии на русском: конкретно, по существу, без эмоций — что сделано правильно и что именно не так

ВАЖНО: отвечай ТОЛЬКО валидным JSON без каких-либо пояснений вне JSON.

Формат ответа:
{{
  "score": <итоговый балл — целое число от 0 до max_score>,
  "feedback": "<общий комментарий на русском, 2-4 предложения, конкретно о работе>",
  "criteria_scores": [
    {{
      "name": "<название критерия>",
      "score": <балл за этот критерий — целое число>,
      "max": <максимум за критерий>,
      "comment": "<конкретный комментарий по данному критерию>"
    }}
  ]
}}"""


def _build_user_prompt(
    text: str,
    criteria: list,
    max_score: int,
    has_file: bool,
    reference_text: Optional[str] = None,
) -> str:
    criteria_text = "\n".join(
        f"- {c['name']} (вес: {c['weight']} баллов)"
        + (f": {c['description']}" if c.get("description") else "")
        for c in criteria
    )

    file_note = ""
    if has_file:
        file_note = "\n[ПРИМЕЧАНИЕ: Студент также прикрепил файл. Содержимое файла включено выше если удалось прочитать.]"

    ref_block = ""
    if reference_text:
        ref_block = f"""
ЭТАЛОННОЕ РЕШЕНИЕ (предоставлено учителем):
\"\"\"
{reference_text[:8000]}
\"\"\"

"""

    return f"""Оцени работу студента по критериям ниже. Оценивай объективно — ровно настолько, насколько критерий реально раскрыт.

КРИТЕРИИ ОЦЕНКИ (максимальный балл = {max_score}):
{criteria_text}
{ref_block}
РАБОТА СТУДЕНТА:
\"\"\"\n{text}
\"\"\"{file_note}

ИНСТРУКЦИИ:
- Оцени каждый критерий строго по содержанию: полное раскрытие = полный балл, частичное = пропорциональный балл, отсутствие = 0
{'- Сравни с эталонным решением: укажи что совпадает и что упущено' if reference_text else ''}
- Сумма баллов по критериям должна точно равняться итоговому score
- Итоговый score не может превышать {max_score}
- Комментарий: конкретно что сделано верно и что именно не так (без общих фраз)

Верни ТОЛЬКО JSON без лишних слов."""


async def _fetch_file_text(url: str) -> str:
    """Downloads a file and returns its text content.
    Supports: PDF, DOCX, DOC, PPTX, XLSX, XLS, TXT, MD, CSV, RTF.
    """
    if not url or not url.startswith("http"):
        return ""
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(url)
            if not resp.is_success:
                return ""

            raw_ext = url.split("?")[0].rsplit(".", 1)
            ext = raw_ext[-1].lower() if len(raw_ext) > 1 else ""
            content_type = resp.headers.get("content-type", "").lower()

            # ── PDF ──────────────────────────────────────────────────────────
            if ext == "pdf" or "pdf" in content_type:
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(resp.content))
                    pages = []
                    for page in reader.pages[:40]:
                        txt = page.extract_text() or ""
                        if txt.strip():
                            pages.append(txt)
                    text = "\n\n".join(pages)
                    return text[:20000] if text.strip() else ""
                except Exception as e:
                    return f"[PDF — не удалось извлечь текст: {e}]"

            # ── DOCX / PPTX / XLSX (ZIP-based Office) ────────────────────────
            elif ext in ("docx", "pptx", "xlsx"):
                try:
                    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                        texts = []
                        for name in z.namelist():
                            if not name.endswith(".xml"):
                                continue
                            if not any(p in name for p in ("word/", "ppt/slides/", "xl/worksheets/")):
                                continue
                            try:
                                xml = z.read(name).decode("utf-8", errors="ignore")
                                found = re.findall(
                                    r"<(?:w:t|a:t|t)[^>]*>([^<]+)</(?:w:t|a:t|t)>", xml
                                )
                                if found:
                                    texts.append(" ".join(found))
                            except Exception:
                                pass
                    result = " ".join(texts).replace("  ", " ")
                    return result[:20000] if result.strip() else ""
                except Exception as e:
                    return f"[Office файл — не удалось прочитать: {e}]"

            # ── Plain text / Markdown / CSV ───────────────────────────────────
            elif ext in ("txt", "md", "csv", "tsv", "log", "json", "xml", "yaml", "yml"):
                return resp.content.decode("utf-8", errors="ignore")[:20000]

            # ── Images — no text available ────────────────────────────────────
            elif ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"):
                return "[Изображение — текстовое содержимое недоступно]"

            # ── Fallback: try UTF-8 decode ────────────────────────────────────
            else:
                try:
                    decoded = resp.content.decode("utf-8", errors="ignore")
                    if decoded.strip():
                        return decoded[:15000]
                    return ""
                except Exception:
                    return ""

    except Exception:
        return ""


async def grade_submission(
    text: str,
    criteria: list,
    max_score: int = 100,
    file_url: Optional[str] = None,
    reference_solution_url: Optional[str] = None,
    reference_solution_urls: Optional[list] = None,
) -> dict:
    """
    Grades a student submission using OpenAI GPT.
    Returns: {"score": int, "feedback": str, "criteria_scores": [...], "_usage": {...}}
    reference_solution_urls: list of multiple reference file URLs (new multi-file support)
    reference_solution_url: single URL (legacy, still supported)
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Please add it to your .env file: OPENAI_API_KEY=sk-..."
        )

    # ── Build student submission text ─────────────────────────────────────────
    full_text = (text or "").strip()
    has_file = False

    if file_url:
        has_file = True
        file_content = await _fetch_file_text(file_url)
        if file_content.strip():
            if full_text:
                full_text = f"ТЕКСТОВЫЙ ОТВЕТ:\n{full_text}\n\nСОДЕРЖИМОЕ ФАЙЛА:\n{file_content}"
            else:
                full_text = f"СОДЕРЖИМОЕ ФАЙЛА:\n{file_content}"
        elif full_text:
            full_text = f"{full_text}\n\n[Файл прикреплён но не удалось прочитать: {file_url}]"
        else:
            full_text = f"[Студент сдал только файл: {file_url}, но прочитать его не удалось]"

    if not full_text:
        full_text = "[Студент не предоставил ответа]"

    # ── Read reference solution(s) ────────────────────────────────────────────
    reference_text: Optional[str] = None

    # Collect all reference URLs (new multi-file + legacy single)
    all_ref_urls: list = []
    if reference_solution_urls:
        all_ref_urls.extend(reference_solution_urls)
    if reference_solution_url and reference_solution_url not in all_ref_urls:
        all_ref_urls.append(reference_solution_url)

    if all_ref_urls:
        ref_parts = []
        for idx, ref_url in enumerate(all_ref_urls):
            ref_content = await _fetch_file_text(ref_url)
            if ref_content.strip():
                label = f"ЭТАЛОННЫЙ ФАЙЛ {idx+1}" if len(all_ref_urls) > 1 else "ЭТАЛОННОЕ РЕШЕНИЕ"
                ref_parts.append(f"{label}:\n{ref_content[:8000]}")
        if ref_parts:
            reference_text = "\n\n".join(ref_parts)

    # ── Build OpenAI request ──────────────────────────────────────────────────
    has_reference = reference_text is not None
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": _build_system_prompt(has_reference)},
            {"role": "user", "content": _build_user_prompt(
                full_text, criteria, max_score, has_file, reference_text
            )},
        ],
        "max_tokens": 1800,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            OPENAI_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json=payload,
        )

    if not resp.is_success:
        try:
            err = resp.json()
            msg = err.get("error", {}).get("message", f"OpenAI error {resp.status_code}")
        except Exception:
            msg = f"OpenAI error {resp.status_code}"
        raise RuntimeError(msg)

    raw = resp.json()["choices"][0]["message"]["content"].strip()

    # Strip markdown code blocks if present
    if raw.startswith("```"):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
    raw = raw.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
            except Exception:
                raise RuntimeError(f"ИИ вернул невалидный JSON: {e}\nОтвет: {raw[:400]}")
        else:
            raise RuntimeError(f"ИИ вернул невалидный JSON: {e}\nОтвет: {raw[:400]}")

    result["score"] = max(0, min(int(result.get("score", 0)), max_score))
    if not isinstance(result.get("criteria_scores"), list):
        result["criteria_scores"] = []

    # Attach usage info for caller to log
    usage = resp.json().get("usage", {})
    result["_usage"] = usage

    return result


# ── Cached document fetch (uses ProcessedDocument JSON if available) ───────────

def get_cached_text_for_url(file_url: str, db) -> str:
    """
    Если для данного URL уже есть ProcessedDocument в БД — возвращаем
    full_text из кэша (без повторного скачивания и парсинга).
    Иначе возвращает пустую строку (вызывающий код сам скачает файл).
    """
    try:
        from models import ProcessedDocument
        # Ищем по имени файла в URL
        filename = file_url.rstrip("/").split("/")[-1].split("?")[0]
        proc = db.query(ProcessedDocument).filter(
            ProcessedDocument.filename == filename
        ).order_by(ProcessedDocument.id.desc()).first()
        if proc:
            import json as _json
            doc = _json.loads(proc.content_json)
            return doc.get("full_text", "")[:20000]
    except Exception:
        pass
    return ""
