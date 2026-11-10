"""deploy/cron/run_job.sh fails closed, preserves the command's exit code, loads the environment in the documented order,
validates critical configuration without printing secrets and reports alert-delivery failures. Fully synthetic: a throw-away
application directory with a fake manage.py, a real (pip-less) virtualenv and a fake `mail`. No real job, database or provider."""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]
WRAPPER = ROOT / "deploy" / "cron" / "run_job.sh"
CRONTAB = ROOT / "deploy" / "cron" / "rastisi.crontab"
SECRET = "S3CR3T-VALUE-MUST-NEVER-BE-PRINTED"
DB_SECRET = "postgres://user:DBPASSWORD-MUST-NEVER-BE-PRINTED@db.internal/rastisi"

FAKE_MANAGE = """\
import os, sys
from pathlib import Path
here = Path(__file__).parent
(here / "ran.marker").write_text(" ".join(sys.argv[1:]))
print("PREFIX=" + sys.prefix)
print("CWD=" + os.getcwd())
print("FOO=" + os.environ.get("FOO", "<unset>"))
print("DB=" + os.environ.get("DATABASE_URL", "<unset>").split("@")[-1])
print("TZ=" + os.environ.get("TZ", "<unset>"))
if sys.argv[1:2] == ["fail"]:
    sys.exit(int(sys.argv[2]))
"""

FAKE_MAIL = """\
#!/bin/sh
# records "<args>" and stdin; exits with $FAKE_MAIL_RC (default 0)
dir="$(dirname "$0")"
printf '%s\\n' "$@" > "$dir/mail.args"
cat > "$dir/mail.stdin"
echo called >> "$dir/mail.calls"
exit "${FAKE_MAIL_RC:-0}"
"""


class WrapperBase(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rastisi-cron-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.app = self.tmp / "app"
        self.app.mkdir()
        (self.app / "manage.py").write_text(FAKE_MANAGE)
        self.venv = self.tmp / "venv"
        venv.EnvBuilder(with_pip=False, symlinks=True).create(self.venv)
        self.logs = self.tmp / "logs"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        mail = self.bin / "mail"
        mail.write_text(FAKE_MAIL)
        mail.chmod(mail.stat().st_mode | stat.S_IEXEC)
        self.env_file = self.tmp / "env"
        self.write_env()

    def write_env(self, extra="", **override):
        values = {
            "DJANGO_SECRET_KEY": SECRET, "DATABASE_URL": DB_SECRET, "DJANGO_DEBUG": "False",
            "RASTISI_ALERT_TO": "ops@alerts.rastisi.test",
        }
        values.update(override)
        lines = [f"{k}='{v}'" for k, v in values.items() if v is not None]
        self.env_file.write_text("\n".join(lines) + "\n" + extra)

    def run_wrapper(self, *args, env=None, drop=()):
        base = {
            "PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.tmp),
            "RASTISI_APP_DIR": str(self.app), "RASTISI_ENV_FILE": str(self.env_file),
            "RASTISI_VENV": str(self.venv), "RASTISI_LOG_DIR": str(self.logs),
        }
        base.update(env or {})
        for key in drop:
            base.pop(key, None)
        return subprocess.run(["bash", str(WRAPPER), *args], env=base, capture_output=True, text=True, timeout=60)

    def log(self, name="job"):
        path = self.logs / f"{name}.log"
        return path.read_text() if path.exists() else ""

    def ran(self):
        return (self.app / "ran.marker").exists()

    def mail_calls(self):
        path = self.bin / "mail.calls"
        return len(path.read_text().split()) if path.exists() else 0


class SuccessAndFailureTests(WrapperBase):
    def test_a_successful_job_runs_under_the_venv_python_in_the_app_dir_and_sends_no_alert(self):
        result = self.run_wrapper("job", "do_something", "--flag")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.app / "ran.marker").read_text(), "do_something --flag")
        log = self.log()
        self.assertIn("start job", log)
        self.assertRegex(log, r"end job rc=0")
        self.assertIn(f"PREFIX={self.venv}", log)                      # the virtualenv interpreter, not the system python
        self.assertIn(f"CWD={self.app}", log)
        self.assertIn("TZ=Asia/Tehran", log)
        self.assertEqual(self.mail_calls(), 0)
        self.assertFalse((self.logs / "ALERT_DELIVERY_FAILED").exists())

    def test_a_failing_command_keeps_its_exact_exit_code_is_logged_and_alerts_the_recipient(self):
        result = self.run_wrapper("job", "fail", "3")
        self.assertEqual(result.returncode, 3)
        self.assertIn("end job rc=3", self.log())
        self.assertEqual(self.mail_calls(), 1)
        args = (self.bin / "mail.args").read_text().split("\n")
        self.assertEqual(args[:3], ["-s", "rastisi job job failed (rc=3)", "ops@alerts.rastisi.test"])
        self.assertIn("end job rc=3", (self.bin / "mail.stdin").read_text())     # the last log lines are the alert body

    def test_other_exit_codes_pass_through_unchanged(self):
        for code in (1, 2, 42, 97):
            with self.subTest(code=code):
                self.assertEqual(self.run_wrapper("job", "fail", str(code)).returncode, code)

    def test_a_custom_alert_command_receives_words_subject_and_recipient_without_a_shell(self):
        custom = self.bin / "notify"
        custom.write_text('#!/bin/sh\nprintf "%s|" "$@" > "$(dirname "$0")/notify.args"\ncat >/dev/null\n')
        custom.chmod(0o755)
        result = self.run_wrapper("job", "fail", "2", env={"RASTISI_ALERT_CMD": "notify --channel ops; touch PWNED"})
        self.assertEqual(result.returncode, 2)
        args = (self.bin / "notify.args").read_text()
        self.assertTrue(args.startswith("--channel|ops;|touch|PWNED|rastisi job job failed (rc=2)|ops@alerts"), args)
        self.assertFalse(Path("PWNED").exists())


