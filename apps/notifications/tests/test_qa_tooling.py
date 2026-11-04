"""The local/Windows QA tooling: guards, idempotent seed, cross-process fake-provider state, simulated provider events,
SPF/DMARC advisory (never gating), the live-SES smoke command's opt-ins, the migration-graph invariant and a repo secret scan.
Nothing here performs any network I/O."""

import json
import os
import re
import subprocess
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings

from apps.notifications.mail import dns as dns_mod
from apps.notifications.mail import provisioning_service as svc
from apps.notifications.mail.fake import FakeTransport
from apps.notifications.models import EmailSenderIdentity, EmailSuppression, NotificationOutbox
from apps.stores.models import Store

QA_ENV = {"RASTISI_QA_MODE": "1"}


def run(*args, **kw):
    out = StringIO()
    call_command(*args, stdout=out, stderr=StringIO(), **kw)
    return out.getvalue()


class QaGuardTests(TestCase):
    def test_refused_without_debug(self):
        with mock.patch.dict(os.environ, QA_ENV), override_settings(DEBUG=False):
            with self.assertRaisesMessage(CommandError, "DEBUG=False"):
                run("seed_qa_notifications", password="x")

    def test_refused_without_qa_env(self):
        env = {k: v for k, v in os.environ.items() if k != "RASTISI_QA_MODE"}
        with mock.patch.dict(os.environ, env, clear=True), override_settings(DEBUG=True):
            with self.assertRaisesMessage(CommandError, "RASTISI_QA_MODE=1"):
                run("seed_qa_notifications", password="x")

    def test_refused_with_a_real_provider(self):
        with mock.patch.dict(os.environ, QA_ENV), override_settings(DEBUG=True, RASTISI_EMAIL_PROVIDER="ses"):
            for cmd, args in (("seed_qa_notifications", {"password": "x"}), ("qa_worker", {"once": True}),
                              ("qa_simulate_email_event", {})):
                with self.assertRaises(CommandError):
                    run(cmd, *(["bounce"] if cmd == "qa_simulate_email_event" else []), **args)


