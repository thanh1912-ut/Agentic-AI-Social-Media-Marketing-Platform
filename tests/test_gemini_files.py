"""Native HTTPX serialization with synthetic media only; zero provider calls."""
from dataclasses import replace
from hashlib import sha256
import base64
import json

import httpx
import pytest
from pydantic import BaseModel

from services.agents.providers.errors import ProviderConfigurationError, ProviderContextLimitError, ProviderOutputError, ProviderRequestError
from services.agents.providers.gemini import ApprovedMediaInput
from services.agents.providers.gemini_files import (
    GeminiFilesClient, GeminiFileMediaAnalyzer, ProviderFileCleanupRequired,
    ProviderUploadOutcomeUnknown, MAX_IMAGE_BYTES, MAX_VIDEO_BYTES, ROOT,
)


class Summary(BaseModel):
    description: str
    timestamps: list[str]


def media(content=b'synthetic-owned-media', mime='image/png'):
    return ApprovedMediaInput(asset_id='synthetic-asset', source_id='synthetic-source', evidence_id='synthetic-evidence',
        sha256_hex=sha256(content).hexdigest(), mime_type=mime, content=content, privacy_status='approved')


def reply_file(asset, state='ACTIVE'):
    return {'file': {'name': 'files/fixture-01', 'uri': ROOT + '/v1beta/files/fixture-01',
        'mimeType': asset.mime_type, 'sizeBytes': str(len(asset.content)),
        'state': state, 'sha256Hash': base64.b64encode(bytes.fromhex(asset.sha256_hex)).decode(),
        'expirationTime': '2099-01-01T00:00:00Z'}}


