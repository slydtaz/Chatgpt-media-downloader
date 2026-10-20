from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


API_ROOT = "https://www.virustotal.com/api/v3"
VT_HOSTS = {"www.virustotal.com", "virustotal.com"}
SMALL_UPLOAD_LIMIT = 32 * 1024 * 1024
MAX_UPLOAD_BYTES = 650 * 1024 * 1024
REQUEST_INTERVAL_SECONDS = 16.5
MAX_POLL_ROUNDS = 12
MAX_WAIT_SECONDS = 22 * 60
_last_request_at = 0.0


class _VerifiedVirusTotalRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urlsplit(newurl)
        if parts.scheme != "https" or parts.hostname not in VT_HOSTS or parts.port not in {None, 443}:
            raise HTTPError(req.full_url, code, "Untrusted VirusTotal redirect destination blocked", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _wait_for_rate_limit() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
    _last_request_at = time.monotonic()


def _api_json(
    url: str,
    api_key: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    content_type: str = "application/json",
    timeout: float = 180.0,
    max_retries: int = 3,
) -> dict:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in VT_HOSTS or parsed.port not in {None, 443}:
        raise RuntimeError("Refusing a VirusTotal request outside the verified HTTPS host.")
    opener = build_opener(_VerifiedVirusTotalRedirects())
    for attempt in range(max_retries + 1):
        _wait_for_rate_limit()
        request = Request(
            url,
            data=body,
            headers={
                "x-apikey": api_key,
                "accept": "application/json",
                "Content-Type": content_type,
            },
            method=method,
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise RuntimeError("VirusTotal API response exceeded the safe size limit.")
            try:
                result = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("VirusTotal returned invalid JSON.") from exc
            if not isinstance(result, dict):
                raise RuntimeError("VirusTotal returned an unexpected response.")
            return result
        except HTTPError as exc:
            if exc.code == 429 and attempt < max_retries:
                try:
                    wait = max(REQUEST_INTERVAL_SECONDS, min(120.0, float(exc.headers.get("Retry-After", "30"))))
                except (TypeError, ValueError):
                    wait = 30.0
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"VirusTotal API returned HTTP {exc.code}; response not interpreted as clean."
            ) from None
        except (URLError, TimeoutError, OSError) as exc:
            if attempt < max_retries:
                time.sleep(min(30.0, 3.0 * (attempt + 1)))
                continue
            raise RuntimeError(
                f"VirusTotal request failed ({type(exc).__name__}); no clean verdict is implied."
            ) from None
    raise RuntimeError("VirusTotal API retry limit was reached.")


def _multipart_body(path: Path) -> tuple[bytes, str]:
    boundary = "----CGMDVirusTotal" + uuid.uuid4().hex
    filename = path.name.replace('"', "_")
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    payload = path.read_bytes()
    suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
    return prefix + payload + suffix, f"multipart/form-data; boundary={boundary}"


def _upload_url(api_key: str) -> str:
    response = _api_json(f"{API_ROOT}/files/upload_url", api_key)
    destination = response.get("data")
    if not isinstance(destination, str) or not destination:
        raise RuntimeError("VirusTotal did not return a large-file upload URL.")
    parts = urlsplit(destination)
    if parts.hostname not in VT_HOSTS:
        raise RuntimeError("VirusTotal returned an unexpected upload host; upload stopped.")
    if parts.scheme == "http":
        destination = urlunsplit(("https", parts.netloc, parts.path, parts.query, ""))
    elif parts.scheme != "https":
        raise RuntimeError("VirusTotal returned a non-HTTPS upload URL; upload stopped.")
    return destination


def submit_file(path: Path, api_key: str) -> str:
    if not path.is_file():
        raise RuntimeError(f"Required scan sample is missing: {path.name}")
    size = path.stat().st_size
    if size <= 0 or size > MAX_UPLOAD_BYTES:
        raise RuntimeError(f"{path.name} has size {size} bytes, outside the supported size range.")
    url = _upload_url(api_key) if size > SMALL_UPLOAD_LIMIT else f"{API_ROOT}/files"
    body, content_type = _multipart_body(path)
    uploaded = _api_json(
        url, api_key, method="POST", body=body, content_type=content_type,
        timeout=max(180.0, size / (512 * 1024)),
    )
    data = uploaded.get("data")
    analysis_id = data.get("id") if isinstance(data, dict) else None
    if not isinstance(analysis_id, str) or not analysis_id:
        raise RuntimeError(f"VirusTotal did not provide an analysis ID for {path.name}.")
    return analysis_id


def summarize_analysis(name: str, attributes: dict) -> tuple[str, list[str], bool]:
    stats = attributes.get("stats") or {}
    if not isinstance(stats, dict):
        stats = {}
    values = {key: int(stats.get(key, 0) or 0) for key in (
        "malicious", "suspicious", "undetected", "harmless", "timeout", "failure", "type-unsupported"
    )}
    result_line = (
        f"RESULT: {name}; malicious={values['malicious']}; suspicious={values['suspicious']}; "
        f"undetected={values['undetected']}; harmless={values['harmless']}; "
        f"timeout={values['timeout']}; failure={values['failure']}; "
        f"type-unsupported={values['type-unsupported']}; status=completed"
    )
    results = attributes.get("results") or {}
    detection_lines = []
    if isinstance(results, dict):
        for engine, value in sorted(results.items(), key=lambda pair: str(pair[0]).casefold()):
            if not isinstance(value, dict):
                continue
            category = str(value.get("category") or "").lower()
            if category not in {"malicious", "suspicious"}:
                continue
            fields = {
                "engine": engine,
                "category": category,
                "result": value.get("result") or "(no label supplied)",
                "method": value.get("method") or "unknown",
                "engine_version": value.get("engine_version") or "unknown",
                "engine_update": value.get("engine_update") or "unknown",
            }
            clean_fields = []
            for key, item in fields.items():
                value_text = " ".join(str(item).replace("\r", " ").replace("\n", " ").split())[:240]
                clean_fields.append(f"{key}={value_text}")
            detection_lines.append(f"DETECTION: {name}; " + "; ".join(clean_fields))
    return result_line, detection_lines, values["malicious"] > 0 or values["suspicious"] > 0


def _write_report(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload public release samples to VirusTotal with per-engine findings.")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--target", action="append", default=[], help="DisplayName=path, repeat for each sample")
    args = parser.parse_args()
    api_key = os.environ.get("VIRUSTOTAL_API_KEY", "").strip()
    lines = [
        "VirusTotal public analysis report",
        f"UTC started: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "Disclosure: all submitted files are added to VirusTotal's shared public dataset; submit only public project builds, source, and upstream public runtime tools.",
        "Required samples: app executable; emergency uninstaller; versioned source ZIP; exact yt-dlp.exe; exact ffmpeg.exe; exact ffprobe.exe.",
        "",
    ]
    if args.metadata and args.metadata.is_file():
        lines.extend([
            "--- Security inventory ---",
            args.metadata.read_text(encoding="utf-8", errors="replace").strip(),
            "--- End inventory ---",
            "",
        ])
    if not api_key:
        lines.extend(["NOT SCANNED: VIRUSTOTAL_API_KEY is not configured.", "OVERALL: SCAN ERROR"])
        _write_report(args.report, lines)
        return 2

    targets = []
    for item in args.target:
        if "=" not in item:
            lines.append(f"SCAN ERROR: invalid target argument: {item!r}")
            continue
        name, raw_path = item.split("=", 1)
        path = Path(raw_path)
        if not path.is_file():
            lines.append(f"SCAN ERROR: missing required sample {name}: {path}")
            continue
        targets.append((name, path))
    if len(targets) != 6 or len({name for name, _ in targets}) != 6:
        lines.extend([f"SCAN ERROR: expected six unique targets; received {len(targets)}.", "OVERALL: SCAN ERROR"])
        _write_report(args.report, lines)
        return 2

    pending = []
    errors = []
    findings = False
    for name, path in targets:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        sample_hash = digest.hexdigest().lower()
        lines.append(f"SAMPLE: {name}; SHA256={sample_hash}; bytes={path.stat().st_size}")
        _write_report(args.report, lines)
        try:
            analysis_id = submit_file(path, api_key)
            pending.append({"name": name, "hash": sample_hash, "analysis_id": analysis_id})
            lines.append(f"SUBMITTED: {name}; analysis_id={analysis_id}")
        except Exception as exc:
            errors.append(name)
            lines.append(f"SCAN ERROR: {name}; {exc}")
        _write_report(args.report, lines)
    if errors:
        lines.extend(["ANALYSIS COMPLETE: 0/6 targets", "OVERALL: SCAN ERROR"])
        _write_report(args.report, lines)
        return 2

    start = time.monotonic()
    completed = set()
    rounds = 0
    while len(completed) < len(pending) and rounds < MAX_POLL_ROUNDS and time.monotonic() - start < MAX_WAIT_SECONDS:
        rounds += 1
        for sample in pending:
            if sample["name"] in completed:
                continue
            try:
                analysis = _api_json(f"{API_ROOT}/analyses/{sample['analysis_id']}", api_key)
                attributes = (analysis.get("data") or {}).get("attributes") or {}
                if attributes.get("status") != "completed":
                    continue
                result_line, detection_lines, sample_findings = summarize_analysis(sample["name"], attributes)
                lines.append(result_line)
                lines.append(f"REPORT: {sample['name']}; https://www.virustotal.com/gui/file/{sample['hash']}/detection")
                lines.extend(detection_lines)
                findings = findings or sample_findings
                completed.add(sample["name"])
                _write_report(args.report, lines)
            except Exception as exc:
                lines.append(f"POLL WARNING: {sample['name']}; {exc}")
                _write_report(args.report, lines)
        if len(completed) < len(pending):
            lines.append(f"POLL: round {rounds}/{MAX_POLL_ROUNDS}; completed {len(completed)}/{len(pending)}.")
            _write_report(args.report, lines)
    if len(completed) != 6:
        lines.extend([
            f"ANALYSIS PENDING: {len(completed)}/6 targets completed after {rounds} poll rounds.",
            "OVERALL: ANALYSIS PENDING",
            "An incomplete scan is not a clean result and blocks publication.",
        ])
        _write_report(args.report, lines)
        return 2
    lines.append("ANALYSIS COMPLETE: 6/6 targets")
    if findings:
        lines.append("OVERALL: REVIEW REQUIRED (one or more engines returned malicious/suspicious; these are not confirmed false positives).")
    else:
        lines.append("OVERALL: no malicious or suspicious detections were returned at scan time; this does not guarantee safety.")
    _write_report(args.report, lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
