"""
email_engine.py — Multi-account SMTP/IMAP dispatcher for SRV AI Outreach.

Three sending strategies:
  • round_robin  — rotate across accounts one email at a time
  • parallel     — send concurrently from all accounts simultaneously
  • batch_count  — send N from Account A, then N from Account B, etc.

Supports Gmail (smtp.gmail.com:587) and Outlook (smtp-mail.outlook.com:587)
via App Passwords — no OAuth required.
"""
import asyncio
import email as email_lib
import imaplib
import logging
import re
import smtplib
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# PROVIDER ROUTING
# ─────────────────────────────────────────────────────────────────────────────

def _smtp_host(provider: str) -> str:
    return "smtp.gmail.com" if provider == "gmail" else "smtp-mail.outlook.com"

def _imap_host(provider: str) -> str:
    return "imap.gmail.com" if provider == "gmail" else "outlook.office365.com"


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
                                        if payload:
                                            body = payload.decode(errors="replace")[:500]
                                        break
                            else:
                                payload = msg.get_payload(decode=True)
                                if payload:
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
            logger.warning(f"IMAP error for {self.email}: {exc}")
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
        self.accounts   = [SMTPAccount(a) for a in accounts]
        self.strategy   = strategy
        self.batch_size = batch_size
        self._rr_index  = 0
        self._lock      = asyncio.Lock()

    # ── Internal: next account for round-robin ────────────────────────────────

    async def _next_rr(self) -> SMTPAccount:
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

        async def _worker(account: SMTPAccount, batch: list) -> list:
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

    async def _dispatch_one(self, job: dict, account: SMTPAccount) -> dict:
        """Runs the blocking SMTP send in a thread pool."""
        lead_id = job.get("lead_id")
        try:
            await asyncio.to_thread(
                account.send,
                job["to"],
                job["subject"],
                job["html"],
                job.get("plain", ""),
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
        """Scan INBOX on all accounts concurrently. Returns deduplicated reply list."""
        tasks = [asyncio.to_thread(acc.check_replies) for acc in self.accounts]
        nested = await asyncio.gather(*tasks, return_exceptions=True)
        all_replies: list[dict] = []
        seen: set[str] = set()
        for result in nested:
            if isinstance(result, Exception):
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
