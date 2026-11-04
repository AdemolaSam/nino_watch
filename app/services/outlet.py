"""Broadcaster packs: validated radio script + SMS per advisory and language.

The artifacts stay clean for air: machine-translation labeling and the
"review before broadcast" note are frontend display concerns (the response
contract carries no metadata fields, and notes inside the script would be
read on air or sent to phones).
"""

import json
import logging

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.outlet import validate_radio_script, validate_sms
from app.domain.sms import sms_segments
from app.llm.client import LlmError, complete_json
from app.llm.prompts import PROMPT_VERSIONS, load_prompt
from app.llm.schemas import LlmParseError, RadioScript, SmsText
from app.repos import advisories as advisories_repo
from app.repos import outlet_packs as outlet_packs_repo
from app.repos import regions as regions_repo
from app.repos.models import Advisory, OutletPack
from app.services.advisory import is_tested

logger = logging.getLogger("ninowatch.outlet")


def advisory_user(advisory: Advisory) -> str:
    return "Advisory JSON:\n" + json.dumps(
        {
            "happening": advisory.happening,
            "atRisk": advisory.at_risk,
            "actions": advisory.actions,
        },
        ensure_ascii=False,
    )


async def _generate_validated(
    system: str,
    user: str,
    model_cls: type[BaseModel],
    field: str,
    validator,
    prompt_version: str,
) -> str | None:
    try:
        first = await complete_json(
            "outlet", system, user, model_cls,
            prompt_version=prompt_version, effort="low", max_tokens=4000,
        )
    except (LlmError, LlmParseError) as e:
        logger.warning("outlet generation failed (%s)", e)
        return None
    text = getattr(first, field)
    if not validator(text):
        return text
    retry_user = (
        f"{user}\n\nYour previous reply failed validation:\n"
        + "\n".join(f"- {err}" for err in validator(text))
        + "\nFix every issue and reply with corrected JSON only."
    )
    try:
        second = await complete_json(
            "outlet", system, retry_user, model_cls,
            prompt_version=prompt_version, effort="low", max_tokens=4000,
        )
    except (LlmError, LlmParseError) as e:
        logger.warning("outlet retry failed (%s)", e)
        return None
    text = getattr(second, field)
    errors = validator(text)
    if errors:
        logger.warning("outlet retry still invalid: %s", errors)
        return None
    return text


async def generate_pack(session: AsyncSession, advisory_id: int) -> OutletPack | None:
    existing = await outlet_packs_repo.get_by_advisory(session, advisory_id)
    if existing is not None:
        return existing
    advisory = await session.get(Advisory, advisory_id)
    if advisory is None:
        return None
    user = advisory_user(advisory)
    radio = await _generate_validated(
        load_prompt("outlet_radio"), user, RadioScript, "script",
        validate_radio_script, PROMPT_VERSIONS["outlet_radio"],
    )
    sms = await _generate_validated(
        load_prompt("outlet_sms"), user, SmsText, "sms",
        validate_sms, PROMPT_VERSIONS["outlet_sms"],
    )
    if radio is None or sms is None:
        return None
    return await outlet_packs_repo.create_pack(
        session,
        advisory_id=advisory.id,
        lang=advisory.lang,
        radio_script=radio,
        sms=sms,
        sms_segments=sms_segments(sms),
    )


async def packable_advisory(
    session: AsyncSession, region_id: str, lang: str
) -> Advisory | None:
    """Latest English advisory, or the current translation when tested."""
    english = await advisories_repo.latest_english(session, region_id)
    if english is None or lang == "en":
        return english
    if not is_tested(lang):
        return None
    return await advisories_repo.get_translation(session, region_id, lang, english.version)


async def generate_region_packs(session: AsyncSession, region_id: str) -> dict[str, int]:
    counts = {"packed": 0, "failed": 0}
    region = await regions_repo.get_region(session, region_id)
    codes = ((region.config or {}).get("languages", ["en"]) if region else ["en"])
    for code in codes:
        advisory = await packable_advisory(session, region_id, code)
        if advisory is None:
            continue
        try:
            pack = await generate_pack(session, advisory.id)
        except Exception as e:
            logger.warning("pack failed for %s/%s (%s)", region_id, code, e)
            counts["failed"] += 1
            continue
        counts["packed" if pack else "failed"] += 1
    return counts
