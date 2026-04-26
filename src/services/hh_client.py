"""hh.ru API client with OAuth client_credentials auth, retry and rate limiting."""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import settings

logger = logging.getLogger("hh-auto.hh_client")

BASE_URL = "https://api.hh.ru"
USER_AGENT = "hh-auto/1.0 (djigolo@gmail.com)"
TOKEN_FILE = Path("/app/data/hh_oauth_token.json")

# Rate limiter: max 5 requests per second
_semaphore = asyncio.Semaphore(5)
_last_request_time = 0.0
_MIN_INTERVAL = 0.25  # 250ms between requests

# Shared OAuth token (client_credentials, no expiry in response)
_access_token: str | None = None


@dataclass
class VacancyShort:
    hh_id: str
    title: str
    company_name: str | None
    company_id: str | None
    salary_from: int | None
    salary_to: int | None
    salary_currency: str | None
    salary_gross: bool | None
    area_name: str | None
    experience: str | None
    employment: str | None
    schedule: str | None
    url: str
    response_letter_required: bool
    published_at: str | None
    employer_logo_url: str | None
    key_skills: list[str] | None
    snippet_requirement: str | None
    snippet_responsibility: str | None


@dataclass
class VacancyFull(VacancyShort):
    description: str | None = None
    key_skills_full: list[dict] | None = None
    archived: bool = False


class HHApiError(Exception):
    def __init__(self, status_code: int, message: str, response_data: dict | None = None):
        self.status_code = status_code
        self.response_data = response_data or {}
        super().__init__(f"HH API error {status_code}: {message}")

    @property
    def is_rate_limited(self) -> bool:
        return self.status_code == 429


