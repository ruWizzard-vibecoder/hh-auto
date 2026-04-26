"""Playwright browser for hh.ru authenticated operations (apply, negotiations, resume touch)."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("hh-auto.hh_browser")

BROWSER_STATE_DIR = Path("/app/data/browser_state")

# Singleton instance
_instance: "HHBrowser | None" = None


@dataclass
class BrowserNegotiation:
    vacancy_id: str
    state: str
    vacancy_name: str
    employer_name: str
    vacancy_url: str


def get_browser() -> "HHBrowser":
    """Get or create the singleton HHBrowser instance."""
    global _instance
    if _instance is None:
        _instance = HHBrowser()
    return _instance


class HHBrowser:
    """Headless browser for hh.ru login and authenticated operations."""

    def __init__(self):
        self._browser = None
        self._context = None
        self._playwright = None

    async def _ensure_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)

            # Restore state if exists
            state_file = BROWSER_STATE_DIR / "state.json"
            if state_file.exists():
                self._context = await self._browser.new_context(
                    storage_state=str(state_file)
                )
                logger.info("Browser state restored from file")
            else:
                self._context = await self._browser.new_context()

    def is_logged_in(self) -> bool:
        """Check if browser state file exists (session may still be expired)."""
        state_file = BROWSER_STATE_DIR / "state.json"
        return state_file.exists()

    async def verify_auth(self) -> bool:
        """Actually verify we're logged in by loading hh.ru and checking for auth indicators."""
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await page.goto("https://hh.ru/", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            # If "Войти" button is visible, we're NOT logged in
            login_btn = page.locator('a[data-qa="login"]')
            if await login_btn.count() > 0:
                logger.warning("Browser session expired — not authenticated")
                return False
            # Check for logged-in indicators
            user_menu = page.locator('[data-qa="mainmenu_applicantProfile"]')
            if await user_menu.count() > 0:
                logger.info("Browser auth verified — logged in")
                return True
            # Fallback: check if "Войти" text is present
            if await page.locator('text="Войти"').count() > 0:
                logger.warning("Browser session expired — 'Войти' text found")
                return False
            logger.info("Browser auth status unclear, assuming logged in")
            return True
        except Exception as e:
            logger.error(f"Auth verification failed: {e}")
            return False
        finally:
            await page.close()

    async def login(self, email: str, password: str) -> bool:
        """Login to hh.ru via browser. Returns True on success."""
        await self._ensure_browser()
        page = await self._context.new_page()

        try:
            await page.goto("https://hh.ru/account/login", wait_until="domcontentloaded")

            # Step 1: Click "Войти" (account type selection → login form)
            submit_btn = page.locator('[data-qa="submit-button"]')
            if await submit_btn.count() > 0:
                await submit_btn.click()
                await page.wait_for_timeout(2000)

            # Step 2: Switch to email mode by clicking "Почта" label
            email_label = page.locator("label", has_text="Почта")
            if await email_label.count() > 0:
                await email_label.click(force=True)
                await page.wait_for_timeout(1500)

            # Step 3: Fill email
            email_input = page.locator('[data-qa="applicant-login-input-email"]')
            if await email_input.count() == 0:
                email_input = page.locator('input[name="username"]')
            await email_input.fill(email)
            await page.wait_for_timeout(500)

            # Step 4: Click "Войти с паролем" to expand password field
            expand_btn = page.locator('[data-qa="expand-login-by-password"]')
            if await expand_btn.count() > 0:
                await expand_btn.click(force=True)
                await page.wait_for_timeout(2000)

            # Step 5: Fill password
            password_input = page.locator('[data-qa="applicant-login-input-password"]')
            if await password_input.count() == 0:
                password_input = page.locator('input[name="password"]')
            await password_input.fill(password)

            # Step 6: Click submit
            login_btn = page.locator('[data-qa="submit-button"]')
            await login_btn.click()

            # Wait for navigation away from login page
            await page.wait_for_timeout(3000)
            if "/account/login" in page.url:
                raise Exception(f"Still on login page: {page.url}")

            # Save browser state
            state_file = BROWSER_STATE_DIR / "state.json"
            await self._context.storage_state(path=str(state_file))
            logger.info("Logged in via browser, state saved")
            return True

        except Exception as e:
            logger.error(f"Browser login failed: {e}")
            return False
        finally:
            await page.close()

    async def _save_popup_html(self, page, label: str = "") -> None:
        """Save popup HTML for debugging resume selector."""
        try:
            popup_html = await page.evaluate("""() => {
                const modal = document.querySelector('[role="dialog"]')
                    || document.querySelector('[class*="modal"]');
                return modal ? modal.innerHTML : document.body.innerHTML.substring(0, 20000);
            }""")
            from datetime import datetime
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            suffix = f"_{label}" if label else ""
            html_path = Path("/app/data") / f"debug_popup_html{suffix}_{ts}.txt"
            html_path.write_text(popup_html[:20000], encoding="utf-8")
            logger.info(f"Popup HTML saved: {html_path}")
        except Exception as e:
            logger.warning(f"Failed to save popup HTML: {e}")

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Split text into meaningful tokens for fuzzy matching."""
        # Split on spaces, slashes, pipes, plus, parens, commas
        tokens = re.split(r'[\s/|+(),]+', text.lower())
        # Keep tokens with 2+ chars, skip noise
        return {t for t in tokens if len(t) >= 2}

    async def _select_resume_in_popup(
        self, page, resume_id: str, resume_title: str = ""
    ) -> bool:
        """Try to select the correct resume in the apply popup.

        hh.ru popup structure (2026):
        - Resume shown as a clickable card with data-qa="resume-title"
        - Clicking the card opens a resume picker list
        - Each resume option in the list also has data-qa="resume-title"

        Always opens the picker and compares ALL options to find the best match.
        """
        if not resume_id and not resume_title:
            return False

        try:
            await self._save_popup_html(page, "before_select")

            # Read currently selected resume title for logging
            current_title_el = page.locator(
                '[data-qa="resume-title"] [data-qa="cell-text-content"]'
            )
            current_title = ""
            if await current_title_el.count() > 0:
                current_title = (await current_title_el.first.inner_text()).strip()
                logger.info(f"Currently selected resume: '{current_title}'")

            # Click the resume card to open the picker
            resume_card = page.locator(
                'div[role="button"]:has([data-qa="resume-title"])'
            )
            if await resume_card.count() == 0:
                resume_card = page.locator('[data-qa="resume-title"]').locator('..')
            if await resume_card.count() == 0:
                logger.warning("Resume card not found in popup")
                return False

            await resume_card.first.click()
            await page.wait_for_timeout(1500)
            await self._save_popup_html(page, "after_card_click")

            # Look for resume options in the expanded picker
            resume_options = page.locator(
                '[data-qa="resume-title"] [data-qa="cell-text-content"]'
            )
            option_count = await resume_options.count()
            logger.info(f"Found {option_count} resume options in picker")

            if option_count <= 1:
                logger.info("Only one resume available, using default")
                return True

            # Score each option and pick the best match
            our_tokens = self._tokenize(resume_title) if resume_title else set()
            best_idx = -1
            best_score = -1
            options_text = []

            for i in range(option_count):
                option = resume_options.nth(i)
                option_text = (await option.inner_text()).strip()
                options_text.append(option_text)
                logger.info(f"Resume option {i}: '{option_text}'")

                score = 0

                # Check for resume_id in parent card HTML (definitive match)
                if resume_id:
                    try:
                        card = option.locator('xpath=ancestor::div[@role="button"]')
                        if await card.count() > 0:
                            card_html = await card.first.inner_html()
                            if resume_id in card_html:
                                score = 200
                    except Exception:
                        pass

                # Exact substring match in title
                if score < 200 and resume_title:
                    if resume_title.lower() in option_text.lower():
                        score = max(score, 100)
                    elif option_text.lower() in resume_title.lower():
                        score = max(score, 90)
                    else:
                        # Token overlap — weighted by specificity
                        opt_tokens = self._tokenize(option_text)
                        common = our_tokens & opt_tokens
                        # Exclude very common tokens that match too broadly
                        common_specific = {
                            t for t in common
                            if t not in {"ai", "ml", "engineer", "developer",
                                         "разработчик", "инженер", "специалист"}
                        }
                        # Score: specific tokens worth 10, common tokens worth 1
                        score = max(
                            score,
                            len(common_specific) * 10 + len(common)
                        )

                if score > best_score:
                    best_score = score
                    best_idx = i

            logger.info(
                f"Best match: option {best_idx} ('{options_text[best_idx] if best_idx >= 0 else 'none'}') "
                f"with score={best_score}"
            )

            # Click the best matching option (if score is meaningful)
            if best_idx >= 0 and best_score >= 1:
                option = resume_options.nth(best_idx)
                try:
                    card = option.locator('xpath=ancestor::div[@role="button"]')
                    if await card.count() > 0:
                        await card.first.click()
                    else:
                        await option.click()
                except Exception:
                    await option.click()
                await page.wait_for_timeout(500)

                # Verify the selection changed
                new_title_el = page.locator(
                    '[data-qa="resume-title"] [data-qa="cell-text-content"]'
                )
                if await new_title_el.count() > 0:
                    new_title = (await new_title_el.first.inner_text()).strip()
                    logger.info(f"Resume after selection: '{new_title}'")

                logger.info(
                    f"Selected resume '{options_text[best_idx]}' "
                    f"(option {best_idx}, score={best_score})"
                )
                return True

            # No match found — close picker and use default
            logger.warning(
                f"No matching resume. Wanted: id={resume_id}, title='{resume_title}'. "
                f"Options: {options_text}. Check /app/data/debug_popup_html_*.txt"
            )
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
            return False

        except Exception as e:
            logger.warning(f"Failed to select resume: {e}")
            return False

    async def apply_to_vacancy(
        self, vacancy_url: str, message: str = "", resume_id: str = "",
        resume_title: str = "",
    ) -> bool:
        """Apply to vacancy via browser. Optionally select specific resume. Returns True on success."""
        self._cleanup_debug_files()
        await self._ensure_browser()
        page = await self._context.new_page()

        try:
            await page.goto(vacancy_url, wait_until="domcontentloaded")

            # Click respond button
            respond_btn = page.locator('[data-qa="vacancy-response-link-top"]').first
            if not await respond_btn.is_visible():
                respond_btn = page.locator('[data-qa="vacancy-response-link-bottom"]').first

            if not await respond_btn.is_visible():
                # Maybe already applied
                already = page.locator('text="Вы уже откликнулись"')
                if await already.count() > 0:
                    logger.info(f"Already applied to {vacancy_url}")
                    return True
                logger.warning(f"No respond button found on {vacancy_url}")
                return False

            await respond_btn.click()
            await page.wait_for_timeout(2000)

            # Handle intermediate modals (e.g., "vacancy from another country")
            # "Всё"/"Все" — ё/е ambiguity, match by partial text
            for confirm_text in ["равно откликнуться", "Все равно откликнуться", "Всё равно откликнуться"]:
                confirm_btn = page.get_by_role("button", name=confirm_text)
                if await confirm_btn.count() > 0 and await confirm_btn.first.is_visible():
                    logger.info(f"Dismissing intermediate modal for {vacancy_url}")
                    await confirm_btn.first.click()
                    await page.wait_for_timeout(2000)
                    break
            else:
                # Also try link/generic locator
                confirm_link = page.locator('button:has-text("равно откликнуться"), a:has-text("равно откликнуться")')
                if await confirm_link.count() > 0:
                    logger.info(f"Dismissing intermediate modal (link) for {vacancy_url}")
                    await confirm_link.first.click()
                    await page.wait_for_timeout(2000)

            # Wait for the apply popup to actually appear
            popup_selectors = [
                'button[data-qa="vacancy-response-submit-popup"]',
                '[data-qa="resume-title"]',
                '[data-qa="add-cover-letter"]',
                'textarea[data-qa="vacancy-response-popup-form-letter-input"]',
            ]
            popup_appeared = False
            for _ in range(10):  # up to 10 seconds
                await page.wait_for_timeout(1000)
                for sel in popup_selectors:
                    if await page.locator(sel).count() > 0:
                        popup_appeared = True
                        break
                if popup_appeared:
                    break

            if not popup_appeared:
                # Maybe redirect happened (some employers have external apply)
                logger.warning(f"Apply popup didn't appear for {vacancy_url}")
                await self._save_debug_screenshot(page, "no_popup")
                return False

            # Try to select the correct resume in the popup
            if resume_id or resume_title:
                await self._select_resume_in_popup(page, resume_id, resume_title)

            # Fill cover letter if message provided
            if message:
                letter_input = page.locator(
                    'textarea[data-qa="vacancy-response-popup-form-letter-input"]'
                )
                # Textarea is hidden by default — click toggle to reveal it
                if await letter_input.count() == 0:
                    letter_toggle = page.locator(
                        '[data-qa="add-cover-letter"], '
                        '[data-qa="vacancy-response-popup-form-letter-toggle"]'
                    )
                    if await letter_toggle.count() == 0:
                        letter_toggle = page.get_by_text(
                            "сопроводительное", exact=False
                        ).first
                    if await letter_toggle.count() > 0 and await letter_toggle.is_visible():
                        await letter_toggle.click()
                        await page.wait_for_timeout(500)

                # Re-check after toggle
                letter_input = page.locator(
                    'textarea[data-qa="vacancy-response-popup-form-letter-input"]'
                )
                if await letter_input.count() > 0:
                    await letter_input.fill(message)
                    logger.info(
                        f"Cover letter filled ({len(message)} chars) for {vacancy_url}"
                    )
                else:
                    logger.warning(f"Cover letter textarea not found for {vacancy_url}")
                    await self._save_debug_screenshot(page, "no_letter_textarea")

            # Submit
            submit_btn = page.locator(
                'button[data-qa="vacancy-response-submit-popup"]'
            )
            if await submit_btn.count() == 0:
                logger.warning(f"Submit button not found for {vacancy_url}")
                await self._save_debug_screenshot(page, "no_submit_btn")
                return False

            await submit_btn.click()
            await page.wait_for_timeout(3000)

            # Check for definitive success indicators
            success_selectors = [
                'text="Отклик отправлен"',
                'text="Вы откликнулись"',
                '[data-qa="vacancy-response-already-applied"]',
            ]
            for sel in success_selectors:
                if await page.locator(sel).count() > 0:
                    logger.info(f"Successfully applied to {vacancy_url}")
                    return True

            # Check for known failure indicators
            failure_selectors = [
                'text="капча"',
                'text="captcha"',
                'text="Ошибка"',
                'text="Произошла ошибка"',
            ]
            for sel in failure_selectors:
                if await page.locator(sel).count() > 0:
                    logger.warning(f"Apply failed (error on page) for {vacancy_url}: {sel}")
                    await self._save_debug_screenshot(page, "apply_error")
                    return False

            # Check if respond button is gone (popup closed = likely success)
            respond_gone = await page.locator('[data-qa="vacancy-response-link-top"]').count() == 0
            already_applied = await page.locator('text="Вы уже откликнулись"').count() > 0
            if respond_gone or already_applied:
                logger.info(f"Applied to {vacancy_url} (respond button gone)")
                return True

            # No clear indicator — save screenshot and report failure
            logger.warning(f"Apply result unclear for {vacancy_url}, saving screenshot")
            await self._save_debug_screenshot(page, "unclear_result")
            return False

        except Exception as e:
            logger.error(f"Browser apply failed for {vacancy_url}: {e}")
            return False
        finally:
            await page.close()

    async def _save_debug_screenshot(self, page, prefix: str):
        """Save screenshot for debugging failed applies."""
        try:
            from datetime import datetime
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            path = Path("/app/data") / f"debug_{prefix}_{ts}.png"
            await page.screenshot(path=str(path), full_page=True)
            logger.info(f"Debug screenshot saved: {path}")
        except Exception as e:
            logger.warning(f"Failed to save debug screenshot: {e}")

    @staticmethod
    def _cleanup_debug_files(keep: int = 20):
        """Remove old debug files, keeping only the most recent ones."""
        try:
            data_dir = Path("/app/data")
            debug_files = sorted(
                data_dir.glob("debug_*"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            for f in debug_files[keep:]:
                f.unlink()
                logger.debug(f"Cleaned up debug file: {f.name}")
        except Exception:
            pass

    async def get_negotiations(self) -> list[BrowserNegotiation]:
        """Parse negotiations (responses) page via browser."""
        await self._ensure_browser()
        page = await self._context.new_page()

        negotiations = []
        try:
            await page.goto(
                "https://hh.ru/applicant/negotiations",
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(2000)

            # Parse each negotiation item
            items = page.locator('[data-qa="negotiations-list-item"]')
            count = await items.count()
            logger.info(f"Found {count} negotiations on page")

            for i in range(count):
                item = items.nth(i)
                try:
                    # Vacancy title and link
                    title_el = item.locator('[data-qa="negotiations-item-title"]')
                    vacancy_name = await title_el.inner_text() if await title_el.count() > 0 else ""
                    vacancy_url = ""
                    if await title_el.count() > 0:
                        link = title_el.locator("a")
                        if await link.count() > 0:
                            vacancy_url = await link.get_attribute("href") or ""

                    # Employer name
                    employer_el = item.locator('[data-qa="negotiations-item-company"]')
                    employer_name = await employer_el.inner_text() if await employer_el.count() > 0 else ""

                    # Status
                    status_el = item.locator('[data-qa="negotiations-item-status"]')
                    state = await status_el.inner_text() if await status_el.count() > 0 else "unknown"

                    # Extract vacancy ID from URL
                    vacancy_id = ""
                    if vacancy_url:
                        parts = vacancy_url.rstrip("/").split("/")
                        # URL like /vacancy/12345 or https://hh.ru/vacancy/12345
                        for j, part in enumerate(parts):
                            if part == "vacancy" and j + 1 < len(parts):
                                vacancy_id = parts[j + 1].split("?")[0]
                                break

                    negotiations.append(BrowserNegotiation(
                        vacancy_id=vacancy_id,
                        state=state.strip().lower(),
                        vacancy_name=vacancy_name.strip(),
                        employer_name=employer_name.strip(),
                        vacancy_url=vacancy_url,
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse negotiation item {i}: {e}")

        except Exception as e:
            logger.error(f"Failed to load negotiations page: {e}")
        finally:
            await page.close()

        return negotiations

    async def touch_all_resumes(self) -> tuple[int, int, list[str]]:
        """Touch all resumes from the resumes list page.

        Returns (touched_count, total_resumes, details_list).
        """
        import re
        await self._ensure_browser()
        page = await self._context.new_page()

        try:
            await page.goto(
                "https://hh.ru/applicant/resumes",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(3000)

            # Save screenshot
            debug_dir = Path("/app/data/browser_state")
            debug_dir.mkdir(parents=True, exist_ok=True)
            await page.screenshot(
                path=str(debug_dir / "resumes_page.png"), full_page=True
            )

            # Count resumes on page — try multiple selectors
            title_links = page.locator('[data-qa="resume-title-link"]')
            total = await title_links.count()

            if total == 0:
                # Try alternative selectors
                for sel in [
                    '[data-qa="resume-title"]',
                    'a[href*="/resume/"]',
                ]:
                    title_links = page.locator(sel)
                    total = await title_links.count()
                    if total > 0:
                        logger.info(
                            f"Found {total} resumes via selector: {sel}"
                        )
                        break

            logger.info(f"Found {total} resumes on page")

            # Check page text for cooldown timers
            body_text = await page.inner_text("body")
            # Note: hh.ru uses non-breaking spaces (\xa0) between words
            cooldowns = re.findall(
                r"Поднять вручную можно[\s\S]+?в[\s\xa0](\d{1,2}:\d{2})",
                body_text,
            )
            details = []
            if cooldowns:
                details.append(
                    f"On cooldown ({len(cooldowns)}), next at: "
                    + ", ".join(sorted(set(cooldowns)))
                )

            # Find available "Поднять в поиске" buttons
            raise_buttons = page.locator(
                '[data-qa="resume-update-button"]'
            )
            btn_count = await raise_buttons.count()

            if btn_count == 0:
                raise_buttons = page.locator(
                    'button:has-text("Поднять в поиске")'
                )
                btn_count = await raise_buttons.count()

            if btn_count == 0:
                logger.info(
                    f"No touch buttons available, "
                    f"{len(cooldowns)} resumes on cooldown"
                )
                return 0, total, details

            logger.info(f"Found {btn_count} touchable resumes")

            # Click buttons one by one, re-querying after each click
            # because the DOM changes (clicked button becomes cooldown text)
            touched = 0
            for i in range(btn_count):
                try:
                    # Re-query: always click the FIRST available button
                    btn = page.locator(
                        '[data-qa="resume-update-button"]'
                    ).first
                    if not await btn.count():
                        btn = page.locator(
                            'button:has-text("Поднять в поиске")'
                        ).first
                    if not await btn.count():
                        logger.info("No more touch buttons available")
                        break

                    await btn.scroll_into_view_if_needed()
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    touched += 1
                    logger.info(f"Touched resume {touched}/{btn_count}")

                    if i < btn_count - 1:
                        await page.wait_for_timeout(3000)
                except Exception as e:
                    details.append(f"Button {i+1} failed: {str(e)[:60]}")
                    logger.warning(f"Failed to click button {i+1}: {e}")
                    break

            details.insert(0, f"Touched {touched}/{btn_count} available")
            return touched, total, details

        except Exception as e:
            logger.error(f"Failed to touch resumes: {e}")
            return 0, 0, [f"Error: {str(e)[:100]}"]
        finally:
            await page.close()

    async def touch_resume(self, resume_url: str) -> bool:
        """Click 'Поднять в поиске' on resume page. Returns True on success."""
        await self._ensure_browser()
        page = await self._context.new_page()

        try:
            await page.goto(resume_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1000)

            # Look for the "raise in search" button
            raise_btn = page.locator('[data-qa="resume-update-button"]')
            if await raise_btn.count() == 0:
                raise_btn = page.locator('button:has-text("Поднять в поиске")')

            if await raise_btn.count() > 0:
                await raise_btn.click()
                await page.wait_for_timeout(2000)
                logger.info(f"Resume touched: {resume_url}")
                return True
            else:
                logger.warning(f"No raise button found on {resume_url}")
                return False

        except Exception as e:
            logger.error(f"Failed to touch resume {resume_url}: {e}")
            return False
        finally:
            await page.close()

    async def set_resume_visibility(self, resume_id: str, visible: bool) -> bool:
        """Publish or hide a resume on hh.ru. Returns True on success."""
        await self._ensure_browser()
        page = await self._context.new_page()
        resume_url = f"https://hh.ru/resume/{resume_id}"

        try:
            await page.goto(resume_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1000)

            if visible:
                # Try to publish the resume
                publish_btn = page.locator('[data-qa="resume-publish"]')
                if await publish_btn.count() == 0:
                    publish_btn = page.locator('button:has-text("Опубликовать")')
                if await publish_btn.count() == 0:
                    publish_btn = page.locator('button:has-text("Поднять в поиске")')

                if await publish_btn.count() > 0:
                    await publish_btn.first.click()
                    await page.wait_for_timeout(2000)
                    logger.info(f"Resume {resume_id} published")
                    return True
                else:
                    # May already be visible
                    hide_btn = page.locator('[data-qa="resume-unpublish"], button:has-text("Скрыть")')
                    if await hide_btn.count() > 0:
                        logger.info(f"Resume {resume_id} already visible")
                        return True
                    logger.warning(f"No publish button found for resume {resume_id}")
                    return False
            else:
                # Try to hide the resume
                hide_btn = page.locator('[data-qa="resume-unpublish"]')
                if await hide_btn.count() == 0:
                    hide_btn = page.locator('button:has-text("Скрыть")')

                if await hide_btn.count() > 0:
                    await hide_btn.first.click()
                    await page.wait_for_timeout(2000)
                    # Confirm hide if dialog appears
                    confirm_btn = page.locator('button:has-text("Скрыть резюме")')
                    if await confirm_btn.count() > 0:
                        await confirm_btn.click()
                        await page.wait_for_timeout(1000)
                    logger.info(f"Resume {resume_id} hidden")
                    return True
                else:
                    # May already be hidden
                    publish_btn = page.locator('[data-qa="resume-publish"], button:has-text("Опубликовать")')
                    if await publish_btn.count() > 0:
                        logger.info(f"Resume {resume_id} already hidden")
                        return True
                    logger.warning(f"No hide button found for resume {resume_id}")
                    return False

        except Exception as e:
            logger.error(f"Failed to set visibility for resume {resume_id}: {e}")
            return False
        finally:
            await page.close()

    async def close(self):
        """Close browser and playwright."""
        global _instance
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._browser = None
        self._context = None
        self._playwright = None
        if _instance is self:
            _instance = None
