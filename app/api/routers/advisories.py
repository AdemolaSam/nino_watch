from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AdvisoryResponse
from app.core.db import get_session
from app.repos import advisories as advisories_repo
from app.repos import regions as regions_repo

router = APIRouter()


@router.get("/advisories/{region_id}", response_model=AdvisoryResponse)
async def get_advisory(
    region_id: str, lang: str = "en", session: AsyncSession = Depends(get_session)
) -> AdvisoryResponse:
    if await regions_repo.get_region(session, region_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown region {region_id!r}")
    english = await advisories_repo.latest_english(session, region_id)
    if english is None:
        raise HTTPException(status_code=503, detail="advisory not generated yet")
    source = {
        "happening": english.happening,
        "atRisk": english.at_risk,
        "actions": english.actions,
    }
    if lang != "en":
        translation = await advisories_repo.get_translation(
            session, region_id, lang, english.version
        )
        if translation is not None:
            return AdvisoryResponse(
                region_id=region_id,
                lang=lang,
                available=True,
                happening=translation.happening,
                at_risk=translation.at_risk,
                actions=translation.actions,
                review_status="reviewed" if translation.reviewed else "machine_preview",
                source_english=source,
            )
    available = lang == "en"
    return AdvisoryResponse(
        region_id=region_id,
        lang=lang,
        available=available,
        happening=english.happening,
        at_risk=english.at_risk,
        actions=english.actions,
        review_status="source" if lang == "en" else "unavailable",
        source_english=source,
    )