class HHClient:
    """Async HTTP client for hh.ru API with OAuth client_credentials auth."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _ensure_token(self) -> str:
        """Get or fetch OAuth access_token via client_credentials flow."""
        global _access_token
        if _access_token:
            return _access_token

        # Try loading persisted token from disk
        if TOKEN_FILE.exists():
            try:
                data = json.loads(TOKEN_FILE.read_text())
                token = data.get("access_token", "")
                if token:
                    _access_token = token
                    logger.info("HH OAuth token loaded from disk")
                    return token
            except Exception:
                pass

        if not settings.hh_client_id or not settings.hh_client_secret:
            logger.warning("No HH OAuth credentials configured, requests will be anonymous")
            return ""

        async with httpx.AsyncClient(timeout=15.0) as c:
            resp = await c.post(
                f"{BASE_URL}/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.hh_client_id,
                    "client_secret": settings.hh_client_secret,
                },
            )
            if resp.status_code == 200:
                token = resp.json().get("access_token", "")
                _access_token = token
                # Persist to disk so it survives container restarts
                TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
                TOKEN_FILE.write_text(json.dumps({"access_token": token}))
                logger.info("HH OAuth token obtained and persisted")
                return token
            else:
                logger.error(f"Failed to get HH OAuth token: {resp.status_code} {resp.text[:200]}")
                return ""

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            token = await self._ensure_token()
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=30.0,
                headers=headers,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _throttled_request(
        self, method: str, url: str, **kwargs
    ) -> httpx.Response:
        global _last_request_time, _access_token

        async with _semaphore:
            now = asyncio.get_event_loop().time()
            wait_time = _MIN_INTERVAL - (now - _last_request_time)
            if wait_time > 0:
                await asyncio.sleep(wait_time)

            client = await self._get_client()
            response = await client.request(method, url, **kwargs)
            _last_request_time = asyncio.get_event_loop().time()

            # If 403 with auth — token may be invalid, refresh once
            if response.status_code == 403 and _access_token:
                logger.warning("HH API 403, refreshing OAuth token")
                _access_token = None
                if TOKEN_FILE.exists():
                    TOKEN_FILE.unlink()
                await self.close()
                client = await self._get_client()
                response = await client.request(method, url, **kwargs)
                _last_request_time = asyncio.get_event_loop().time()

            if response.status_code >= 400:
                try:
                    data = response.json()
                except Exception:
                    data = {}
                raise HHApiError(response.status_code, response.text[:200], data)

            return response

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def _get(self, url: str, params: dict | None = None) -> dict:
        resp = await self._throttled_request("GET", url, params=params)
        return resp.json()

    # --- Vacancy Search (public, no auth) ---

    async def search_vacancies(
        self,
        text: str | None = None,
        area: int | None = None,
        experience: str | None = None,
        employment: str | None = None,
        schedule: str | None = None,
        salary: int | None = None,
        only_with_salary: bool = False,
        professional_role: list[int] | None = None,
        search_field: str | None = None,
        order_by: str = "publication_time",
        page: int = 0,
        per_page: int = 100,
    ) -> tuple[list[VacancyShort], int]:
        """Search vacancies. Returns (vacancies, total_found)."""
        params = {"page": page, "per_page": per_page, "order_by": order_by}
        if text:
            params["text"] = text
        if area:
            params["area"] = area
        if experience:
            params["experience"] = experience
        if employment:
            params["employment"] = employment
        if schedule:
            params["schedule"] = schedule
        if salary:
            params["salary"] = salary
        if only_with_salary:
            params["only_with_salary"] = "true"
        if professional_role:
            params["professional_role"] = professional_role
        if search_field:
            params["search_field"] = search_field

        data = await self._get("/vacancies", params=params)
        vacancies = [self._parse_vacancy_short(item) for item in data.get("items", [])]
        total = data.get("found", 0)
        logger.info(f"Search returned {len(vacancies)} vacancies (total: {total})")
        return vacancies, total

    async def search_all_pages(
        self, max_pages: int = 5, **search_kwargs
    ) -> list[VacancyShort]:
        """Search vacancies across multiple pages."""
        all_vacancies = []
        for page in range(max_pages):
            vacancies, total = await self.search_vacancies(page=page, **search_kwargs)
            all_vacancies.extend(vacancies)
            if len(all_vacancies) >= total or not vacancies:
                break
        return all_vacancies

    async def get_similar_vacancies(
        self, vacancy_id: str, per_page: int = 20
    ) -> list[VacancyShort]:
        """Get vacancies similar to the given one (hh.ru "Вам подойдут эти вакансии").

        Uses /vacancies/{id}/similar_vacancies endpoint.
        """
        data = await self._get(
            f"/vacancies/{vacancy_id}/similar_vacancies",
            params={"per_page": per_page},
        )
        return [self._parse_vacancy_short(item) for item in data.get("items", [])]

    async def get_vacancy(self, vacancy_id: str) -> VacancyFull:
        """Get full vacancy details including description."""
        data = await self._get(f"/vacancies/{vacancy_id}")
        return self._parse_vacancy_full(data)

    # --- Parsers ---

    @staticmethod
    def _parse_vacancy_short(item: dict) -> VacancyShort:
        salary = item.get("salary") or {}
        employer = item.get("employer") or {}
        area = item.get("area") or {}
        experience = item.get("experience") or {}
        employment = item.get("employment") or {}
        schedule = item.get("schedule") or {}
        snippet = item.get("snippet") or {}
        logo_urls = employer.get("logo_urls") or {}

        return VacancyShort(
            hh_id=str(item["id"]),
            title=item.get("name", ""),
            company_name=employer.get("name"),
            company_id=str(employer["id"]) if employer.get("id") else None,
            salary_from=salary.get("from"),
            salary_to=salary.get("to"),
            salary_currency=salary.get("currency"),
            salary_gross=salary.get("gross"),
            area_name=area.get("name"),
            experience=experience.get("id"),
            employment=employment.get("id"),
            schedule=schedule.get("id"),
            url=item.get("alternate_url", ""),
            response_letter_required=item.get("response_letter_required", False),
            published_at=item.get("published_at"),
            employer_logo_url=logo_urls.get("90"),
            key_skills=[s["name"] for s in item.get("key_skills", [])],
            snippet_requirement=snippet.get("requirement"),
            snippet_responsibility=snippet.get("responsibility"),
        )

    @staticmethod
    def _parse_vacancy_full(item: dict) -> VacancyFull:
        salary = item.get("salary") or {}
        employer = item.get("employer") or {}
        area = item.get("area") or {}
        experience = item.get("experience") or {}
        employment = item.get("employment") or {}
        schedule = item.get("schedule") or {}
        snippet = item.get("snippet") or {}
        logo_urls = employer.get("logo_urls") or {}

        return VacancyFull(
            hh_id=str(item["id"]),
            title=item.get("name", ""),
            company_name=employer.get("name"),
            company_id=str(employer["id"]) if employer.get("id") else None,
            salary_from=salary.get("from"),
            salary_to=salary.get("to"),
            salary_currency=salary.get("currency"),
            salary_gross=salary.get("gross"),
            area_name=area.get("name"),
            experience=experience.get("id"),
            employment=employment.get("id"),
            schedule=schedule.get("id"),
            url=item.get("alternate_url", ""),
            response_letter_required=item.get("response_letter_required", False),
            published_at=item.get("published_at"),
            employer_logo_url=logo_urls.get("90"),
            key_skills=[s["name"] for s in item.get("key_skills", [])],
            snippet_requirement=snippet.get("requirement"),
            snippet_responsibility=snippet.get("responsibility"),
            description=item.get("description"),
            key_skills_full=item.get("key_skills"),
            archived=item.get("archived", False),
        )
