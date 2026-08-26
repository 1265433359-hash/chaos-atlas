# Reliable Email Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move SMTP delivery outside Codex's restricted command environment by enqueueing notifications locally and sending them from a Windows scheduled worker.

**Architecture:** `send_email_notification.py` validates and atomically writes a JSON message to a local outbox. A separate `notification_worker.py`, launched by Windows Task Scheduler, claims pending messages, sends them through QQ SMTP, retries transient failures, and moves successful messages to `sent`. The outbox contains only project/session/status/summary metadata and never credentials.

**Tech Stack:** Python standard library, JSON files, `smtplib`, Windows Task Scheduler, pytest.

---

### Task 1: Define queue behavior with tests

**Files:**
- Create: `tools/tests/test_email_notify_queue.py`
- Create: `tools/email_notify/notification_queue.py`

- [ ] Write tests for dynamic subject/body generation, atomic enqueue, retry metadata, and successful/failed moves.
- [ ] Run the focused tests and confirm they fail because the queue module does not exist.

### Task 2: Implement queue and worker

**Files:**
- Create: `tools/email_notify/notification_queue.py`
- Create: `tools/email_notify/notification_worker.py`
- Modify: `C:\Users\23741\.codex\skills\email-notify\scripts\send_email_notification.py`

- [ ] Implement JSON outbox paths under `%LOCALAPPDATA%\Codex\email-notify`.
- [ ] Make the notification command enqueue by default and retain `--direct` for worker/manual use.
- [ ] Implement one-pass worker processing with atomic claiming, bounded retries, and `sent`/`failed` archives.
- [ ] Run focused tests and syntax checks.

### Task 3: Update instructions

**Files:**
- Modify: `C:\Users\23741\.codex\skills\email-notify\SKILL.md`
- Modify: `C:\Users\23741\Desktop\XIAO\ChaosAtlas\AGENTS.md`

- [ ] Document that Codex enqueues locally and does not connect to SMTP.
- [ ] Document worker status and safe metadata constraints.

### Task 4: Install and verify the Windows worker

**Files:**
- Create: `tools/email_notify/install_worker.ps1`

- [ ] Persist the existing SMTP settings to the Windows User environment without printing the password.
- [ ] Register a per-minute scheduled task that runs the worker once.
- [ ] Enqueue a dry-run notification and verify the JSON payload.
- [ ] Run the worker with network permission and verify the message moves to `sent`.

### Task 5: Final verification

- [ ] Confirm the scheduled task exists and is enabled.
- [ ] Run the focused tests and syntax checks again.
- [ ] Send the completion notification through the queue and verify delivery.
