import asyncio
import os
import time
from dotenv import load_dotenv

from server import O365Inbox, load_o365_accounts

load_dotenv()

async def test_email_flow():
    accounts = load_o365_accounts()
    if not accounts:
        print("❌ No O365 accounts configured in .env")
        return

    # Use the third configured account (brian.johnson)
    config = accounts[2]
    inbox = O365Inbox(config)
    
    print(f"📧 Using Sender Account: {inbox.email}")
    
    # Prompt for destination email
    dest_email = input("Enter destination email address to send the test email to: ").strip()
    if not dest_email:
        print("❌ Destination email required.")
        return

    subject = f"Test Email from SRV Outreach ({int(time.time())})"
    html_body = f"""
    <p>Hi,</p>
    <p>This is a test email sent from the SRV Outreach system to verify sending and reply detection.</p>
    <p>Please reply to this email so we can detect it and send an auto-reply back.</p>
    <p>Best,<br>SRV Tester</p>
    """
    plain_body = "Hi,\n\nThis is a test email sent from the SRV Outreach system to verify sending and reply detection.\nPlease reply to this email so we can detect it and send an auto-reply back.\n\nBest,\nSRV Tester"
    
    print(f"🚀 Sending initial test email to '{dest_email}'...")
    try:
        inbox.send(dest_email, subject, html_body, plain_body)
        print("✅ Email sent successfully.")
    except Exception as e:
        print(f"❌ Failed to send initial email: {e}")
        return

    print("⏳ Waiting for a reply... (Checking every 10 seconds)")
    print("   Please open your inbox for '{}' and reply to the email.".format(dest_email))
    
    # Wait for reply loop
    target_subject_part = f"Re: {subject}"
    
    import imaplib
    import email as em
    from email.header import decode_header
    
    def check_replies_all(config) -> list[dict]:
        replies = []
        try:
            with imaplib.IMAP4_SSL("outlook.office365.com", 993) as imap:
                imap.login(config["email"], config["password"])
                imap.select("INBOX")
                status, messages = imap.search(None, "ALL") # search ALL emails
                if status == "OK":
                    for num in messages[0].split():
                        res, msg_data = imap.fetch(num, "(RFC822)")
                        if res == "OK":
                            for response_part in msg_data:
                                if isinstance(response_part, tuple):
                                    msg_obj = em.message_from_bytes(response_part[1])
                                    subject, encoding = decode_header(msg_obj["Subject"])[0]
                                    if isinstance(subject, bytes):
                                        subject = subject.decode(encoding if encoding else "utf-8")
                                    
                                    sender = msg_obj.get("From", "")
                                    body = ""
                                    if msg_obj.is_multipart():
                                        for part in msg_obj.walk():
                                            content_type = part.get_content_type()
                                            if content_type == "text/plain":
                                                body = part.get_payload(decode=True).decode()
                                                break
                                    else:
                                        body = msg_obj.get_payload(decode=True).decode()
                                    
                                    replies.append({
                                        "from": sender,
                                        "subject": subject,
                                        "body": body
                                    })
        except Exception as e:
            print(f"IMAP Error: {e}")
        return replies

    while True:
        try:
            print("   -> Checking inbox for replies (Checking ALL emails)...")
            # Call custom function
            replies = check_replies_all(config)
            
            for reply in replies:
                sender = reply.get("from", "")
                reply_subject = reply.get("subject", "")
                body = reply.get("body", "")
                
                # Check if this reply matches our destination email AND matches the subject
                if dest_email.lower() in sender.lower() and "Re:" in reply_subject and str(int(time.time()))[:5] in reply_subject:
                    print("\n🎉 REPLIED! A reply was detected from your address:")
                    print("-" * 50)
                    print(f"From:    {sender}")
                    print(f"Subject: {reply_subject}")
                    print(f"Body:    {body.strip()[:100]}...") # truncate
                    print("-" * 50)
                    
                    # Send an auto-reply
                    auto_reply_subject = f"Re: {reply_subject}"
                    auto_reply_html = f"<p>Awesome!</p><p>We received your reply. Automatic reply detection is working perfectly.</p><p>Best,</p>"
                    auto_reply_plain = "Awesome!\nWe received your reply. Automatic reply detection is working perfectly.\nBest,"

                    print(f"🚀 Sending automatic reply back to '{dest_email}'...")
                    inbox.send(dest_email, auto_reply_subject, auto_reply_html, auto_reply_plain)
                    print("✅ Automated reply sent successfully! Test complete.")
                    
                    return # Exit the test
                    
            await asyncio.sleep(10) # wait 10 seconds before checking again
        except KeyboardInterrupt:
            print("\n⏹️ Test cancelled by user.")
            break
        except Exception as e:
            print(f"⚠️ Error checking inbox: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(test_email_flow())
    except KeyboardInterrupt:
        pass
