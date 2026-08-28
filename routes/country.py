from fastapi import APIRouter, Response

from core.http import serve
from services.country_service import CountriesService

router = APIRouter(prefix="/countries", tags=["Countries"])


@router.get("/")
def get_countries():
    return CountriesService.get_countries()


@router.get("/{country_name}")
def get_country_info(country_name: str, response: Response):
    return serve(CountriesService.get_country_info(country_name), response)
