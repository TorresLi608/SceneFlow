"""Email sending service for verification codes and notifications."""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import os
import smtplib

from fastapi import HTTPException


logger = logging.getLogger(__name__)


def is_smtp_configured() -> bool:
    return bool(os.getenv("SCENEFLOW_SMTP_HOST", "").strip() and os.getenv("SCENEFLOW_SMTP_USER", "").strip())


def send_verification_email(email: str, code: str) -> None:
    """Send a 6-digit registration verification code to the given email address.

    In local development / unconfigured environments, the code is logged to the console
    so that developer workflows are never blocked.
    """
    host = os.getenv("SCENEFLOW_SMTP_HOST", "").strip()
    port_str = os.getenv("SCENEFLOW_SMTP_PORT", "").strip()
    user = os.getenv("SCENEFLOW_SMTP_USER", "").strip()
    password = os.getenv("SCENEFLOW_SMTP_PASSWORD", "").strip()
    sender = os.getenv("SCENEFLOW_SMTP_FROM", "").strip() or user or "SceneFlow <no-reply@sceneflow.ai>"
    use_ssl = os.getenv("SCENEFLOW_SMTP_SSL", "true").strip().lower() in {"1", "true", "yes"}

    if not host or not user:
        logger.info("[DEV EMAIL] ========================================")
        logger.info("[DEV EMAIL] Verification Code for %s: %s", email, code)
        logger.info("[DEV EMAIL] Valid for 5 minutes.")
        logger.info("[DEV EMAIL] ========================================")
        return

    port = int(port_str) if port_str.isdigit() else (465 if use_ssl else 587)

    subject = "【SceneFlow】注册验证码"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0d1117; color: #e6edf3; padding: 20px; }}
        .container {{ max-width: 520px; margin: 0 auto; background-color: #161b22; border-radius: 12px; border: 1px solid #30363d; padding: 32px; }}
        .brand {{ font-size: 20px; font-weight: bold; color: #58a6ff; margin-bottom: 20px; }}
        .title {{ font-size: 16px; margin-bottom: 12px; }}
        .code-box {{ background-color: #0d1117; border: 1px solid #388bfd; border-radius: 8px; padding: 18px; text-align: center; margin: 24px 0; }}
        .code {{ font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #58a6ff; font-family: monospace; }}
        .notice {{ font-size: 13px; color: #8b949e; line-height: 1.6; }}
        .footer {{ margin-top: 32px; font-size: 12px; color: #6e7681; border-top: 1px solid #21262d; padding-top: 16px; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="brand">SceneFlow</div>
        <div class="title">您正在注册 SceneFlow 账号，验证码如下：</div>
        <div class="code-box">
          <span class="code">{code}</span>
        </div>
        <div class="notice">
          <p>• 验证码有效期为 <strong>5 分钟</strong>，请尽快完成注册。</p>
          <p>• 如非本人操作，请忽略此邮件，请勿向任何人泄露此验证码。</p>
        </div>
        <div class="footer">
          此邮件为系统自动发出，请勿直接回复。
        </div>
      </div>
    </body>
    </html>
    """

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = email

    part_text = MIMEText(f"【SceneFlow】您的注册验证码为：{code}，5分钟内有效。如非本人操作请忽略。", "plain", "utf-8")
    part_html = MIMEText(html_content, "html", "utf-8")
    message.attach(part_text)
    message.attach(part_html)

    try:
        if use_ssl or port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=10) as server:
                if password:
                    server.login(user, password)
                server.sendmail(sender, [email], message.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls()
                if password:
                    server.login(user, password)
                server.sendmail(sender, [email], message.as_string())
        logger.info("verification email sent successfully to %s", email)
    except Exception as exc:
        logger.error("failed to send verification email to %s: %s", email, exc)
        raise HTTPException(500, "邮件发送失败，请稍后重试") from exc
