from fastapi import Depends

from app.core.config import Settings, get_settings
from app.extractors.page_extractor import PageExtractor
from app.providers.playwright_provider import PlaywrightSearchProvider
from app.services.research_service import ResearchService


def get_research_service(settings: Settings = Depends(get_settings)) -> ResearchService:
    provider = PlaywrightSearchProvider(settings)
    extractor = PageExtractor(settings)
    return ResearchService(provider, extractor, settings)
