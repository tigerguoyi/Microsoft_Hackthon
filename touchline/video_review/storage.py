"""Private bounded storage and immutable revisions, following Jolin's evidence lab.

Media never enters the static document root. IDs are opaque, paths are server-owned.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

LOCK = threading.RLock()
MAX_BYTES = 64 * 1024 * 1024
ROOT = Path(os.getenv('NEXTPLAY_STATE_DIR', str(Path(__file__).resolve().parents[1] / '.local'))) / 'video-review'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()[:32]


def folder(video_id, root=None):
    if not isinstance(video_id, str) or not re.fullmatch('[a-f0-9]{32}', video_id):
        raise ValueError('Invalid private video ID')
    return Path(root or ROOT) / video_id


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as out:
        json.dump(value, out, ensure_ascii=False, allow_nan=False)
    os.chmod(out.name, 0o600)
    os.replace(out.name, path)


def read(path):
    return json.loads(path.read_text())


def asset(video_id, owner, root=None):
    result = read(folder(video_id, root) / 'asset.json')
    if result['owner'] != owner:
        raise FileNotFoundError('Private video not found')
    return result


def decoder(path):
    """Decode first/last frame independently of client declarations (optional OpenCV)."""
    try:
        import cv2
    except ImportError as exc:
        raise ValueError('Media decoder unavailable; install the optional video dependencies') from exc
    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS); frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        width = cap.get(cv2.CAP_PROP_FRAME_WIDTH); height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if not cap.isOpened() or not 1 <= fps <= 240 or not 1 <= frames or not 16 <= width <= 3840 or not 16 <= height <= 2160:
            raise ValueError('Invalid media stream, frame rate or resolution')
        duration = frames / fps
        if not .1 <= duration <= 120:
            raise ValueError('Only clips from 0.1 to 120 seconds are supported')
        ok, frame = cap.read()
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frames) - 1)); last_ok, last = cap.read()
        if not ok or frame is None or not last_ok or last is None:
            raise ValueError('Media failed first/last frame decode')
        return dict(duration_ms=round(duration * 1000), fps=fps, frame_count=int(frames), width=int(width), height=int(height), decoder_verified=True)
    finally:
        cap.release()


def upload(stream, size, media_type, owner, root=None, probe=decoder):
    root = Path(root or ROOT)
    if type(size) is not int or not 32 <= size <= MAX_BYTES or media_type not in ('video/mp4', 'video/webm'):
        raise ValueError('Use MP4/WebM under 64 MiB')
    with LOCK:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        total = sum(p.stat().st_size for p in root.glob('*/media'))
        if total + size > int(os.getenv('NEXTPLAY_VIDEO_STORAGE_MB', '512')) * 1024 * 1024:
            raise ValueError('Private storage quota reached; delete old videos')
        vid = uuid.uuid4().hex; target = folder(vid, root); target.mkdir(mode=0o700)
        try:
            sha = hashlib.sha256(); remaining = size
            with (target / 'media').open('xb') as out:
                while remaining:
                    block = stream.read(min(65536, remaining))
                    if not block:
                        raise ValueError('Incomplete media')
                    if remaining == size and (media_type == 'video/mp4' and block[4:8] != b'ftyp' or media_type == 'video/webm' and not block.startswith(b'\x1aE\xdf\xa3')):
                        raise ValueError('Container signature does not match declared format')
                    sha.update(block); out.write(block); remaining -= len(block)
            os.chmod(target / 'media', 0o600)
            # Decoder subprocess isolates malformed-media handling and bounds elapsed time.
            if probe is decoder:
                result = subprocess.run([os.sys.executable, '-m', 'video_review.probe', str(target / 'media')], capture_output=True, timeout=25, check=True)
                details = json.loads(result.stdout)
            else:
                details = probe(target / 'media')  # Test injection only.
            record = dict(video_id=vid, schema_version='video-asset-2', sha256=sha.hexdigest(), bytes=size,
                          media_type=media_type, owner=owner, created_at=time.time(), latest_revision_id=None, **details)
            write(target / 'asset.json', record)
            return {k: v for k, v in record.items() if k != 'owner'}
        except Exception:
            shutil.rmtree(target)
            raise


def revision(video_id, revision_id, owner, root=None, current=True):
    a = asset(video_id, owner, root)
    if not isinstance(revision_id, str) or not re.fullmatch('[a-f0-9]{32}', revision_id):
        raise ValueError('Invalid revision')
    if current and a['latest_revision_id'] != revision_id:
        raise ValueError('Stale revision; reselect and recompute after annotation edits')
    return read(folder(video_id, root) / ('revision-' + revision_id + '.json'))


def remove(video_id, owner, root=None):
    asset(video_id, owner, root)
    with LOCK:
        if any(read(p).get('status') in ('queued', 'running') and time.time()-read(p).get('created_at',0)<310 for p in folder(video_id, root).glob('job-*.json')):
            raise ValueError('Wait for detection to finish before deletion')
        shutil.rmtree(folder(video_id, root))


def expire(root=None, now=None):
    """Operator retention task; default seven days. Never touches shared match data."""
    root = Path(root or ROOT); now = time.time() if now is None else now
    for p in root.glob('*/asset.json'):
        a = read(p)
        if now - a['created_at'] > int(os.getenv('NEXTPLAY_VIDEO_RETENTION_DAYS', '7')) * 86400:
            try:
                remove(a['video_id'], a['owner'], root)
            except ValueError:
                pass
