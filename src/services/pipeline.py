"""Main pipeline: search → score → generate cover letters → apply (hybrid API + browser)."""

import logging
from datetime import datetime, date
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.vacancy import Vacancy
from src.models.cover_letter import CoverLetter
from src.models.application import Application
from src.models.search_profile import SearchProfile
from src.models.resume import Resume
from src.models.company_rule import CompanyRule
from src.models.event_log import EventLog
from src.services.hh_client import HHClient, VacancyShort, HHApiError
from src.services.hh_browser import HHBrowser
from src.services.vacancy_scorer import fast_score, ai_score
from src.services.cover_letter_generator import generate_cover_letter
from src.services.resume_matcher import match_resume
from src.services.telegram_bot import notifier
from src.config import settings

logger = logging.getLogger("hh-auto.pipeline")

RESUME_TEXT_PATH = Path("/app/data/resume_avanov_2026.md")


def _load_resume_text() -> str:
    if RESUME_TEXT_PATH.exists():
        return RESUME_TEXT_PATH.read_text(encoding="utf-8")
    # Fallback: try workspace path
    alt = Path("/workspace/hh-auto/data/resume_avanov_2026.md")
    if alt.exists():
        return alt.read_text(encoding="utf-8")
    logger.warning("Resume text file not found")
    return ""


