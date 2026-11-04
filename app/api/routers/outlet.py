from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import OutletPackResponse
from app.core.db import get_session
from app.repos import advisories as advisories_repo
from app.repos import outlet_packs as outlet_packs_repo
from app.repos import regions as regions_repo
from app.services.advisory import is_tested

router = APIRouter()


@router.get("/outlet-packs/{region_id}", response_model=OutletPackResponse)
async def get_outlet_pack(
    region_id: str, lang: str = "en", session: AsyncSession = Depends(get_session)
) -> OutletPackResponse:
    if await regions_repo.get_region(session, region_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown region {region_id!r}")
    english = await advisories_repo.latest_english(session, region_id)
    if english is None:
        raise HTTPException(status_code=503, detail="advisory not generated yet")
    english_pack = await outlet_packs_repo.get_by_advisory(session, english.id)
    if lang != "en" and is_tested(lang):
        translation = await advisories_repo.get_translation(
            session, region_id, lang, english.version
        )
        if translation is not None:
            pack = await outlet_packs_repo.get_by_advisory(session, translation.id)
            if pack is not None:
                return OutletPackResponse(
                    region_id=region_id,
                    lang=lang,
                    available=True,
                    radio_script=pack.radio_script,
                    sms=pack.sms,
                )
    if english_pack is None:
        raise HTTPException(status_code=503, detail="broadcaster pack not generated yet")
    return OutletPackResponse(
        region_id=region_id,
        lang=lang,
        available=lang == "en",
        radio_script=english_pack.radio_script,
        sms=english_pack.sms,
    )