@override_settings(DEBUG=True, RASTISI_EMAIL_PROVIDER="fake")
class QaSeedTests(TestCase):
    def setUp(self):
        FakeTransport.reset()
        patcher = mock.patch.dict(os.environ, QA_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_seed_states_idempotent_and_isolated(self):
        info = json.loads(run("seed_qa_notifications", password="Qa-Pass-Test-1"))
        states = {s["slug"]: s["sender_status"] for s in info["stores"]}
        self.assertEqual(states, {"qa-no-domain": "inactive", "qa-pending": "pending", "qa-bike": "active", "qa-other": "active"})
        again = json.loads(run("seed_qa_notifications", password="Qa-Pass-Test-1"))
        self.assertEqual(states, {s["slug"]: s["sender_status"] for s in again["stores"]})
        self.assertEqual(Store.objects.filter(slug__startswith="qa-").count(), 4)
        self.assertEqual(EmailSenderIdentity.objects.get(store__slug="qa-bike").from_address, "info@mybikestore.test")

    def test_order_then_bounce_suppresses_and_duplicate_event_is_ignored(self):
        run("seed_qa_notifications", password="Qa-Pass-Test-1")
        self.assertIn("queued: order.created [email]", run("qa_place_order"))
        run("process_notification_outbox")
        row = NotificationOutbox.objects.get(event_key="order.created", channel="email")
        self.assertTrue(row.provider_ref)
        self.assertIn("ingested bounce", run("qa_simulate_email_event", "bounce", "--event-id", "e1"))
        self.assertIn("ignored", run("qa_simulate_email_event", "bounce", "--event-id", "e1"))
        self.assertEqual(EmailSuppression.objects.filter(store__slug="qa-bike", email="buyer@example.com").count(), 1)
        self.assertFalse(EmailSuppression.objects.filter(store__slug="qa-other").exists())  # tenant isolation

    def test_domain_verdict_flows_through_to_the_sender(self):
        run("seed_qa_notifications", password="Qa-Pass-Test-1")
        store = Store.objects.get(slug="qa-pending")
        self.assertEqual(svc.sync_sender_identity(store).status, "pending")
        run("qa_email_domain", "verify", "pendingstore.test")
        self.assertEqual(svc.sync_sender_identity(store).status, "active")


class FakeStateSharingTests(SimpleTestCase):
    def test_identity_state_is_shared_through_the_state_file_and_mail_is_dumped(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"RASTISI_FAKE_EMAIL_STATE_FILE": f"{tmp}/s.json", "RASTISI_FAKE_EMAIL_MAILBOX_DIR": f"{tmp}/mb"}
            with mock.patch.dict(os.environ, env):
                FakeTransport.reset()
                FakeTransport().create_identity("a.test")
                FakeTransport.identities.clear()               # simulate "another process"
                FakeTransport.verify("a.test")
                FakeTransport.identities.clear()
                self.assertTrue(FakeTransport().get_identity("a.test").verified_for_sending)
                from apps.notifications.mail.base import OutboundEmail

                outcome = FakeTransport().send(OutboundEmail("info@a.test", "A", "x@y.test", "موضوع", "متن", "<p>x</p>"))
                self.assertTrue(outcome.ok)
                names = sorted(p.suffix for p in Path(tmp, "mb").iterdir())
                self.assertEqual(names, [".html", ".json", ".txt"])
            FakeTransport.reset()


class AdvisoryTests(SimpleTestCase):
    def test_disabled_by_default_and_never_gates(self):
        got = dns_mod.advisory_checks("a.test", enabled=False)
        self.assertEqual({a["status"] for a in got}, {"not_checked"})
        self.assertEqual({a["kind"] for a in got}, {"spf", "dmarc"})

    def test_ok_missing_unknown(self):
        table = {"a.test": ["v=spf1 include:amazonses.com ~all"], "_dmarc.a.test": []}
        got = {a["kind"]: a["status"] for a in dns_mod.advisory_checks("a.test", enabled=True, txt_lookup=table.get)}
        self.assertEqual(got, {"spf": "ok", "dmarc": "missing"})
        got = {a["status"] for a in dns_mod.advisory_checks("a.test", enabled=True, txt_lookup=lambda n: None)}
        self.assertEqual(got, {"unknown"})


@override_settings(DEBUG=True)
class AdvisoryNeverBlocksSenderTests(TestCase):
    def test_active_sender_stays_active_with_missing_spf_dmarc(self):
        from apps.notifications.tests.helpers import give_active_sender

        store = Store.objects.create(name="s", slug="adv", status=Store.Status.ACTIVE)
        give_active_sender(store, "info@adv.test")
        with mock.patch.object(dns_mod, "_txt_values", return_value=[]), override_settings(RASTISI_EMAIL_DNS_ADVISORY_LOOKUP=True):
            d = svc.diagnostics(store)
        self.assertEqual(d.status, "active")
        self.assertEqual({a["status"] for a in d.advisory}, {"missing"})
        self.assertEqual(svc.active_sender_address(store), "info@adv.test")


class SesSmokeOptInTests(SimpleTestCase):
    def test_refuses_when_provider_is_not_ses(self):
        with override_settings(RASTISI_EMAIL_PROVIDER="fake"):
            with self.assertRaisesMessage(CommandError, "not 'ses'"):
                run("ses_smoke_test", from_address="info@a.test")

    def test_requires_explicit_confirmation_and_verified_identity_and_leaks_nothing(self):
        from apps.notifications.mail.base import IdentityState

        fake = mock.Mock()
        fake.get_identity.return_value = IdentityState(status="verified", verified_for_sending=True)
        with override_settings(RASTISI_EMAIL_PROVIDER="ses"), mock.patch(
                "apps.notifications.management.commands.ses_smoke_test.get_transport", return_value=fake):
            with self.assertRaisesMessage(CommandError, "--i-understand-this-sends-real-email"):
                run("ses_smoke_test", from_address="info@a.test")
            fake.send.assert_not_called()
            self.assertIn("provider status=verified", run("ses_smoke_test", "--check-only", from_address="info@a.test"))
            fake.send.assert_not_called()
            fake.get_identity.return_value = IdentityState(status="temporary_failure", error_type="ClientError")
            with self.assertRaisesMessage(CommandError, "FAILED"):   # an unverified / unreachable identity must NOT look like success
                run("ses_smoke_test", "--check-only", from_address="info@a.test")
            fake.get_identity.return_value = IdentityState(status="verified", verified_for_sending=True)
            fake.send.return_value = mock.Mock(ok=True, message_id="mid-1")
            out = run("ses_smoke_test", "--i-understand-this-sends-real-email", from_address="info@a.test")
            self.assertIn("mid-1", out)
            self.assertEqual(fake.send.call_args.args[0].to_address, "success@simulator.amazonses.com")


class MigrationGraphTests(TestCase):
    def test_notifications_has_exactly_one_migration_leaf(self):
        from django.db import connection
        from django.db.migrations.loader import MigrationLoader

        loader = MigrationLoader(connection, ignore_no_migrations=True)
        leaves = [n for n in loader.graph.leaf_nodes() if n[0] == "notifications"]
        self.assertEqual(len(leaves), 1, f"conflicting notifications migrations: {leaves}")


class SecretScanTests(SimpleTestCase):
    PATTERNS = (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
                re.compile(r"aws_secret_access_key\s*=\s*[A-Za-z0-9/+=]{30,}", re.I))
    ALLOW = {"AKIAIOSFODNN7EXAMPLE"}

    def test_no_credentials_committed_in_notification_code_docs_or_qa_tooling(self):
        root = Path(__file__).resolve().parents[3]
        files = subprocess.run(["git", "ls-files", "apps/notifications", "docs/notifications", "tools/windows-qa", "deploy"],
                               cwd=root, capture_output=True, text=True).stdout.split()
        self.assertTrue(files)
        hits = []
        for rel in files:
            path = root / rel
            if path.suffix in {".png", ".jpg", ".pyc"} or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in self.PATTERNS:
                hits += [f"{rel}: {m.group(0)[:8]}…" for m in pat.finditer(text) if m.group(0) not in self.ALLOW and not re.fullmatch(r"(AKIA|ASIA)X+", m.group(0))]
        self.assertEqual(hits, [])
