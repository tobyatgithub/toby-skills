---
name: android-apk-release
description: Validate, preview, submit, publish, and monitor an existing Android APK release across Xiaomi GetApps, HONOR App Market, Tencent MyApp, OPPO App Market, vivo App Store, plus configurable self-hosted download servers when provided. Use when given an APK and release notes, when checking release status, or when completing an existing app update. This skill does not create store listings.
---

# Android APK Release

Release one existing Android APK to Xiaomi, HONOR, Tencent, OPPO, and vivo, plus an optional self-hosted download URL when configured. Keep credentials outside the skill and never print them.

Set `ANDROID_CI_CONFIG` to the runtime configuration directory; it defaults to `~/.config/android-ci`. Set `SKILL_DIR` to this skill's installed directory before running its CLI. Never commit the runtime configuration directory. See [README.md](README.md) for what each credential is and where to get it.

## Workflow

1. Run a read-only status check for the five stores (plus the self-hosted target when configured):

   ```bash
   uvx --from "$SKILL_DIR" android-apk-release status
   ```

2. Given an APK and a UTF-8 release-note file, build a release plan:

   ```bash
   uvx --from "$SKILL_DIR" android-apk-release plan \
     --apk /absolute/path/app-release.apk \
     --notes-file /absolute/path/release-notes.txt
   ```

   Treat any failed APK integrity, package, ABI, signature, version, credential, self-hosted configuration, or privacy check as blocking. Do not upload merely because the APK builds.

3. Show the user one compact preflight containing the exact release targets, package/version/ABI, release mode, APK path/SHA-256, exact release notes, self-hosted hosts/path/public URL/backup retention, and privacy-review result. Obtain a fresh explicit confirmation immediately before the first upload. A prior general instruction to publish is not this confirmation.

4. After confirmation, read [references/provider-api.md](references/provider-api.md) completely. Submit the five requested stores. Upload only the APK listed in the plan; do not modify existing listing text, screenshots, icon, categories, privacy URL, or rollout settings unless the user explicitly asked. If a store already has an unresolved rejection reason, verify that the candidate addresses it before resubmitting.

5. Skip this step when the self-hosted target is not configured. Otherwise, only after all five stores report that submission for review succeeded, publish the same confirmed bytes to the configured self-hosted servers. "Submission succeeded" means the submission API returned success; it does not mean store review was approved:

   ```bash
   uvx --from "$SKILL_DIR" android-apk-release ship-server \
     --plan /absolute/path/release-plan.json \
     --confirm CONFIRMATION_DIGEST
   ```

   The command stages the planned APK under the Makefile's fixed public filename, invokes `make ship-apk`, then requires matching SHA-256 values from every configured host and the cache-busted public URL.

6. Poll the read-only status endpoints and report each store separately as submitted, under review, approved, rejected, or unknown. Report the self-hosted target only after its two host checks and public download check pass; report it as not configured when it is not. Never describe a skipped or unavailable check as passed.

If the user asks to build as well as publish, build with the project's pinned Flutter/FVM version and its existing Gradle layout. Use the backed-up `key.properties` and `keys/` only as signing inputs; never display their contents. Run the same APK plan checks on the built artifact before any upload.

## Safety Rules

- Read secrets only from `ANDROID_CI_CONFIG`; never place secret values in commands, logs, plans, or responses.
- `status` and `plan` are read-only. Upload/update/submit calls are external writes and require the confirmation gate above.
- The configured Make target may immediately replace public files, create backups, and prune old backups. Read its exact targets and retention behavior and include them in the confirmation preview.
- Xiaomi has no sandbox. Do not test its push endpoint. Its `/dev/query` response describes update capability, not current audit status.
- Tencent's current status is `audit_status`; if it is approved, label a non-empty `audit_reason` as historical rather than current.
- Default to release immediately after approval. Use scheduled release only when the user supplies a date and timezone.
- Stop on partial provider failure. Do not run `ship-server` unless all five submission-for-review APIs returned success. If the user explicitly scopes a release to fewer stores, operate only on that subset and report excluded targets as untouched. Do not retry an upload or submission blindly; query current state first to avoid duplicate releases.

## Configuration

The script expects one value per file in `ANDROID_CI_CONFIG`: `package_name` and `signing_certificate_path`; the optional self-hosted target adds `app_workspace`, `self_hosted_apk_url`, and `self_hosted_backup_policy` (when `self_hosted_apk_url` is absent, plans cover the five stores only); Tencent `tencent_app_id`, `tencent_user_id`, `tencent_access_secret`; HONOR `honor_app_id`, `honor_client_id`, `honor_client_key`; Xiaomi `xiaomi_username`, `xiaomi_private_key`, `xiaomi_public.cer`, `xiaomi_privacy_url`, `xiaomi_icon_path`; OPPO `oppo_client_id`, `oppo_client_secret`; vivo `vivo_access_key`, `vivo_access_secret`. Keep Android signing inputs outside this skill.

Read [references/provider-api.md](references/provider-api.md) only for actual submission, provider-specific errors, or endpoint maintenance.