def setup(asset, *, upload_url=ROOT + '/upload/v1beta/files?upload_id=synthetic&upload_protocol=resumable', file_reply=None, fail_delete=False, fail_upload=False):
    requests = []
    def transport(request):
        requests.append(request)
        assert request.url.host == 'generativelanguage.googleapis.com'
        if request.method == 'DELETE':
            return httpx.Response(503 if fail_delete else 200, json={})
        if request.url.path.endswith(':generateContent'):
            return httpx.Response(200, json={'modelVersion': 'gemini-3.8-flash', 'candidates': [{'finishReason': 'STOP',
                'content': {'parts': [{'text': '{"description":"Sản phẩm tổng hợp","timestamps":["00:01"]}'}]}}],
                'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 10, 'thoughtsTokenCount': 2, 'totalTokenCount': 112}})
        if request.method == 'GET':
            return httpx.Response(200, json=reply_file(asset))
        if 'upload_id=' not in str(request.url):
            return httpx.Response(200, headers={'x-goog-upload-url': upload_url})
        if fail_upload:
            raise httpx.ReadTimeout('secret-containing-url-must-not-leak', request=request)
        return httpx.Response(200, json=file_reply or reply_file(asset))
    client = httpx.Client(transport=httpx.MockTransport(transport))
    return GeminiFilesClient(api_key='fixture-secret', client=client), client, requests


def test_upload_journals_before_metadata_then_analyzes_only_file_reference_and_deletes():
    asset = media()
    files, client, requests = setup(asset)
    journal = []
    file = files.upload(asset, on_uploaded=journal.append)
    assert [entry.state for entry in journal] == ['UNVERIFIED', 'ACTIVE']
    assert file.provider_hash_verified and file.size_bytes == len(asset.content)
    analyzer = GeminiFileMediaAnalyzer(api_key='fixture-secret', model='gemini-3.8-flash', client=client)
    result, usage = analyzer.analyze_uploaded_media(media=asset, file=file, duration_ms=None,
        system_prompt='Describe the business product.', input_payload={'coverage': 'one image'}, response_model=Summary)
    body = json.loads(requests[-1].content)
    assert body['contents'][0]['parts'][0]['fileData']['fileUri'] == file.uri
    assert 'inlineData' not in str(body) and 'fixture-secret' not in str(body)
    assert result.description == 'Sản phẩm tổng hợp' and usage.output_tokens == 12
    assert 'untrusted' in body['systemInstruction']['parts'][0]['text']
    files.delete(file)
    assert [r.method for r in requests] == ['POST', 'POST', 'POST', 'DELETE']
    assert requests[1].content == asset.content and 'identity' not in str(requests[0].content)
    assert 'files/fixture-01' not in repr(file)


def test_large_video_uses_binary_upload_and_requires_measured_duration():
    asset = media(b'x' * (MAX_IMAGE_BYTES + 1), 'video/mp4')
    files, _client, requests = setup(asset)
    with pytest.raises(ProviderContextLimitError, match='measured duration'):
        files.upload(asset, on_uploaded=lambda _file: None)
    assert requests == []
    file = files.upload(asset, on_uploaded=lambda _file: None, duration_ms=600_000)
    assert file.size_bytes == MAX_IMAGE_BYTES + 1 and MAX_VIDEO_BYTES == 100 * 1024 * 1024
    assert len(requests) == 2


@pytest.mark.parametrize('url', [
    'http://generativelanguage.googleapis.com/upload/v1beta/files?upload_id=x',
    'https://127.0.0.1/upload/v1beta/files?upload_id=x',
    'https://googleapis.com.evil.example/upload/v1beta/files?upload_id=x',
    ROOT + ':444/upload/v1beta/files?upload_id=x',
    ROOT + '/upload/v1beta/files/../other?upload_id=x',
    ROOT + '/upload/v1beta/files?upload_id=x&key=secret',
    ROOT + '/upload/v1beta/files?upload_id=x&upload_id=y',
    ROOT + '/upload/v1beta/files?upload_id=x#fragment',
])
def test_upload_destination_rejected_before_sending_bytes(url):
    asset = media()
    files, _client, requests = setup(asset, upload_url=url)
    with pytest.raises(ProviderOutputError, match='destination'):
        files.upload(asset, on_uploaded=lambda _file: None)
    assert len(requests) == 1 and asset.content not in requests[0].content


@pytest.mark.parametrize('field,value', [
    ('mimeType', 'text/html'), ('sizeBytes', '999'), ('sha256Hash', 'AAAA'),
    ('uri', 'http://127.0.0.1/private'), ('state', 'UNRECOGNIZED'),
])
def test_invalid_receipt_has_journaled_handle_and_is_deleted(field, value):
    asset = media()
    receipt = reply_file(asset)
    receipt['file'][field] = value
    files, _client, requests = setup(asset, file_reply=receipt)
    journal = []
    with pytest.raises(ProviderOutputError, match='metadata'):
        files.upload(asset, on_uploaded=journal.append)
    assert len(journal) == 1 and journal[0].state == 'UNVERIFIED'
    assert requests[-1].method == 'DELETE'


def test_journal_failure_cleans_up_and_delete_failure_exposes_only_opaque_handle():
    asset = media()
    files, _client, requests = setup(asset, fail_delete=True)
    with pytest.raises(ProviderFileCleanupRequired) as failure:
        files.upload(asset, on_uploaded=lambda _file: (_ for _ in ()).throw(RuntimeError('sensitive-db-detail')))
    assert failure.value.file.name == 'files/fixture-01'
    assert 'sensitive' not in str(failure.value) and 'fixture-secret' not in str(failure.value)
    assert len(requests) == 3 and failure.value.retryable is False


def test_timeout_does_not_upload_again_and_keeps_reconciliation_tag():
    asset = media()
    files, _client, requests = setup(asset, fail_upload=True)
    with pytest.raises(ProviderUploadOutcomeUnknown) as failure:
        files.upload(asset, on_uploaded=lambda _file: None)
    assert len(requests) == 2
    assert failure.value.upload_tag.startswith('agentic-') and asset.asset_id not in failure.value.upload_tag
    assert 'secret-containing-url' not in str(failure.value)


def test_recheck_ready_hash_privacy_and_provenance_before_generation():
    asset = media()
    files, client, requests = setup(asset, file_reply=reply_file(asset, 'PROCESSING'))
    pending = files.upload(asset, on_uploaded=lambda _file: None)
    analyzer = GeminiFileMediaAnalyzer(api_key='fixture-secret', model='gemini-3.8-flash', client=client)
    for candidate, record in [(asset, pending), (replace(asset, privacy_status='privacy_hold'), replace(pending, state='ACTIVE')),
        (asset, replace(pending, state='ACTIVE', source_id='other-source'))]:
        with pytest.raises(ProviderConfigurationError):
            analyzer.analyze_uploaded_media(media=candidate, file=record, duration_ms=None,
                system_prompt='Analyze.', input_payload={}, response_model=Summary)
    assert len(requests) == 2
    ready = files.get(pending)
    assert ready.state == 'ACTIVE' and ready.provider_hash_verified


def test_delete_404_is_idempotent_and_does_not_follow_redirect():
    asset = media()
    files, _client, _requests = setup(asset)
    file = files.upload(asset, on_uploaded=lambda _file: None)
    files.client = httpx.Client(transport=httpx.MockTransport(lambda _req: httpx.Response(404)))
    files.delete(file)
    calls = []
    def redirect(request):
        calls.append(request)
        return httpx.Response(302, headers={'location': 'http://127.0.0.1/internal'})
    files.client = httpx.Client(transport=httpx.MockTransport(redirect), follow_redirects=True)
    with pytest.raises(ProviderOutputError, match='redirected'):
        files.delete(file)
    assert len(calls) == 1


def test_reconcile_unknown_upload_only_journals_opaque_tag_matches_and_reports_partial():
    from services.agents.providers.gemini_files import ProviderMediaBinding
    asset = media()
    binding = ProviderMediaBinding(asset_id=asset.asset_id, source_id=asset.source_id, evidence_id=asset.evidence_id,
        sha256_hex=asset.sha256_hex, mime_type=asset.mime_type, size_bytes=len(asset.content))
    matching = reply_file(asset)['file']
    matching['displayName'] = binding.upload_tag
    requests, journal = [], []
    def transport(request):
        requests.append(request)
        assert request.method == 'GET' and request.url.path == '/v1beta/files' and request.content == b''
        if len(requests) == 1:
            return httpx.Response(200, json={'files': [{'displayName': 'unrelated-private-document'}], 'nextPageToken': 'page-2'})
        return httpx.Response(200, json={'files': [matching]})
    client = httpx.Client(transport=httpx.MockTransport(transport))
    files = GeminiFilesClient(api_key='fixture-secret', client=client)
    found, complete = files.find_uploaded(binding, on_found=journal.append, max_pages=1)
    assert not complete and found == () and journal == []
    requests.clear()
    found, complete = files.find_uploaded(binding, on_found=journal.append, max_pages=3)
    assert complete and len(found) == 1 and len(journal) == 1
    assert requests[1].url.params['page_token'] == 'page-2'
    assert 'unrelated-private-document' not in repr(found)
    assert asset.asset_id not in binding.upload_tag
    other_hash = replace(binding, sha256_hex='0' * 64)
    assert other_hash.upload_tag != binding.upload_tag


def test_reconciliation_does_not_assume_empty_page_is_completion_when_cursor_remains():
    from services.agents.providers.gemini_files import ProviderMediaBinding
    asset = media()
    binding = ProviderMediaBinding(asset_id=asset.asset_id, source_id=asset.source_id, evidence_id=asset.evidence_id,
        sha256_hex=asset.sha256_hex, mime_type=asset.mime_type, size_bytes=len(asset.content))
    def transport(_request):
        return httpx.Response(200, json={'files': [], 'nextPageToken': 'same-cursor'})
    files = GeminiFilesClient(api_key='fixture-secret', client=httpx.Client(transport=httpx.MockTransport(transport)))
    with pytest.raises(ProviderOutputError, match='invalid page'):
        files.find_uploaded(binding, on_found=lambda _file: None, max_pages=3)


@pytest.mark.parametrize('change', ['privacy', 'hash', 'image_limit', 'video_duration', 'no_journal'])
def test_preflight_errors_send_no_binary_or_metadata(change):
    asset = media()
    files, _client, requests = setup(asset)
    callback, duration = (lambda _file: None), None
    if change == 'privacy':
        asset = replace(asset, privacy_status='privacy_hold')
    elif change == 'hash':
        asset = replace(asset, sha256_hex='0' * 64)
    elif change == 'image_limit':
        asset = media(b'x' * (MAX_IMAGE_BYTES + 1))
    elif change == 'video_duration':
        asset, duration = media(mime='video/mp4'), 600_001
    else:
        callback = None
    with pytest.raises((ProviderConfigurationError, ProviderContextLimitError)):
        files.upload(asset, on_uploaded=callback, duration_ms=duration)
    assert requests == []


def test_file_hash_is_canonical_and_expired_file_cannot_be_analyzed():
    from datetime import datetime, timezone
    asset = replace(media(), sha256_hex=media().sha256_hex.upper())
    receipt = reply_file(asset)
    files, client, requests = setup(asset, file_reply=receipt)
    file = files.upload(asset, on_uploaded=lambda _file: None)
    assert file.sha256_hex == asset.sha256_hex.lower()
    analyzer = GeminiFileMediaAnalyzer(api_key='fixture-secret', model='gemini-3.8-flash', client=client)
    with pytest.raises(ProviderConfigurationError, match='not ready'):
        analyzer.analyze_uploaded_media(media=asset, file=replace(file, expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc)),
            duration_ms=None, system_prompt='Analyze.', input_payload={}, response_model=Summary)
    assert len(requests) == 2


def test_oversized_reply_and_missing_handle_become_uncertain_without_retry():
    asset = media()
    files, _client, requests = setup(asset, file_reply={'file': {'name': '../other'}})
    with pytest.raises(ProviderUploadOutcomeUnknown):
        files.upload(asset, on_uploaded=lambda _file: None)
    assert len(requests) == 2
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(200, content=b'x' * (64 * 1024 + 1))
    files.client = httpx.Client(transport=httpx.MockTransport(transport))
    with pytest.raises(ProviderOutputError, match='response limit'):
        files.upload(asset, on_uploaded=lambda _file: None)
    assert len(calls) == 1


def test_reconciliation_journal_failure_is_sanitized_and_cleans_only_matched_file():
    from services.agents.providers.gemini_files import ProviderMediaBinding
    asset = media()
    binding = ProviderMediaBinding(asset_id=asset.asset_id, source_id=asset.source_id, evidence_id=asset.evidence_id,
        sha256_hex=asset.sha256_hex, mime_type=asset.mime_type, size_bytes=len(asset.content))
    data = reply_file(asset)['file']
    data['displayName'] = binding.upload_tag
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={} if request.method == 'DELETE' else {'files': [data]})
    files = GeminiFilesClient(api_key='fixture-secret', client=httpx.Client(transport=httpx.MockTransport(transport)))
    def reject(_file):
        raise RuntimeError('private-db-details')
    with pytest.raises(ProviderRequestError, match='file was deleted') as error:
        files.find_uploaded(binding, on_found=reject)
    assert 'private-db-details' not in str(error.value)
    assert [request.method for request in calls] == ['GET', 'DELETE']
