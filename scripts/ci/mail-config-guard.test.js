// Regression tests for deploy/mail-config-guard.sh, run against a fake `az` on PATH.
// Read-only by construction: nothing here talks to Azure.
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const GUARD = path.resolve(__dirname, '..', '..', 'deploy', 'mail-config-guard.sh');

// Fake az: `containerapp show -n <svc> --query <q> -o tsv`.
//   FAKE_<SVC>_MISSING=1            → ResourceNotFound
//   FAKE_<SVC>_<VAR>=<value>        → live env value (unset → empty output, like az for null)
//   FAKE_WARN=1                     → az-extension WARNING lines on stderr for every call
//   FAKE_FAIL=show|env              → that call fails with a non-not-found error
//   FAKE_MULTILINE=1                → env query prints two lines
const FAKE_AZ = `#!/usr/bin/env bash
svc=""; query=""
while [ $# -gt 0 ]; do
  case "$1" in -n) svc="$2"; shift;; --query) query="$2"; shift;; esac; shift
done
key="$(printf '%s' "$svc" | tr 'a-z-' 'A-Z_')"
if [ "\${FAKE_WARN:-0}" = 1 ]; then
  echo "WARNING: The command requires the extension containerapp. It will be installed first." >&2
  echo "WARNING: This command is in preview and under development." >&2
fi
missing="FAKE_\${key}_MISSING"
if [ "\${!missing:-0}" = 1 ]; then
  echo "ERROR: (ResourceNotFound) The Resource '$svc' was not found." >&2; exit 3
fi
if [ "$query" = name ]; then
  [ "\${FAKE_FAIL:-}" = show ] && { echo "ERROR: Please run 'az login' to setup account." >&2; exit 1; }
  echo "$svc"; exit 0
fi
[ "\${FAKE_FAIL:-}" = env ] && { echo "ERROR: (AuthorizationFailed) not authorized" >&2; exit 1; }
var="$(printf '%s' "$query" | sed -nE "s/.*name=='([A-Z_]+)'.*/\\\\1/p")"
[ "\${FAKE_MULTILINE:-0}" = 1 ] && { printf 'graph\\nnull\\n'; exit 0; }
val="FAKE_\${key}_\${var}"
[ -n "\${!val:-}" ] && printf '%s\\n' "\${!val}"
exit 0
`;

const BIRTHDAY_LIVE = {
  FAKE_BIRTHDAY_API_MAIL_TRANSPORT: 'graph',
  FAKE_BIRTHDAY_API_MAIL_POLICY: 'internal_allowlist',
  FAKE_BIRTHDAY_API_MAIL_SHARED_MAILBOX: 'sender@example.com',
};
const PARAMS_MATCH = `
param birthdayMailTransport = 'graph'
param birthdayMailPolicy = 'internal_allowlist'
param birthdayMailSharedMailbox = 'sender@example.com'
`;

function run({ env = {}, params = PARAMS_MATCH } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mail-guard-'));
  const bin = path.join(dir, 'bin');
  fs.mkdirSync(bin);
  fs.writeFileSync(path.join(bin, 'az'), FAKE_AZ, { mode: 0o755 });
  const paramFile = path.join(dir, 'main.test.bicepparam');
  fs.writeFileSync(paramFile, params);
  const r = spawnSync('bash', [GUARD, 'rg-test', paramFile], {
    encoding: 'utf8',
    env: { PATH: `${bin}:${process.env.PATH}`, HOME: dir, ...env },
  });
  fs.rmSync(dir, { recursive: true, force: true });
  return { code: r.status, out: r.stdout, err: r.stderr };
}

test('matching configuration passes', () => {
  const r = run({ env: BIRTHDAY_LIVE });
  assert.equal(r.code, 0, r.err);
  assert.match(r.out, /birthday-api: mail configuration unchanged \(transport='graph'\)/);
  assert.match(r.out, /platform-api: mail configuration unchanged \(transport='<unset>'\)/);
});

