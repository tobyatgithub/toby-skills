#!/usr/bin/env python3
"""Preflight and guarded deployment support for one Android release."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding


class ReleaseError(RuntimeError):
    pass


CONFIG_ROOT = (
    Path(os.environ.get("ANDROID_CI_CONFIG", Path.home() / ".config" / "android-ci"))
    .expanduser()
    .resolve()
)
STORES = ("xiaomi", "honor", "tencent", "oppo", "vivo")


def config(name: str) -> str:
    path = CONFIG_ROOT / name
    if not path.is_file():
        raise ReleaseError(f"Missing config file: {path}")
    # .env-style: blank lines and lines starting with '#' are ignored; the
    # remaining lines are the value (multi-line values such as PEM stay intact).
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    value = "\n".join(lines).strip()
    if not value:
        raise ReleaseError(f"Empty config file: {path}")
    return value


def post_form(
    url: str, values: dict[str, str], headers: dict[str, str] | None = None
) -> dict[str, Any]:
    data = urlencode(values).encode()
    request = Request(url, data=data, headers=headers or {}, method="POST")
    return request_json(request)


def get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    return request_json(Request(url, headers=headers or {}, method="GET"))


def request_json(request: Request) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        raise ReleaseError(f"HTTP {exc.code}: provider returned non-success") from exc
    except (URLError, TimeoutError) as exc:
        raise ReleaseError(
            f"Provider request failed: {exc.reason if isinstance(exc, URLError) else exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ReleaseError("Provider returned non-JSON data") from exc


def self_hosted_configured() -> bool:
    return (CONFIG_ROOT / "self_hosted_apk_url").is_file()


def self_hosted_status() -> dict[str, Any]:
    if not self_hosted_configured():
        return {"provider": "self_hosted", "ok": None, "status": "not_configured"}
    url = config("self_hosted_apk_url")
    try:
        with urlopen(Request(url, method="HEAD"), timeout=30) as response:
            return clean(
                {
                    "provider": "self_hosted",
                    "ok": 200 <= response.status < 300,
                    "url": url,
                    "http_status": response.status,
                    "content_length": as_int(response.headers.get("Content-Length")),
                    "last_modified": response.headers.get("Last-Modified"),
                    "etag": response.headers.get("ETag"),
                }
            )
    except HTTPError as exc:
        return {
            "provider": "self_hosted",
            "ok": False,
            "url": url,
            "http_status": exc.code,
        }
    except (URLError, TimeoutError) as exc:
        raise ReleaseError(
            f"Self-hosted status request failed: {exc.reason if isinstance(exc, URLError) else exc}"
        ) from exc


def recursive_pick(value: Any, *keys: str) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if key in value:
                return value[key]
        for child in value.values():
            found = recursive_pick(child, *keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = recursive_pick(child, *keys)
            if found is not None:
                return found
    return None


def as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def clean(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def xiaomi_status() -> dict[str, Any]:
    request_data = json.dumps(
        {"packageName": config("package_name"), "userName": config("xiaomi_username")},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    sig_data = json.dumps(
        {
            "sig": [
                {
                    "name": "RequestData",
                    "hash": hashlib.md5(request_data.encode()).hexdigest(),
                }
            ],
            "password": config("xiaomi_private_key"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    certificate = x509.load_pem_x509_certificate(
        (CONFIG_ROOT / "xiaomi_public.cer").read_bytes()
    )
    public_key = certificate.public_key()
    encrypted = b"".join(
        public_key.encrypt(sig_data.encode()[offset : offset + 117], padding.PKCS1v15())
        for offset in range(0, len(sig_data.encode()), 117)
    ).hex()
    response = post_form(
        "https://api.developer.xiaomi.com/devupload/dev/query",
        {"RequestData": request_data, "SIG": encrypted},
    )
    data = response.get("data") or response.get("resultData") or response
    return clean(
        {
            "provider": "xiaomi",
            "ok": as_int(response.get("result")) == 0,
            "code": response.get("result"),
            "message": response.get("message") or response.get("msg"),
            "app_name": recursive_pick(data, "appName"),
            "package_name": recursive_pick(data, "packageName"),
            "version_name": recursive_pick(data, "versionName"),
            "version_code": as_int(recursive_pick(data, "versionCode")),
            "can_update_version": recursive_pick(data, "updateVersion"),
            "can_update_info": recursive_pick(data, "updateInfo"),
            "audit_status": "not_exposed_by_api",
        }
    )


def tencent_signed_post(route: str) -> dict[str, Any]:
    values = {
        "app_id": config("tencent_app_id"),
        "pkg_name": config("package_name"),
        "timestamp": str(int(time.time())),
        "user_id": config("tencent_user_id"),
    }
    canonical = "&".join(f"{key}={value}" for key, value in sorted(values.items()))
    values["sign"] = hmac.new(
        config("tencent_access_secret").encode(), canonical.encode(), hashlib.sha256
    ).hexdigest()
    return post_form(f"https://p.open.qq.com/open_file/developer_api/{route}", values)


def tencent_status() -> dict[str, Any]:
    detail = tencent_signed_post("query_app_detail")
    update = tencent_signed_post("query_app_update_status")
    data = detail.get("data") or detail
    update_data = update.get("data") or update
    audit = recursive_pick(update_data, "audit_status") or recursive_pick(
        data, "audit_status"
    )
    reason = recursive_pick(update_data, "audit_reason") or recursive_pick(
        data, "audit_reason"
    )
    return clean(
        {
            "provider": "tencent",
            "ok": as_int(detail.get("ret")) == 0 and as_int(update.get("ret")) == 0,
            "code": update.get("ret"),
            "message": update.get("msg"),
            "app_name": recursive_pick(data, "app_name"),
            "package_name": recursive_pick(data, "pkg_name", "package_name"),
            "version_name": recursive_pick(data, "version_name"),
            "version_code": as_int(recursive_pick(data, "version_code")),
            "audit_status": audit,
            "audit_reason": reason,
            "audit_reason_context": "historical_when_approved"
            if as_int(audit) == 3 and reason
            else None,
        }
    )


def honor_status() -> dict[str, Any]:
    token_response = post_form(
        "https://iam.developer.honor.com/auth/token",
        {
            "grant_type": "client_credentials",
            "client_id": config("honor_client_id"),
            "client_secret": config("honor_client_key"),
        },
    )
    token = token_response.get("access_token") or recursive_pick(
        token_response.get("data"), "access_token"
    )
    if not token:
        raise ReleaseError("HONOR token response contained no access token")
    app_id = config("honor_app_id")
    release = get_json(
        "https://appmarket-openapi-drcn.cloud.honor.com/openapi/v1/publish/"
        f"get-app-current-release?appId={app_id}",
        {"Authorization": f"Bearer {token}"},
    )
    data = release.get("data") or release
    code = release.get("code")
    return clean(
        {
            "provider": "honor",
            "ok": code is None or str(code).lower() in {"0", "success"},
            "code": code,
            "message": release.get("message") or release.get("msg"),
            "app_id": app_id,
            "package_name": recursive_pick(data, "pkgName", "packageName")
            or config("package_name"),
            "version_name": recursive_pick(data, "versionName"),
            "version_code": as_int(recursive_pick(data, "versionCode")),
            "audit_status": recursive_pick(data, "auditResult", "audit_result"),
        }
    )


def oppo_signed(values: dict[str, str], access_token: str) -> dict[str, str]:
    signed = {
        **values,
        "access_token": access_token,
        "timestamp": str(int(time.time())),
    }
    canonical = "&".join(
        f"{key}={signed[key]}"
        for key in sorted(signed)
        if signed[key] is not None and str(signed[key]) != ""
    )
    signed["api_sign"] = hmac.new(
        config("oppo_client_secret").encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()
    return signed


def oppo_status() -> dict[str, Any]:
    token_values = urlencode(
        {
            "client_id": config("oppo_client_id"),
            "client_secret": config("oppo_client_secret"),
        }
    )
    token_response = get_json(
        f"https://oop-openapi-cn.heytapmobi.com/developer/v1/token?{token_values}"
    )
    if as_int(token_response.get("errno")) != 0:
        raise ReleaseError("OPPO token request failed")
    access_token = recursive_pick(token_response.get("data"), "access_token")
    if not access_token:
        raise ReleaseError("OPPO token response contained no access token")
    query = oppo_signed({"pkg_name": config("package_name")}, str(access_token))
    response = get_json(
        f"https://oop-openapi-cn.heytapmobi.com/resource/v1/app/info?{urlencode(query)}"
    )
    data = response.get("data") or response
    return clean(
        {
            "provider": "oppo",
            "ok": as_int(response.get("errno")) == 0,
            "code": response.get("errno"),
            "message": response.get("errmsg") or response.get("message"),
            "app_id": recursive_pick(data, "app_id"),
            "app_name": recursive_pick(data, "app_name"),
            "package_name": recursive_pick(data, "pkg_name", "package_name"),
            "version_name": recursive_pick(data, "version_name"),
            "version_code": as_int(recursive_pick(data, "version_code")),
            "audit_status": recursive_pick(data, "audit_status"),
            "audit_status_name": recursive_pick(data, "audit_status_name"),
            "sale_status": recursive_pick(data, "state"),
            "audit_reason": recursive_pick(data, "refuse_reason"),
            "audit_advice": recursive_pick(data, "refuse_advice"),
        }
    )


def vivo_signed_post(method: str, business: dict[str, str]) -> dict[str, Any]:
    values = {
        **business,
        "method": method,
        "access_key": config("vivo_access_key"),
        "timestamp": str(int(time.time() * 1000)),
        "format": "json",
        "v": "1.0",
        "sign_method": "hmac",
        "target_app_key": "developer",
    }
    canonical = "&".join(f"{key}={values[key]}" for key in sorted(values))
    values["sign"] = hmac.new(
        config("vivo_access_secret").encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()
    return post_form("https://developer-api.vivo.com.cn/router/rest", values)


def vivo_status() -> dict[str, Any]:
    response = vivo_signed_post(
        "app.query.details", {"packageName": config("package_name")}
    )
    if as_int(response.get("code")) != 0 or str(response.get("subCode")) != "0":
        raise ReleaseError("vivo app detail query failed")
    data = response.get("data") or {}
    audit = as_int(data.get("status"))
    sale = as_int(data.get("saleStatus"))
    audit_names = {
        1: "draft",
        2: "pending_review",
        3: "approved",
        4: "rejected",
        5: "withdrawn",
    }
    sale_names = {0: "pending_publish", 1: "published", 2: "unpublished"}
    return clean(
        {
            "provider": "vivo",
            "ok": True,
            "code": response.get("code"),
            "message": response.get("msg"),
            "app_name": data.get("appName"),
            "package_name": data.get("packageName"),
            "version_name": data.get("versionName"),
            "version_code": as_int(data.get("versionCode")),
            "audit_status": audit,
            "audit_status_name": audit_names.get(audit, "unknown"),
            "sale_status": sale,
            "sale_status_name": sale_names.get(sale, "unknown"),
            "audit_reason": data.get("unPassReason"),
            "release_mode": data.get("onlineType"),
            "compatible_device": data.get("compatibleDevice"),
        }
    )


def all_statuses() -> dict[str, Any]:
    providers = {
        "xiaomi": xiaomi_status,
        "honor": honor_status,
        "tencent": tencent_status,
        "oppo": oppo_status,
        "vivo": vivo_status,
    }
    stores: list[dict[str, Any]] = []
    for name in STORES:
        try:
            stores.append(providers[name]())
        except Exception as exc:  # noqa: BLE001 - isolate provider failures
            stores.append({"provider": name, "ok": False, "error": str(exc)})
    try:
        stores.append(self_hosted_status())
    except Exception as exc:  # noqa: BLE001 - keep store results on URL failure
        stores.append({"provider": "self_hosted", "ok": False, "error": str(exc)})
    return {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "package_name": config("package_name"),
        "stores": stores,
    }


def run_command(*args: str) -> str:
    result = subprocess.run(args, check=False, text=True, capture_output=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).splitlines()
        raise ReleaseError(
            f"Command failed: {Path(args[0]).name}: {detail[0] if detail else 'unknown error'}"
        )
    return result.stdout + result.stderr


def android_tool(name: str) -> str:
    direct = shutil.which(name)
    if direct:
        return direct
    roots = []
    if configured := os.environ.get("ANDROID_BUILD_TOOLS"):
        roots.append(Path(configured).expanduser())
    for variable in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        if sdk_root := os.environ.get(variable):
            roots.append(Path(sdk_root).expanduser() / "build-tools")
    roots.append(Path("/opt/homebrew/share/android-commandlinetools/build-tools"))
    candidates = sorted(
        (candidate for root in roots for candidate in root.glob(f"*/{name}")),
        reverse=True,
    )
    for candidate in candidates:
        if os.access(candidate, os.X_OK):
            return str(candidate)
    raise ReleaseError(f"Android build tool not found: {name}")


def inspect_apk(apk_value: str) -> dict[str, Any]:
    apk = Path(apk_value).expanduser().resolve()
    if not apk.is_file():
        raise ReleaseError(f"APK not found: {apk}")
    run_command("/usr/bin/unzip", "-tq", str(apk))
    badging = run_command(android_tool("aapt"), "dump", "badging", str(apk))
    signature = run_command(
        android_tool("apksigner"), "verify", "--verbose", "--print-certs", str(apk)
    )
    package_match = re.search(
        r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", badging
    )
    if not package_match:
        raise ReleaseError("Unable to read APK package/version with aapt")
    package_name, version_code, version_name = package_match.groups()
    native_code_match = re.search(r"^native-code:\s*(.+)$", badging, re.MULTILINE)
    abis = (
        re.findall(r"'([^']+)'", native_code_match.group(1))
        if native_code_match
        else []
    )
    expected_package = config("package_name")
    if package_name != expected_package:
        raise ReleaseError(
            f"APK package {package_name} does not match configured {expected_package}"
        )
    digest_match = re.search(
        r"Signer #1 certificate SHA-256 digest: ([0-9a-fA-F]+)", signature
    )
    if not digest_match:
        raise ReleaseError("Unable to read APK signing certificate digest")
    signer_digest = digest_match.group(1).lower()
    certificate_path = Path(config("signing_certificate_path")).expanduser().resolve()
    certificate = run_command(
        "/usr/bin/keytool", "-printcert", "-file", str(certificate_path)
    )
    expected_match = re.search(r"SHA256:\s*([0-9A-F:]+)", certificate, re.IGNORECASE)
    if not expected_match:
        raise ReleaseError("Unable to read configured signing certificate digest")
    if signer_digest != expected_match.group(1).replace(":", "").lower():
        raise ReleaseError(
            "APK signing certificate does not match configured release certificate"
        )
    content = apk.read_bytes()
    return {
        "path": str(apk),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "md5": hashlib.md5(content).hexdigest(),
        "package_name": package_name,
        "version_name": version_name,
        "version_code": int(version_code),
        "abis": abis,
        "signer_sha256": signer_digest,
        "zip_integrity": "passed",
        "apk_signature": "passed",
        "configured_signer_match": "passed",
    }


def make_settings() -> dict[str, Any]:
    workspace = Path(config("app_workspace")).expanduser().resolve()
    makefile = workspace / "Makefile"
    if not makefile.is_file():
        raise ReleaseError(f"Makefile not found: {makefile}")
    text = makefile.read_text(encoding="utf-8")

    def variable(name: str) -> str:
        match = re.search(rf"^{re.escape(name)}\s*=\s*(.+?)\s*$", text, re.MULTILINE)
        if not match:
            raise ReleaseError(f"Missing Makefile variable: {name}")
        return match.group(1)

    apk_name = variable("APK_NAME")
    remote_path = variable("REMOTE_PATH")
    hosts = variable("REMOTE_HOSTS").split()
    safe_name = re.compile(r"^[A-Za-z0-9._-]+$")
    safe_path = re.compile(r"^/[A-Za-z0-9._/-]+$")
    if not safe_name.fullmatch(apk_name) or not safe_path.fullmatch(remote_path):
        raise ReleaseError("Unsafe APK_NAME or REMOTE_PATH in Makefile")
    if not hosts or any(not safe_name.fullmatch(host) for host in hosts):
        raise ReleaseError("Unsafe or empty REMOTE_HOSTS in Makefile")
    return {
        "workspace": str(workspace),
        "make_target": "ship-apk",
        "apk_name": apk_name,
        "remote_hosts": hosts,
        "remote_path": remote_path,
        "public_url": config("self_hosted_apk_url"),
        "backup_policy": config("self_hosted_backup_policy"),
    }


def build_plan(apk_value: str, notes_file_value: str) -> dict[str, Any]:
    notes_file = Path(notes_file_value).expanduser().resolve()
    if not notes_file.is_file():
        raise ReleaseError(f"Release-note file not found: {notes_file}")
    notes = notes_file.read_text(encoding="utf-8").strip()
    if not notes:
        raise ReleaseError("Release notes are empty")
    if re.search(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", notes):
        raise ReleaseError("Release notes contain emoji, which Tencent rejects")
    if re.search(
        r"access[_ -]?secret|client[_ -]?key|private[_ -]?key|password\s*[:=]|-----BEGIN",
        notes,
        re.IGNORECASE,
    ):
        raise ReleaseError("Privacy review failed: release notes may contain a secret")

    apk = inspect_apk(apk_value)
    remote = all_statuses()
    version_checks = [
        {
            "provider": store["provider"],
            "current": store["version_code"],
            "candidate": apk["version_code"],
            "passed": apk["version_code"] > store["version_code"],
        }
        for store in remote["stores"]
        if store.get("version_code") is not None
    ]
    failed = [check["provider"] for check in version_checks if not check["passed"]]
    if failed:
        raise ReleaseError(
            f"APK versionCode is not greater than every readable live version: {', '.join(failed)}"
        )
    if self_hosted_configured():
        self_hosted = make_settings()
        if (
            self_hosted["apk_name"] == "app-arm64-v8a-release.apk"
            and "arm64-v8a" not in apk["abis"]
        ):
            raise ReleaseError(
                "Self-hosted target app-arm64-v8a-release.apk requires an APK containing arm64-v8a; "
                f"candidate ABIs: {apk['abis'] or ['none detected']}"
            )
    else:
        self_hosted = None
    plan: dict[str, Any] = {
        "schema": 3,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "operation": (
            "submit_store_updates_then_publish_self_hosted_apk"
            if self_hosted
            else "submit_store_updates"
        ),
        "targets": list(STORES) + (["self_hosted"] if self_hosted else []),
        "stores": list(STORES),
        "release_mode": "after_approval_immediate",
        "apk": apk,
        "release_notes": notes,
        "privacy_review": "passed_no_obvious_secret",
        "remote_status": remote,
        "version_checks": version_checks,
        "self_hosted_deployment": self_hosted or "not_configured",
        "execution_order": ["xiaomi", "honor", "tencent", "oppo", "vivo"]
        + (["self_hosted"] if self_hosted else []),
        "confirmation_required": True,
    }
    canonical = json.dumps(
        plan, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    plan["confirmation_digest"] = hashlib.sha256(canonical.encode()).hexdigest()
    directory = (
        Path(os.environ.get("ANDROID_CI_PLAN_DIR", CONFIG_ROOT / "release-plans"))
        .expanduser()
        .resolve()
    )
    directory.mkdir(mode=0o700, exist_ok=True)
    filename = f"{time.strftime('%Y%m%d-%H%M%S')}-v{apk['version_name']}.json"
    destination = directory / filename
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(plan, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return {"plan_path": str(destination), "plan": plan}


def verify_plan(plan_path_value: str, confirmation: str) -> dict[str, Any]:
    plan_path = Path(plan_path_value).expanduser().resolve()
    if not plan_path.is_file():
        raise ReleaseError(f"Release plan not found: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    stored_digest = plan.pop("confirmation_digest", None)
    canonical = json.dumps(
        plan, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    calculated_digest = hashlib.sha256(canonical.encode()).hexdigest()
    if not stored_digest or not hmac.compare_digest(stored_digest, calculated_digest):
        raise ReleaseError("Release plan digest is invalid")
    if not hmac.compare_digest(confirmation, stored_digest):
        raise ReleaseError("Confirmation digest does not match this release plan")
    plan["confirmation_digest"] = stored_digest
    if plan.get("schema") != 3 or "self_hosted" not in plan.get("targets", []):
        raise ReleaseError("Release plan does not include the self-hosted target")
    return plan


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def url_sha256(url: str) -> str:
    separator = "&" if "?" in url else "?"
    cache_busted = f"{url}{separator}android_ci_verify={int(time.time())}"
    digest = hashlib.sha256()
    try:
        with urlopen(Request(cache_busted, method="GET"), timeout=120) as response:
            if not 200 <= response.status < 300:
                raise ReleaseError(
                    f"Public APK verification returned HTTP {response.status}"
                )
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
    except HTTPError as exc:
        raise ReleaseError(f"Public APK verification returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise ReleaseError(
            f"Public APK verification failed: {exc.reason if isinstance(exc, URLError) else exc}"
        ) from exc
    return digest.hexdigest()


def ship_server(plan_path_value: str, confirmation: str) -> dict[str, Any]:
    plan = verify_plan(plan_path_value, confirmation)
    apk = Path(plan["apk"]["path"]).expanduser().resolve()
    if not apk.is_file():
        raise ReleaseError(f"Planned APK no longer exists: {apk}")
    local_digest = file_sha256(apk)
    if not hmac.compare_digest(local_digest, plan["apk"]["sha256"]):
        raise ReleaseError("APK SHA-256 changed after confirmation")

    current = make_settings()
    if current != plan["self_hosted_deployment"]:
        raise ReleaseError("Self-hosted Makefile settings changed after confirmation")
    with tempfile.TemporaryDirectory(prefix="android-ci-ship-") as temporary:
        staged = Path(temporary) / current["apk_name"]
        shutil.copy2(apk, staged)
        staged.chmod(0o644)
        if not hmac.compare_digest(file_sha256(staged), local_digest):
            raise ReleaseError("Staged APK SHA-256 mismatch")
        result = subprocess.run(
            [
                "make",
                "-C",
                current["workspace"],
                current["make_target"],
                f"APK_DIR={temporary}",
                f"APK_NAME={current['apk_name']}",
            ],
            check=False,
        )
        if result.returncode:
            raise ReleaseError(
                f"make ship-apk failed with exit code {result.returncode}"
            )

    remote_file = f"{current['remote_path'].rstrip('/')}/{current['apk_name']}"
    remote_checks = []
    for host in current["remote_hosts"]:
        output = run_command("ssh", host, "sha256sum", remote_file)
        remote_digest = output.split()[0].lower() if output.split() else ""
        passed = hmac.compare_digest(remote_digest, local_digest)
        remote_checks.append({"host": host, "sha256": remote_digest, "passed": passed})
    public_digest = url_sha256(current["public_url"])
    public_passed = hmac.compare_digest(public_digest, local_digest)
    if not all(item["passed"] for item in remote_checks) or not public_passed:
        raise ReleaseError(
            "Self-hosted upload completed but post-deployment SHA-256 verification failed"
        )
    return {
        "provider": "self_hosted",
        "ok": True,
        "url": current["public_url"],
        "sha256": local_digest,
        "remote_checks": remote_checks,
        "public_check": {"sha256": public_digest, "passed": public_passed},
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="android-apk-release")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "status",
        help="query five stores and the self-hosted APK without changing state",
    )
    plan = commands.add_parser(
        "plan", help="validate APK and create one release preview across all configured targets"
    )
    plan.add_argument("--apk", required=True)
    plan.add_argument("--notes-file", required=True)
    ship = commands.add_parser(
        "ship-server", help="run make ship-apk for an exactly confirmed release plan"
    )
    ship.add_argument("--plan", required=True)
    ship.add_argument("--confirm", required=True)
    return root


def main() -> None:
    try:
        arguments = parser().parse_args()
        if arguments.command == "status":
            result = all_statuses()
        elif arguments.command == "plan":
            result = build_plan(arguments.apk, arguments.notes_file)
        else:
            result = ship_server(arguments.plan, arguments.confirm)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except ReleaseError as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
