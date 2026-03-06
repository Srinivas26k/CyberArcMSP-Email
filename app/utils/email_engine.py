"""
email_engine.py — Multi-provider email dispatcher for SRV AI Outreach.

Three sending strategies:
  • round_robin  — rotate across accounts one email at a time
  • parallel     — send concurrently from all accounts simultaneously
  • batch_count  — send N from Account A, then N from Account B, etc.

Supported providers:
  • outlook  — O365 Personal/Business SMTP (smtp-mail.outlook.com:587) + App Password
  • m365     — Microsoft 365 Business/Enterprise SMTP (smtp.office365.com:587) + App Password
  • gmail    — Gmail SMTP (smtp.gmail.com:587) + App Password
  • resend   — Resend.com HTTP API (app_password = API key, re_xxxx…)
"""
import asyncio
import email as email_lib
import imaplib
import json
import logging
import re
import smtplib
import time
import urllib.request
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER ROUTING
# ─────────────────────────────────────────────────────────────────────────────

def _smtp_host(provider: str) -> str:
    if provider == "gmail":
        return "smtp.gmail.com"
    if provider == "m365":
        return "smtp.office365.com"
    return "smtp-mail.outlook.com"   # outlook (O365 personal/business)

def _imap_host(provider: str) -> str:
    if provider == "gmail":
        return "imap.gmail.com"
    return "outlook.office365.com"   # m365 and outlook share the same IMAP host

RESEND_SEND_URL = "https://api.resend.com/emails"


# ─────────────────────────────────────────────────────────────────────────────
# DRAFT FOLDER DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def _find_drafts_folder(imap: imaplib.IMAP4_SSL) -> str:
    """
    Return the IMAP folder name for Drafts.
    Tries standard names: [Gmail]/Drafts, Drafts, Draft — first match wins.
    """
    candidates = ["[Gmail]/Drafts", "Drafts", "Draft", "INBOX.Drafts", "Drafts/"]
    try:
        _, folders = imap.list()
        folder_names: list[str] = []
        for item in folders or []:
            if isinstance(item, bytes):
                # Item looks like: b'(\\HasNoChildren) "/" "Drafts"'
                parts = item.decode(errors="replace").split('"')
                if len(parts) >= 3:
                    folder_names.append(parts[-2])
        # Prefer exact matches first
        for name in candidates:
            if name in folder_names:
                return name
        # Case-insensitive fallback
        for name in folder_names:
            if "draft" in name.lower():
                return name
    except Exception:
        pass
    return "Drafts"   # safe default


# ─────────────────────────────────────────────────────────────────────────────
# RESEND ACCOUNT (HTTP API — no SMTP)
# ─────────────────────────────────────────────────────────────────────────────