test('Azure CLI WARNING lines on stderr are not mistaken for drift (regression)', () => {
  const r = run({ env: { ...BIRTHDAY_LIVE, FAKE_WARN: '1' } });
  assert.equal(r.code, 0, r.err);
  assert.doesNotMatch(r.err, /would become/);
});

test('genuine drift stops the deployment', () => {
  const r = run({ env: { ...BIRTHDAY_LIVE, FAKE_BIRTHDAY_API_MAIL_TRANSPORT: 'null' } });
  assert.equal(r.code, 1);
  assert.match(r.err, /birthday-api MAIL_TRANSPORT: live='null' would become 'graph'/);
  assert.match(r.err, /Stopping/);
});

test('genuine drift is still caught when warnings are present', () => {
  const r = run({ env: { ...BIRTHDAY_LIVE, FAKE_WARN: '1', FAKE_BIRTHDAY_API_MAIL_POLICY: 'open' } });
  assert.equal(r.code, 1);
  assert.match(r.err, /birthday-api MAIL_POLICY: live='open' would become 'internal_allowlist'/);
});

test('turning mail off is drift too (live set, param empty)', () => {
  const r = run({ env: BIRTHDAY_LIVE, params: '' });
  assert.equal(r.code, 1);
  assert.match(r.err, /birthday-api MAIL_TRANSPORT: live='graph' would become '<unset>'/);
});

test('az failure on the resource check fails closed', () => {
  const r = run({ env: { ...BIRTHDAY_LIVE, FAKE_WARN: '1', FAKE_FAIL: 'show' } });
  assert.equal(r.code, 1);
  assert.match(r.err, /cannot read birthday-api from Azure \(ERROR: Please run 'az login'/);
});

test('az failure reading an env value fails closed, reporting the error not the warning', () => {
  const r = run({ env: { ...BIRTHDAY_LIVE, FAKE_WARN: '1', FAKE_FAIL: 'env' } });
  assert.equal(r.code, 1);
  assert.match(r.err, /cannot read birthday-api MAIL_TRANSPORT from Azure \(ERROR: \(AuthorizationFailed\)/);
});

test('malformed (multi-line) result fails closed', () => {
  const r = run({ env: { ...BIRTHDAY_LIVE, FAKE_MULTILINE: '1' } });
  assert.equal(r.code, 1);
  assert.match(r.err, /malformed az result/);
});

test('a service that is not deployed is skipped, not treated as a failure', () => {
  const r = run({ env: { ...BIRTHDAY_LIVE, FAKE_PLATFORM_API_MISSING: '1' } });
  assert.equal(r.code, 0, r.err);
  assert.match(r.out, /platform-api: not deployed yet/);
});

test('Birthday and platform-api are protected independently', () => {
  const platformDrift = run({ env: { ...BIRTHDAY_LIVE, FAKE_PLATFORM_API_MAIL_TRANSPORT: 'graph' } });
  assert.equal(platformDrift.code, 1);
  assert.match(platformDrift.err, /platform-api MAIL_TRANSPORT: live='graph' would become '<unset>'/);
  assert.doesNotMatch(platformDrift.err, /birthday-api MAIL_/);
  assert.match(platformDrift.out, /birthday-api: mail configuration unchanged/);

  const birthdayDrift = run({ env: { ...BIRTHDAY_LIVE, FAKE_BIRTHDAY_API_MAIL_SHARED_MAILBOX: 'other@example.com' } });
  assert.equal(birthdayDrift.code, 1);
  assert.doesNotMatch(birthdayDrift.err, /platform-api MAIL_/);
  assert.match(birthdayDrift.out, /platform-api: mail configuration unchanged/);
});

test('the explicit ALLOW_MAIL_CONFIG_CHANGE=1 override is unchanged', () => {
  const r = run({ env: { ...BIRTHDAY_LIVE, FAKE_BIRTHDAY_API_MAIL_TRANSPORT: 'null', ALLOW_MAIL_CONFIG_CHANGE: '1' } });
  assert.equal(r.code, 0);
  assert.match(r.out, /ALLOW_MAIL_CONFIG_CHANGE=1: proceeding/);
});