class FailClosedTests(WrapperBase):
    def test_missing_environment_file_stops_before_the_command_and_never_uses_defaults(self):
        self.env_file.unlink()
        result = self.run_wrapper("job", "do_something", env={"DATABASE_URL": "sqlite:///inherited.db", "RASTISI_ALERT_TO": "ops@alerts.rastisi.test"})
        self.assertEqual(result.returncode, 98)
        self.assertFalse(self.ran())
        self.assertIn("environment file is missing", result.stderr)
        self.assertEqual(self.mail_calls(), 1)                          # the failure is reported (alert path known from the cron env)

    def test_environment_file_with_a_syntax_error_stops_the_job(self):
        self.write_env(extra="if then fi (\n")
        result = self.run_wrapper("job", "do_something")
        self.assertEqual(result.returncode, 98)
        self.assertFalse(self.ran())

    def test_missing_virtualenv_stops_the_job_and_the_system_python_is_never_used(self):
        shutil.rmtree(self.venv)
        result = self.run_wrapper("job", "do_something")
        self.assertEqual(result.returncode, 99)
        self.assertFalse(self.ran())
        self.assertIn("system python is never used", result.stderr)

    def test_a_python_that_is_not_a_virtualenv_interpreter_is_refused(self):
        shutil.rmtree(self.venv)
        (self.venv / "bin").mkdir(parents=True)
        (self.venv / "bin" / "python").symlink_to(getattr(sys, "_base_executable", sys.executable))
        result = self.run_wrapper("job", "do_something")
        self.assertEqual(result.returncode, 99)
        self.assertFalse(self.ran())

    def test_incorrect_application_directory_stops_the_job(self):
        for path in (self.tmp / "nowhere", self.tmp):                    # missing, and a real directory without manage.py
            with self.subTest(path=path.name):
                result = self.run_wrapper("job", "do_something", env={"RASTISI_APP_DIR": str(path)})
                self.assertEqual(result.returncode, 97)
                self.assertFalse(self.ran())
                self.assertIn("application directory", result.stderr)

    def test_bad_usage_and_unsafe_job_names_are_refused(self):
        self.assertEqual(self.run_wrapper().returncode, 64)
        self.assertEqual(self.run_wrapper("job").returncode, 64)
        self.assertEqual(self.run_wrapper("../evil", "x").returncode, 64)
        self.assertFalse(self.ran())