class ResendAccount:
    """Sends via Resend.com REST API. app_password field holds the API key."""

    def __init__(self, account: dict):
        self.email        = account["email"]
        self.api_key      = account["app_password"]   # re_xxxx…
        self.provider     = "resend"
        self.display_name = account.get("display_name", self.email.split("@")[0].title())
        self.id           = account.get("id")

    def send(self, to: str, subject: str, html: str, plain: str) -> None:
        """POST to Resend API. Raises on non-2xx."""
        payload = json.dumps({
            "from":    f"{self.display_name} <{self.email}>",
            "to":      [to],
            "subject": subject,
            "html":    html,
            "text":    plain,
        }).encode()
        req = urllib.request.Request(
            RESEND_SEND_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type":  "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(f"Resend API error {resp.status}: {resp.read().decode()[:200]}")

    def test_connection(self) -> dict:
        """Validate the API key is non-empty (no network call needed — avoids sending a real email)."""
        if self.api_key and self.api_key.startswith("re_"):
            return {"ok": True,  "email": self.email, "message": "Resend API key looks valid (re_…) ✓"}
        return    {"ok": False, "email": self.email, "message": "Resend API key must start with re_"}

    def check_replies(self) -> list[dict]:
        """Resend is send-only — reply detection not supported via Resend API."""
        logger.info(f"Resend account {self.email}: IMAP reply check skipped (Resend is send-only).")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE ACCOUNT
# ─────────────────────────────────────────────────────────────────────────────

class SMTPAccount:
    """
    Wraps one sender email account.
    All network I/O is blocking SMTP/IMAP — call from threads via asyncio.to_thread().
    """

    def __init__(self, account: dict):
        self.email        = account["email"]
        self.password     = account["app_password"]
        self.provider     = account.get("provider", "outlook").lower()
        self.display_name = account.get("display_name", self.email.split("@")[0].title())
        self.id           = account.get("id")

    # ── Send ─────────────────────────────────────────────────────────────────

    def send(self, to: str, subject: str, html: str, plain: str) -> None:
        """Send an HTML email synchronously. Raises on any SMTP error."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{self.display_name} <{self.email}>"
        msg["To"]      = to
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html,  "html"))

        host = _smtp_host(self.provider)
        with smtplib.SMTP(host, 587, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(self.email, self.password)
            smtp.sendmail(self.email, to, msg.as_string())

    # ── Draft (IMAP APPEND) ──────────────────────────────────────────────────

    def save_draft(self, to: str, subject: str, html: str, plain: str) -> None:
        """
        Save an email to the provider's Drafts folder via IMAP APPEND.
        Works for Gmail, Outlook, and M365.
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{self.display_name} <{self.email}>"
        msg["To"]      = to
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html,  "html"))
        raw = msg.as_bytes()

        host = _imap_host(self.provider)
        with imaplib.IMAP4_SSL(host, 993) as imap:
            imap.login(self.email, self.password)
            # Discover the Drafts folder name (varies by provider/locale)
            drafts_folder = _find_drafts_folder(imap)
            imap.append(
                drafts_folder,
                r"\Draft",
                imaplib.Time2Internaldate(time.time()),
                raw,
            )

    # ── Test ─────────────────────────────────────────────────────────────────

    def test_connection(self) -> dict:
        """Probe SMTP connectivity. Returns {"ok": bool, "message": str}."""
        try:
            host = _smtp_host(self.provider)
            with smtplib.SMTP(host, 587, timeout=10) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self.email, self.password)
            return {"ok": True, "email": self.email, "message": "SMTP connection successful ✓"}
        except Exception as exc:
            return {"ok": False, "email": self.email, "message": str(exc)}

    # ── Reply Check ──────────────────────────────────────────────────────────

    def check_replies(self) -> list[dict]:
        """
        Scan INBOX for UNSEEN messages via IMAP.
        Returns a list of reply dicts.
        """
        replies: list[dict] = []
        try:
            host = _imap_host(self.provider)
            with imaplib.IMAP4_SSL(host, 993) as imap:
                imap.login(self.email, self.password)
                imap.select("INBOX")
                _, msg_ids = imap.search(None, "UNSEEN")
                ids = msg_ids[0].split() if msg_ids[0] else []
                for mid in ids:
                    try:
                        _, data = imap.fetch(mid, "(RFC822)")
                        for part in data:
                            if not isinstance(part, tuple):
                                continue
                            msg = email_lib.message_from_bytes(part[1])

                            # Decode subject
                            raw_subj, encoding = decode_header(msg.get("subject", ""))[0]
                            if isinstance(raw_subj, bytes):
                                subject = raw_subj.decode(encoding or "utf-8", errors="replace")
                            else:
                                subject = raw_subj or ""

                            sender = msg.get("from", "")

                            # Extract plain-text snippet
                            body = ""
                            if msg.is_multipart():
                                for p in msg.walk():
                                    if p.get_content_type() == "text/plain":
                                        payload = p.get_payload(decode=True)
                                        if isinstance(payload, bytes):
                                            body = payload.decode(errors="replace")[:500]
                                        break
                            else:
                                payload = msg.get_payload(decode=True)
                                if isinstance(payload, bytes):
                                    body = payload.decode(errors="replace")[:500]

                            # Parse sender name/email
                            name_match  = re.match(r'^"?([^"<]+)"?\s*<', sender)
                            email_match = re.search(r"<([^>]+)>", sender)
                            from_name   = name_match.group(1).strip()  if name_match  else sender
                            from_email  = email_match.group(1)         if email_match else sender

                            replies.append({
                                "from_email":    from_email,
                                "from_name":     from_name,
                                "subject":       subject,
                                "snippet":       body.strip(),
                                "inbox_account": self.email,
                            })
                    except Exception as e:
                        logger.warning(f"IMAP parse error for msg {mid}: {e}")
        except Exception as exc:
            hint = ""
            exc_str = str(exc)
            if "LOGIN failed" in exc_str or "login failed" in exc_str.lower():
                hint = (
                    " — Microsoft 365 has disabled Basic Auth since Oct 2022. "
                    "Ensure an App Password is configured or SMTP AUTH is enabled "
                    "for this account in the M365 Admin Center."
                )
            elif "AUTHENTICATE failed" in exc_str:
                hint = " — Check that IMAP is enabled for this account in Gmail/M365 settings."
            logger.warning(f"IMAP reply-check failed for {self.email}: {exc_str}{hint}")
        return replies


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-ACCOUNT ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class EmailEngine:
    """
    Orchestrates multi-account sending with three strategies.

    accounts:    list of account dicts (id, email, app_password, provider, display_name)
    strategy:    "round_robin" | "parallel" | "batch_count"
    batch_size:  emails per account before switching (batch_count only)
    """

    def __init__(self, accounts: list[dict], strategy: str = "round_robin", batch_size: int = 5):
        self.accounts   = [ResendAccount(a) if a.get("provider") == "resend" else SMTPAccount(a)
                           for a in accounts]
        self.strategy   = strategy
        self.batch_size = batch_size
        self._rr_index  = 0
        self._lock      = asyncio.Lock()

    # ── Internal: next account for round-robin ────────────────────────────────

    async def _next_rr(self) -> "SMTPAccount | ResendAccount":
        async with self._lock:
            acc = self.accounts[self._rr_index % len(self.accounts)]
            self._rr_index += 1
            return acc

    # ── Public send method (dispatches to strategy) ───────────────────────────

    async def send_batch(
        self,
        jobs: list[dict],
        delay_seconds: int = 10,
        on_sent: Optional[asyncio.Queue] = None,
    ) -> list[dict]:
        """
        Send a batch of email jobs.

        Each job dict must have: to, subject, html, plain, lead_id.
        on_sent: asyncio.Queue to push send-result events for SSE.

        Returns list of result dicts: {lead_id, success, sent_from, error}.
        """
        if not self.accounts:
            raise RuntimeError("No active email accounts configured.")

        if self.strategy == "parallel":
            return await self._send_parallel(jobs, on_sent)
        elif self.strategy == "batch_count":
            return await self._send_batch_count(jobs, delay_seconds, on_sent)
        else:
            return await self._send_round_robin(jobs, delay_seconds, on_sent)

    # ── Round-Robin ──────────────────────────────────────────────────────────

    async def _send_round_robin(self, jobs, delay, on_sent):
        results = []
        for i, job in enumerate(jobs):
            acc = await self._next_rr()
            result = await self._dispatch_one(job, acc)
            results.append(result)
            if on_sent:
                await on_sent.put({"type": "lead_update", "data": result})
            if i < len(jobs) - 1:
                await asyncio.sleep(delay)
        return results

    # ── Parallel ─────────────────────────────────────────────────────────────

    async def _send_parallel(self, jobs, on_sent):
        """Assign jobs evenly across accounts and run all simultaneously."""
        n = len(self.accounts)
        buckets: list[list] = [[] for _ in range(n)]
        for i, job in enumerate(jobs):
            buckets[i % n].append(job)

        async def _worker(account: "SMTPAccount | ResendAccount", batch: list) -> list:
            out = []
            for j in batch:
                r = await self._dispatch_one(j, account)
                out.append(r)
                if on_sent:
                    await on_sent.put({"type": "lead_update", "data": r})
                await asyncio.sleep(2)  # slight stagger within parallel worker
            return out

        nested = await asyncio.gather(*[_worker(self.accounts[i], buckets[i]) for i in range(n)])
        return [r for sub in nested for r in sub]

    # ── Batch-Count ──────────────────────────────────────────────────────────

    async def _send_batch_count(self, jobs, delay, on_sent):
        """Send self.batch_size from Account A, then Account B, etc."""
        results = []
        acc_idx = 0
        sent_from_current = 0

        for i, job in enumerate(jobs):
            acc = self.accounts[acc_idx % len(self.accounts)]
            result = await self._dispatch_one(job, acc)
            results.append(result)
            sent_from_current += 1

            if on_sent:
                await on_sent.put({"type": "lead_update", "data": result})

            if sent_from_current >= self.batch_size:
                acc_idx += 1
                sent_from_current = 0

            if i < len(jobs) - 1:
                await asyncio.sleep(delay)

        return results

    # ── Core dispatcher ───────────────────────────────────────────────────────

    async def _dispatch_one(self, job: dict, account: "SMTPAccount | ResendAccount") -> dict:
        """Runs the blocking SMTP send in a thread pool."""
        lead_id = job.get("lead_id")
        # Inject sender details into the pre-generated HTML/plain templates
        html_final = job["html"].replace("{{SENDER_EMAIL}}", account.email).replace("{{SENDER_NAME}}", account.display_name or "Client Engagement Team")
        plain_final = job.get("plain", "").replace("{{SENDER_EMAIL}}", account.email).replace("{{SENDER_NAME}}", account.display_name or "Client Engagement Team")

        try:
            await asyncio.to_thread(
                account.send,
                job["to"],
                job["subject"],
                html_final,
                plain_final,
            )
            logger.info(f"✅ Sent to {job['to']} via {account.email}")
            return {
                "lead_id":   lead_id,
                "success":   True,
                "sent_from": account.email,
                "error":     None,
            }
        except Exception as exc:
            logger.error(f"❌ Failed {job['to']} via {account.email}: {exc}")
            return {
                "lead_id":   lead_id,
                "success":   False,
                "sent_from": account.email,
                "error":     str(exc)[:300],
            }

    # ── Reply Check ───────────────────────────────────────────────────────────

    async def check_all_replies(self) -> list[dict]:
        """Scan INBOX on SMTP accounts concurrently (Resend accounts skipped — send-only)."""
        tasks = [asyncio.to_thread(acc.check_replies) for acc in self.accounts]
        nested = await asyncio.gather(*tasks, return_exceptions=True)
        all_replies: list[dict] = []
        seen: set[str] = set()
        for result in nested:
            if isinstance(result, BaseException):
                logger.warning(f"Reply check failed: {result}")
                continue
            for r in result:
                key = r["from_email"] + "|" + r["subject"]
                if key not in seen:
                    seen.add(key)
                    all_replies.append(r)
        return all_replies

    # ── Account Test ─────────────────────────────────────────────────────────

    async def test_account(self, email: str) -> dict:
        for acc in self.accounts:
            if acc.email == email:
                return await asyncio.to_thread(acc.test_connection)
        return {"ok": False, "email": email, "message": "Account not found in engine"}
