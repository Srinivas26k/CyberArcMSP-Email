import asyncio
import smtplib
import imaplib
import email as em
from email.message import EmailMessage
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class EmailDispatcher:
    def __init__(self, accounts: list[dict]):
        # accounts list format: [{"email": "...", "app_password": "...", "provider_type": "..."}]
        self.accounts = accounts
        self.queue = asyncio.Queue()
        self.current_index = 0
        self.lock = asyncio.Lock()

    async def add_email_job(self, to_email: str, subject: str, html_body: str, lead_id: int):
        await self.queue.put({
            "to": to_email,
            "subject": subject,
            "html": html_body,
            "lead_id": lead_id
        })

    async def start_workers(self, num_workers: int = 3):
        workers = [asyncio.create_task(self._worker()) for _ in range(num_workers)]
        return workers

    async def _worker(self):
        while True:
            job = await self.queue.get()
            try:
                await self.dispatch(job)
            except Exception as e:
                logger.error(f"Failed to dispatch to {job['to']}: {e}")
            finally:
                self.queue.task_done()

    async def dispatch(self, job: dict):
        # Round-robin
        async with self.lock:
            account = self.accounts[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.accounts)

        host = "smtp.gmail.com" if account["provider_type"] == "gmail" else "smtp-mail.outlook.com"
        port = 587

        msg = EmailMessage()
        msg["Subject"] = job["subject"]
        msg["From"] = account["email"]
        msg["To"] = job["to"]
        msg.set_content(job["html"], subtype="html")

        # Offload blocking SMTP call to a thread
        await asyncio.to_thread(self._send_smtp, host, port, account, msg)
        logger.info(f"Sent email to {job['to']} via {account['email']}")

    def _send_smtp(self, host, port, account, msg):
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(account["email"], account["app_password"])
            server.send_message(msg)


class IMAPReplyDetector:
    def __init__(self, accounts: list[dict]):
        self.accounts = accounts

    async def start_polling(self, interval: int = 60):
        while True:
            for acc in self.accounts:
                try:
                    await asyncio.to_thread(self.check_replies, acc)
                except Exception as e:
                    logger.error(f"IMAP poll error for {acc['email']}: {e}")
            await asyncio.sleep(interval)

    def check_replies(self, account: dict):
        host = "imap.gmail.com" if account["provider_type"] == "gmail" else "outlook.office365.com"
        with imaplib.IMAP4_SSL(host, 993) as imap:
            imap.login(account["email"], account["app_password"])
            imap.select("INBOX")
            
            # Use 'ALL' to bypass read/unread issues where devices mark it read early
            status, messages = imap.search(None, "ALL")
            if status == "OK" and messages[0]:
                for num in messages[0].split():
                    res, msg_data = imap.fetch(num, "(RFC822)")
                    if res == "OK":
                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                msg = em.message_from_bytes(response_part[1])
                                # Logic to parse headers (In-Reply-To, References, Form) 
                                # and update CampaignState in the database to 'replied' to stop automated follow-ups.
                                pass