class ConfigurationValidationTests(WrapperBase):
    def assertRefused(self, result, *names):
        self.assertEqual(result.returncode, 96, result.stderr)
        self.assertFalse(self.ran())
        for name in names:
            self.assertIn(name, result.stderr)
        for secret in (SECRET, "DBPASSWORD-MUST-NEVER-BE-PRINTED", "S3CR3T"):
            self.assertNotIn(secret, result.stdout + result.stderr + self.log() + self.log("_check"))

    def test_the_database_url_must_come_from_the_environment_file_and_be_postgresql(self):
        self.write_env(DATABASE_URL=None)
        self.assertRefused(self.run_wrapper("job", "x", env={"DATABASE_URL": "sqlite:///inherited-from-cron.db"}), "DATABASE_URL")
        self.write_env(DATABASE_URL="sqlite:///db.sqlite3")
        self.assertRefused(self.run_wrapper("job", "x"), "DATABASE_URL")

    def test_secret_key_debug_and_simulation_are_validated_without_printing_values(self):
        self.write_env(DJANGO_SECRET_KEY="")
        self.assertRefused(self.run_wrapper("job", "x"), "DJANGO_SECRET_KEY")
        self.write_env(DJANGO_DEBUG="True")
        self.assertRefused(self.run_wrapper("job", "x"), "DJANGO_DEBUG")
        self.write_env(DJANGO_DEBUG=None)
        self.assertRefused(self.run_wrapper("job", "x"), "DJANGO_DEBUG")                 # unset means Django's DEBUG default: refused
        self.write_env(PAYMENTS_SIMULATION_ENABLED="true")
        self.assertRefused(self.run_wrapper("job", "x"), "PAYMENTS_SIMULATION_ENABLED")

    def test_staging_may_explicitly_allow_debug(self):
        self.write_env(DJANGO_DEBUG="True")
        self.assertEqual(self.run_wrapper("job", "x", env={"RASTISI_JOB_ALLOW_DEBUG": "1"}).returncode, 0)

    def test_placeholder_or_missing_alert_recipient_and_missing_mail_command_are_refused(self):
        for recipient in ("CHANGE_ME_ALERT_RECIPIENT", "ops@example.com", "not-an-address", ""):
            with self.subTest(recipient=recipient):
                self.write_env(RASTISI_ALERT_TO=recipient)
                self.assertRefused(self.run_wrapper("job", "x"), "RASTISI_ALERT_TO")
        self.write_env()
        self.assertRefused(self.run_wrapper("job", "x", env={"RASTISI_ALERT_CMD": "no-such-mailer -s"}), "RASTISI_ALERT_CMD")

    def test_the_shipped_crontab_placeholders_are_rejected_until_the_operator_supplies_real_values(self):
        text = CRONTAB.read_text(encoding="utf-8")
        self.assertIn("RASTISI_ALERT_TO=CHANGE_ME_ALERT_RECIPIENT", text)
        self.assertIn("RASTISI_ALERT_CMD=\"mail -s\"", text)
        self.write_env(RASTISI_ALERT_TO=None)
        self.assertRefused(self.run_wrapper("job", "x", env={"RASTISI_ALERT_TO": "CHANGE_ME_ALERT_RECIPIENT"}), "RASTISI_ALERT_TO")

    def test_check_config_validates_and_runs_nothing(self):
        result = self.run_wrapper("--check-config")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("configuration OK", result.stdout)
        self.assertFalse(self.ran())
        self.assertEqual(self.mail_calls(), 0)
        shutil.rmtree(self.venv)
        self.assertEqual(self.run_wrapper("--check-config").returncode, 99)