class Pipeline:
    def __init__(self, db: AsyncSession, hh_client: HHClient, hh_browser: HHBrowser):
        self.db = db
        self.hh = hh_client
        self.browser = hh_browser
        self._resume_text: str | None = None

    @property
    def resume_text(self) -> str:
        if self._resume_text is None:
            self._resume_text = _load_resume_text()
        return self._resume_text

    async def _log_event(
        self, event_type: str, details: dict | None = None,
        vacancy_id: int | None = None, error: str | None = None,
    ):
        self.db.add(EventLog(
            event_type=event_type,
            details=details,
            vacancy_id=vacancy_id,
            error_message=error,
        ))
        await self.db.flush()

    # --- Search Cycle (public API) ---

    async def run_search_cycle(self):
        """Find new vacancies, score them, generate cover letters."""
        logger.info("Starting search cycle")
        profiles = await self._get_active_profiles()

        if not profiles:
            logger.warning("No active search profiles")
            return

        total_new = 0
        total_scored = 0
        total_letters = 0

        for profile in profiles:
            try:
                new, scored, letters = await self._process_profile(profile)
                total_new += new
                total_scored += scored
                total_letters += letters
            except Exception as e:
                logger.error(f"Error processing profile '{profile.name}': {e}")
                await self._log_event(
                    "search_error",
                    {"profile_id": profile.id, "profile_name": profile.name},
                    error=str(e),
                )

        await self._log_event("search_cycle_complete", {
            "profiles": len(profiles),
            "new_vacancies": total_new,
            "scored": total_scored,
            "letters_generated": total_letters,
        })
        await self.db.commit()
        logger.info(
            f"Search cycle complete: {total_new} new, {total_scored} scored, "
            f"{total_letters} letters generated"
        )

        # Telegram notification
        if notifier.is_configured and total_letters > 0:
            pending = (await self.db.execute(
                select(func.count(CoverLetter.id)).where(CoverLetter.status == "pending")
            )).scalar_one()
            await notifier.notify_search_complete(total_new, total_letters, pending)

    async def _process_profile(self, profile: SearchProfile) -> tuple[int, int, int]:
        """Process a single search profile. Returns (new, scored, letters)."""
        # Search via public API
        vacancies = await self.hh.search_all_pages(
            max_pages=3,
            text=profile.search_text,
            area=profile.area_id,
            experience=profile.experience,
            employment=profile.employment,
            schedule=profile.schedule,
            salary=profile.salary_from,
            only_with_salary=profile.only_with_salary,
            order_by=profile.order_by,
        )

        # Deduplicate
        new_vacancies = await self._filter_known(vacancies)
        if not new_vacancies:
            logger.info(f"Profile '{profile.name}': no new vacancies")
            return 0, 0, 0

        # Apply company rules
        filtered = await self._apply_company_rules(new_vacancies)

        scored_count = 0
        letters_count = 0

        for v in filtered:
            # Fast score
            fast_sc, fast_reason = fast_score(
                title=v.title,
                company_name=v.company_name,
                description_snippet=v.snippet_requirement,
                key_skills=v.key_skills,
                experience=v.experience,
                schedule=v.schedule,
                area_name=v.area_name,
            )

            if fast_sc < 0.3:
                # Save but mark as skipped
                await self._save_vacancy(v, fast_sc, fast_reason, "skipped", profile.id)
                continue

            # Fetch full description via public API
            try:
                full = await self.hh.get_vacancy(v.hh_id)
            except HHApiError as e:
                logger.warning(f"Failed to fetch vacancy {v.hh_id}: {e}")
                continue

            # AI score
            ai_result = await ai_score(
                title=full.title,
                company_name=full.company_name,
                description=full.description,
                key_skills=full.key_skills,
                resume_text=self.resume_text,
            )
            scored_count += 1

            # Match best resume for this vacancy
            resume_match = await match_resume(
                self.db,
                vacancy_title=full.title,
                vacancy_skills=full.key_skills,
                vacancy_description=full.description,
            )

            db_vacancy = await self._save_vacancy(
                v, ai_result.score, ai_result.reasoning, "scored", profile.id,
                description=full.description,
                matched_skills=ai_result.matched_skills,
                missing_skills=ai_result.missing_skills,
            )
            db_vacancy.recommended_resume_id = resume_match.resume_hh_id or None

            # Generate cover letter only for high-scoring vacancies
            # Lower-scoring ones (between min_relevance_score and auto_generate_score)
            # are saved as "scored" and can have letters generated manually via UI
            if ai_result.score >= settings.auto_generate_score:
                resume_id_for_letter = resume_match.resume_hh_id or profile.resume_id or ""
                try:
                    draft = await generate_cover_letter(
                        title=full.title,
                        company_name=full.company_name,
                        description=full.description,
                        key_skills=full.key_skills,
                        resume_text=self.resume_text,
                        scoring=ai_result,
                    )
                    self.db.add(CoverLetter(
                        vacancy_id=db_vacancy.id,
                        resume_id=resume_id_for_letter,
                        generated_text=draft.text,
                        generation_prompt=draft.prompt_used[:5000],
                        model_used=draft.model,
                        status="pending",
                    ))
                    db_vacancy.status = "queued"
                    letters_count += 1
                    await self.db.flush()

                    # Notify about new match
                    if notifier.is_configured:
                        await notifier.notify_new_match(
                            vacancy_title=full.title,
                            company_name=full.company_name,
                            score=ai_result.score,
                            vacancy_url=v.url,
                            letter_preview=draft.text,
                        )
                except Exception as e:
                    logger.error(f"Cover letter generation failed for {v.hh_id}: {e}")

        return len(new_vacancies), scored_count, letters_count

    # --- Apply Cycle (browser) ---

    async def run_apply_cycle(self):
        """Send approved cover letters as applications via browser."""
        logger.info("Starting apply cycle")

        # Verify browser is actually logged in before attempting applies
        if not await self.browser.verify_auth():
            logger.warning("Browser session expired, attempting re-login")
            if not settings.hh_email or not settings.hh_password:
                logger.error("Cannot apply: no hh.ru credentials configured")
                await self._log_event("apply_cycle_skipped", {"reason": "no_credentials"})
                return
            login_ok = await self.browser.login(settings.hh_email, settings.hh_password)
            if not login_ok:
                logger.error("Cannot apply: browser login failed")
                await self._log_event("apply_cycle_skipped", {"reason": "login_failed"})
                return
            logger.info("Re-authenticated successfully")

        daily_count = await self._get_today_application_count()
        if daily_count >= settings.max_applications_per_day:
            logger.info(f"Daily limit reached ({daily_count}/{settings.max_applications_per_day})")
            return

        approved = await self._get_approved_letters()
        sent = 0

        import asyncio

        for i, letter in enumerate(approved):
            if daily_count + sent >= settings.max_applications_per_day:
                logger.info("Daily limit reached during apply cycle")
                break

            # Delay between applications to avoid detection and ensure proper page loads
            if i > 0:
                await asyncio.sleep(10)

            vacancy = letter.vacancy
            message = "" if letter.status == "no_letter" else (letter.edited_text or letter.generated_text)

            # Look up resume title for better popup matching
            resume_title = ""
            if letter.resume_id:
                resume_result = await self.db.execute(
                    select(Resume.title).where(Resume.hh_id == letter.resume_id)
                )
                row = resume_result.first()
                if row:
                    resume_title = row[0]

            try:
                success = await self.browser.apply_to_vacancy(
                    vacancy_url=vacancy.url,
                    message=message,
                    resume_id=letter.resume_id,
                    resume_title=resume_title,
                )

                if success:
                    self.db.add(Application(
                        vacancy_id=vacancy.id,
                        cover_letter_id=letter.id,
                        resume_id=letter.resume_id,
                        status="sent",
                        applied_via="browser",
                    ))
                    letter.status = "sent"
                    letter.sent_at = datetime.utcnow()
                    vacancy.status = "applied"
                    sent += 1
                    await self.db.flush()

                    await self._log_event("application_sent", {
                        "vacancy_id": vacancy.hh_id,
                        "vacancy_title": vacancy.title,
                        "company": vacancy.company_name,
                    }, vacancy_id=vacancy.id)
                else:
                    letter.status = "failed"
                    await self._log_event(
                        "application_failed",
                        {"vacancy_id": vacancy.hh_id},
                        vacancy_id=vacancy.id,
                        error="Browser apply returned False",
                    )

            except Exception as e:
                letter.status = "failed"
                await self._log_event(
                    "application_failed",
                    {"vacancy_id": vacancy.hh_id},
                    vacancy_id=vacancy.id,
                    error=str(e),
                )

        await self.db.commit()
        logger.info(f"Apply cycle complete: {sent} applications sent")

    # --- Status Check (browser) ---

    async def run_status_check(self):
        """Check status of sent applications via browser negotiations page."""
        logger.info("Starting status check")

        result = await self.db.execute(
            select(Application).where(Application.status.in_(["sent", "viewed"]))
        )
        active_apps = result.scalars().all()

        if not active_apps:
            logger.info("No active applications to check")
            return

        try:
            negotiations = await self.browser.get_negotiations()
        except Exception as e:
            logger.error(f"Failed to fetch negotiations: {e}")
            return

        neg_map = {n.vacancy_id: n for n in negotiations if n.vacancy_id}
        updated = 0

        for app in active_apps:
            vacancy = await self.db.get(Vacancy, app.vacancy_id)
            if not vacancy:
                continue

            neg = neg_map.get(vacancy.hh_id)
            if neg and neg.state in ("sent", "viewed", "invited", "declined", "offer"):
                new_status = neg.state
                if new_status != app.status:
                    old_status = app.status
                    app.status = new_status
                    app.hh_status = neg.state
                    app.last_status_check = datetime.utcnow()
                    updated += 1
                    await self._log_event("status_changed", {
                        "vacancy_title": vacancy.title,
                        "company": vacancy.company_name,
                        "old_status": old_status,
                        "new_status": new_status,
                    }, vacancy_id=vacancy.id)

                    # Telegram notification
                    if notifier.is_configured:
                        await notifier.notify_status_change(
                            vacancy_title=vacancy.title,
                            company_name=vacancy.company_name,
                            old_status=old_status,
                            new_status=new_status,
                        )

        await self.db.commit()
        logger.info(f"Status check complete: {updated} applications updated")

    # --- Resume Touch (browser) ---

    async def run_resume_touch(self):
        """Touch ALL resumes from the resumes list page on hh.ru."""
        logger.info("Starting resume touch for all resumes")

        # Verify auth before touching
        if not await self.browser.verify_auth():
            logger.warning("Browser session expired, attempting re-login")
            if not settings.hh_email or not settings.hh_password:
                logger.error("Cannot touch resumes: no hh.ru credentials configured")
                await self._log_event("resume_touch_skipped", {"reason": "no_credentials"})
                return
            login_ok = await self.browser.login(settings.hh_email, settings.hh_password)
            if not login_ok:
                logger.error("Cannot touch resumes: browser login failed")
                await self._log_event("resume_touch_skipped", {"reason": "login_failed"})
                return
            logger.info("Re-authenticated successfully")

        # Touch all resumes from the list page
        touched, total, details = await self.browser.touch_all_resumes()

        # Update last_touched_at for all resumes if any were touched
        if touched > 0:
            db_result = await self.db.execute(select(Resume))
            resumes = list(db_result.scalars().all())
            now = datetime.utcnow()
            for resume in resumes:
                resume.last_touched_at = now

        await self._log_event("resume_touch_complete", {
            "touched": touched,
            "total": total,
            "details": details,
        })
        await self.db.commit()
        logger.info(
            f"Resume touch complete: {touched}/{total} touched. "
            + "; ".join(details)
        )

    # --- Archive Check (public API) ---

    async def run_archive_check(self):
        """Check if pending vacancies are still active on hh.ru."""
        logger.info("Starting archive check")

        result = await self.db.execute(
            select(Vacancy).where(Vacancy.status.in_(["scored", "queued"]))
        )
        vacancies = list(result.scalars().all())

        if not vacancies:
            logger.info("No pending vacancies to check")
            return

        archived = 0
        for v in vacancies:
            is_archived = False
            try:
                full = await self.hh.get_vacancy(v.hh_id)
                is_archived = full.archived
            except HHApiError as e:
                if e.status_code == 404:
                    is_archived = True
                else:
                    logger.warning(f"API error checking {v.hh_id}: {e}")
                    continue
            except Exception as e:
                logger.warning(f"Error checking vacancy {v.hh_id}: {e}")
                continue

            if is_archived:
                v.status = "archived"
                archived += 1
                # Reject pending cover letters for this vacancy
                letters_result = await self.db.execute(
                    select(CoverLetter).where(
                        CoverLetter.vacancy_id == v.id,
                        CoverLetter.status == "pending",
                    )
                )
                for letter in letters_result.scalars().all():
                    letter.status = "rejected"
                    letter.rejection_reason = "vacancy_archived"

        await self._log_event("archive_check_complete", {
            "checked": len(vacancies),
            "archived": archived,
        })
        await self.db.commit()
        logger.info(f"Archive check complete: {archived}/{len(vacancies)} archived")

    # --- Similar Vacancies Expansion ---

    async def run_similar_expansion(
        self, top_n: int = 50, days_back: int = 7, per_seed: int = 20
    ):
        """Expand vacancy pool via hh.ru "Вам подойдут эти вакансии".

        For top_n recent high-scoring vacancies, fetch similar vacancies and
        process new ones through the standard pipeline.
        """
        from datetime import timedelta
        logger.info(
            f"Starting similar expansion: top {top_n} seeds from last {days_back}d"
        )

        cutoff = datetime.utcnow() - timedelta(days=days_back)
        result = await self.db.execute(
            select(Vacancy).where(
                Vacancy.status.in_(["scored", "queued", "applied"]),
                Vacancy.relevance_score >= settings.auto_generate_score,
                Vacancy.created_at >= cutoff,
            ).order_by(Vacancy.relevance_score.desc()).limit(top_n)
        )
        seeds = list(result.scalars().all())
        if not seeds:
            logger.info("Similar expansion: no high-scoring seed vacancies")
            return

        logger.info(f"Similar expansion: using {len(seeds)} seeds")

        all_similar: list[VacancyShort] = []
        for seed in seeds:
            try:
                similar = await self.hh.get_similar_vacancies(
                    seed.hh_id, per_page=per_seed
                )
                all_similar.extend(similar)
            except HHApiError as e:
                logger.warning(f"Failed similar for {seed.hh_id}: {e}")
                continue
            except Exception as e:
                logger.warning(f"Error similar for {seed.hh_id}: {e}")
                continue

        # Deduplicate within batch by hh_id
        seen_ids = set()
        deduped: list[VacancyShort] = []
        for v in all_similar:
            if v.hh_id in seen_ids:
                continue
            seen_ids.add(v.hh_id)
            deduped.append(v)

        # Filter against DB (by hh_id + title+company)
        new_vacancies = await self._filter_known(deduped)
        # Apply company blacklist rules
        new_vacancies = await self._apply_company_rules(new_vacancies)

        logger.info(
            f"Similar expansion: {len(all_similar)} fetched, "
            f"{len(deduped)} unique, {len(new_vacancies)} new after filters"
        )

        scored_count, letters_count = await self._process_new_vacancies(new_vacancies)

        await self._log_event("similar_expansion_complete", {
            "seeds": len(seeds),
            "fetched": len(all_similar),
            "new": len(new_vacancies),
            "scored": scored_count,
            "letters": letters_count,
        })
        await self.db.commit()
        logger.info(
            f"Similar expansion complete: {len(seeds)} seeds → "
            f"{len(new_vacancies)} new, {scored_count} scored, "
            f"{letters_count} letters"
        )

    async def expand_from_seed(self, seed_hh_id: str, per_seed: int = 20) -> dict:
        """Fetch similar vacancies for one seed and process new ones through the pipeline.

        Used by the seed-expansion worker to react to user-approved letters.
        """
        logger.info(f"Seed expansion: {seed_hh_id} (per_seed={per_seed})")

        try:
            similar = await self.hh.get_similar_vacancies(seed_hh_id, per_page=per_seed)
        except HHApiError as e:
            logger.warning(f"Seed expansion: hh.ru API error for {seed_hh_id}: {e}")
            return {"fetched": 0, "new": 0, "scored": 0, "letters": 0}
        except Exception as e:
            logger.warning(f"Seed expansion: unexpected error for {seed_hh_id}: {e}")
            return {"fetched": 0, "new": 0, "scored": 0, "letters": 0}

        if not similar:
            return {"fetched": 0, "new": 0, "scored": 0, "letters": 0}

        new_vacancies = await self._filter_known(similar)
        new_vacancies = await self._apply_company_rules(new_vacancies)

        scored_count, letters_count = await self._process_new_vacancies(new_vacancies)

        await self._log_event("seed_expansion_complete", {
            "seed_hh_id": seed_hh_id,
            "fetched": len(similar),
            "new": len(new_vacancies),
            "scored": scored_count,
            "letters": letters_count,
        })
        await self.db.commit()
        logger.info(
            f"Seed expansion complete: {seed_hh_id} → "
            f"{len(similar)} fetched, {len(new_vacancies)} new, "
            f"{scored_count} scored, {letters_count} letters"
        )
        return {
            "fetched": len(similar),
            "new": len(new_vacancies),
            "scored": scored_count,
            "letters": letters_count,
        }

    async def _process_new_vacancies(
        self, new_vacancies: list[VacancyShort]
    ) -> tuple[int, int]:
        """Score, save, and generate cover letters for a batch of new vacancies.

        Returns (scored_count, letters_count). Caller is responsible for commit.
        """
        scored_count = 0
        letters_count = 0
        profiles = await self._get_active_profiles()
        fallback_profile_id = profiles[0].id if profiles else None

        for v in new_vacancies:
            fast_sc, fast_reason = fast_score(
                title=v.title,
                company_name=v.company_name,
                description_snippet=v.snippet_requirement,
                key_skills=v.key_skills,
                experience=v.experience,
                schedule=v.schedule,
                area_name=v.area_name,
            )

            if fast_sc < 0.3:
                await self._save_vacancy(v, fast_sc, fast_reason, "skipped", fallback_profile_id)
                continue

            try:
                full = await self.hh.get_vacancy(v.hh_id)
            except HHApiError as e:
                logger.warning(f"Failed to fetch full {v.hh_id}: {e}")
                continue

            ai_result = await ai_score(
                title=full.title,
                company_name=full.company_name,
                description=full.description,
                key_skills=full.key_skills,
                resume_text=self.resume_text,
            )
            scored_count += 1

            resume_match = await match_resume(
                self.db,
                vacancy_title=full.title,
                vacancy_skills=full.key_skills,
                vacancy_description=full.description,
            )

            db_vacancy = await self._save_vacancy(
                v, ai_result.score, ai_result.reasoning, "scored", fallback_profile_id,
                description=full.description,
                matched_skills=ai_result.matched_skills,
                missing_skills=ai_result.missing_skills,
            )
            db_vacancy.recommended_resume_id = resume_match.resume_hh_id or None

            if ai_result.score >= settings.auto_generate_score:
                resume_id_for_letter = resume_match.resume_hh_id or ""
                try:
                    draft = await generate_cover_letter(
                        title=full.title,
                        company_name=full.company_name,
                        description=full.description,
                        key_skills=full.key_skills,
                        resume_text=self.resume_text,
                        scoring=ai_result,
                    )
                    self.db.add(CoverLetter(
                        vacancy_id=db_vacancy.id,
                        resume_id=resume_id_for_letter,
                        generated_text=draft.text,
                        generation_prompt=draft.prompt_used[:5000],
                        model_used=draft.model,
                        status="pending",
                    ))
                    db_vacancy.status = "queued"
                    letters_count += 1
                    await self.db.flush()

                    if notifier.is_configured:
                        await notifier.notify_new_match(
                            vacancy_title=full.title,
                            company_name=full.company_name,
                            score=ai_result.score,
                            vacancy_url=v.url,
                            letter_preview=draft.text,
                        )
                except Exception as e:
                    logger.error(f"Cover letter gen failed for {v.hh_id}: {e}")

        return scored_count, letters_count

    # --- Resume Rotation ---

    async def run_resume_rotation(self):
        """Rotate visibility of secondary resumes. Primary stays always visible."""
        logger.info("Starting resume rotation")

        result = await self.db.execute(
            select(Resume).order_by(Resume.rotation_priority.asc())
        )
        resumes = list(result.scalars().all())
        secondary = [r for r in resumes if not r.is_primary]

        if len(secondary) < 2:
            logger.info("Less than 2 secondary resumes, nothing to rotate")
            return

        # Find next resume to activate (round-robin by rotation_priority)
        secondary_sorted = sorted(secondary, key=lambda r: r.rotation_priority)
        current_visible = [r for r in secondary if r.visibility_status == "visible"]

        if current_visible:
            current_idx = next(
                (i for i, r in enumerate(secondary_sorted) if r.id == current_visible[0].id),
                0,
            )
            next_idx = (current_idx + 1) % len(secondary_sorted)
        else:
            next_idx = 0
        next_resume = secondary_sorted[next_idx]

        # Toggle visibility
        for r in secondary:
            if r.id == next_resume.id:
                success = await self.browser.set_resume_visibility(r.hh_id, visible=True)
                if success:
                    r.visibility_status = "visible"
                    r.last_rotated_at = datetime.utcnow()
                    r.rotation_priority = max(s.rotation_priority for s in secondary) + 1
            else:
                if r.visibility_status == "visible":
                    success = await self.browser.set_resume_visibility(r.hh_id, visible=False)
                    if success:
                        r.visibility_status = "hidden"

        await self.db.commit()
        await self._log_event("resume_rotation", {
            "activated": next_resume.short_name or next_resume.title,
            "activated_hh_id": next_resume.hh_id,
        })
        logger.info(f"Resume rotation: activated '{next_resume.short_name or next_resume.title}'")

    # --- Helpers ---

    async def _get_active_profiles(self) -> list[SearchProfile]:
        result = await self.db.execute(
            select(SearchProfile).where(SearchProfile.is_active == True)
        )
        return list(result.scalars().all())

    async def _filter_known(self, vacancies: list[VacancyShort]) -> list[VacancyShort]:
        """Remove vacancies already in DB (by hh_id or by title+company duplicate)."""
        hh_ids = [v.hh_id for v in vacancies]
        result = await self.db.execute(
            select(Vacancy.hh_id).where(Vacancy.hh_id.in_(hh_ids))
        )
        known_ids = {row[0] for row in result.all()}

        # Also check for title+company duplicates already in DB
        new_vacancies = [v for v in vacancies if v.hh_id not in known_ids]
        if not new_vacancies:
            return new_vacancies

        # Build set of existing title+company pairs
        pairs = [(v.title, v.company_name) for v in new_vacancies if v.company_name]
        if pairs:
            from sqlalchemy import tuple_
            dup_result = await self.db.execute(
                select(Vacancy.title, Vacancy.company_name).where(
                    tuple_(Vacancy.title, Vacancy.company_name).in_(pairs)
                )
            )
            known_pairs = {(row[0], row[1]) for row in dup_result.all()}
        else:
            known_pairs = set()

        # Also deduplicate within the current batch
        seen_pairs = set()
        filtered = []
        for v in new_vacancies:
            pair = (v.title, v.company_name)
            if pair in known_pairs:
                logger.debug(f"Skipping duplicate: {v.title} @ {v.company_name}")
                continue
            if v.company_name and pair in seen_pairs:
                logger.debug(f"Skipping batch duplicate: {v.title} @ {v.company_name}")
                continue
            if v.company_name:
                seen_pairs.add(pair)
            filtered.append(v)

        skipped = len(new_vacancies) - len(filtered)
        if skipped:
            logger.info(f"Filtered {skipped} duplicate vacancies (same title+company)")
        return filtered

    async def _apply_company_rules(
        self, vacancies: list[VacancyShort]
    ) -> list[VacancyShort]:
        """Apply blacklist/whitelist rules."""
        result = await self.db.execute(
            select(CompanyRule).where(CompanyRule.is_active == True)
        )
        rules = list(result.scalars().all())
        if not rules:
            return vacancies

        blacklist_names = set()
        blacklist_ids = set()
        blacklist_title_kw = set()

        for rule in rules:
            if rule.rule_type == "blacklist":
                if rule.match_type == "company_name":
                    blacklist_names.add(rule.match_value.lower())
                elif rule.match_type == "company_id":
                    blacklist_ids.add(rule.match_value)
                elif rule.match_type == "keyword_in_title":
                    blacklist_title_kw.add(rule.match_value.lower())

        filtered = []
        for v in vacancies:
            if v.company_name and v.company_name.lower() in blacklist_names:
                continue
            if v.company_id and v.company_id in blacklist_ids:
                continue
            if any(kw in v.title.lower() for kw in blacklist_title_kw):
                continue
            filtered.append(v)

        skipped = len(vacancies) - len(filtered)
        if skipped:
            logger.info(f"Filtered {skipped} vacancies by company rules")
        return filtered

    async def _save_vacancy(
        self,
        v: VacancyShort,
        score: float,
        reasoning: str,
        status: str,
        profile_id: int,
        description: str | None = None,
        matched_skills: list[str] | None = None,
        missing_skills: list[str] | None = None,
    ) -> Vacancy:
        vacancy = Vacancy(
            hh_id=v.hh_id,
            title=v.title,
            company_name=v.company_name,
            company_id=v.company_id,
            salary_from=v.salary_from,
            salary_to=v.salary_to,
            salary_currency=v.salary_currency,
            salary_gross=v.salary_gross,
            area_name=v.area_name,
            experience=v.experience,
            employment=v.employment,
            schedule=v.schedule,
            description=description,
            key_skills=v.key_skills,
            url=v.url,
            response_letter_required=v.response_letter_required,
            published_at=v.published_at if isinstance(v.published_at, datetime) else None,
            employer_logo_url=v.employer_logo_url,
            relevance_score=score,
            score_reasoning=reasoning,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            status=status,
            search_profile_id=profile_id,
        )
        self.db.add(vacancy)
        await self.db.flush()
        return vacancy

    async def _get_approved_letters(self) -> list[CoverLetter]:
        result = await self.db.execute(
            select(CoverLetter)
            .options(selectinload(CoverLetter.vacancy))
            .where(CoverLetter.status.in_(["approved", "edited", "no_letter"]))
            .order_by(CoverLetter.generated_at.asc())
        )
        return list(result.scalars().all())

    async def _get_today_application_count(self) -> int:
        today = date.today()
        result = await self.db.execute(
            select(func.count(Application.id)).where(
                func.date(Application.applied_at) == today
            )
        )
        return result.scalar_one()
