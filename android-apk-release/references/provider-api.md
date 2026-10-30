# Provider API reference

This reference records the official REST flows for updating an existing app. It intentionally contains no credentials.

## Self-hosted download

- Workspace comes from `ANDROID_CI_CONFIG/app_workspace`.
- `make ship-apk` reads `APK_NAME`, `REMOTE_HOSTS`, and `REMOTE_PATH` from that workspace's Makefile. The candidate must contain `arm64-v8a`; it is published to every configured host at the fixed public filename.
- Inspect the target to determine whether it backs up, replaces, or prunes remote files. These are external and potentially destructive operations covered by the release confirmation.
- Run this target last, only after all five stores report that submission for review succeeded. This refers to a successful submission API response, not review approval. Stage the exact planned APK and pass `APK_DIR`/`APK_NAME` on the make command line; do not overwrite a checkout build artifact merely to satisfy the target.
- A zero make exit is insufficient because a per-host shell-chain failure can be masked by the loop. Verify SHA-256 independently over SSH on every configured host, then download the cache-busted public URL and verify the same SHA-256.

## Xiaomi GetApps

- Official guide: <https://dev.mi.com/xiaomihyperos/documentation/detail?pId=1134>
- Base: `https://api.developer.xiaomi.com/devupload`
- Read-only: `POST /dev/query`
- Submit: `POST /dev/push`, multipart form
- `RequestData` is the exact JSON string sent in the form. `SIG` contains MD5 entries for `RequestData`, `apk`, and any other attached files, plus the configured private-key/password string. Encrypt the SIG JSON with the X.509 certificate public key using RSA PKCS#1 v1.5 in 117-byte plaintext chunks; concatenate 128-byte ciphertext chunks and lowercase-hex encode.
- For an update use `synchroType=1`; attach the APK as `apk` and the configured 512x512 PNG as `icon`. Preserve current listing metadata. Set `appInfo.packageName`, current `appName`, `updateDesc`, and configured `privacyUrl`. Never guess missing listing fields.
- `/dev/query` fields `updateVersion` and `updateInfo` are capability flags. The API does not expose review status.

## HONOR App Market

- Official guide: <https://developer.honor.com/cn/doc/guides/101359>
- Token: `POST https://iam.developer.honor.com/auth/token`, OAuth client credentials
- Base: `https://appmarket-openapi-drcn.cloud.honor.com/openapi/v1/publish`
- Read-only: `get-app-id`, `get-app-detail`, `get-app-current-release`, `get-audit-result`
- Submit sequence: `get-file-upload-url` -> upload (`file-upload` or upload-by-URL) -> `update-file-info` -> update the existing locale's `newFeature` with `update-language-info` -> `submit-audit`.
- Bind only the newly uploaded APK and inherit unchanged assets/metadata. Re-read app detail before updates so required locale fields are preserved byte-for-byte. Default `releaseType=1` and `forceUpdate=0` unless explicitly changed.

## Tencent MyApp (应用宝)

- Official guide: <https://wikinew.open.qq.com/index.html#/iwiki/4015262492>
- Base: `https://p.open.qq.com/open_file/developer_api`
- Read-only: `POST /query_app_detail`, `POST /query_app_update_status`
- Upload: `POST /get_file_upload_info` with `file_type=apk` and the APK filename; synchronously PUT the entire file to returned `pre_sign_url`; retain returned `serial_number`.
- Submit: `POST /update_app` with `app_id`, `pkg_name`, `feature`, `deploy_type=1`, APK flags, serial number, and APK MD5. A universal 32/64-bit APK uses `apk32_flag=1` and `apk32_file_serial_number`; a 64-bit-only APK uses the corresponding `apk64_*` fields. Do not guess the ABI category: inspect the APK first.
- Common parameters are `user_id`, seconds `timestamp`, and `sign`. Build `sign` by sorting all unsigned parameters by ASCII key, joining `key=value` with `&`, then HMAC-SHA256 with `tencent_access_secret`; encode lowercase hex.
- `feature` must not contain emoji. `deploy_type=2` additionally requires a future Beijing-time seconds timestamp in `deploy_time`.
- Limits: 100 upload-info calls and 50 update calls per user per day.

## OPPO App Market

- Official guide: <https://open.oppomobile.com/new/developmentDoc/info?id=10998>
- Base: `https://oop-openapi-cn.heytapmobi.com`
- Token: `GET /developer/v1/token` with `client_id` and `client_secret`; cache the returned token for at most 48 hours and never log it.
- Read-only: signed `GET /resource/v1/app/info` with `pkg_name`.
- Upload: signed `GET /resource/v1/upload/get-upload-url`, then multipart `POST` the APK to the returned one-time URL with `type=apk` and its returned `sign`. Preserve the returned APK URL and calculate the local MD5.
- Submit: signed `POST /resource/v1/app/upd`. Re-read current app detail and preserve required listing metadata. Set `pkg_name`, candidate `version_code`, `apk_url` as a JSON array containing `url`, `md5`, and `cpu_code`, `update_desc`, and `online_type=1` for release immediately after approval. A universal APK uses `cpu_code=0`.
- Poll signed `POST /resource/v1/app/task-state` with `pkg_name` and `version_code` (the endpoint does not use a task ID); `task_state=1` is pending, `2` is successful, and `3` is failed. Do not repeat upload/update merely because task processing is pending.
- Sign every business request except token creation by sorting all non-empty public and business parameters except `api_sign` by ASCII key, joining `key=value` with `&`, and applying lowercase HMAC-SHA256 with `oppo_client_secret`.
- If current detail reports a rejection, inspect `refuse_reason` and `refuse_advice`. Do not resubmit a candidate that demonstrably leaves the rejection cause unchanged.

## vivo App Store

- Official guides: [common API and signing](https://dev.vivo.com.cn/documentCenter/doc/327), [APK upload](https://dev.vivo.com.cn/documentCenter/doc/332), [update submission](https://dev.vivo.com.cn/documentCenter/doc/343), [app detail](https://dev.vivo.com.cn/documentCenter/doc/346), and [status dictionary](https://dev.vivo.com.cn/documentCenter/doc/344).
- Base: `https://developer-api.vivo.com.cn/router/rest`
- Read-only: `app.query.details` with `packageName`.
- Upload: multipart `app.upload.apk.app` with `packageName`, `file`, and `fileMd5`; exclude the binary `file` field from the signature and retain the returned `serialnumber`.
- Submit: `app.sync.update.app` with `packageName`, candidate `versionCode`, upload `serialnumber` as `apk`, `fileMd5`, `updateDesc`, `onlineType=1`, and the current compatible-device value. A successful response creates the review submission.
- Every request includes `method`, `access_key`, millisecond `timestamp`, `format=json`, `v=1.0`, `sign_method=hmac`, and `target_app_key=developer`. Sort every signed field by ASCII key, join `key=value` with `&`, and apply lowercase HMAC-SHA256 with `vivo_access_secret`.
- Audit status values: `1` draft, `2` pending review, `3` approved, `4` rejected, `5` withdrawn. Sale status values: `0` pending publish, `1` published, `2` unpublished.
- The production API quota is limited. Upload and submit once, then use `app.query.details` for verification instead of blind retries.