class EnvironmentLoadingTests(WrapperBase):
    def test_the_environment_file_overrides_inherited_values_and_is_the_only_source_of_database_url(self):
        self.write_env(extra="FOO=from-file\n")
        result = self.run_wrapper("job", "x", env={"FOO": "from-cron", "DATABASE_URL": "sqlite:///inherited.db"})
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.log()
        self.assertIn("FOO=from-file", log)
        self.assertIn("DB=db.internal/rastisi", log)                     # the file's database, not the inherited one
        self.assertNotIn("inherited.db", log)

    def test_values_not_in_the_file_still_come_from_the_cron_environment(self):
        result = self.run_wrapper("job", "x", env={"FOO": "from-cron", "TZ": "UTC"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FOO=from-cron", self.log())
        self.assertIn("TZ=UTC", self.log())

    def test_the_alert_recipient_in_the_environment_file_wins_over_the_crontab(self):
        self.write_env(RASTISI_ALERT_TO="file@alerts.rastisi.test")
        self.run_wrapper("job", "fail", "1", env={"RASTISI_ALERT_TO": "cron@alerts.rastisi.test"})
        self.assertEqual((self.bin / "mail.args").read_text().split("\n")[2], "file@alerts.rastisi.test")

    def test_an_unset_variable_inside_the_environment_file_does_not_abort_the_wrapper(self):
        self.write_env(extra='DERIVED="${NOT_DEFINED_ANYWHERE}/x"\n')
        self.assertEqual(self.run_wrapper("job", "x").returncode, 0)


class AlertDeliveryTests(WrapperBase):
    def test_a_failed_alert_is_reported_loudly_and_the_job_exit_code_is_still_the_jobs(self):
        result = self.run_wrapper("job", "fail", "5", env={"FAKE_MAIL_RC": "1"})
        self.assertEqual(result.returncode, 5)
        self.assertIn("ALERT DELIVERY FAILED", result.stderr)             # cron mails stderr to MAILTO
        self.assertIn("ALERT DELIVERY FAILED", self.log())
        self.assertTrue((self.logs / "ALERT_DELIVERY_FAILED").exists())
        self.assertIn("end job rc=5", self.log())

    def test_the_failure_marker_is_cleared_by_the_next_delivered_alert(self):
        self.run_wrapper("job", "fail", "5", env={"FAKE_MAIL_RC": "1"})
        self.assertTrue((self.logs / "ALERT_DELIVERY_FAILED").exists())
        result = self.run_wrapper("job", "fail", "5")
        self.assertEqual(result.returncode, 5)
        self.assertFalse((self.logs / "ALERT_DELIVERY_FAILED").exists())

    def test_test_alert_delivers_and_reports_failure_with_exit_95(self):
        ok = self.run_wrapper("--test-alert")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(self.mail_calls(), 1)
        self.assertEqual((self.bin / "mail.args").read_text().split("\n")[:3], ["-s", "rastisi cron test alert", "ops@alerts.rastisi.test"])
        bad = self.run_wrapper("--test-alert", env={"FAKE_MAIL_RC": "1"})
        self.assertEqual(bad.returncode, 95)
        self.assertIn("ALERT DELIVERY FAILED", bad.stderr)
        self.assertFalse(self.ran())

    def test_an_environment_error_with_a_known_alert_path_is_alerted_not_only_logged(self):
        shutil.rmtree(self.venv)
        result = self.run_wrapper("job", "x", env={"RASTISI_ALERT_TO": "ops@alerts.rastisi.test"})
        self.assertEqual(result.returncode, 99)
        self.assertEqual(self.mail_calls(), 1)
        self.assertIn("NOT started", (self.bin / "mail.args").read_text())
        self.assertIn("NOT started", (self.logs / "_wrapper.log").read_text())


class UnchangedScheduleTests(SimpleTestCase):
    def test_job_names_schedules_and_the_wrapper_entry_point_are_unchanged(self):
        text = CRONTAB.read_text(encoding="utf-8")
        self.assertIn("JOB=/srv/rastisi/deploy/cron/run_job.sh", text)
        for line in (
            "*/5  * * * *  $JOB billing_webhooks  reprocess_billing_webhooks",
            "10   * * * *  $JOB billing_states    evaluate_subscription_states",
            "*/10 * * * *  $JOB billing_recon     reconcile_platform_payments --min-age-minutes 5",
            "0    4 * * *  $JOB billing_verify    verify_billing_consistency --strict",
        ):
            self.assertIn(line, text)
        self.assertEqual(sum(1 for l in text.splitlines() if "$JOB " in l and not l.startswith("#")), 20)
